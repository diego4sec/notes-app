-- Keycloak and the app share one Postgres instance but never one database.
-- Runs as POSTGRES_USER, so that role owns it.
CREATE DATABASE keycloak;
