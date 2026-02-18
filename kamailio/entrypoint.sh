#!/bin/sh
set -e

TEMPLATE="/etc/kamailio/kamailio.cfg.tmpl"
OUTPUT="/tmp/kamailio.cfg"

cp "$TEMPLATE" "$OUTPUT"

# Substitute XMPP domain
DOMAIN="${XMPP_DOMAIN:-example.com}"
sed -i "s/__XMPP_DOMAIN__/$DOMAIN/g" "$OUTPUT"

# Substitute server IP — wrap IPv6 addresses in brackets for SIP URIs
if [ -n "$SERVER_IP" ]; then
    if echo "$SERVER_IP" | grep -q ':'; then
        ADVERTISE_IP="[$SERVER_IP]"
    else
        ADVERTISE_IP="$SERVER_IP"
    fi
    sed -i "s/__SERVER_IP__/$ADVERTISE_IP/g" "$OUTPUT"
else
    # No SERVER_IP set — remove advertise directives so Kamailio uses defaults
    sed -i 's/ advertise __SERVER_IP__:[0-9]*//g' "$OUTPUT"
fi

exec kamailio -DD -E -f "$OUTPUT"
