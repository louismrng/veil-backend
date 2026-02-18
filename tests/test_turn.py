"""Integration tests for TURN/STUN server (coturn).

Tests verify:
- UDP connectivity on port 3478
- STUN Binding request receives a valid Binding response
"""

import socket
import struct

import pytest

from conftest import TURN_HOST, TURN_PORT


def _build_stun_binding_request() -> bytes:
    """Build a minimal STUN Binding Request (RFC 5389).

    Format:
      - Message Type: 0x0001 (Binding Request)
      - Message Length: 0x0000 (no attributes)
      - Magic Cookie: 0x2112A442
      - Transaction ID: 12 random bytes
    """
    msg_type = 0x0001
    msg_length = 0
    magic_cookie = 0x2112A442
    # Deterministic transaction ID for testing
    transaction_id = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"
    return struct.pack(
        "!HHI", msg_type, msg_length, magic_cookie
    ) + transaction_id


class TestTurnConnectivity:
    """Verify STUN/TURN server is reachable and responds."""

    def test_stun_binding_request(self) -> None:
        """Send a STUN Binding Request and verify a Binding Success Response."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        try:
            request = _build_stun_binding_request()
            sock.sendto(request, (TURN_HOST, TURN_PORT))
            data, _ = sock.recvfrom(1024)

            # Verify STUN response header
            assert len(data) >= 20, "STUN response too short"

            msg_type, msg_length, magic_cookie = struct.unpack("!HHI", data[:8])
            # 0x0101 = Binding Success Response
            assert msg_type == 0x0101, f"Expected Binding Success (0x0101), got 0x{msg_type:04x}"
            assert magic_cookie == 0x2112A442, "Invalid magic cookie"

            # Transaction ID should match
            assert data[8:20] == b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"
        finally:
            sock.close()

    def test_stun_udp_port_reachable(self) -> None:
        """Port 3478/UDP is open and responds."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        try:
            request = _build_stun_binding_request()
            sock.sendto(request, (TURN_HOST, TURN_PORT))
            data, addr = sock.recvfrom(1024)
            assert len(data) > 0, "No response from STUN server"
        finally:
            sock.close()
