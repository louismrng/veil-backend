"""Integration tests for XMPP connectivity against the Ejabberd server.

Tests verify:
- TCP connectivity on STARTTLS (5222) and direct TLS (5223) ports
- STARTTLS upgrade on port 5222
- Direct TLS handshake on port 5223
"""

import socket
import ssl

import pytest

from conftest import XMPP_HOST, XMPP_PORT_STARTTLS, XMPP_PORT_TLS, XMPP_DOMAIN


class TestXmppConnectivity:
    """Verify basic XMPP server connectivity."""

    def test_starttls_port_reachable(self) -> None:
        """Port 5222 accepts TCP connections."""
        sock = socket.create_connection((XMPP_HOST, XMPP_PORT_STARTTLS), timeout=5)
        try:
            data = sock.recv(4096)
            # Ejabberd sends an XML stream header on connect
            assert b"<?xml" in data or b"<stream:" in data or b"stream:stream" in data
        finally:
            sock.close()

    def test_direct_tls_port_reachable(self) -> None:
        """Port 5223 accepts TLS connections."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = socket.create_connection((XMPP_HOST, XMPP_PORT_TLS), timeout=5)
        try:
            tls_sock = context.wrap_socket(sock, server_hostname=XMPP_DOMAIN)
            try:
                # After TLS handshake, send stream header and expect XML response
                stream_header = (
                    f"<?xml version='1.0'?>"
                    f"<stream:stream xmlns='jabber:client' "
                    f"xmlns:stream='http://etherx.jabber.org/streams' "
                    f"to='{XMPP_DOMAIN}' version='1.0'>"
                ).encode()
                tls_sock.sendall(stream_header)
                data = tls_sock.recv(4096)
                assert b"stream:stream" in data or b"stream:features" in data
            finally:
                tls_sock.close()
        except ssl.SSLError:
            sock.close()
            raise

    def test_starttls_offered(self) -> None:
        """Port 5222 offers STARTTLS in stream features."""
        sock = socket.create_connection((XMPP_HOST, XMPP_PORT_STARTTLS), timeout=5)
        try:
            stream_header = (
                f"<?xml version='1.0'?>"
                f"<stream:stream xmlns='jabber:client' "
                f"xmlns:stream='http://etherx.jabber.org/streams' "
                f"to='{XMPP_DOMAIN}' version='1.0'>"
            ).encode()
            sock.sendall(stream_header)
            data = b""
            # Read until we see features or timeout
            while b"</stream:features>" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            assert b"starttls" in data.lower()
        finally:
            sock.close()
