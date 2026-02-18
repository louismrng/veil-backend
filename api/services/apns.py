"""APNs VoIP push notification service.

Sends VoIP pushes via the APNs HTTP/2 provider API using aioapns.
Push payloads contain zero plaintext message content (SECURITY_MODEL.md).
"""

import logging
import os
from pathlib import Path

from aioapns import APNs, NotificationRequest, ConnectionError

logger = logging.getLogger(__name__)

_client: APNs | None = None


def _get_client() -> APNs | None:
    """Lazily initialize the APNs client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client

    key_path = os.environ.get("APNS_KEY_PATH", "")
    key_id = os.environ.get("APNS_KEY_ID", "")
    team_id = os.environ.get("APNS_TEAM_ID", "")

    if not key_path or not key_id or not team_id:
        logger.warning("APNs not configured — missing APNS_KEY_PATH, APNS_KEY_ID, or APNS_TEAM_ID")
        return None

    if not Path(key_path).exists():
        logger.warning("APNs key file not found at %s", key_path)
        return None

    _client = APNs(
        key=key_path,
        key_id=key_id,
        team_id=team_id,
        topic=os.environ.get("APNS_BUNDLE_ID", "com.example.veil") + ".voip",
        use_sandbox=os.environ.get("APNS_USE_SANDBOX", "true").lower() == "true",
    )
    return _client


async def send_voip_push(
    device_token: str,
    caller_name: str,
    call_id: str,
    call_type: str,
) -> bool | None:
    """Send a VoIP push notification to an iOS device.

    Returns True if the push was accepted, False if the token is bad/rejected,
    or None if APNs is not configured.
    The payload contains only caller_name, call_id, and call_type — no plaintext content.
    """
    client = _get_client()
    if client is None:
        logger.info("APNs not configured — skipping VoIP push to %s...%s", device_token[:8], device_token[-4:])
        return None

    request = NotificationRequest(
        device_token=device_token,
        message={
            "caller_name": caller_name,
            "call_id": call_id,
            "call_type": call_type,
        },
        push_type="voip",
    )

    try:
        response = await client.send_notification(request)
        if not response.is_successful:
            logger.error(
                "APNs rejected push for token %s...%s: %s",
                device_token[:8], device_token[-4:],
                response.description,
            )
            return False
        return True
    except ConnectionError:
        logger.exception("APNs connection error sending to %s...%s", device_token[:8], device_token[-4:])
        return False


def is_bad_token_error(description: str | None) -> bool:
    """Check if an APNs error indicates a bad/expired device token."""
    if description is None:
        return False
    return description in ("BadDeviceToken", "Unregistered", "ExpiredToken")
