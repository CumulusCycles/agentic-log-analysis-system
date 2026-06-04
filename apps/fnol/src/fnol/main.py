from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .clients.shared_data_api import SharedDataAPIClient
from .config import get_settings
from .exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .logging_setup import configure_logging, get_logger
from .middleware.request_logger import RequestLoggerMiddleware
from .routers import auth, claims, health


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_file_path)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.sda = SharedDataAPIClient(settings)
        log.info("startup_complete")
        try:
            yield
        finally:
            await app.state.sda.aclose()

    # FNOL is a SPA + write-proxy, not an integration target. Suppress
    # FastAPI's auto-mounted Swagger / ReDoc / OpenAPI schema — SDA is the
    # only app in this stack that exposes Swagger (see ADR-001 and the
    # Healthcheck endpoints table in README.md).
    app = FastAPI(
        title="FNOL",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.add_middleware(RequestLoggerMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth")
    app.include_router(claims.router, prefix="/fnol")

    # Static React build — mounted under /assets/ for hashed bundles, with a
    # catch-all GET that serves index.html for every other unknown path so the
    # client-side React Router can take over (otherwise FastAPI would 404 on
    # routes like /submit and /claims/<uuid>).
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        dist_resolved = dist.resolve()
        index_html = dist_resolved / "index.html"
        app.mount("/assets", StaticFiles(directory=str(dist_resolved / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
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
