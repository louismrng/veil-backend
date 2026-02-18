"""Server discovery endpoint (INTERFACES.md §4.4) — unauthenticated."""

import os

from fastapi import APIRouter

from models import ServerInfoResponse

router = APIRouter(prefix="/api/v1/server", tags=["server"])


@router.get("/info", response_model=ServerInfoResponse)
async def server_info() -> ServerInfoResponse:
    """Return server endpoints for client bootstrap.

    This is the first endpoint clients call on startup to discover
    XMPP, SIP, TURN, and upload service locations.
    """
    xmpp_domain = os.environ.get("XMPP_DOMAIN", "example.com")
    xmpp_host = os.environ.get("XMPP_HOST", f"xmpp.{xmpp_domain}")
    xmpp_ws_url = os.environ.get("XMPP_WS_URL", f"ws://{xmpp_host}:5280/ws")
    sip_domain = os.environ.get("SIP_DOMAIN", "sip.example.com")
    turn_domain = os.environ.get("TURN_DOMAIN", "turn.example.com")
    upload_domain = os.environ.get("HTTP_UPLOAD_DOMAIN", "upload.example.com")
    server_version = os.environ.get("SERVER_VERSION", "1.0.0")
    min_client_version = os.environ.get("MIN_CLIENT_VERSION", "1.0.0")

    return ServerInfoResponse(
        xmpp_domain=xmpp_domain,
        xmpp_host=xmpp_host,
        xmpp_port_tls=5223,
        xmpp_port_starttls=5222,
        xmpp_ws_url=xmpp_ws_url,
        sip_domain=sip_domain,
        sip_port_tls=5061,
        turn_server=f"{turn_domain}:3478",
        turn_server_tls=f"{turn_domain}:5349",
        http_upload_host=upload_domain,
        server_version=server_version,
        min_client_version=min_client_version,
    )
