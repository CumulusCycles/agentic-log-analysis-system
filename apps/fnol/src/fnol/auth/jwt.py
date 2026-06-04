"""JWT decode-only path.

FNOL never issues JWTs — that's the SDA's job. FNOL verifies the iss/aud/exp
of bearer tokens presented by clients so it can attribute requests and
forward them to SDA.

Constants `JWT_ISSUER` and `JWT_AUDIENCE` MUST stay in sync with SDA's
`apps/shared-data-api/src/shared_data_api/auth/jwt.py`. See ADR-006 and
`.claude/rules/apps.md`.
"""

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings, get_settings
from ..logging_setup import get_logger

log = get_logger(__name__)

JWT_ISSUER = "shared-data-api"
JWT_AUDIENCE = "agentic-log-analysis-insurance-apps"

_bearer = HTTPBearer(auto_error=False)


def decode_token(token: str, settings: Settings) -> dict:
    try:
        return pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
    except pyjwt.PyJWTError as exc:
        # Log the real reason server-side; surface a generic message.
        log.info("jwt_decode_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_token(credentials.credentials, settings)
    # Stash for request_logger middleware + downstream SDA forwarding.
    request.state.user_id = claims.get("user_id", "-")
    request.state.bearer = credentials.credentials
    return claims
