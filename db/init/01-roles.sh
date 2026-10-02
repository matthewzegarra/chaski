#!/bin/bash
# Runs once, on the first start of the local Postgres container (docker-entrypoint-initdb.d).
# Creates the least-privilege roles used by the services and the test database.
# Passwords come from environment variables (.env); nothing is hardcoded.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_pw="$CHASKI_APP_DB_PASSWORD" \
  -v ro_pw="$CHASKI_READONLY_DB_PASSWORD" \
  -v owner="$POSTGRES_USER" <<'EOSQL'
CREATE ROLE chaski_app LOGIN PASSWORD :'app_pw';
CREATE ROLE chaski_readonly LOGIN PASSWORD :'ro_pw';
ALTER ROLE chaski_readonly SET statement_timeout = '10s';
ALTER ROLE chaski_readonly SET default_transaction_read_only = on;
CREATE DATABASE chaski_test OWNER :"owner";
EOSQL
