import asyncio

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from ..logging_setup import get_logger

log = get_logger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_client(
    uri: str, database: str, *, retries: int = 10, backoff_seconds: float = 3.0
) -> None:
    global _client, _db

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
            await client.admin.command("ping")
            _client = client
            _db = client[database]
            log.info("mongo_connected", attempt=attempt, database=database)
            return
        except Exception as exc:
            last_error = exc
            log.warning("mongo_connect_failed", attempt=attempt, error=str(exc))
            if attempt < retries:
                await asyncio.sleep(backoff_seconds)

    assert last_error is not None
    raise last_error


async def ensure_indexes() -> None:
    """Enforce schema invariants from docs/tech/data-model.md."""
    db = get_db()
    await db.users.create_index("username", unique=True, name="users_username_unique")
    await db.policies.create_index(
        "policy_number", unique=True, name="policies_policy_number_unique"
    )
    await db.policies.create_index("customer_id", name="policies_customer_id")
    log.info("mongo_indexes_ensured")


def set_db(database: AsyncIOMotorDatabase) -> None:
    """Override the global DB handle (used by tests with an in-memory mock)."""
    global _db
    _db = database


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Mongo database not initialized")
    return _db


def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def to_object_id(raw: str) -> ObjectId | str:
    """Convert a string id back to an ObjectId for Mongo lookups; pass through on failure."""
    try:
        return ObjectId(raw)
    except Exception:
        return raw
