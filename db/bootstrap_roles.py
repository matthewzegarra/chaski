"""Create the least-privilege database roles in a managed PostgreSQL (Azure).

Locally db/init/01-roles.sh does this on the first container start; Azure Database for
PostgreSQL has no init hook, so the caj-migrate job runs this before `alembic upgrade`.
Idempotent: existing roles only get their password and settings refreshed.

Env: MIGRATIONS_DATABASE_URL (admin), CHASKI_APP_DB_PASSWORD, CHASKI_READONLY_DB_PASSWORD.
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql


def _dsn(url: str) -> str:
    # SQLAlchemy URL (postgresql+psycopg://...) -> libpq URL.
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    roles = {
        "chaski_app": os.environ["CHASKI_APP_DB_PASSWORD"],
        "chaski_readonly": os.environ["CHASKI_READONLY_DB_PASSWORD"],
    }
    with psycopg.connect(_dsn(os.environ["MIGRATIONS_DATABASE_URL"]), autocommit=True) as conn:
        for role, password in roles.items():
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            conn.execute(
                sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
                    sql.SQL(verb), sql.Identifier(role), sql.Literal(password)
                )
            )
            print(f"role {role}: {'updated' if exists else 'created'}")
        conn.execute("ALTER ROLE chaski_readonly SET statement_timeout = '10s'")
        conn.execute("ALTER ROLE chaski_readonly SET default_transaction_read_only = on")


if __name__ == "__main__":
    main()
