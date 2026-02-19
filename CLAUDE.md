# Veil Backend — CLAUDE.md

## Build / Run

- `docker compose up` — starts PostgreSQL, Ejabberd, RTPEngine, Kamailio, coturn, and API
- API hot-reloads (uvicorn with reload). Runs on port **8443 (plain HTTP, not HTTPS)**.
- Tests: `pytest tests/`
- Python 3.12, dependencies pinned in `api/requirements.txt`
- Automated deployment: `bash scripts/deploy.sh` (generates secrets, certs, builds, starts, health-checks)
- Certificate setup: `bash scripts/setup-certs.sh` (Let's Encrypt or self-signed fallback)

## Architecture

```
Docker Compose
├── db (PostgreSQL 16) — port 5432
├── ejabberd (XMPP) — ports 5222, 5223, 5280, 5443
├── rtpengine (media relay) — ports 20000-20100/UDP (DTLS-SRTP mandatory)
├── kamailio (SIP proxy) — ports 5060/UDP, 5061/TLS, 8089/WSS
├── coturn (TURN/STUN) — ports 3478, 5349 (host network mode)
└── api (FastAPI) — port 8443
    ├── Ejabberd admin API calls (register, check_password)
    ├── Push notification services (APNs, FCM)
    └── PostgreSQL via asyncpg pool (2-10 connections)
```

## Key Files

| Component | Path | Notes |
|-----------|------|-------|
| Compose config | `docker-compose.yml` | 6 services |
| API entry | `api/main.py` | FastAPI app, lifespan for DB pool init/cleanup |
| Account routes | `api/routes/account.py` | Register, login, delete |
| Push routes | `api/routes/push.py` | Token register/deregister, call-notify webhook |
| Server info route | `api/routes/server_info.py` | XMPP/SIP/TURN discovery |
| TURN credentials | `api/routes/turn.py` | HMAC-SHA1, 24h TTL |
| Groups routes | `api/routes/groups.py` | MUC create, list, member management |
| JWT auth | `api/auth.py` | HS256, 24h expiry |
| DB pool | `api/db.py` | asyncpg, min=2 max=10 |
| Pydantic models | `api/models.py` | All request/response types |
| APNs push | `api/services/apns.py` | VoIP push via HTTP/2 (aioapns) |
| FCM push | `api/services/fcm.py` | Data-only push via Firebase Admin SDK |
| DB schema | `sql/init.sql` | `push_registrations`, `subscriber`, `location`, `version` tables |
| Ejabberd config | `ejabberd/ejabberd.yml` | Template with `__PLACEHOLDER__` vars |
| Kamailio config | `kamailio/kamailio.cfg` | SIP routing, RTPEngine, push webhook |
| Kamailio TLS | `kamailio/tls.cfg` | TLS cipher/cert settings |
| coturn config | `coturn/turnserver.conf` | TURN/STUN with shared secret auth |
| RTPEngine config | `rtpengine/rtpengine.conf` | DTLS-SRTP, port range, timeouts |
| Cert setup | `scripts/setup-certs.sh` | Let's Encrypt or self-signed |
| Deploy script | `scripts/deploy.sh` | Full VPS deployment automation |
| Requirements | `api/requirements.txt` | fastapi, uvicorn, asyncpg, pydantic, PyJWT, httpx, aioapns, firebase-admin |

## API Routes

All under `/api/v1/`:

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/account/register` | POST | No | Register user (creates in Ejabberd + SIP subscriber, returns JWT) |
| `/account/login` | POST | No | Login (validates via Ejabberd, upserts SIP subscriber, returns JWT) |
| `/account` | DELETE | Bearer | Delete account and all associated data |
| `/push/register` | POST | Bearer | Register device push token |
| `/push/register` | DELETE | Bearer | Deregister device push token |
| `/push/call-notify` | POST | No* | Webhook: Kamailio sends push for offline callee |
| `/server/info` | GET | No | XMPP/SIP/TURN connection details for client bootstrap |
| `/turn/credentials` | GET | Bearer | Time-limited TURN credentials (HMAC-SHA1, 24h TTL) |
| `/groups` | POST | Bearer | Create MUC room |
| `/groups` | GET | Bearer | List user's groups |
| `/groups/{group_id}/members` | GET | Bearer | List group members |
| `/groups/{group_id}/members` | POST | Bearer | Add member to group |
| `/groups/{group_id}/members/{jid}` | DELETE | Bearer | Remove member from group |

*\* Internal webhook from Kamailio, not for external clients.*

**Auth pattern:** JWT Bearer token (HS256, 24h expiry). Protected endpoints use `Depends(verify_token)` which returns the caller's JID. Route handlers validate `request.jid == caller_jid`.

## Ejabberd Admin API

API calls Ejabberd at `https://ejabberd:5443/api/` (internal Docker network):
- `POST /register` — `{"user", "host", "password"}`
- `POST /check_password` — `{"user", "host", "password"}` → returns `"0"` (success) or `"1"` (failure)
- `POST /create_room_with_opts`, `POST /set_room_affiliation`, etc. for MUC management
- SSL verification disabled (`verify=False`) for internal Docker communication

## Ejabberd Configuration

Key modules in `ejabberd/ejabberd.yml`:
- **mod_mam** — Message archiving (SQL-backed)
- **mod_muc** — Group chat (members-only default, persistent rooms)
- **mod_http_upload** — File upload (100MB max, CORS enabled)
- **mod_push** — Push notifications (`include_body: false` — no plaintext in push payloads)
- **mod_pubsub** — OMEMO bundles (`urn:xmpp:omemo:2:bundles:*`) and device lists (`urn:xmpp:omemo:2:devices`)
- **mod_roster** — Contact list (SQL-backed)
- **mod_offline** — Offline message storage

Auth: SQL via PostgreSQL with SCRAM-SHA256.

Config uses `__PLACEHOLDER__` template vars substituted by `ejabberd/entrypoint.sh` at container startup.

## Kamailio

SIP proxy with call routing, WebSocket support, and push notification integration.

- **Auth**: Digest auth against `subscriber` table (ha1 column)
- **RTPEngine**: Bridges WebRTC ↔ native SIP. Forces relay + DTLS-SRTP for WebSocket clients.
- **Push flow**: INVITE for offline user → HTTP POST to `http://api:8443/api/v1/push/call-notify` → returns 480 Temporarily Unavailable
- **DDoS protection**: pike module with IP ban htable

Config uses `__PLACEHOLDER__` template vars substituted by `kamailio/entrypoint.sh`.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_PASSWORD` | *(required)* | PostgreSQL password |
| `JWT_SECRET` | *(required)* | JWT signing key (HS256) |
| `TURN_SECRET` | *(required)* | TURN credential HMAC secret |
| `SERVER_IP` | `127.0.0.1` | Public IP for SIP, RTP, TURN |
| `XMPP_DOMAIN` | `example.com` | JID domain suffix |
| `SIP_DOMAIN` | `example.com` | SIP domain |
| `TURN_DOMAIN` | `example.com` | TURN server domain |
| `HTTP_UPLOAD_DOMAIN` | `upload.example.com` | File upload subdomain |
| `XMPP_HOST` | `example.com` | XMPP hostname for clients |
| `XMPP_WS_URL` | `wss://example.com:5280/ws` | WebSocket endpoint for clients |
| `APNS_KEY_PATH` | `/etc/veil/apns_key.p8` | APNs key file path |
| `APNS_KEY_ID` | *(empty)* | APNs key ID |
| `APNS_TEAM_ID` | *(empty)* | Apple Developer Team ID |
| `APNS_BUNDLE_ID` | `com.example.veil` | iOS bundle ID |
| `FCM_SERVICE_ACCOUNT_PATH` | `/etc/veil/fcm_service_account.json` | Firebase service account JSON |
| `SERVER_VERSION` | `1.0.0` | Returned in /server/info |
| `MIN_CLIENT_VERSION` | `1.0.0` | Minimum client version |

## Database

**Ejabberd-managed tables:** users, roster, MAM archives, MUC, offline messages, etc. — do NOT create or modify these in `init.sql`. Ejabberd manages its own schema.

**App-managed tables** (in `sql/init.sql`):
- `push_registrations` — jid, device_uuid (PK), platform (ios/android), push_token, app_id
- `subscriber` — Kamailio SIP digest auth. PK: (username, domain). Contains ha1/ha1b MD5 hashes. INSERT on register, UPSERT on login.
- `location` — Kamailio user registrations (online SIP clients). Standard Kamailio db_mode=2 schema.
- `version` — Kamailio schema versioning table.

A `kamailio` database role is created with read access to `subscriber` and read/write to `location`.

## Testing

Tests in `tests/` using pytest:
- `test_push_api.py` — REST API push endpoints, auth, server info, TURN, account deletion
- `test_sip_register.py` — SIP TLS connectivity, OPTIONS
- `test_sip_calls.py` — SIP call flows
- `test_turn.py` — TURN credential generation
- `test_xmpp_connect.py` — XMPP client connections
- `test_push_delivery.py` — APNs/FCM delivery
- `test_muc.py` — MUC room operations

Connection defaults (localhost, standard ports) are overridable via `TEST_*` env vars in `tests/conftest.py`.

## Gotchas

- **Domain defaults to `example.com`** everywhere — set `XMPP_DOMAIN` in `.env` to change.
- **API is plain HTTP** on port 8443 (not HTTPS despite the port number).
- **Kamailio SIP ports:** 5060/UDP, 5061/TLS, 8089/WSS (mapped from 8443 internal).
- **RTPEngine** uses port range 20000-20100/UDP for media relay.
- **Ejabberd manages its own user table** — don't INSERT users directly into PostgreSQL. Use the Ejabberd admin API.
- **SIP subscriber ha1 format:** `MD5(username:domain:password)` — computed in `account.py` on register/login.
- **coturn runs in host network mode** — it binds directly to host interfaces, no Docker port mapping.
- **Config templating** — Ejabberd, Kamailio, and coturn configs use `__PLACEHOLDER__` patterns. Entrypoint scripts run `envsubst` at container startup. Edit the template files, not the runtime configs.
- **`.env` file** contains secrets — it is gitignored. Copy `.env.example` to get started. Never commit real secrets.
- **Push notifications are optional** — APNs/FCM services initialize lazily and return `None` if credentials aren't configured.
