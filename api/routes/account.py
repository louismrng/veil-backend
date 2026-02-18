"""Account management endpoints (INTERFACES.md §4.3)."""

import hashlib
import logging
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from auth import create_token, verify_token
from db import get_pool
from models import (
    AccountDeleteRequest,
    AccountLoginRequest,
    AccountLoginResponse,
    AccountRegisterRequest,
    AccountRegisterResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/account", tags=["account"])

_EJABBERD_API_URL = os.environ.get("EJABBERD_API_URL", "https://ejabberd:5443/api")
_XMPP_DOMAIN = os.environ.get("XMPP_DOMAIN", "example.com")


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AccountRegisterResponse)
async def register_account(body: AccountRegisterRequest) -> AccountRegisterResponse:
    """Create a new user account.

    Registers the user with Ejabberd (XMPP) and inserts a Kamailio
    subscriber row for SIP digest authentication.
    """
    username = body.username.lower()
    domain = _XMPP_DOMAIN

    # Register with Ejabberd via admin API
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{_EJABBERD_API_URL}/register",
                json={"user": username, "host": domain, "password": body.password},
                timeout=10.0,
            )
    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Registration service unavailable. Please try again later.",
        )

    if resp.status_code == 409 or (resp.status_code == 200 and resp.text and "already registered" in resp.text.lower()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken.",
        )

    if resp.status_code not in (200, 201):
        logger.error("Ejabberd register returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Registration failed. Please try again later.",
        )

    # Insert Kamailio subscriber row for SIP digest authentication
    ha1 = hashlib.md5(f"{username}:{domain}:{body.password}".encode()).hexdigest()
    ha1b = hashlib.md5(f"{username}@{domain}:{domain}:{body.password}".encode()).hexdigest()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO subscriber (username, domain, password, ha1, ha1b)
                   VALUES ($1, $2, '', $3, $4)
                   ON CONFLICT (username, domain) DO UPDATE
                   SET ha1 = EXCLUDED.ha1, ha1b = EXCLUDED.ha1b""",
                username, domain, ha1, ha1b,
            )
    except Exception:
        logger.exception("Failed to insert Kamailio subscriber for %s", username)

    jid = f"{username}@{domain}"
    token = create_token(jid)
    return AccountRegisterResponse(jid=jid, token=token)


@router.post("/login", response_model=AccountLoginResponse)
async def login_account(body: AccountLoginRequest) -> AccountLoginResponse:
    """Authenticate an existing user and issue a JWT."""
    username = body.username.lower()
    domain = _XMPP_DOMAIN

    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{_EJABBERD_API_URL}/check_password",
                json={"user": username, "host": domain, "password": body.password},
                timeout=10.0,
            )
    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API for login")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service unavailable.",
        )

    # Ejabberd check_password returns 0 (success) or 1 (failure) as plain text
    if resp.status_code != 200 or resp.text.strip() != "0":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Ensure Kamailio subscriber row exists (upsert for existing users)
    ha1 = hashlib.md5(f"{username}:{domain}:{body.password}".encode()).hexdigest()
    ha1b = hashlib.md5(f"{username}@{domain}:{domain}:{body.password}".encode()).hexdigest()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO subscriber (username, domain, password, ha1, ha1b)
                   VALUES ($1, $2, '', $3, $4)
                   ON CONFLICT (username, domain) DO UPDATE
                   SET ha1 = EXCLUDED.ha1, ha1b = EXCLUDED.ha1b""",
                username, domain, ha1, ha1b,
            )
    except Exception:
        logger.exception("Failed to upsert Kamailio subscriber for %s", username)

    jid = f"{username}@{domain}"
    token = create_token(jid)
    return AccountLoginResponse(jid=jid, token=token)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_account(
    body: AccountDeleteRequest,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> dict:
    """Delete a user account and all associated data.

    The caller must provide their current password for confirmation.
    This removes the user from Ejabberd (via the admin API or SQL),
    all push registrations, and the subscriber table.
    """
    if body.jid != caller_jid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token JID does not match request JID",
        )

    pool = await get_pool()
    username = body.jid.split("@")[0]

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Remove push registrations
            await conn.execute(
                "DELETE FROM push_registrations WHERE jid = $1",
                body.jid,
            )

            # Remove subscriber record (SIP auth)
            await conn.execute(
                "DELETE FROM subscriber WHERE username = $1",
                username,
            )

            # Remove Ejabberd user record.
            # Ejabberd stores users in its own `users` table when using SQL auth.
            await conn.execute(
                "DELETE FROM users WHERE username = $1",
                username,
            )

    return {"status": "deleted"}
