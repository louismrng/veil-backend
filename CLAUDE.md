# Backend Module — CLAUDE.md

## Build / Run

- `docker compose up` from `backend/` — starts PostgreSQL, Ejabberd, RTPEngine, Kamailio, coturn, and API
- API hot-reloads (uvicorn with reload). Runs on port **8443 (plain HTTP, not HTTPS)**.
- Tests: `pytest` from `backend/tests/`
- Python 3.12, dependencies pinned in `api/requirements.txt`

## Architecture

```
Docker Compose
├── db (PostgreSQL 16) — port 5432
├── ejabberd (XMPP) — ports 5222, 5223, 5280, 5443
├── rtpengine (media relay) — ports 20000-20100/UDP (DTLS-SRTP mandatory)
├── kamailio (SIP proxy) — ports 5060/UDP, 5061/TLS, 8089/WSS (mapped from 8443 internal)
├── coturn (TURN/STUN) — ports 3478, 5349
└── api (FastAPI) — port 8443
    ├── Ejabberd admin API calls (register, check_password)
    ├── Push notification services (APNs, FCM)
    └── PostgreSQL via asyncpg pool (2-10 connections)
```

## Key Files

| Component | Path | Status |
|-----------|------|--------|
| Compose config | `docker-compose.yml` | Implemented (6 active services) |
| API entry | `api/main.py` | Implemented (~39 LOC, lifespan for DB pool) |
| Account routes | `api/routes/account.py` | Implemented (register, login, delete) |
| Push routes | `api/routes/push.py` | Implemented (151 LOC — register, deregister, send push for calls/messages) |
| Server info route | `api/routes/server.py` | Implemented |
| TURN credentials | `api/routes/turn.py` | Implemented (HMAC-SHA1, 24h TTL) |
| JWT auth | `api/auth.py` | Implemented (HS256, 24h expiry) |
| DB pool | `api/db.py` | Implemented (asyncpg, min=2 max=10) |
| Pydantic models | `api/models.py` | Implemented (all request/response types) |
| DB schema | `sql/init.sql` | `push_registrations` + `subscriber` tables |
| Ejabberd config | `ejabberd/ejabberd.yml` | Fully configured |
| Push services | `api/services/apns.py`, `api/services/fcm.py` | Implemented (APNs + FCM) |
| Groups route | `api/routes/groups.py` | Implemented (277 LOC) |
| Kamailio config | `kamailio/kamailio.cfg` | Implemented (TLS, WebSocket, RTPEngine, auth_db) |
| Kamailio Dockerfile | `kamailio/Dockerfile` | Implemented (Kamailio 5.7) |
| RTPEngine config | docker-compose env | Active (DTLS-SRTP mandatory) |
| coturn config | `coturn/turnserver.conf` | Active |
| Requirements | `api/requirements.txt` | fastapi, uvicorn, asyncpg, pydantic, PyJWT, httpx |

## API Routes

All under `/api/v1/`:

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/account/register` | POST | None | Register user (creates in Ejabberd + returns JWT) |
| `/account/login` | POST | None | Login (validates via Ejabberd + returns JWT) |
| `/account` | DELETE | Bearer | Delete account |
| `/push/register` | POST | Bearer | Register push token |
| `/push/register` | DELETE | Bearer | Deregister push token |
| `/server/info` | GET | None | Returns XMPP/SIP connection details |
| `/turn/credentials` | GET | Bearer | Time-limited TURN credentials |
| `/groups/create` | POST | Bearer | Create MUC room |
| `/groups/{jid}/members` | POST/DELETE | Bearer | Add/remove members |

**Auth pattern:** JWT Bearer token. Protected endpoints use `Depends(verify_token)` which returns the caller's JID. Endpoints validate `request.jid == caller_jid`.

## Ejabberd Admin API

API calls Ejabberd at `https://ejabberd:5443/api/` (internal Docker network):
- `POST /register` — `{"user", "host", "password"}`
- `POST /check_password` — `{"user", "host", "password"}` → returns `"0"` (success) or `"1"` (failure)
- SSL verification disabled (`verify=False`) for internal Docker communication

## Ejabberd Configuration

Key modules in `ejabberd/ejabberd.yml`:
- **mod_mam** — Message archiving (SQL-backed)
- **mod_muc** — Group chat (members-only default, persistent rooms)
- **mod_http_upload** — File upload (100MB max, CORS enabled)
- **mod_push** — Push notifications (`include_body: false` — no plaintext)
- **mod_pubsub** — OMEMO bundles (`urn:xmpp:omemo:2:bundles:*`) and device lists (`urn:xmpp:omemo:2:devices`)
- **mod_roster** — Contact list (SQL-backed)

Auth: SQL via PostgreSQL with SCRAM-SHA256.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_PASSWORD` | (from .env) | PostgreSQL password |
| `JWT_SECRET` | (from .env) | HS256 signing key |
| `XMPP_DOMAIN` | `example.com` | JID domain suffix |
| `XMPP_HOST` | `localhost` | XMPP hostname for clients |
| `XMPP_WS_URL` | `ws://localhost:5280/ws` | WebSocket endpoint for clients |
| `TURN_SECRET` | (from .env) | HMAC-SHA1 secret for TURN credentials |
| `SERVER_VERSION` | `1.0.0` | Returned in /server/info |
| `MIN_CLIENT_VERSION` | `1.0.0` | Minimum client version |

## Database

**Ejabberd-managed tables:** users, roster, MAM archives, MUC, etc. — do NOT create these in `init.sql`.

**App-managed tables** (in `sql/init.sql`):
- `push_registrations` — jid, device_uuid (PK), platform, push_token, app_id
- `subscriber` — Kamailio SIP auth (INSERT on register, UPSERT on login)

## Gotchas

- **Domain defaults to `example.com`** everywhere — set `XMPP_DOMAIN` env var to change.
- **API is plain HTTP** on port 8443 (not HTTPS despite the port number).
- **Kamailio SIP ports:** 5060/UDP, 5061/TLS, 8089/WSS (mapped from 8443 internal).
- **RTPEngine** uses port range 20000-20100 for media relay.
- **Ejabberd manages its own user table** — don't try to INSERT users directly into PostgreSQL.
- **`.env` file** contains placeholder secrets for dev. Never commit real secrets.
