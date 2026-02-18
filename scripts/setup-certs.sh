#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CERT_DIR="$PROJECT_DIR/certs"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    . "$PROJECT_DIR/.env"
    set +a
fi

DOMAIN="${XMPP_DOMAIN:-example.com}"

mkdir -p "$CERT_DIR"

echo "=== TLS Certificate Setup ==="
echo "Domain: $DOMAIN"

# Try Let's Encrypt if certbot is available and domain resolves to this server
if command -v certbot &>/dev/null; then
    # Detect public IP (try IPv6 first, then IPv4)
    SERVER_PUBLIC_IP=$(curl -s -6 --connect-timeout 5 ifconfig.me 2>/dev/null || \
                       curl -s -4 --connect-timeout 5 ifconfig.me 2>/dev/null || echo "")
    # Check both AAAA and A records
    DOMAIN_IP=$(dig +short "$DOMAIN" AAAA 2>/dev/null | head -1 || echo "")
    if [ -z "$DOMAIN_IP" ]; then
        DOMAIN_IP=$(dig +short "$DOMAIN" A 2>/dev/null | head -1 || echo "")
    fi

    if [ -n "$DOMAIN_IP" ] && [ "$DOMAIN_IP" = "$SERVER_PUBLIC_IP" ]; then
        echo "Domain $DOMAIN resolves to this server ($SERVER_PUBLIC_IP)."
        echo "Requesting Let's Encrypt certificate..."

        certbot certonly --standalone \
            -d "$DOMAIN" \
            --non-interactive \
            --agree-tos \
            --register-unsafely-without-email \
            --cert-name veil

        # Copy certs to project directory
        cp /etc/letsencrypt/live/veil/fullchain.pem "$CERT_DIR/server.pem"
        cp /etc/letsencrypt/live/veil/privkey.pem "$CERT_DIR/key.pem"
        cp /etc/letsencrypt/live/veil/chain.pem "$CERT_DIR/ca.pem"

        echo "Let's Encrypt certificates installed to $CERT_DIR"
        exit 0
    else
        echo "Domain does not resolve to this server (domain=$DOMAIN_IP, server=$SERVER_PUBLIC_IP)."
        echo "Falling back to self-signed certificates."
    fi
else
    echo "certbot not found. Generating self-signed certificates."
fi

# Generate self-signed certificates
openssl req -x509 -newkey rsa:4096 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -days 365 -nodes \
    -subj "/CN=$DOMAIN"

# Create combined server.pem (cert + key) for services that expect it
cat "$CERT_DIR/cert.pem" "$CERT_DIR/key.pem" > "$CERT_DIR/server.pem"
cp "$CERT_DIR/cert.pem" "$CERT_DIR/ca.pem"

echo "Self-signed certificates generated in $CERT_DIR"
echo "WARNING: Self-signed certs will cause TLS warnings. Use Let's Encrypt for production."
