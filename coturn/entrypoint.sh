#!/bin/sh
set -e

TEMPLATE="/etc/coturn/turnserver.conf.tmpl"
OUTPUT="/tmp/turnserver.conf"

sed -e "s/__TURN_SECRET__/${TURN_SECRET}/g" \
    -e "s/__XMPP_DOMAIN__/${XMPP_DOMAIN:-example.com}/g" \
    -e "s/__SERVER_IP__/${SERVER_IP:-127.0.0.1}/g" \
    "$TEMPLATE" > "$OUTPUT"

exec turnserver -c "$OUTPUT"
