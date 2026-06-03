import pytest
from pymongo.errors import DuplicateKeyError

from shared_data_api.db import mongo


@pytest.mark.asyncio
async def test_ensure_indexes_creates_unique_username_index(mongo_db):
    await mongo.ensure_indexes()
    indexes = await mongo_db.users.index_information()
    assert "users_username_unique" in indexes
    assert indexes["users_username_unique"].get("unique") is True


@pytest.mark.asyncio
async def test_ensure_indexes_creates_unique_policy_number_index(mongo_db):
    await mongo.ensure_indexes()
    indexes = await mongo_db.policies.index_information()
    assert "policies_policy_number_unique" in indexes
    assert indexes["policies_policy_number_unique"].get("unique") is True


@pytest.mark.asyncio
async def test_duplicate_username_rejected(mongo_db):
    await mongo.ensure_indexes()
    await mongo_db.users.insert_one({"username": "alice", "role": "customer"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.users.insert_one({"username": "alice", "role": "customer"})


@pytest.mark.asyncio
async def test_duplicate_policy_number_rejected(mongo_db):
    await mongo.ensure_indexes()
    await mongo_db.policies.insert_one({"policy_number": "POL-1", "customer_id": "x"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.policies.insert_one({"policy_number": "POL-1", "customer_id": "y"})
