-- Veil Backend — Database Initialization
-- This script runs on first PostgreSQL startup via docker-entrypoint-initdb.d.
-- It creates tables shared between Ejabberd, Kamailio, and the REST API.

-- Shared subscriber table for SIP (Kamailio) authentication.
-- Ejabberd manages its own user store via its SQL schema; Kamailio reads
-- from this table for SIP digest auth. A trigger keeps the two in sync
-- when users register through Ejabberd (see below).
CREATE TABLE IF NOT EXISTS subscriber (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL,
    domain          TEXT NOT NULL DEFAULT 'example.com',
    password        TEXT NOT NULL,
    ha1             TEXT NOT NULL,
    ha1b            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (username, domain)
);

CREATE INDEX idx_subscriber_username ON subscriber (username);

-- Push notification registrations (see INTERFACES.md §4.1, DATA_MODELS.md §3.2).
CREATE TABLE IF NOT EXISTS push_registrations (
    jid             TEXT NOT NULL,
    device_uuid     TEXT NOT NULL,
    platform        TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
    push_token      TEXT NOT NULL,
    app_id          TEXT NOT NULL,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (jid, device_uuid)
);

CREATE INDEX idx_push_registrations_jid ON push_registrations (jid);

-- Grant Kamailio read access to the subscriber table.
-- The ejabberd user owns the database; create a kamailio role with SELECT.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kamailio') THEN
        CREATE ROLE kamailio WITH LOGIN PASSWORD 'kamailio_default';
    END IF;
END
$$;

GRANT SELECT ON subscriber TO kamailio;

-- Kamailio usrloc (location) table — used for SIP registrations (db_mode=2).
CREATE TABLE IF NOT EXISTS location (
    id              SERIAL PRIMARY KEY,
    ruid            TEXT NOT NULL DEFAULT '',
    username        TEXT NOT NULL DEFAULT '',
    domain          TEXT DEFAULT NULL,
    contact         TEXT NOT NULL DEFAULT '',
    received        TEXT DEFAULT NULL,
    path            TEXT DEFAULT NULL,
    expires         TIMESTAMPTZ NOT NULL DEFAULT '2030-05-28 21:32:15+00',
    q               REAL NOT NULL DEFAULT 1.0,
    callid          TEXT NOT NULL DEFAULT 'Default-Call-ID',
    cseq            INT NOT NULL DEFAULT 1,
    last_modified   TIMESTAMPTZ NOT NULL DEFAULT '2000-01-01 00:00:01+00',
    flags           INT NOT NULL DEFAULT 0,
    cflags          INT NOT NULL DEFAULT 0,
    user_agent      TEXT NOT NULL DEFAULT '',
    socket          TEXT DEFAULT NULL,
    methods         INT DEFAULT NULL,
    instance        TEXT DEFAULT NULL,
    reg_id          INT NOT NULL DEFAULT 0,
    server_id       INT NOT NULL DEFAULT 0,
    connection_id   INT NOT NULL DEFAULT 0,
    keepalive       INT NOT NULL DEFAULT 0,
    partition       INT NOT NULL DEFAULT 0,
    UNIQUE (ruid)
);

CREATE INDEX idx_location_account ON location (username, domain, contact);
CREATE INDEX idx_location_expires ON location (expires);

GRANT ALL ON location TO kamailio;
GRANT USAGE, SELECT ON SEQUENCE location_id_seq TO kamailio;

-- Kamailio version table — required for schema version checks at startup.
CREATE TABLE IF NOT EXISTS version (
    table_name      VARCHAR(32) NOT NULL,
    table_version   INT NOT NULL DEFAULT 0,
    CONSTRAINT version_table_name_idx UNIQUE (table_name)
);

INSERT INTO version (table_name, table_version) VALUES ('location', 9)
    ON CONFLICT (table_name) DO NOTHING;
INSERT INTO version (table_name, table_version) VALUES ('subscriber', 7)
    ON CONFLICT (table_name) DO NOTHING;

GRANT SELECT ON version TO kamailio;
