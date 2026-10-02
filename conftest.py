"""Repository-wide pytest setup.

Configures a safe test environment *before* any service module caches its settings, and
provides a migrated `chaski_test` database on the docker compose Postgres (see D13).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _dotenv() -> dict[str, str]:
    env_file = ROOT / ".env"
    values: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


_env = _dotenv()
_host = os.environ.get("TEST_DB_HOST", "localhost")
_admin_pw = os.environ.get("POSTGRES_PASSWORD", _env.get("POSTGRES_PASSWORD", ""))
_app_pw = os.environ.get("CHASKI_APP_DB_PASSWORD", _env.get("CHASKI_APP_DB_PASSWORD", ""))
_ro_pw = os.environ.get("CHASKI_READONLY_DB_PASSWORD", _env.get("CHASKI_READONLY_DB_PASSWORD", ""))

TEST_ADMIN_URL = f"postgresql+psycopg://chaski_admin:{_admin_pw}@{_host}:5432/chaski_test"
TEST_APP_URL = f"postgresql+psycopg://chaski_app:{_app_pw}@{_host}:5432/chaski_test"
TEST_READONLY_URL = f"postgresql+psycopg://chaski_readonly:{_ro_pw}@{_host}:5432/chaski_test"

os.environ.update(
    {
        "CHASKI_ENV": "TEST",
        "AUTH_MODE": "dev",
        "DEV_JWT_SECRET": "test-only-secret-0123456789abcdef0123456789",
        "DATABASE_URL": TEST_APP_URL,
        "ANALYTICS_DB_URL": TEST_APP_URL,
        "NL2SQL_DB_URL": TEST_READONLY_URL,
        "MIGRATIONS_DATABASE_URL": TEST_ADMIN_URL,
        "AI_MODE": "mock",
        "DEMO_MODE": "true",
        "RATE_LIMIT_PER_MINUTE": "0",
        "FRAUD_WEBHOOK_SECRET": "test-webhook-secret",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
        "EVENTSTREAM_CONNECTION_STRING": "",
    }
)

_TRUNCATE = """
TRUNCATE core.customers, core.accounts, core.cards, core.loans, core.loan_installments,
         core.transactions, core.complaints, core.kyc_documents,
         ops.audit_log, ops.fraud_alerts, ops.pipeline_runs, ops.quality_checks,
         ops.raw_ingest, ops.quarantine_records, ops.ai_interactions, ops.idempotency_keys
RESTART IDENTITY CASCADE
"""


def _db_reachable() -> bool:
    import psycopg

    try:
        with psycopg.connect(
            TEST_ADMIN_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=3
        ):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Rebuilds the chaski_test schema once per session with Alembic."""
    if not _db_reachable():
        pytest.skip("Postgres not reachable: run `docker compose up -d postgres` first")
    alembic = [sys.executable, "-m", "alembic", "-c", str(ROOT / "db" / "alembic.ini")]
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(  # noqa: S603 - fixed argv, no user input
            [*alembic, *args], check=True, capture_output=True, env=os.environ.copy()
        )
    return TEST_APP_URL


@pytest.fixture
def db(migrated_db: str) -> Iterator[None]:
    """Empty core/ops tables before each test that touches the database."""
    from sqlalchemy import create_engine, text

    engine = create_engine(TEST_ADMIN_URL)
    with engine.begin() as conn:
        conn.execute(text(_TRUNCATE))
    engine.dispose()
    yield
