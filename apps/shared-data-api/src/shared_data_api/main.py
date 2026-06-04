from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .db import mongo, postgres
from .db.consistency import warn_on_volume_asymmetry
from .exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .logging_setup import configure_logging, get_logger
from .middleware.api_key import APIKeyMiddleware
from .middleware.request_logger import RequestLoggerMiddleware
from .routers import auth, claims, health, policies, users
from .seeds.seed import run_seed_if_empty
from .simulator.claim_status import ClaimStatusSimulator


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_file_path)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await postgres.init_engine(settings.postgres_url)
        await postgres.run_migrations()
        await mongo.init_client(settings.mongodb_uri, settings.mongodb_database)
        await mongo.ensure_indexes()
        await run_seed_if_empty(settings)
        await warn_on_volume_asymmetry()
        simulator = ClaimStatusSimulator(settings)
        task = simulator.start()
        log.info("startup_complete")
        try:
            yield
        finally:
            await simulator.stop(task)
            await postgres.dispose()
            mongo.close()

    app = FastAPI(title="Shared Data API", version="0.1.0", lifespan=lifespan)

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Last-added middleware is outermost — request logger wraps everything,
    # api-key check runs inside it so 401s are still logged.
    app.add_middleware(APIKeyMiddleware, settings=settings)
    app.add_middleware(RequestLoggerMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth")
    app.include_router(users.router, prefix="/users")
    app.include_router(policies.router, prefix="/policies")
    app.include_router(claims.router, prefix="/claims")
    return app


app = create_app()
