from __future__ import annotations

from collections.abc import Iterator

import pytest
from chaski_common import testing
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def client(db: None) -> TestClient:
    from cuentas_api.main import app

    return TestClient(app)


@pytest.fixture
def s(db: None) -> Iterator[Session]:
    session = testing.session()
    yield session
    session.close()
