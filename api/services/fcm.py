"""FCM push notification service for Android VoIP calls.

Sends high-priority data-only FCM messages via firebase-admin SDK.
Push payloads contain zero plaintext message content (SECURITY_MODEL.md).
"""

import logging
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None
_initialized = False


def _ensure_initialized() -> bool:
    """Lazily initialize the Firebase Admin SDK. Returns True if ready."""
    global _app, _initialized
    if _initialized:
        return _app is not None

    _initialized = True
    sa_path = os.environ.get("FCM_SERVICE_ACCOUNT_PATH", "")

    if not sa_path or not Path(sa_path).exists():
        logger.warning("FCM not configured — missing or invalid FCM_SERVICE_ACCOUNT_PATH")
        return False

    try:
        cred = credentials.Certificate(sa_path)
        _app = firebase_admin.initialize_app(cred)
        return True
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")
        return False


def send_call_push(
    device_token: str,
    caller_name: str,
    call_id: str,
    call_type: str,
) -> bool | None:
    """Send a high-priority data-only FCM message for an incoming call.

    Returns True if the message was accepted, False if the token is bad/rejected,
    or None if FCM is not configured.
    The payload contains only caller_name, call_id, and call_type — no plaintext content.
    """
    if not _ensure_initialized():
        logger.info("FCM not configured — skipping push to %s...%s", device_token[:8], device_token[-4:])
        return None

    message = messaging.Message(
        token=device_token,
        data={
            "type": "call",
            "caller_name": caller_name,
            "call_id": call_id,
            "call_type": call_type,
        },
        android=messaging.AndroidConfig(
            priority="high",
            ttl=60,
        ),
    )

    try:
        messaging.send(message)
        return True
    except messaging.UnregisteredError:
        logger.warning("FCM token unregistered: %s...%s", device_token[:8], device_token[-4:])
        return False
    except messaging.InvalidArgumentError:
        logger.error("FCM invalid token: %s...%s", device_token[:8], device_token[-4:])
        return False
    except Exception:
        logger.exception("FCM send error for %s...%s", device_token[:8], device_token[-4:])
        return False


def is_bad_token_error(error: Exception) -> bool:
    """Check if an FCM error indicates a bad/expired device token."""
    return isinstance(error, (messaging.UnregisteredError, messaging.InvalidArgumentError))
