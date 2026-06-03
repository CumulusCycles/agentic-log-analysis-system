"""Alembic environment.

This env uses the async SQLAlchemy engine because the Shared Data API uses
asyncpg in production. The bridge pattern is `connection.run_sync(do_run_migrations)`
— the documented Alembic recipe for async drivers.

`sqlalchemy.url` is intentionally blank in alembic.ini; we set it here from
`Settings.postgres_url` (env var `SHARED_DATA_API_POSTGRES_URL`) so dev CLI and
container runtime share the same configuration source.
"""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from shared_data_api.config import get_settings
from shared_data_api.db.models import Base

config = context.config

# We deliberately do NOT call logging.config.fileConfig() here. The Shared Data
# API configures logging via structlog (logging_setup.py) BEFORE the lifespan
# runs `run_migrations`. fileConfig would replace the root handler with
# Alembic's plain stdlib formatter, breaking JSON output for everything that
# logs after migration. Alembic's own log lines pipe through the existing
# structlog ProcessorFormatter bridge — which is what we want.

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.postgres_url)

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.postgres_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


def run_migrations_offline() -> None:
    context.configure(
        url=settings.postgres_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
