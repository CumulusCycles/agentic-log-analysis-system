"""Tests for FNOL's three global exception handlers.

Builds a minimal FastAPI app with only our handlers attached. The httpx-error
classification path is unique to FNOL (SDA is its only upstream).
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from fnol.exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


@pytest.fixture
def handler_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/throw")
    async def throw() -> None:
        raise ValueError("kaboom — must not appear in response body")

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail="i am a teapot")

    @app.get("/sda-down")
    async def sda_down() -> None:
        # Simulate the case where a route forgot to catch httpx errors and
        # the connection to SDA failed.
        raise httpx.ConnectError("[Errno 111] Connection refused")

    class Item(BaseModel):
        name: str

    @app.post("/items")
    async def make_item(item: Item) -> Item:
        return item

    return app


@pytest_asyncio.fixture
async def handler_client(handler_app):
    transport = ASGITransport(app=handler_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_with_generic_body(handler_client):
    response = await handler_client.get("/throw")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "kaboom" not in response.text


@pytest.mark.asyncio
async def test_http_exception_preserves_status_and_detail(handler_client):
    response = await handler_client.get("/teapot")
    assert response.status_code == 418
    assert response.json() == {"detail": "i am a teapot"}


@pytest.mark.asyncio
async def test_uncaught_httpx_request_error_returns_502(handler_client):
    """An httpx.RequestError that escapes a route lands as 502 (not 500)."""
    response = await handler_client.get("/sda-down")
    assert response.status_code == 502
    assert response.json() == {"detail": "shared data api unreachable"}


@pytest.mark.asyncio
async def test_request_validation_error_returns_422_with_field_details(handler_client):
    response = await handler_client.post("/items", json={"wrong_field": "x"})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    assert any("name" in (err.get("loc") or []) for err in body["detail"])
