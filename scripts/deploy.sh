#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

echo "============================================"
echo "  Veil Backend — VPS Deployment"
echo "============================================"
echo ""

# ── Prerequisites ──────────────────────────────────────────
echo "Checking prerequisites..."

for cmd in docker git openssl curl; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not installed."
        exit 1
    fi
done

# Check Docker Compose (v2 plugin or standalone)
if docker compose version &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "ERROR: Docker Compose is required but not installed."
    exit 1
fi

echo "All prerequisites met."
echo ""

# ── Environment Setup ─────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    echo "Found existing .env file."
    read -rp "Overwrite with new configuration? [y/N] " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Keeping existing .env"
    else
        rm "$ENV_FILE"
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Configuring environment..."

    # Domain
    read -rp "Enter your domain (e.g., chat.example.com): " DOMAIN
    DOMAIN="${DOMAIN:-example.com}"

    # Server IP — try IPv6 first, then IPv4
    DETECTED_IP=$(curl -s -6 --connect-timeout 5 ifconfig.me 2>/dev/null || \
                  curl -s -4 --connect-timeout 5 ifconfig.me 2>/dev/null || echo "")
    if [ -n "$DETECTED_IP" ]; then
        read -rp "Server public IP [$DETECTED_IP]: " SERVER_IP
        SERVER_IP="${SERVER_IP:-$DETECTED_IP}"
    else
        read -rp "Server public IP: " SERVER_IP
    fi

    # Generate secrets
    DB_PASSWORD=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 64)
    TURN_SECRET=$(openssl rand -hex 32)

    cat > "$ENV_FILE" <<EOF
# Veil Backend — Generated $(date -u +%Y-%m-%dT%H:%M:%SZ)

# Secrets
DB_PASSWORD=$DB_PASSWORD
JWT_SECRET=$JWT_SECRET
TURN_SECRET=$TURN_SECRET

# Network
SERVER_IP=$SERVER_IP
XMPP_DOMAIN=$DOMAIN
SIP_DOMAIN=$DOMAIN
TURN_DOMAIN=$DOMAIN
HTTP_UPLOAD_DOMAIN=upload.$DOMAIN
XMPP_HOST=$DOMAIN
XMPP_WS_URL=wss://$DOMAIN:5280/ws

# Versioning
SERVER_VERSION=1.0.0
MIN_CLIENT_VERSION=1.0.0
EOF

    echo "Generated .env with random secrets."
fi

echo ""

# ── TLS Certificates ──────────────────────────────────────
echo "Setting up TLS certificates..."
bash "$SCRIPT_DIR/setup-certs.sh"
echo ""

# ── Build and Start ───────────────────────────────────────
echo "Building and starting services..."
cd "$PROJECT_DIR"
$COMPOSE build
$COMPOSE up -d

echo ""
echo "Waiting for services to start..."
sleep 10

# ── Health Checks ─────────────────────────────────────────
echo "Checking service health..."
HEALTHY=true

# Check PostgreSQL
if $COMPOSE exec -T db pg_isready -U ejabberd &>/dev/null; then
    echo "  OK  PostgreSQL"
else
    echo "  ERR PostgreSQL"
    HEALTHY=false
fi

# Check API
if curl -sf "http://localhost:8443/api/v1/server/info" &>/dev/null; then
    echo "  OK  API"
else
    echo "  ERR API (may still be starting)"
    HEALTHY=false
fi

# Check Ejabberd
if $COMPOSE exec -T ejabberd ejabberdctl status &>/dev/null; then
    echo "  OK  Ejabberd"
else
    echo "  ERR Ejabberd (may still be starting)"
    HEALTHY=false
fi

echo ""

# Load env for display
set -a
. "$ENV_FILE"
set +a

# Format IP for display (bracket IPv6)
if echo "$SERVER_IP" | grep -q ':'; then
    DISPLAY_IP="[$SERVER_IP]"
else
    DISPLAY_IP="$SERVER_IP"
fi

echo "============================================"
echo "  Deployment Complete"
echo "============================================"
echo ""
echo "Services:"
echo "  API:      http://${XMPP_DOMAIN}:8443/api/v1/server/info"
echo "  XMPP:     ${XMPP_DOMAIN}:5222 (STARTTLS)"
echo "  XMPP TLS: ${XMPP_DOMAIN}:5223"
echo "  XMPP WS:  ${XMPP_DOMAIN}:5280/ws"
echo "  SIP UDP:  ${DISPLAY_IP}:5060"
echo "  SIP TLS:  ${DISPLAY_IP}:5061"
echo "  SIP WSS:  ${DISPLAY_IP}:8089"
echo "  TURN:     ${DISPLAY_IP}:3478 (UDP) / ${DISPLAY_IP}:5349 (TLS)"
echo ""
echo "Required firewall ports:"
echo "  TCP: 22, 5222, 5223, 5280, 5443, 8443, 5061, 8089"
echo "  UDP: 5060, 3478, 5349, 20000-20100, 49152-65535"
echo ""
echo "Test:"
echo "  curl http://${XMPP_DOMAIN}:8443/api/v1/server/info"
echo ""

if [ "$HEALTHY" = false ]; then
    echo "Some services may still be starting. Check logs:"
    echo "  docker compose logs -f"
fi
