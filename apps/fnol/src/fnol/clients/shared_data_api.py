"""Thin async HTTP client around the Shared Data API.

Holds a single `httpx.AsyncClient` for the lifetime of the FNOL app. The
`X-API-Key` header is set once at construction so every outgoing request
includes it — per ADR-006 §1 the key is required on every SDA call,
including `/auth/login`.
"""

import httpx

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger(__name__)


class SharedDataAPIClient:
    def __init__(self, settings: Settings, *, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            base_url=settings.shared_data_api_base_url,
            timeout=timeout,
            headers={"X-API-Key": settings.shared_data_api_key_fnol},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self, username: str, password: str) -> dict:
        r = await self._client.post(
            "/auth/login", json={"username": username, "password": password}
        )
        r.raise_for_status()
        return r.json()

    async def create_claim(self, payload: dict, bearer: str) -> dict:
        r = await self._client.post(
            "/claims",
            json=payload,
            headers={"Authorization": f"Bearer {bearer}"},
        )
        r.raise_for_status()
        return r.json()

    async def get_claim(self, claim_id: str, bearer: str) -> dict:
        r = await self._client.get(
            f"/claims/{claim_id}",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        r.raise_for_status()
        return r.json()
