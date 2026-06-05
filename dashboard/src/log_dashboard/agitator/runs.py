"""In-memory registry of Agitator runs.

A run lives for the lifetime of one operator click — `running` until the
scenario's worker task completes (or is cancelled), then a terminal state
(`succeeded` / `failed` / `cancelled`). The registry is a bounded ring
buffer of the most recent 50 records; `running` entries are never evicted.

State lives only in-process. A dashboard restart loses run history — that's
fine; the corpus the runs produced is durable in Chroma + the apps' log
volumes, which is what matters.

Concurrency model: every mutation that touches `_records` or `_by_id` runs
inside `_lock`. `try_start` is the only path that adds a record — it does
cap check + same-scenario check + eviction + add + task creation + task
assignment atomically, so the cap is enforced under contention and cancel
can never observe a `task=None` record.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

RunState = Literal["running", "succeeded", "failed", "cancelled"]

_MAX_RECENT = 50
_MAX_LAST_ERROR_LEN = 200

# Three base64url-ish segments separated by dots. Matches both real JWTs and
# obvious fakes. We're defensive — if the shape is there, redact regardless.
_JWT_SHAPE = re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
_SENSITIVE_NEEDLES = ("authorization", "bearer", "x-api-key", "password")


class ConcurrentRunCapError(RuntimeError):
    """Too many runs already `running`. Router maps to 429."""

    def __init__(self, cap: int) -> None:
        super().__init__(f"concurrent-run cap reached ({cap})")
        self.cap = cap


class ScenarioAlreadyRunningError(RuntimeError):
    """The requested scenario already has a `running` run. Router maps to 409."""

    def __init__(self, scenario: str) -> None:
        super().__init__(f"{scenario} is already running")
        self.scenario = scenario


class RegistryFullError(RuntimeError):
    """Defensive: the registry is at capacity AND every record is `running`.

    The router's cap check should make this unreachable in practice
    (`AGITATOR_MAX_CONCURRENT_RUNS=2` << `_MAX_RECENT=50`), but raising
    explicitly here is safer than silently losing a record via
    `deque.maxlen` while leaving the stale `_by_id` entry behind.
    """


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

    Two checks compose:
    1. Keyword: any of `Authorization` / `Bearer` / `X-API-Key` / `password`
       in the message text → drop the message entirely.
    2. Shape: a three-segment JWT-shaped token (≥20 chars per segment,
       base64url alphabet) → drop entirely. Catches the case where a
       token value is present without a nearby keyword.
    """
    lower = message.lower()
    for needle in _SENSITIVE_NEEDLES:
        if needle in lower:
            return "redacted (contained sensitive header/field name)"
    if _JWT_SHAPE.search(message):
        return "redacted (contained JWT-shaped token)"
    if len(message) > _MAX_LAST_ERROR_LEN:
        return message[:_MAX_LAST_ERROR_LEN] + "…"
    return message


class RunRegistry:
    """Async-safe bounded ring buffer of Agitator runs.

    The registry is owned by the FastAPI app state and lives for the
    lifetime of the process. `try_start` is the only public mutator that
    inserts; counter / state updates run under `self._lock` as well.
    """

    def __init__(self, max_recent: int = _MAX_RECENT) -> None:
        self._lock = asyncio.Lock()
        self._records: deque[RunRecord] = deque(maxlen=max_recent)
        self._by_id: dict[str, RunRecord] = {}

    async def try_start(
        self,
        record: RunRecord,
        *,
        max_concurrent: int,
        task_factory: Callable[[], asyncio.Task[None]],
    ) -> None:
        """Atomically: cap check + same-scenario check + eviction + add +
        task creation + task assignment. All under `_lock` so two concurrent
        callers cannot both pass the cap check, and cancel cannot observe
        the record before `task` is set.

        Raises:
            ConcurrentRunCapError — too many runs already `running`.
            ScenarioAlreadyRunningError — same scenario already has a
                `running` run.
            RegistryFullError — buffer is at capacity AND every record is
                `running` (defensive; should be unreachable when
                `max_concurrent` < `max_recent`).
        """
        async with self._lock:
            running_records = [r for r in self._records if r.state == "running"]
            if len(running_records) >= max_concurrent:
                raise ConcurrentRunCapError(max_concurrent)
            if any(r.scenario_name == record.scenario_name for r in running_records):
                raise ScenarioAlreadyRunningError(record.scenario_name)

            # Explicit eviction — never rely on `deque.maxlen` for
            # correctness, since maxlen-driven eviction would leave a stale
            # `_by_id` entry behind.
            maxlen = self._records.maxlen
            if maxlen is not None and len(self._records) >= maxlen:
                evicted_idx: int | None = None
                for i, existing in enumerate(self._records):
                    if existing.state != "running":
                        evicted_idx = i
                        break
                if evicted_idx is None:
                    raise RegistryFullError()
                evicted = self._records[evicted_idx]
                del self._records[evicted_idx]
                self._by_id.pop(evicted.run_id, None)

            self._records.append(record)
            self._by_id[record.run_id] = record
            # Task creation under the lock — synchronous schedule, no await.
            # Guarantees cancel cannot observe `task=None`.
            record.task = task_factory()

    async def get(self, run_id: str) -> RunRecord | None:
        async with self._lock:
            return self._by_id.get(run_id)

    async def list_recent(self) -> list[RunRecord]:
        async with self._lock:
            return list(self._records)

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
        # Release the lock before calling cancel — task.cancel is a sync
        # method but the cancelled coroutine may try to take the same lock
        # via finalize/mark_failure.
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
