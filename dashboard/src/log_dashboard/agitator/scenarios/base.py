"""Scenario base class + registry.

A `Scenario` is a self-contained async task that drives a bounded amount of
HTTP traffic at one or more target apps. Subclasses implement `run()` and
declare a `ScenarioSpec` describing what the UI card shows.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ClassVar

from ...config import Settings
from ..auth import AppSession
from ..runs import RunRegistry


@dataclass(frozen=True)
class ScenarioParam:
    """One numeric param the UI surfaces as a number input or slider."""

    name: str
    minimum: int
    maximum: int
    default: int


@dataclass(frozen=True)
class ScenarioSpec:
    """Metadata the UI uses to render a scenario card."""

    name: str
    display_name: str
    description: str
    target_app: str
    requires_chaos: bool = False
    params: tuple[ScenarioParam, ...] = field(default_factory=tuple)


SCENARIOS: dict[str, type[Scenario]] = {}


def register(cls: type[Scenario]) -> type[Scenario]:
    """Decorator: register a scenario subclass in the global registry."""
    SCENARIOS[cls.spec.name] = cls
    return cls


class Scenario(ABC):
    """Abstract base — subclasses must declare `spec` and implement `run`."""

    spec: ClassVar[ScenarioSpec]

    def __init__(
        self,
        *,
        settings: Settings,
        session: AppSession,
        registry: RunRegistry,
        run_id: str,
        params: dict[str, int],
    ) -> None:
        self.settings = settings
        self.session = session
        self.registry = registry
        self.run_id = run_id
        self.params = params

    @abstractmethod
    async def run(self) -> None:
        """Execute the scenario. Must update the registry on each request."""

    async def _fire(
        self,
        send: Callable[[], Awaitable[tuple[int, bool]]],
        semaphore: asyncio.Semaphore,
    ) -> None:
        """One bounded request. Updates counters; never raises into the caller.

        `send` is an async callable returning `(status_code, ok)`. `ok` is the
        scenario's own definition of "expected" — a 401 in `auth-spike` is
        expected and counts as `ok=True`.
        """
        async with semaphore:
            try:
                status_code, ok = await send()
                await self.registry.mark_sent(self.run_id, status_code, ok)
            except asyncio.CancelledError:
                raise
            except (
                Exception
            ) as exc:  # noqa: BLE001 — scenarios must keep running through transport errors
                await self.registry.mark_failure(self.run_id, str(exc))

    async def _run_paced(
        self,
        count: int,
        duration_s: int,
        send: Callable[[], Awaitable[tuple[int, bool]]],
    ) -> None:
        """Spawn `count` `_fire` tasks paced over `duration_s` with proper
        cancellation propagation.

        Why this helper exists: the naive pattern (spawn-loop + sleep +
        gather) leaks tasks when the parent `run()` is cancelled during
        the spawn loop. CancelledError exits the `for` loop, the spawned
        tasks become orphans and keep firing HTTP requests after the
        registry state has flipped to `cancelled`. The try/except below
        catches the cancel, explicitly cancels every spawned task, drains
        them, then re-raises — so the wrapper's `finalize("cancelled")`
        runs against a fully-quiesced run.
        """
        interval = duration_s / max(count, 1)
        semaphore = asyncio.Semaphore(
            min(self.settings.agitator_default_concurrency, max(count, 1))
        )
        tasks: list[asyncio.Task[None]] = []
        try:
            for _ in range(count):
                tasks.append(asyncio.create_task(self._fire(send, semaphore)))
                await asyncio.sleep(interval)
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            raise
