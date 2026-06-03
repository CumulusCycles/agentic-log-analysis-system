import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..logging_setup import get_logger
from .models import Base

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_engine(url: str, *, retries: int = 10, backoff_seconds: float = 3.0) -> None:
    global _engine, _session_factory

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            engine = create_async_engine(url, echo=False, pool_pre_ping=True)
            async with engine.connect() as conn:
                await conn.exec_driver_sql("SELECT 1")
            _engine = engine
            _session_factory = async_sessionmaker(engine, expire_on_commit=False)
            log.info("postgres_connected", attempt=attempt)
            return
        except Exception as exc:
            last_error = exc
            log.warning("postgres_connect_failed", attempt=attempt, error=str(exc))
            if attempt < retries:
                await asyncio.sleep(backoff_seconds)

    assert last_error is not None
    raise last_error


async def create_all(*, retries: int = 5, backoff_seconds: float = 2.0) -> None:
    if _engine is None:
        raise RuntimeError("Postgres engine not initialized")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("postgres_schema_ready", attempt=attempt)
            return
        except Exception as exc:
            last_error = exc
            log.warning("postgres_create_all_failed", attempt=attempt, error=str(exc))
            if attempt < retries:
                await asyncio.sleep(backoff_seconds)
    assert last_error is not None
    raise last_error


async def dispose() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Postgres session factory not initialized")
    async with _session_factory() as s:
        yield s


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session() as s:
        yield s
