"""SessionIndex — bounded LRU of `thread_id`s for the in-process MemorySaver.

LangGraph's `InMemorySaver` keeps every thread's checkpoint history in a
process dict; left alone, an admin who chats once per day for a year would
accumulate thousands of `thread_id` checkpoints. The SessionIndex bounds
the working set: when a new `thread_id` lands and the index is at capacity,
the oldest non-active `thread_id` is evicted via
`checkpointer.adelete_thread`.

`SessionIndex` is owned by `app.state.session_index`, constructed in
lifespan, and ends at shutdown via `aclose`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING

from ..logging_setup import get_logger

if TYPE_CHECKING:
    from langgraph.checkpoint.memory import InMemorySaver

log = get_logger("agent.sessions")


def new_session_id() -> str:
    """Return a fresh UUID4 string. Exposed at module level so the router
    can mint a `session_id` without instantiating SessionIndex."""
    return str(uuid.uuid4())


def thread_id_for(jwt_sub: str, session_id: str) -> str:
    """Compose the LangGraph `thread_id` from auth + session.

    Scoped by JWT subject so two admins (if we ever support more than one)
    can't see each other's chat history through a shared `session_id`.
    """
    return f"{jwt_sub}:{session_id}"


class SessionIndex:
    """Async-safe LRU of `thread_id`s.

    `touch(thread_id)` records the thread as most-recently-used. When the
    cap is hit, the oldest entry is evicted and the checkpointer is told to
    forget that thread.

    Eviction failures are logged but do NOT crash the request — better to
    leak a session checkpoint than to fail the operator's chat.
    """

    def __init__(self, *, checkpointer: InMemorySaver, max_entries: int) -> None:
        self._checkpointer = checkpointer
        self._max = max_entries
        self._lock = asyncio.Lock()
        self._lru: OrderedDict[str, None] = OrderedDict()

    async def touch(self, thread_id: str) -> None:
        """Record `thread_id` as MRU. Evicts the LRU entry if over cap."""
        async with self._lock:
            if thread_id in self._lru:
                self._lru.move_to_end(thread_id)
                return
            self._lru[thread_id] = None
            self._lru.move_to_end(thread_id)
            if len(self._lru) <= self._max:
                return
            # Evict the least-recently-used entry.
            evicted, _ = self._lru.popitem(last=False)
        # Release the lock before talking to the checkpointer — the call may
        # do work and we don't want it blocking concurrent `touch`es.
        await self._delete_thread_safely(evicted)

    async def size(self) -> int:
        async with self._lock:
            return len(self._lru)

    async def contains(self, thread_id: str) -> bool:
        async with self._lock:
            return thread_id in self._lru

    async def aclose(self) -> None:
        """Drop every tracked thread + clear the index. Called at shutdown."""
        async with self._lock:
            evicted = list(self._lru.keys())
            self._lru.clear()
        for thread_id in evicted:
            await self._delete_thread_safely(thread_id)

    async def _delete_thread_safely(self, thread_id: str) -> None:
        """Forget the thread on the checkpointer; never raise."""
        try:
            adelete = getattr(self._checkpointer, "adelete_thread", None)
            if adelete is not None:
                await adelete(thread_id)
                return
            # Fallback: sync `delete_thread` off the event loop.
            delete = getattr(self._checkpointer, "delete_thread", None)
            if delete is not None:
                await asyncio.to_thread(delete, thread_id)
        except Exception as exc:  # noqa: BLE001 — never crash a request over eviction
            log.warning(
                "session_eviction_failed",
                thread_id=thread_id,
                error_class=type(exc).__name__,
            )
