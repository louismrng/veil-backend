"""Bearer token authentication for the REST API.

Tokens are JWTs signed with the shared JWT_SECRET.  Each token carries
the ``sub`` claim set to the user's bare JID.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer()


def _get_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_token(jid: str) -> str:
    """Create a signed JWT for the given JID.

    The token expires 24 hours after issuance.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": jid,
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> str:
    """Decode and validate a JWT bearer token.

    Returns the bare JID from the ``sub`` claim.
    Raises 401 on any validation failure.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            _get_secret(),
            algorithms=["HS256"],
        )
        jid: str | None = payload.get("sub")
        if jid is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing sub claim",
            )
        return jid
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
