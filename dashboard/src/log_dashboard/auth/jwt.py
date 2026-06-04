from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings, get_settings
from ..logging_setup import get_logger

log = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)

# Stable identifiers for the dashboard's JWT iss/aud claims. The audience is
# this dashboard alone — never confused with SDA's `agentic-log-analysis-insurance-apps`
# audience (validated server-side on every decode).
JWT_ISSUER = "dashboard"
JWT_AUDIENCE = "agentic-log-analysis-dashboard"


def encode_token(*, username: str, role: str, settings: Settings) -> str:
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, settings: Settings) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
    except jwt.PyJWTError as exc:
        # Log the specific reason server-side but return a generic message so
        # the response cannot be used as an oracle (expired vs wrong-aud vs
        # wrong-iss vs bad-signature).
        log.info("jwt_decode_failed", reason=exc.__class__.__name__, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        ) from exc


async def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    payload = decode_token(credentials.credentials, settings=settings)
    request.state.username = payload.get("sub", "-")
    request.state.user_role = payload.get("role")
    return payload
