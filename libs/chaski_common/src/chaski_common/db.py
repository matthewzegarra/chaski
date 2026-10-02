"""Database engine and session helpers (sync SQLAlchemy 2, FastAPI runs them in a threadpool)."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from chaski_common.settings import get_common_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_common_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Endpoints commit explicitly; anything uncommitted is rolled back."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def ping(engine: Engine | None = None) -> bool:
    try:
        with (engine or get_engine()).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
