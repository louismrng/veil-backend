FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends gnupg2 curl ca-certificates && \
    curl -fsSL https://deb.kamailio.org/kamailiodebkey.gpg | gpg --dearmor -o /usr/share/keyrings/kamailio.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/kamailio.gpg] http://deb.kamailio.org/kamailio57 bookworm main" \
        > /etc/apt/sources.list.d/kamailio.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        kamailio \
        kamailio-websocket-modules \
        kamailio-tls-modules \
        kamailio-xml-modules \
        kamailio-extra-modules \
        kamailio-postgres-modules \
        kamailio-utils-modules \
    && rm -rf /var/lib/apt/lists/*

COPY kamailio.cfg /etc/kamailio/kamailio.cfg.tmpl
COPY tls.cfg /etc/kamailio/tls.cfg
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5060/udp 5061/tcp 8089/tcp

ENTRYPOINT ["/entrypoint.sh"]
