import jwt as pyjwt
import pytest

from shared_data_api.auth.jwt import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    decode_token,
    encode_token,
)
from shared_data_api.config import get_settings


def test_encoded_token_includes_iss_and_aud():
    settings = get_settings()
    token = encode_token(user_id="u1", role="customer", app="fnol", settings=settings)
    # Decode without validation to inspect claims.
    payload = pyjwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_aud": False, "verify_iss": False},
    )
    assert payload["iss"] == JWT_ISSUER
    assert payload["aud"] == JWT_AUDIENCE


def test_decode_rejects_wrong_issuer():
    settings = get_settings()
    bad = pyjwt.encode(
        {
            "iss": "someone-else",
            "aud": JWT_AUDIENCE,
            "user_id": "u1",
            "role": "customer",
            "exp": 9999999999,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        decode_token(bad, settings=settings)
    assert exc.value.status_code == 401


def test_decode_rejects_wrong_audience():
    settings = get_settings()
    bad = pyjwt.encode(
        {
            "iss": JWT_ISSUER,
            "aud": "some-other-audience",
            "user_id": "u1",
            "role": "customer",
            "exp": 9999999999,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        decode_token(bad, settings=settings)
    assert exc.value.status_code == 401


def test_decode_accepts_token_we_just_minted():
    settings = get_settings()
    token = encode_token(user_id="u1", role="customer", app="fnol", settings=settings)
    payload = decode_token(token, settings=settings)
    assert payload["user_id"] == "u1"


def test_decode_rejects_expired_token():
    """An exp claim in the past must fail decode regardless of other validity."""
    from fastapi import HTTPException

    settings = get_settings()
    expired = pyjwt.encode(
        {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "user_id": "u1",
            "role": "customer",
            "exp": 1,  # 1970 — long expired
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as exc:
        decode_token(expired, settings=settings)
    assert exc.value.status_code == 401
    # Detail is a flat string — server logs the specific reason; the response
    # must not be an oracle for "why" the token was rejected.
    assert exc.value.detail == "invalid token"


def test_decode_accepts_token_just_before_expiry():
    """Boundary: a token expiring 30s in the future is still valid."""
    import time

    settings = get_settings()
    near_future_exp = int(time.time()) + 30
    token = pyjwt.encode(
        {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "user_id": "u1",
            "role": "customer",
            "exp": near_future_exp,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    payload = decode_token(token, settings=settings)
    assert payload["user_id"] == "u1"


@pytest.mark.asyncio
async def test_expired_token_rejected_by_auth_me(client, customer_portal_key, seeded_users):
    """End-to-end: an expired token at /auth/me returns 401."""
    settings = get_settings()
    expired = pyjwt.encode(
        {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "user_id": seeded_users["customer_id"],
            "role": "customer",
            "exp": 1,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = await client.get(
        "/auth/me",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {expired}",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid token"
