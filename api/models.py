"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field


# ---------- Push registration (INTERFACES.md §4.1 / §4.2) ----------

class PushRegisterRequest(BaseModel):
    jid: str = Field(..., examples=["alice@example.com"])
    device_id: str = Field(..., examples=["550e8400-e29b-41d4-a716-446655440000"])
    platform: str = Field(..., pattern="^(ios|android)$", examples=["ios"])
    push_token: str
    app_id: str = Field(..., examples=["com.example.veil"])


class PushRegisterResponse(BaseModel):
    status: str = "registered"


class PushDeregisterRequest(BaseModel):
    jid: str = Field(..., examples=["alice@example.com"])
    device_id: str = Field(..., examples=["550e8400-e29b-41d4-a716-446655440000"])


# ---------- Account deletion (INTERFACES.md §4.3) ----------

class AccountDeleteRequest(BaseModel):
    jid: str = Field(..., examples=["alice@example.com"])
    password: str


# ---------- Server info (INTERFACES.md §4.4) ----------

class ServerInfoResponse(BaseModel):
    xmpp_domain: str
    xmpp_host: str
    xmpp_port_tls: int
    xmpp_port_starttls: int
    xmpp_ws_url: str
    sip_domain: str
    sip_port_tls: int
    turn_server: str
    turn_server_tls: str
    http_upload_host: str
    server_version: str
    min_client_version: str


# ---------- Account registration ----------

class AccountRegisterRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
        examples=["alice"],
    )
    password: str = Field(..., min_length=8, max_length=128)


class AccountRegisterResponse(BaseModel):
    jid: str = Field(..., examples=["alice@example.com"])
    status: str = "registered"
    token: str | None = Field(None, examples=["eyJhbGciOiJIUzI1NiIs..."])


class AccountLoginRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
        examples=["alice"],
    )
    password: str = Field(..., min_length=8, max_length=128)


class AccountLoginResponse(BaseModel):
    jid: str = Field(..., examples=["alice@example.com"])
    token: str = Field(..., examples=["eyJhbGciOiJIUzI1NiIs..."])


# ---------- TURN credentials (MODULE_01_BACKEND.md §3.3) ----------

class TurnCredentialsResponse(BaseModel):
    username: str
    password: str
    ttl: int
    uris: list[str]


# ---------- Group management ----------

class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["Project Team"])
    member_jids: list[str] = Field(default_factory=list, examples=[["alice@example.com"]])


class GroupCreateResponse(BaseModel):
    group_id: str
    jid: str
    name: str


class GroupInfo(BaseModel):
    group_id: str
    jid: str
    name: str


class GroupListResponse(BaseModel):
    groups: list[GroupInfo]


class GroupMember(BaseModel):
    jid: str
    affiliation: str


class GroupMembersResponse(BaseModel):
    members: list[GroupMember]


class GroupAddMemberRequest(BaseModel):
    jid: str = Field(..., examples=["bob@example.com"])


# ---------- Call push notification (Kamailio webhook) ----------

class CallNotifyRequest(BaseModel):
    callee_username: str = Field(..., examples=["bob"])
    caller_username: str = Field(..., examples=["alice"])
    caller_display_name: str = Field("", examples=["Alice"])
    call_id: str = Field(..., examples=["abc123@kamailio"])
    call_type: str = Field("audio", pattern="^(audio|video)$", examples=["audio"])
