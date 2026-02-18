"""Integration tests for SIP registration against the Kamailio server.

Tests verify:
- TCP/TLS connectivity on port 5061
- SIP OPTIONS response (server is alive)
"""

import socket
import ssl

import pytest

from conftest import SIP_HOST, SIP_PORT, XMPP_DOMAIN


class TestSipConnectivity:
    """Verify basic SIP server connectivity."""

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

    def test_sip_options(self) -> None:
        """Send SIP OPTIONS and expect a valid response."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw_sock = socket.create_connection((SIP_HOST, SIP_PORT), timeout=5)
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=SIP_HOST)
            try:
                options_req = (
                    f"OPTIONS sip:{XMPP_DOMAIN} SIP/2.0\r\n"
                    f"Via: SIP/2.0/TLS {SIP_HOST}:5061;branch=z9hG4bK-test-001\r\n"
                    f"Max-Forwards: 70\r\n"
                    f"From: <sip:test@{XMPP_DOMAIN}>;tag=test001\r\n"
                    f"To: <sip:test@{XMPP_DOMAIN}>\r\n"
                    f"Call-ID: test-options-001@{SIP_HOST}\r\n"
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
