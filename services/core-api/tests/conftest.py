from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from chaski_common import testing
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

IaResponder = Callable[[str, dict[str, Any]], dict[str, Any] | None]


@pytest.fixture(autouse=True)
def _core_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from core_api.settings import get_settings

    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def ia(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Controls what ia-api "returns". Empty by default = ia-api unavailable."""
    from core_api import ia_client

    responses: dict[str, Any] = {}
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(path: str, token: str, **kwargs: Any) -> dict[str, Any] | None:
        calls.append((path, kwargs))
        value = responses.get(path)
        return value(kwargs) if callable(value) else value

    monkeypatch.setattr(ia_client, "_post", fake_post)
    return {"responses": responses, "calls": calls}


@pytest.fixture
def client(db: None, ia: dict[str, Any]) -> TestClient:
    from core_api.main import app

    return TestClient(app)


@pytest.fixture
def s(db: None) -> Iterator[Session]:
    session = testing.session()
    yield session
    session.close()
