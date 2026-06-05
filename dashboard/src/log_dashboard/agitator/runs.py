"""In-memory registry of Agitator runs.

A run lives for the lifetime of one operator click — `running` until the
scenario's worker task completes (or is cancelled), then a terminal state
(`succeeded` / `failed` / `cancelled`). The registry is a bounded ring
buffer of the most recent 50 records; `running` entries are never evicted.

State lives only in-process. A dashboard restart loses run history — that's
fine; the corpus the runs produced is durable in Chroma + the apps' log
volumes, which is what matters.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

RunState = Literal["running", "succeeded", "failed", "cancelled"]

_MAX_RECENT = 50
_MAX_LAST_ERROR_LEN = 200


@dataclass
class RunRecord:
    """One Agitator run. Counters update under the registry's lock.

    `task` is the asyncio task running the scenario; it is excluded from
    serialization (the response schema strips it).
    """

    run_id: str
    scenario_name: str
    params: dict[str, int]
    started_at: datetime
    state: RunState = "running"
    ended_at: datetime | None = None
    sent: int = 0
    succeeded: int = 0
    failed: int = 0
    last_status_code: int | None = None
    last_error: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


def _sanitize_error(message: str) -> str:
    """Strip credential-shaped tokens and bound the length.

    Defence-in-depth: scenario error paths never include credentials in
    raised exceptions today, but the gate stays here so future code can't
    accidentally leak via `last_error`.
    """
    redacted = message
    for needle in ("Authorization", "Bearer", "X-API-Key", "password"):
        if needle.lower() in redacted.lower():
            redacted = "redacted (contained sensitive header/field name)"
            break
    if len(redacted) > _MAX_LAST_ERROR_LEN:
        redacted = redacted[:_MAX_LAST_ERROR_LEN] + "…"
    return redacted


class RunRegistry:
    """Async-safe bounded ring buffer of Agitator runs.

    The registry is owned by the FastAPI app state and lives for the
    lifetime of the process. All public methods hold `self._lock` while
    mutating; readers should call `get()` / `list_recent()` which copy.
    """

    def __init__(self, max_recent: int = _MAX_RECENT) -> None:
        self._lock = asyncio.Lock()
        self._records: deque[RunRecord] = deque(maxlen=max_recent)
        self._by_id: dict[str, RunRecord] = {}

    async def add(self, record: RunRecord) -> None:
        async with self._lock:
            # Evict the oldest non-running record if we're at cap. deque's
            # maxlen would evict blindly, so we manually drop the right thing.
            if len(self._records) >= self._records.maxlen:  # type: ignore[operator]
                for i, existing in enumerate(self._records):
                    if existing.state != "running":
                        evicted = self._records[i]
                        del self._records[i]
                        self._by_id.pop(evicted.run_id, None)
                        break
            self._records.append(record)
            self._by_id[record.run_id] = record

    async def get(self, run_id: str) -> RunRecord | None:
        async with self._lock:
            return self._by_id.get(run_id)

    async def list_recent(self) -> list[RunRecord]:
        async with self._lock:
            return list(self._records)

    async def running_count(self) -> int:
        async with self._lock:
            return sum(1 for r in self._records if r.state == "running")

    async def running_scenarios(self) -> set[str]:
        async with self._lock:
            return {r.scenario_name for r in self._records if r.state == "running"}

    async def mark_sent(self, run_id: str, status_code: int, ok: bool) -> None:
        async with self._lock:
            record = self._by_id.get(run_id)
            if record is None or record.state != "running":
                return
            record.sent += 1
            record.last_status_code = status_code
            if ok:
                record.succeeded += 1
            else:
                record.failed += 1

    async def mark_failure(self, run_id: str, error: str) -> None:
        async with self._lock:
            record = self._by_id.get(run_id)
            if record is None or record.state != "running":
                return
            record.failed += 1
            record.last_error = _sanitize_error(error)

    async def finalize(self, run_id: str, state: RunState, error: str | None = None) -> None:
        async with self._lock:
            record = self._by_id.get(run_id)
            if record is None or record.state != "running":
                return
            record.state = state
            record.ended_at = datetime.now(tz=UTC)
            if error is not None:
                record.last_error = _sanitize_error(error)

    async def cancel(self, run_id: str) -> RunRecord | None:
        async with self._lock:
            record = self._by_id.get(run_id)
            if record is None:
                return None
            if record.state != "running":
                return record
            task = record.task
        if task is not None and not task.done():
            task.cancel()
        return record

    async def cancel_all(self) -> None:
        """Cancel every currently-running task. Called on dashboard shutdown."""
        async with self._lock:
            tasks = [r.task for r in self._records if r.state == "running" and r.task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
