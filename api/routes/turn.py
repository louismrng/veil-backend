"""TURN credential generation endpoint (MODULE_01_BACKEND.md §3.3)."""

import base64
import hashlib
import hmac
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends

from auth import verify_token
from models import TurnCredentialsResponse

router = APIRouter(prefix="/api/v1/turn", tags=["turn"])

_TURN_CREDENTIAL_TTL = 86400  # 24 hours


@router.get("/credentials", response_model=TurnCredentialsResponse)
async def turn_credentials(
    caller_jid: Annotated[str, Depends(verify_token)],
) -> TurnCredentialsResponse:
    """Generate time-limited TURN credentials using the shared secret.

    The credential format follows the TURN REST API spec (draft-uberti-behave-turn-rest):
    username = "{expiry_timestamp}:{user_identifier}"
    password = base64(HMAC-SHA1(secret, username))
    """
    secret = os.environ["TURN_SECRET"]
    turn_domain = os.environ.get("TURN_DOMAIN", "turn.example.com")

    username_part = caller_jid.split("@")[0]
    expiry = int(time.time()) + _TURN_CREDENTIAL_TTL
    turn_username = f"{expiry}:{username_part}"

    hmac_value = hmac.new(
        secret.encode(),
        turn_username.encode(),
        hashlib.sha1,
    ).digest()
    password = base64.b64encode(hmac_value).decode()

    return TurnCredentialsResponse(
        username=turn_username,
        password=password,
        ttl=_TURN_CREDENTIAL_TTL,
        uris=[
            f"turn:{turn_domain}:3478?transport=udp",
            f"turn:{turn_domain}:3478?transport=tcp",
            f"turns:{turn_domain}:5349?transport=tcp",
        ],
    )
