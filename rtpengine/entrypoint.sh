#!/bin/bash
set -e

# Detect the container's internal IP (for local bind address)
LOCAL_IP=$(ip addr | grep 'state UP' -A2 | tail -n1 | awk '{print $2}' | cut -f1 -d'/')

# Generate rtpengine config from environment variables.
# The drachtio image's built-in entrypoint ignores our env vars and
# auto-detects the Docker internal IP, which is unreachable from clients.
# We bind to LOCAL_IP but advertise SERVER_IP in SDP so phones can reach us
# via Docker's port mapping.
cat > /etc/rtpengine.conf <<EOF
[rtpengine]
interface=${LOCAL_IP}!${SERVER_IP:-127.0.0.1}
foreground=true
log-stderr=true
listen-ng=${LOCAL_IP}:22222
port-min=${PORT_MIN:-20000}
port-max=${PORT_MAX:-20100}
log-level=${LOG_LEVEL:-6}
delete-delay=0
EOF

echo "RTPEngine config: interface=${LOCAL_IP}!${SERVER_IP:-127.0.0.1} ports=${PORT_MIN}-${PORT_MAX}"
exec rtpengine --config-file /etc/rtpengine.conf
