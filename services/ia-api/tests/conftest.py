from __future__ import annotations

from collections.abc import Iterator

import pytest
from chaski_common import testing
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _fresh_providers() -> Iterator[None]:
    """Providers and settings are cached per process; tests may switch them."""
    from ia_api.providers.docintel import get_docintel
    from ia_api.providers.llm import get_llm
    from ia_api.providers.safety import get_safety
    from ia_api.routers.insights import analytics_engine, readonly_engine
    from ia_api.settings import get_settings

    caches = (get_settings, get_llm, get_safety, get_docintel, analytics_engine, readonly_engine)
    for c in caches:
        c.cache_clear()
    yield
    for c in caches:
        c.cache_clear()


@pytest.fixture
def client(db: None) -> TestClient:
    from ia_api.main import app

    return TestClient(app)


@pytest.fixture
def s(db: None) -> Iterator[Session]:
    session = testing.session()
    yield session
    session.close()
