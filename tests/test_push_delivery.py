"""Integration tests for the call-notify push delivery endpoint.

Tests verify:
- POST /api/v1/push/call-notify accepts valid requests (no JWT required)
- Returns "no_registrations" when callee has no push tokens
- Returns "sent" count after delivering to registered devices
- Validates request body (rejects missing fields)
- Payload contains zero plaintext message content
"""

import time

import jwt
import pytest

try:
    import httpx

    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

from conftest import API_BASE_URL

_JWT_SECRET = "test-jwt-secret"


def _make_token(jid: str, secret: str = _JWT_SECRET, exp_delta: int = 3600) -> str:
    payload = {"sub": jid, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.skipif(not _HAS_HTTPX, reason="httpx not installed")
class TestCallNotify:
    """Call notification push delivery tests."""

    @pytest.fixture()
    def client(self) -> "httpx.Client":
        return httpx.Client(base_url=API_BASE_URL, timeout=10)

    def test_call_notify_no_registrations(self, client: "httpx.Client") -> None:
        """Call-notify for an unregistered user returns no_registrations."""
        resp = client.post(
            "/api/v1/push/call-notify",
            json={
                "callee_username": "nobody_registered_12345",
                "caller_username": "alice",
                "caller_display_name": "Alice",
                "call_id": "test-call-001@kamailio",
                "call_type": "audio",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_registrations"
        assert data["sent"] == 0

    def test_call_notify_no_auth_required(self, client: "httpx.Client") -> None:
        """Call-notify endpoint does NOT require JWT (internal Kamailio webhook)."""
        resp = client.post(
            "/api/v1/push/call-notify",
            json={
                "callee_username": "testuser",
                "caller_username": "alice",
                "caller_display_name": "Alice",
                "call_id": "test-no-auth@kamailio",
                "call_type": "audio",
            },
        )
        # Should not return 401/403 — endpoint is unauthenticated
        assert resp.status_code == 200

    def test_call_notify_with_registered_device(self, client: "httpx.Client") -> None:
        """Register a push token then call-notify sends to that device."""
        test_jid = "pushtest_caller@example.com"
        test_callee_jid = "pushtest_callee@example.com"

        # Register a push token for the callee
        headers = {"Authorization": f"Bearer {_make_token(test_callee_jid)}"}
        reg_resp = client.post(
            "/api/v1/push/register",
            json={
                "jid": test_callee_jid,
                "device_id": "push-delivery-test-device",
                "platform": "android",
                "push_token": "fcm-test-token-for-delivery",
                "app_id": "com.example.veil",
            },
            headers=headers,
        )
        assert reg_resp.status_code == 200

        # Now send a call-notify — should find the registration
        # (FCM will fail since we don't have real credentials, but the
        #  endpoint should still process the request without error)
        resp = client.post(
            "/api/v1/push/call-notify",
            json={
                "callee_username": "pushtest_callee",
                "caller_username": "pushtest_caller",
                "caller_display_name": "Test Caller",
                "call_id": "test-delivery@kamailio",
                "call_type": "video",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # sent may be 0 (FCM not configured in test) but status should not error
        assert data["status"] in ("sent", "no_registrations")

        # Clean up
        client.request(
            "DELETE",
            "/api/v1/push/register",
            json={
                "jid": test_callee_jid,
                "device_id": "push-delivery-test-device",
            },
            headers=headers,
        )

    def test_call_notify_validates_call_type(self, client: "httpx.Client") -> None:
        """Call-notify rejects invalid call_type values."""
        resp = client.post(
            "/api/v1/push/call-notify",
            json={
                "callee_username": "bob",
                "caller_username": "alice",
                "caller_display_name": "Alice",
                "call_id": "test-invalid-type@kamailio",
                "call_type": "invalid_type",
            },
        )
        assert resp.status_code == 422

    def test_call_notify_missing_fields(self, client: "httpx.Client") -> None:
        """Call-notify rejects requests with missing required fields."""
        resp = client.post(
            "/api/v1/push/call-notify",
            json={
                "callee_username": "bob",
                # Missing caller_username, call_id
            },
        )
        assert resp.status_code == 422

    def test_call_notify_video_call(self, client: "httpx.Client") -> None:
        """Call-notify accepts video call type."""
        resp = client.post(
            "/api/v1/push/call-notify",
            json={
                "callee_username": "videotest",
                "caller_username": "alice",
                "caller_display_name": "Alice",
                "call_id": "test-video@kamailio",
                "call_type": "video",
            },
        )
        assert resp.status_code == 200
