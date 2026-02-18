#!/bin/sh
set -e

TEMPLATE="/etc/kamailio/kamailio.cfg.tmpl"
OUTPUT="/tmp/kamailio.cfg"

if [ -n "$SERVER_IP" ]; then
    sed "s/__SERVER_IP__/$SERVER_IP/g" "$TEMPLATE" > "$OUTPUT"
else
    # No SERVER_IP set — remove advertise directives so Kamailio uses defaults
    sed 's/ advertise __SERVER_IP__:[0-9]*//g' "$TEMPLATE" > "$OUTPUT"
fi

exec kamailio -DD -E -f "$OUTPUT"
