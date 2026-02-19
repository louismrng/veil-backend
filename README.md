# Veil Backend

Backend infrastructure for the Veil secure messaging and VoIP platform. Provides XMPP messaging, SIP calling, push notifications, media relaying, and TURN/STUN connectivity — all orchestrated via Docker Compose.

## Architecture

```
Docker Compose
├── db          — PostgreSQL 16 (user data, SIP auth, push tokens)
├── ejabberd    — XMPP server (messaging, group chat, file uploads, OMEMO)
├── kamailio    — SIP proxy (voice/video calls, WebSocket, TLS)
├── rtpengine   — Media relay (DTLS-SRTP, WebRTC bridging)
├── coturn      — TURN/STUN relay (NAT traversal for calls)
└── api         — FastAPI REST API (accounts, push, groups, TURN credentials)
```

The **API** service is the main integration point. It handles user registration (syncing credentials to both Ejabberd and Kamailio), JWT authentication, push notification dispatch, group chat management via Ejabberd's admin API, and time-limited TURN credential generation.

**Kamailio** handles SIP call routing and triggers push notifications for offline users by calling back into the API. **RTPEngine** relays media with mandatory DTLS-SRTP encryption. **coturn** provides TURN/STUN for NAT traversal.

## Prerequisites

- Docker and Docker Compose
- A server with a public IP (for SIP/TURN to work correctly)
- (Optional) A domain name with DNS pointing to your server
- (Optional) APNs key (`.p8`) and/or Firebase service account JSON for push notifications

## Getting Started

### 1. Clone and configure

```bash
cp .env.example .env
```

Edit `.env` and fill in your values. At minimum, generate the three secrets:

```bash
# Generate secrets
openssl rand -hex 32   # DB_PASSWORD
openssl rand -hex 64   # JWT_SECRET
openssl rand -hex 32   # TURN_SECRET
```

Set `SERVER_IP` to your server's public IP and `XMPP_DOMAIN` to your domain.

### 2. Set up TLS certificates

```bash
bash scripts/setup-certs.sh
```

This attempts Let's Encrypt via certbot if your domain resolves to the server. Falls back to self-signed certificates otherwise. Certificates are placed in `certs/`.

### 3. Start services

```bash
docker compose up -d
```

All six services start up. The API is available on port **8443** (plain HTTP).

### 4. Automated deployment (alternative)

For a fresh VPS, `scripts/deploy.sh` handles the full setup — generates `.env`, sets up certificates, builds images, starts services, and runs health checks.

```bash
bash scripts/deploy.sh
```

## Environment Variables

See `.env.example` for the full list with descriptions.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_PASSWORD` | *(required)* | PostgreSQL password |
| `JWT_SECRET` | *(required)* | JWT signing key (HS256) |
| `TURN_SECRET` | *(required)* | TURN credential HMAC secret |
| `SERVER_IP` | `127.0.0.1` | Public IP for SIP, RTP, TURN |
| `XMPP_DOMAIN` | `example.com` | Domain for JIDs (`user@domain`) |
| `SIP_DOMAIN` | `example.com` | SIP domain |
| `TURN_DOMAIN` | `example.com` | TURN server domain |
| `HTTP_UPLOAD_DOMAIN` | `upload.example.com` | File upload subdomain |
| `XMPP_HOST` | `example.com` | XMPP hostname for client connections |
| `XMPP_WS_URL` | `wss://example.com:5280/ws` | XMPP WebSocket URL |
| `APNS_KEY_PATH` | `/etc/veil/apns_key.p8` | Path to APNs `.p8` key file |
| `APNS_KEY_ID` | *(empty)* | APNs key identifier |
| `APNS_TEAM_ID` | *(empty)* | Apple Developer Team ID |
| `APNS_BUNDLE_ID` | `com.example.veil` | iOS app bundle ID |
| `FCM_SERVICE_ACCOUNT_PATH` | `/etc/veil/fcm_service_account.json` | Firebase service account JSON |
| `SERVER_VERSION` | `1.0.0` | Returned in `/server/info` |
| `MIN_CLIENT_VERSION` | `1.0.0` | Minimum supported client version |

