"""SessionIndex — LRU bookkeeping + eviction calls checkpointer.adelete_thread."""

from __future__ import annotations

import pytest

from log_dashboard.agent.sessions import SessionIndex, new_session_id, thread_id_for


class _FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


@pytest.mark.asyncio
async def test_touch_records_thread() -> None:
    cp = _FakeCheckpointer()
    idx = SessionIndex(checkpointer=cp, max_entries=10)
    await idx.touch("admin:abc")
    assert await idx.size() == 1
    assert await idx.contains("admin:abc")


@pytest.mark.asyncio
async def test_touch_moves_existing_to_mru() -> None:
    """Re-touching an existing thread keeps it; cap stays the same."""
    cp = _FakeCheckpointer()
    idx = SessionIndex(checkpointer=cp, max_entries=2)
    await idx.touch("admin:a")
    await idx.touch("admin:b")
    # `a` was LRU; touching it again pushes `b` to LRU position.
    await idx.touch("admin:a")
    await idx.touch("admin:c")
    # Eviction should have removed `b`, not `a`.
    assert cp.deleted == ["admin:b"]
    assert not await idx.contains("admin:b")
    assert await idx.contains("admin:a")
    assert await idx.contains("admin:c")


@pytest.mark.asyncio
async def test_eviction_calls_adelete_thread_on_lru_entry() -> None:
    cp = _FakeCheckpointer()
    idx = SessionIndex(checkpointer=cp, max_entries=2)
    await idx.touch("admin:1")
    await idx.touch("admin:2")
    await idx.touch("admin:3")
    assert cp.deleted == ["admin:1"]
    assert await idx.size() == 2


@pytest.mark.asyncio
async def test_aclose_evicts_all_tracked_threads() -> None:
    cp = _FakeCheckpointer()
    idx = SessionIndex(checkpointer=cp, max_entries=10)
    for i in range(3):
        await idx.touch(f"admin:s{i}")
    await idx.aclose()
    assert set(cp.deleted) == {"admin:s0", "admin:s1", "admin:s2"}
    assert await idx.size() == 0


@pytest.mark.asyncio
async def test_eviction_failure_does_not_crash() -> None:
    """`adelete_thread` raising must not propagate — better to leak a
    session than to fail a chat request mid-flight."""

    class _BrokenCheckpointer:
        async def adelete_thread(self, thread_id: str) -> None:
            raise RuntimeError("eviction failure")

    idx = SessionIndex(checkpointer=_BrokenCheckpointer(), max_entries=1)
    await idx.touch("admin:a")
    # This should NOT raise — the eviction failure is logged and swallowed.
    await idx.touch("admin:b")
    assert await idx.contains("admin:b")


def test_new_session_id_returns_uuid_shape() -> None:
    sid = new_session_id()
    # UUID4 hex has 4 dashes.
    assert sid.count("-") == 4
    assert len(sid) == 36


def test_thread_id_for_composes_scoped_key() -> None:
    assert thread_id_for("admin", "sess-1") == "admin:sess-1"
    assert thread_id_for("admin", "another-id") == "admin:another-id"
