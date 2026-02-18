FROM ghcr.io/processone/ejabberd:latest

USER root
RUN apk add --no-cache openssl

COPY ejabberd.yml /opt/ejabberd/conf/ejabberd.yml.tmpl
COPY entrypoint.sh /custom-entrypoint.sh
RUN chmod +x /custom-entrypoint.sh && \
    chown ejabberd:ejabberd /opt/ejabberd/conf/ejabberd.yml.tmpl

USER ejabberd

ENTRYPOINT ["/custom-entrypoint.sh"]