## API

All endpoints are under `/api/v1/`. The API runs on port **8443** (plain HTTP, not HTTPS despite the port number).

### Authentication

Protected endpoints require a JWT Bearer token in the `Authorization` header. Tokens are issued on register/login and expire after 24 hours.

### Endpoints

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/account/register` | POST | No | Create account (Ejabberd + SIP subscriber), returns JWT |
| `/account/login` | POST | No | Validate credentials, returns JWT |
| `/account` | DELETE | Yes | Delete account and all associated data |
| `/push/register` | POST | Yes | Register a device push token (APNs/FCM) |
| `/push/register` | DELETE | Yes | Deregister a device push token |
| `/push/call-notify` | POST | No* | Webhook from Kamailio to send push for incoming calls |
| `/server/info` | GET | No | XMPP/SIP/TURN connection details for client bootstrap |
| `/turn/credentials` | GET | Yes | Time-limited TURN credentials (HMAC-SHA1, 24h TTL) |
| `/groups` | POST | Yes | Create a group chat (MUC room) |
| `/groups` | GET | Yes | List user's group chats |
| `/groups/{group_id}/members` | GET | Yes | List group members |
| `/groups/{group_id}/members` | POST | Yes | Add a member to a group |
| `/groups/{group_id}/members/{jid}` | DELETE | Yes | Remove a member from a group |

*\* `/push/call-notify` is an internal webhook called by Kamailio, not intended for external clients.*

## Services

### PostgreSQL (db)

Port **5432**. Stores app-managed tables (`push_registrations`, `subscriber`, `location`) and Ejabberd-managed tables (users, roster, MAM, MUC). Schema initialized from `sql/init.sql`.

### Ejabberd (XMPP)

Ports **5222** (STARTTLS), **5223** (Direct TLS), **5280** (WebSocket), **5443** (HTTPS — admin API, file uploads).

Key modules: `mod_mam` (message archiving), `mod_muc` (group chat), `mod_http_upload` (file transfer, 100MB max), `mod_push` (push notifications, no plaintext bodies), `mod_pubsub` (OMEMO key distribution), `mod_roster` (contacts).

Auth: SQL-backed SCRAM-SHA256.

### Kamailio (SIP)

Ports **5060/UDP**, **5061/TLS**, **8089/WSS**.

Handles SIP registration, call routing, and NAT traversal. Integrates with RTPEngine for media relay and triggers push notifications for offline callees via the API webhook. Includes DDoS protection (pike module) and IP ban lists.

### RTPEngine (Media)

Ports **20000–20100/UDP**.

Relays RTP media between call participants. DTLS-SRTP is mandatory — media is always encrypted. Bridges between WebRTC (WebSocket) and native SIP clients.

### coturn (TURN/STUN)

Ports **3478/UDP** (STUN/TURN), **5349/TCP** (TURNS).

Provides NAT traversal for clients behind firewalls. Uses shared-secret authentication with time-limited credentials generated by the API. Runs in host network mode. Private IP ranges are denied to prevent relay abuse.

## Network Ports

| Port | Protocol | Service | Purpose |
|------|----------|---------|---------|
| 5060 | UDP | Kamailio | SIP signaling |
| 5061 | TCP/TLS | Kamailio | SIP over TLS |
| 5222 | TCP | Ejabberd | XMPP (STARTTLS) |
| 5223 | TCP | Ejabberd | XMPP (Direct TLS) |
| 5280 | TCP | Ejabberd | XMPP WebSocket |
| 5349 | TCP | coturn | TURNS (TLS) |
| 5443 | TCP | Ejabberd | HTTPS (admin API, file uploads) |
| 3478 | UDP | coturn | STUN/TURN |
| 8089 | TCP | Kamailio | SIP over WebSocket (WSS) |
| 8443 | TCP | API | REST API (HTTP) |
| 20000–20100 | UDP | RTPEngine | RTP media relay |

## Database Schema

**App-managed** (in `sql/init.sql`):

- **`push_registrations`** — Device push tokens. PK: `(jid, device_uuid)`. Columns: platform, push_token, app_id, registered_at.
- **`subscriber`** — Kamailio SIP digest auth. PK: `(username, domain)`. Columns: password, ha1, ha1b, created_at. Populated on user registration/login.
- **`location`** — Kamailio user location (online SIP registrations). Standard Kamailio schema.
- **`version`** — Kamailio schema versioning.

**Ejabberd-managed** (do not modify directly):

- `users`, `roster_*`, `mam_*`, `muc_*`, `offline_message`, `vcard`, etc.

## Testing

Tests are in `tests/` and use pytest:

```bash
pytest tests/
```

Test files cover REST API endpoints, SIP connectivity, SIP call flows, TURN credentials, XMPP connections, push delivery, and MUC operations. Connection defaults (localhost, standard ports) can be overridden with `TEST_*` environment variables — see `tests/conftest.py`.

## Project Structure

```
.
├── api/
│   ├── main.py              # FastAPI app with lifespan (DB pool init/cleanup)
│   ├── auth.py              # JWT creation and verification (HS256, 24h expiry)
│   ├── db.py                # asyncpg connection pool (min=2, max=10)
│   ├── models.py            # Pydantic request/response schemas
│   ├── Dockerfile
│   ├── requirements.txt     # Python 3.12 dependencies
│   ├── routes/
│   │   ├── account.py       # Register, login, delete
│   │   ├── push.py          # Push token management, call notification webhook
│   │   ├── server_info.py   # Server discovery endpoint
│   │   ├── turn.py          # TURN credential generation
│   │   └── groups.py        # MUC room CRUD
│   └── services/
│       ├── apns.py          # APNs VoIP push (HTTP/2)
│       └── fcm.py           # FCM data-only push (Firebase Admin SDK)
├── ejabberd/
│   ├── Dockerfile
│   ├── ejabberd.yml         # XMPP server configuration
│   └── entrypoint.sh        # Config template substitution
├── kamailio/
│   ├── Dockerfile           # Kamailio 5.7 on Debian 12
│   ├── kamailio.cfg         # SIP routing, auth, RTPEngine, push webhook
│   ├── tls.cfg              # TLS settings
│   └── entrypoint.sh
├── coturn/
│   ├── turnserver.conf      # TURN/STUN configuration
│   └── entrypoint.sh
├── rtpengine/
│   ├── rtpengine.conf       # Media relay configuration
│   └── entrypoint.sh
├── sql/
│   └── init.sql             # Database schema
├── scripts/
│   ├── setup-certs.sh       # TLS certificate generation
│   └── deploy.sh            # VPS deployment automation
├── tests/                   # pytest integration tests
├── certs/                   # TLS certificates (gitignored)
├── docker-compose.yml
├── .env.example
└── CLAUDE.md
```

## Security Notes

- **Encryption in transit**: XMPP supports STARTTLS and Direct TLS. SIP uses TLS and WSS. RTPEngine enforces DTLS-SRTP for all media. TURNS available on port 5349.
- **Push payload privacy**: Push notifications contain only metadata (caller name, call ID, call type) — no message content is ever sent through push services.
- **OMEMO support**: Ejabberd is configured with `mod_pubsub` nodes for OMEMO key bundles and device lists, enabling end-to-end encryption at the client level.
- **SIP auth**: Digest authentication with MD5 ha1 hashes, credentials synced from the API on registration.
- **TURN relay hardening**: Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, loopback) are denied as relay targets to prevent abuse.
- **Rate limiting**: Kamailio includes pike-based rate limiting and IP ban tables for DDoS mitigation.
- **Secrets**: All secrets are loaded from environment variables. The `.env` file is gitignored. Never commit real credentials.
