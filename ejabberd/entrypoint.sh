#!/bin/sh
set -e

CONFIG_TMPL="/opt/ejabberd/conf/ejabberd.yml.tmpl"
CONFIG="/opt/ejabberd/conf/ejabberd.yml"
DOMAIN="${XMPP_DOMAIN:-example.com}"

# Substitute placeholders in config template
sed -e "s/__XMPP_DOMAIN__/${DOMAIN}/g" \
    -e "s/__DB_PASSWORD__/${DB_PASSWORD}/g" \
    "$CONFIG_TMPL" > "$CONFIG"

# Generate self-signed certs for development if none are mounted
if [ ! -f "/etc/ejabberd/certs/server.pem" ]; then
    echo "WARNING: No TLS certs found. Generating self-signed certs for development."
    CERT_DIR="/tmp/ejabberd-certs"
    mkdir -p "$CERT_DIR"
    openssl req -x509 -newkey rsa:2048 \
        -keyout "$CERT_DIR/key.pem" \
        -out "$CERT_DIR/cert.pem" \
        -days 365 -nodes \
        -subj "/CN=${DOMAIN}" 2>/dev/null
    # Ejabberd expects combined cert+key in server.pem
    cat "$CERT_DIR/cert.pem" "$CERT_DIR/key.pem" > "$CERT_DIR/server.pem"
    cp "$CERT_DIR/server.pem" "$CERT_DIR/ca.pem"
    # Update config to point to generated certs
    sed -i "s|/etc/ejabberd/certs|${CERT_DIR}|g" "$CONFIG"
    echo "Self-signed certs generated at ${CERT_DIR}"
fi

exec /home/ejabberd/bin/ejabberdctl foreground
