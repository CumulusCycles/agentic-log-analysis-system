from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth.password import hash_password
from .config import get_settings
from .exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .logging_setup import configure_logging, get_logger
from .routers import auth, health, logs, status

# Paths FastAPI auto-mounts that the SPA catch-all MUST NOT intercept.
# Swagger UI is intentionally exposed per ADR-001 — the dashboard's audience
# is a single admin/operator, and Swagger is a strict diagnostic win
# (especially once 7e lands /api/chat).
_FASTAPI_RESERVED_PREFIXES = ("docs", "redoc", "openapi.json")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(log_file_path=None)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bcrypt-hash the admin password once at startup and drop the
        # plaintext reference. The hash lives on app.state for the lifetime
        # of the process; the plaintext is never persisted or logged.
        app.state.admin_password_hash = hash_password(settings.admin_password)
        log.info("startup_complete")
        yield

    app = FastAPI(
        title="Agentic Log Analysis Dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(logs.router, prefix="/api")
    app.include_router(status.router, prefix="/api")

    # Static React build — mounted under /assets/ for hashed bundles, with a
    # catch-all GET that serves index.html for every other unknown path so the
    # client-side React Router can take over. The catch-all explicitly skips
    # FastAPI's own /docs, /redoc, /openapi.json so Swagger continues to work.
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        dist_resolved = dist.resolve()
        index_html = dist_resolved / "index.html"
        app.mount("/assets", StaticFiles(directory=str(dist_resolved / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # Never shadow FastAPI's Swagger / ReDoc / OpenAPI auto-mounts.
            if full_path.startswith(_FASTAPI_RESERVED_PREFIXES):
                raise HTTPException(status_code=404, detail="Not Found")
            # Serve static files from dist root if they exist (favicon, etc.),
            # otherwise fall through to index.html for SPA routes. Resolve
            # candidate then verify it stays under dist_resolved to block
            # path-traversal like `../../etc/passwd`.
            if full_path:
                candidate = (dist_resolved / full_path).resolve()
                if candidate.is_file() and candidate.is_relative_to(dist_resolved):
                    return FileResponse(candidate)
            if index_html.is_file():
                return FileResponse(index_html)
            raise HTTPException(status_code=404, detail="Not Found")

    else:
        log.warning("frontend_dist_missing", expected=str(dist))

    return app


app = create_app()
