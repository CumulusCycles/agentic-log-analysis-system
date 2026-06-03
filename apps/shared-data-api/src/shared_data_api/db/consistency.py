"""Cross-DB consistency checks.

Postgres `claims` rows reference Mongo user `_id` strings via `customer_id` and
`assigned_adjuster_id`. Because Mongo and Postgres live in independent Docker
volumes, wiping one without the other produces dangling references that look
fine from each side but break the dashboard's correlation joins.

We surface this asymmetry as a startup WARNING — not a hard failure — so the
container still comes up and the dashboard sees a real signal to flag.
"""

from bson import ObjectId
from sqlalchemy import select

from ..logging_setup import get_logger
from . import mongo, postgres
from .models import SYSTEM_ACTOR_ID, Claim, ClaimStatusHistory

log = get_logger(__name__)


def _to_object_id_safe(raw: str | None) -> ObjectId | None:
    if raw is None:
        return None
    try:
        return ObjectId(raw)
    except Exception:
        return None


async def warn_on_volume_asymmetry() -> dict[str, int]:
    """Count Postgres references to Mongo users that no longer exist.

    Returns a small summary so callers (and tests) can assert behavior.
    """
    async with postgres.session() as s:
        customer_ids = (await s.execute(select(Claim.customer_id).distinct())).scalars().all()
        adjuster_ids = (
            (
                await s.execute(
                    select(Claim.assigned_adjuster_id)
                    .where(Claim.assigned_adjuster_id.is_not(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        actor_ids = (
            (await s.execute(select(ClaimStatusHistory.actor_id).distinct())).scalars().all()
        )

    db = mongo.get_db()
    all_referenced = set(customer_ids) | set(adjuster_ids) | set(actor_ids)
    candidate_oids = [_to_object_id_safe(r) for r in all_referenced]
    valid_oids = [oid for oid in candidate_oids if oid is not None]

    known_ids: set[str] = set()
    if valid_oids:
        cursor = db.users.find({"_id": {"$in": valid_oids}}, {"_id": 1})
        known_ids = {str(d["_id"]) async for d in cursor}

    missing_customers = [c for c in customer_ids if c not in known_ids]
    missing_adjusters = [a for a in adjuster_ids if a not in known_ids]
    missing_actors = [a for a in actor_ids if a not in known_ids and a != SYSTEM_ACTOR_ID]

    summary = {
        "missing_customer_refs": len(missing_customers),
        "missing_adjuster_refs": len(missing_adjusters),
        "missing_actor_refs": len(missing_actors),
    }
    if any(summary.values()):
        log.warning(
            "volume_asymmetry_detected",
            message=(
                "Postgres claims reference Mongo users that no longer exist — "
                "one volume was likely wiped without the other"
            ),
            **summary,
        )
    else:
        log.info("volume_asymmetry_check_clean")
    return summary
