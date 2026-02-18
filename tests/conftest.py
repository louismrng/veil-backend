"""Shared test fixtures for backend integration tests.

These tests are designed to run against the full Docker Compose stack.
Start the stack with `docker compose up -d` before running tests.
"""

import os

import pytest

# Default test configuration — override via environment variables.
XMPP_HOST = os.environ.get("TEST_XMPP_HOST", "localhost")
XMPP_PORT_STARTTLS = int(os.environ.get("TEST_XMPP_PORT_STARTTLS", "5222"))
XMPP_PORT_TLS = int(os.environ.get("TEST_XMPP_PORT_TLS", "5223"))
XMPP_DOMAIN = os.environ.get("TEST_XMPP_DOMAIN", "example.com")
SIP_HOST = os.environ.get("TEST_SIP_HOST", "localhost")
SIP_PORT = int(os.environ.get("TEST_SIP_PORT", "5061"))
SIP_WSS_PORT = int(os.environ.get("TEST_SIP_WSS_PORT", "8089"))
TURN_HOST = os.environ.get("TEST_TURN_HOST", "localhost")
TURN_PORT = int(os.environ.get("TEST_TURN_PORT", "3478"))
API_BASE_URL = os.environ.get("TEST_API_BASE_URL", "http://localhost:8443")
DB_URL = os.environ.get(
    "TEST_DB_URL", "postgresql://ejabberd:testpassword@localhost:5432/ejabberd"
)
