"""Push notification registration and call-notify endpoints (INTERFACES.md §4.1 / §4.2)."""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from auth import verify_token
from db import get_pool
from models import CallNotifyRequest, PushDeregisterRequest, PushRegisterRequest, PushRegisterResponse
from services import apns as apns_service
from services import fcm as fcm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/push", tags=["push"])

_XMPP_DOMAIN = os.environ.get("XMPP_DOMAIN", "example.com")


@router.post("/register", response_model=PushRegisterResponse)
async def register_push(
    body: PushRegisterRequest,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> PushRegisterResponse:
    """Register a device push token for APNs or FCM delivery."""
    if body.jid != caller_jid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token JID does not match request JID",
        )

    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO push_registrations (jid, device_uuid, platform, push_token, app_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (jid, device_uuid)
        DO UPDATE SET push_token = EXCLUDED.push_token,
                      platform   = EXCLUDED.platform,
                      app_id     = EXCLUDED.app_id,
                      registered_at = NOW()
        """,
        body.jid,
        body.device_id,
        body.platform,
        body.push_token,
        body.app_id,
    )
    return PushRegisterResponse(status="registered")


@router.delete("/register", status_code=status.HTTP_200_OK)
async def deregister_push(
    body: PushDeregisterRequest,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> dict:
    """Remove a device's push token."""
    if body.jid != caller_jid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token JID does not match request JID",
        )

    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM push_registrations WHERE jid = $1 AND device_uuid = $2",
        body.jid,
        body.device_id,
    )
    if result == "DELETE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Push registration not found",
        )
    return {"status": "deregistered"}


@router.post("/call-notify", status_code=status.HTTP_200_OK)
async def call_notify(body: CallNotifyRequest) -> dict:
    """Send VoIP push notifications for an incoming call.

    Called by Kamailio when a callee is not registered (internal webhook,
    NOT JWT-protected since it comes from the Kamailio container on the
    Docker network).

    Looks up all push registrations for the callee and sends:
    - iOS: APNs VoIP push (apns-push-type: voip)
    - Android: High-priority data-only FCM message

    Push payload contains only caller_name, call_id, call_type — zero
    plaintext message content.
    """
    callee_jid = f"{body.callee_username}@{_XMPP_DOMAIN}"
    caller_display = body.caller_display_name or body.caller_username

    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT device_uuid, platform, push_token FROM push_registrations WHERE jid = $1",
        callee_jid,
    )

    if not rows:
        logger.info("No push registrations found for %s", callee_jid)
        return {"status": "no_registrations", "sent": 0}

    sent = 0
    bad_tokens: list[tuple[str, str]] = []

    for row in rows:
        platform = row["platform"]
        token = row["push_token"]
        device_uuid = row["device_uuid"]

        if platform == "ios":
            result = await apns_service.send_voip_push(
                device_token=token,
                caller_name=caller_display,
                call_id=body.call_id,
                call_type=body.call_type,
            )
            if result is True:
                sent += 1
            elif result is False:
                # Explicitly rejected — bad token
                bad_tokens.append((callee_jid, device_uuid))
            # result is None means not configured — skip silently
        elif platform == "android":
            result = fcm_service.send_call_push(
                device_token=token,
                caller_name=caller_display,
                call_id=body.call_id,
                call_type=body.call_type,
            )
            if result is True:
                sent += 1
            elif result is False:
                bad_tokens.append((callee_jid, device_uuid))

    # Clean up bad tokens
    if bad_tokens:
        async with pool.acquire() as conn:
            for jid, device_uuid in bad_tokens:
                await conn.execute(
                    "DELETE FROM push_registrations WHERE jid = $1 AND device_uuid = $2",
                    jid, device_uuid,
                )
        logger.info("Cleaned up %d bad push tokens for %s", len(bad_tokens), callee_jid)

    return {"status": "sent", "sent": sent}
