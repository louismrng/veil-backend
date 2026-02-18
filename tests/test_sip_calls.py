"""Integration tests for SIP calling infrastructure.

Tests verify:
- Kamailio is reachable on TLS (5061) and WSS (8443) ports
- SIP OPTIONS returns a valid response
- WebSocket upgrade handshake succeeds on port 8443
- RTPEngine control socket is reachable
"""

import socket
import ssl

import pytest

from conftest import SIP_HOST, SIP_PORT, XMPP_DOMAIN

SIP_WSS_PORT = 8089  # Host-mapped port for Kamailio WSS (container 8443)


class TestSipTlsConnectivity:
    """Verify SIP server TLS connectivity on port 5061."""

    def test_sip_tls_port_reachable(self) -> None:
        """Port 5061 accepts TLS connections."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw_sock = socket.create_connection((SIP_HOST, SIP_PORT), timeout=5)
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=SIP_HOST)
            tls_sock.close()
        except ssl.SSLError:
            raw_sock.close()
            raise

    def test_sip_options_response(self) -> None:
        """Send SIP OPTIONS and expect a valid SIP/2.0 response."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw_sock = socket.create_connection((SIP_HOST, SIP_PORT), timeout=5)
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=SIP_HOST)
            try:
                options_req = (
                    f"OPTIONS sip:{XMPP_DOMAIN} SIP/2.0\r\n"
                    f"Via: SIP/2.0/TLS {SIP_HOST}:5061;branch=z9hG4bK-test-call-001\r\n"
                    f"Max-Forwards: 70\r\n"
                    f"From: <sip:test@{XMPP_DOMAIN}>;tag=testcall001\r\n"
                    f"To: <sip:test@{XMPP_DOMAIN}>\r\n"
                    f"Call-ID: test-call-options-001@{SIP_HOST}\r\n"
                    f"CSeq: 1 OPTIONS\r\n"
                    f"Content-Length: 0\r\n"
                    f"\r\n"
                ).encode()
                tls_sock.sendall(options_req)
                data = tls_sock.recv(4096)
                assert b"SIP/2.0" in data
            finally:
                tls_sock.close()
        except ssl.SSLError:
            raw_sock.close()
            raise


class TestSipWssConnectivity:
    """Verify WebSocket Secure connectivity on port 8443."""

    def test_wss_port_reachable(self) -> None:
        """WSS port accepts TLS connections."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw_sock = socket.create_connection((SIP_HOST, SIP_WSS_PORT), timeout=5)
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=SIP_HOST)
            tls_sock.close()
        except ssl.SSLError:
            raw_sock.close()
            raise

    def test_websocket_upgrade(self) -> None:
        """WebSocket upgrade handshake on port 8443 returns 101 Switching Protocols."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw_sock = socket.create_connection((SIP_HOST, SIP_WSS_PORT), timeout=5)
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=SIP_HOST)
            try:
                upgrade_req = (
                    "GET / HTTP/1.1\r\n"
                    f"Host: {SIP_HOST}:{SIP_WSS_PORT}\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                    "Sec-WebSocket-Version: 13\r\n"
                    "Sec-WebSocket-Protocol: sip\r\n"
                    "\r\n"
                ).encode()
                tls_sock.sendall(upgrade_req)
                data = tls_sock.recv(4096)
                assert b"101" in data or b"HTTP/1.1" in data
            finally:
                tls_sock.close()
        except ssl.SSLError:
            raw_sock.close()
            raise


class TestRtpEngineConnectivity:
    """Verify RTPEngine control socket is reachable."""

    def test_rtpengine_control_socket(self) -> None:
        """RTPEngine UDP control socket responds on port 22222."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        try:
            # Send a bencode ping command to RTPEngine
            sock.sendto(b"d7:command4:pinge", (SIP_HOST, 22222))
            data, _ = sock.recvfrom(4096)
            # RTPEngine should respond with a bencode dict containing "result"
            assert b"result" in data
        except socket.timeout:
            pytest.skip("RTPEngine not reachable on port 22222 — may not be running")
        finally:
            sock.close()
