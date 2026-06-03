import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from ..auth.password import hash_password
from ..config import Settings
from ..db import mongo, postgres
from ..db.models import Claim, ClaimStatusHistory
from ..logging_setup import get_logger

log = get_logger(__name__)

_DEFAULT_CUSTOMER_USERNAMES = [
    "alice",
    "bob",
    "carol",
    "dave",
    "eve",
    "frank",
    "grace",
    "henry",
    "ivy",
    "jack",
]
_DEFAULT_AGENT_USERNAMES = ["agent1", "agent2", "agent3", "agent4", "agent5"]

_COVERAGES = ["auto-comprehensive", "auto-liability", "auto-collision"]
_MAKES_MODELS = [
    ("Honda", "Civic"),
    ("Toyota", "Camry"),
    ("Ford", "F-150"),
    ("Tesla", "Model 3"),
    ("Subaru", "Outback"),
    ("Chevrolet", "Equinox"),
]
_STATUS_DISTRIBUTION = [
    "submitted",
    "submitted",
    "triaged",
    "triaged",
    "investigating",
    "investigating",
    "settled",
    "closed",
    "denied",
    "denied",
]


def _parse_csv(raw: str, fallback: list[str]) -> list[str]:
    items = [s.strip() for s in raw.split(",") if s.strip()]
    return items or fallback


def _random_vin(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(rng.choice(alphabet) for _ in range(17))


async def _seed_users_and_policies(settings: Settings, rng: random.Random) -> bool:
    db = mongo.get_db()
    if await db.users.count_documents({}) > 0:
        return False

    customer_names = _parse_csv(settings.demo_customer_usernames, _DEFAULT_CUSTOMER_USERNAMES)
    agent_names = _parse_csv(settings.demo_agent_usernames, _DEFAULT_AGENT_USERNAMES)

    # Ensure exactly 10 customers and 5 agents.
    while len(customer_names) < 10:
        customer_names.append(f"customer{len(customer_names) + 1}")
    customer_names = customer_names[:10]
    while len(agent_names) < 5:
        agent_names.append(f"agent{len(agent_names) + 1}")
    agent_names = agent_names[:5]

    customer_pw = hash_password("customer")
    agent_pw = hash_password("agent")

    customers = [
        {
            "username": name,
            "password_hash": customer_pw,
            "role": "customer",
            "display_name": name.capitalize(),
            "created_at": datetime.now(tz=UTC),
        }
        for name in customer_names
    ]
    agents = [
        {
            "username": name,
            "password_hash": agent_pw,
            "role": "agent",
            "display_name": name.capitalize(),
            "created_at": datetime.now(tz=UTC),
        }
        for name in agent_names
    ]
    result_c = await db.users.insert_many(customers)
    await db.users.insert_many(agents)
    customer_ids = [str(_id) for _id in result_c.inserted_ids]

    today = date.today()
    policies = []
    for i in range(15):
        owner = rng.choice(customer_ids)
        n_vehicles = rng.randint(1, 2)
        vehicles = []
        for _ in range(n_vehicles):
            make, model = rng.choice(_MAKES_MODELS)
            vehicles.append(
                {
                    "vin": _random_vin(rng),
                    "make": make,
                    "model": model,
                    "year": rng.randint(2015, 2024),
                }
            )
        policies.append(
            {
                "policy_number": f"POL-{1000 + i}",
                "customer_id": owner,
                "effective_date": datetime.combine(
                    today - timedelta(days=rng.randint(30, 365)), datetime.min.time()
                ),
                "expiration_date": datetime.combine(
                    today + timedelta(days=rng.randint(30, 365)), datetime.min.time()
                ),
                "coverage_type": rng.choice(_COVERAGES),
                "premium_cents": rng.randint(60_000, 200_000),
                "vehicles": vehicles,
            }
        )
    await db.policies.insert_many(policies)

    log.info(
        "mongo_seed_complete",
        customers=len(customers),
        agents=len(agents),
        policies=len(policies),
    )
    return True


async def _seed_claims(rng: random.Random) -> bool:
    db = mongo.get_db()
    policies = await db.policies.find({}).to_list(length=100)
    agents = await db.users.find({"role": "agent"}, {"_id": 1}).to_list(length=20)
    if not policies or not agents:
        log.warning("claims_seed_skipped", reason="missing_policies_or_agents")
        return False
    agent_ids = [str(a["_id"]) for a in agents]

    now = datetime.now(tz=UTC)
    async with postgres.session() as s:
        existing = await s.scalar(select(func.count()).select_from(Claim))
        if existing and existing > 0:
            return False
        for i in range(10):
            policy = rng.choice(policies)
            vehicle = rng.choice(policy["vehicles"])
            target_status = _STATUS_DISTRIBUTION[i % len(_STATUS_DISTRIBUTION)]
            adjuster_id = rng.choice(agent_ids) if target_status != "submitted" else None
            created_at = now - timedelta(days=rng.randint(0, 30))
            claim = Claim(
                policy_number=policy["policy_number"],
                customer_id=policy["customer_id"],
                vin=vehicle["vin"],
                vehicle_snapshot={
                    "make": vehicle["make"],
                    "model": vehicle["model"],
                    "year": vehicle["year"],
                },
                incident_at=created_at - timedelta(hours=rng.randint(1, 48)),
                description=f"Seeded incident #{i + 1}",
                current_status=target_status,
                assigned_adjuster_id=adjuster_id,
                created_at=created_at,
            )
            s.add(claim)
            await s.flush()

            # Valid transitions per ADR-007:
            #   submitted → triaged → investigating → settled → closed
            #                      ↘ denied            ↘ denied
            chain: list[str] = ["submitted"]
            if target_status in {"triaged", "investigating", "settled", "closed"}:
                chain.append("triaged")
            if target_status in {"investigating", "settled", "closed"}:
                chain.append("investigating")
            if target_status in {"settled", "closed"}:
                chain.append("settled")
            if target_status == "closed":
                chain.append("closed")
            if target_status == "denied":
                # Always pass through triaged; randomly include investigating.
                chain.append("triaged")
                if rng.random() < 0.5:
                    chain.append("investigating")
                chain.append("denied")

            prev: str | None = None
            for idx, status_value in enumerate(chain):
                changed_at = created_at + timedelta(hours=idx * 6)
                # Initial submission is the customer; later transitions are the
                # assigned adjuster (or the customer if seed somehow lacks one).
                if idx == 0:
                    actor = claim.customer_id
                else:
                    actor = adjuster_id or claim.customer_id
                s.add(
                    ClaimStatusHistory(
                        claim_id=claim.id,
                        from_status=prev,
                        to_status=status_value,
                        actor_id=actor,
                        changed_at=changed_at,
                        note="seed" if idx == 0 else None,
                    )
                )
                prev = status_value
        await s.commit()

    log.info("postgres_seed_complete", claims=10)
    return True


async def run_seed_if_empty(settings: Settings) -> None:
    rng = random.Random(42)
    seeded_mongo = await _seed_users_and_policies(settings, rng)
    seeded_pg = await _seed_claims(rng)
    log.info("seed_run_complete", mongo=seeded_mongo, postgres=seeded_pg)
