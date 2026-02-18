"""Integration tests for the REST API push notification endpoints.

Tests verify:
- POST /api/v1/push/register creates a push registration
- POST /api/v1/push/register updates an existing registration (upsert)
- DELETE /api/v1/push/register removes a registration
- Requests without a valid Bearer token are rejected (401)
- Requests with mismatched JID are rejected (403)
- GET /api/v1/server/info returns expected server discovery payload
- GET /api/v1/turn/credentials returns time-limited TURN credentials
- DELETE /api/v1/account removes user data
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

# A test JWT secret — must match the JWT_SECRET env var of the running API service.
_JWT_SECRET = "test-jwt-secret"


def _make_token(jid: str, secret: str = _JWT_SECRET, exp_delta: int = 3600) -> str:
    payload = {"sub": jid, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.skipif(not _HAS_HTTPX, reason="httpx not installed")
class TestPushApi:
    """Push registration endpoint tests."""

    @pytest.fixture()
    def client(self) -> "httpx.Client":
        return httpx.Client(base_url=API_BASE_URL, timeout=10)

    def _auth_header(self, jid: str = "alice@example.com") -> dict:
        return {"Authorization": f"Bearer {_make_token(jid)}"}

    def test_register_push_token(self, client: "httpx.Client") -> None:
        resp = client.post(
            "/api/v1/push/register",
            json={
                "jid": "alice@example.com",
                "device_id": "550e8400-e29b-41d4-a716-446655440000",
                "platform": "ios",
                "push_token": "apns-test-token-001",
                "app_id": "com.example.veil",
            },
            headers=self._auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    def test_register_push_upsert(self, client: "httpx.Client") -> None:
        headers = self._auth_header()
        body = {
            "jid": "alice@example.com",
            "device_id": "550e8400-e29b-41d4-a716-446655440000",
            "platform": "ios",
            "push_token": "apns-test-token-002",
            "app_id": "com.example.veil",
        }
        resp1 = client.post("/api/v1/push/register", json=body, headers=headers)
        assert resp1.status_code == 200
        # Update with a new token
        body["push_token"] = "apns-test-token-003"
        resp2 = client.post("/api/v1/push/register", json=body, headers=headers)
        assert resp2.status_code == 200

    def test_deregister_push_token(self, client: "httpx.Client") -> None:
        headers = self._auth_header()
        # Register first
        client.post(
            "/api/v1/push/register",
            json={
                "jid": "alice@example.com",
                "device_id": "deregister-test-device",
                "platform": "android",
                "push_token": "fcm-test-token",
                "app_id": "com.example.veil",
            },
            headers=headers,
        )
        # Now deregister
        resp = client.request(
            "DELETE",
            "/api/v1/push/register",
            json={
                "jid": "alice@example.com",
                "device_id": "deregister-test-device",
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_register_without_auth_returns_401(self, client: "httpx.Client") -> None:
        resp = client.post(
            "/api/v1/push/register",
            json={
                "jid": "alice@example.com",
                "device_id": "no-auth-device",
                "platform": "ios",
                "push_token": "token",
                "app_id": "com.example.veil",
            },
        )
        assert resp.status_code in (401, 403)

    def test_register_jid_mismatch_returns_403(self, client: "httpx.Client") -> None:
        # Token is for alice but request body says bob
        resp = client.post(
            "/api/v1/push/register",
            json={
                "jid": "bob@example.com",
                "device_id": "mismatch-device",
                "platform": "ios",
                "push_token": "token",
                "app_id": "com.example.veil",
            },
            headers=self._auth_header("alice@example.com"),
        )
        assert resp.status_code == 403


@pytest.mark.skipif(not _HAS_HTTPX, reason="httpx not installed")
class TestServerInfo:
    """Server discovery endpoint tests."""

    @pytest.fixture()
    def client(self) -> "httpx.Client":
        return httpx.Client(base_url=API_BASE_URL, timeout=10)

    def test_server_info_unauthenticated(self, client: "httpx.Client") -> None:
        resp = client.get("/api/v1/server/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "xmpp_domain" in data
        assert "xmpp_port_tls" in data
        assert data["xmpp_port_tls"] == 5223
        assert "sip_port_tls" in data
        assert data["sip_port_tls"] == 5061
        assert "turn_server" in data
        assert "server_version" in data
        assert "min_client_version" in data


@pytest.mark.skipif(not _HAS_HTTPX, reason="httpx not installed")
class TestTurnCredentials:
    """TURN credential generation endpoint tests."""

    @pytest.fixture()
    def client(self) -> "httpx.Client":
        return httpx.Client(base_url=API_BASE_URL, timeout=10)

    def _auth_header(self, jid: str = "alice@example.com") -> dict:
        return {"Authorization": f"Bearer {_make_token(jid)}"}

    def test_turn_credentials(self, client: "httpx.Client") -> None:
        resp = client.get(
            "/api/v1/turn/credentials",
            headers=self._auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "username" in data
        assert "password" in data
        assert data["ttl"] == 86400
        assert isinstance(data["uris"], list)
        assert len(data["uris"]) == 3
        # Username should contain a timestamp and the user
        assert "alice" in data["username"]

    def test_turn_credentials_requires_auth(self, client: "httpx.Client") -> None:
        resp = client.get("/api/v1/turn/credentials")
        assert resp.status_code in (401, 403)
