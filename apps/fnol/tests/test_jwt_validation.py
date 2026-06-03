"""Decode rejects tokens with wrong iss/aud/expired claims."""

import time

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from fnol.auth.jwt import JWT_AUDIENCE, JWT_ISSUER, decode_token


def _make_token(settings, **overrides):
    now = int(time.time())
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "user_id": "u1",
        "role": "customer",
        "app": "fnol",
        "iat": now,
        "exp": now + 600,
    }
    payload.update(overrides)
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_valid_token_decodes(settings):
    token = _make_token(settings)
    claims = decode_token(token, settings)
    assert claims["user_id"] == "u1"
    assert claims["app"] == "fnol"


def test_wrong_issuer_rejected(settings):
    token = _make_token(settings, iss="evil-issuer")
    with pytest.raises(HTTPException) as exc:
        decode_token(token, settings)
    assert exc.value.status_code == 401


def test_wrong_audience_rejected(settings):
    token = _make_token(settings, aud="other-audience")
    with pytest.raises(HTTPException) as exc:
        decode_token(token, settings)
    assert exc.value.status_code == 401


def test_expired_token_rejected(settings):
    token = _make_token(settings, exp=int(time.time()) - 60)
    with pytest.raises(HTTPException) as exc:
        decode_token(token, settings)
    assert exc.value.status_code == 401


def test_wrong_secret_rejected(settings):
    now = int(time.time())
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "user_id": "u1",
        "exp": now + 600,
    }
    token = pyjwt.encode(payload, "wrong-secret", algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc:
        decode_token(token, settings)
    assert exc.value.status_code == 401


def test_decode_error_detail_is_generic(settings):
    """The 401 detail must not leak the underlying PyJWT error reason."""
    token = _make_token(settings, iss="evil-issuer")
    with pytest.raises(HTTPException) as exc:
        decode_token(token, settings)
    assert exc.value.detail == "invalid token"
