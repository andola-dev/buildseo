#!/bin/bash
# Creates the least-privilege runtime database role.
#
# This is the linchpin of the RLS design: POSTGRES_USER in the official image
# is a SUPERUSER, and a superuser bypasses Row-Level Security entirely. The
# application must therefore never connect as it. The role created here is
# NOSUPERUSER and explicitly NOBYPASSRLS, so every policy applies to it.
#
# Table privileges are granted by the Alembic revision that creates the schema
# (0018_indexes_and_grants), which targets DB_APP_ROLE.
set -euo pipefail

APP_DB_ROLE="${APP_DB_ROLE:-buildseo_app}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	DO \$\$
	BEGIN
	  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_DB_ROLE}') THEN
	    CREATE ROLE ${APP_DB_ROLE} LOGIN
	      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT
	      PASSWORD '${APP_DB_PASSWORD}';
	  ELSE
	    ALTER ROLE ${APP_DB_ROLE} NOSUPERUSER NOBYPASSRLS
	      PASSWORD '${APP_DB_PASSWORD}';
	  END IF;
	END
	\$\$;

	GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_ROLE};
	GRANT USAGE ON SCHEMA public TO ${APP_DB_ROLE};

	-- The runtime role must not be able to reshape the schema.
	REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL

echo "created runtime role ${APP_DB_ROLE} (NOSUPERUSER, NOBYPASSRLS)"
