import asyncio
import random
from datetime import UTC, datetime

from sqlalchemy import select

from ..config import Settings
from ..db import mongo, postgres
from ..db.models import CLAIM_STATUS_VALUES, SYSTEM_ACTOR_ID, Claim, ClaimStatusHistory
from ..logging_setup import get_logger

log = get_logger("simulator")

TRANSITIONS: dict[str, list[tuple[str, float]]] = {
    "submitted": [("triaged", 0.9)],
    "triaged": [("investigating", 0.7), ("denied", 0.1)],
    "investigating": [("settled", 0.6), ("denied", 0.1)],
    "settled": [("closed", 0.8)],
}
TERMINAL: frozenset[str] = frozenset({"closed", "denied"})


def _validate_status_coverage() -> None:
    """Fail-fast at import if the simulator's state machine drifts from the DB enum.

    Without this, adding a status to ``models.CLAIM_STATUS_VALUES`` without
    updating the simulator (or vice versa) would silently break runtime
    transitions or pass invalid statuses through the CHECK constraint.
    """
    declared = set(CLAIM_STATUS_VALUES)
    covered = set(TRANSITIONS.keys()) | TERMINAL
    missing = declared - covered
    extra = covered - declared
    if missing:
        raise RuntimeError(f"simulator missing handling for declared statuses: {sorted(missing)}")
    if extra:
        raise RuntimeError(
            f"simulator references statuses not in CLAIM_STATUS_VALUES: {sorted(extra)}"
        )
    for source, choices in TRANSITIONS.items():
        for target, _weight in choices:
            if target not in declared:
                raise RuntimeError(f"transition {source!r} → {target!r} references unknown status")


_validate_status_coverage()

__all__ = [
    "ALARM_THRESHOLD",
    "ClaimStatusSimulator",
    "SYSTEM_ACTOR_ID",
    "TERMINAL",
    "TRANSITIONS",
    "pick_next_status",
]


def pick_next_status(current: str, rng: random.Random) -> str | None:
    """Choose the next status for a claim, or None to stay.

    Weights are independent and proportional: each `(target, weight)` gets exactly
    that share of the probability space. The remainder is the "stay" probability.
    Sampling order does not affect outcome probability (unlike sequential
    independent rolls, where earlier options bias later ones toward never firing).
    """
    choices = TRANSITIONS.get(current, [])
    if not choices:
        return None
    r = rng.random()
    cumulative = 0.0
    for target, weight in choices:
        cumulative += weight
        if r < cumulative:
            return target
    return None


# When this many consecutive ticks fail, escalate to a louder log line so the
# dashboard's anomaly correlation has something high-signal to surface.
ALARM_THRESHOLD = 5


class ClaimStatusSimulator:
    def __init__(self, settings: Settings, rng: random.Random | None = None) -> None:
        self._settings = settings
        self._rng = rng or random.Random()
        self._stop = asyncio.Event()
        self._consecutive_failures = 0
        self._alarm_active = False

    def start(self) -> asyncio.Task:
        return asyncio.create_task(self._run(), name="claim-status-simulator")

    async def stop(self, task: asyncio.Task) -> None:
        self._stop.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
                self._on_tick_success()
            except Exception:
                self._on_tick_failure()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._settings.simulator_tick_seconds
                )
            except TimeoutError:
                pass

    def _on_tick_success(self) -> None:
        if self._alarm_active:
            log.info(
                "simulator_recovered",
                after_failures=self._consecutive_failures,
            )
        self._consecutive_failures = 0
        self._alarm_active = False

    def _on_tick_failure(self) -> None:
        log.exception("simulator_tick_failed", consecutive=self._consecutive_failures + 1)
        self._consecutive_failures += 1
        if self._consecutive_failures >= ALARM_THRESHOLD and not self._alarm_active:
            log.error(
                "simulator_persistent_failure",
                consecutive=self._consecutive_failures,
                message=(
                    "simulator has failed multiple consecutive ticks — claim status"
                    " advancement has stalled"
                ),
            )
            self._alarm_active = True

    async def tick(self) -> str | None:
        async with postgres.session() as s:
            stmt = select(Claim).where(Claim.current_status.notin_(TERMINAL))
            claims = (await s.execute(stmt)).scalars().all()
            if not claims:
                return None
            claim = self._rng.choice(claims)
            new_status = pick_next_status(claim.current_status, self._rng)
            if new_status is None:
                return None

            actor = claim.assigned_adjuster_id
            if claim.current_status == "submitted":
                actor = await self._pick_random_agent_id()
                claim.assigned_adjuster_id = actor

            history = ClaimStatusHistory(
                claim_id=claim.id,
                from_status=claim.current_status,
                to_status=new_status,
                actor_id=actor or SYSTEM_ACTOR_ID,
                changed_at=datetime.now(tz=UTC),
            )
            s.add(history)
            log.info(
                "status_transition",
                caller="simulator",
                user=actor or "-",
                claim_id=str(claim.id),
                from_status=claim.current_status,
                to_status=new_status,
            )
            claim.current_status = new_status
            await s.commit()
            return new_status

    async def _pick_random_agent_id(self) -> str | None:
        db = mongo.get_db()
        agents = await db.users.find({"role": "agent"}, {"_id": 1}).to_list(length=100)
        if not agents:
            return None
        return str(self._rng.choice(agents)["_id"])
