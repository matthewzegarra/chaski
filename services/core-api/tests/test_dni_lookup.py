from __future__ import annotations

from typing import Any

import httpx
import pytest
from core_api import dni_lookup
from core_api.settings import get_settings
from fastapi.testclient import TestClient


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DNI_LOOKUP_MODE", "apisperu")
    monkeypatch.setenv("DNI_LOOKUP_TOKEN", "test-token-not-a-secret")
    monkeypatch.setenv("DNI_LOOKUP_BASE_URL", "https://dniruc.apisperu.com/api/v1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_mock_lookup_is_deterministic() -> None:
    first = dni_lookup.lookup("45678912")
    again = dni_lookup.lookup("45678912")
    assert first.found and first.available and first.fuente == "MOCK"
    assert first.person is not None
    assert first.person.nombres == "Rosa"
    assert first.person.apellidos == "Mamani Quispe"
    assert again.person == first.person


def test_lookup_endpoint_autofills(client: TestClient) -> None:
    resp = client.get("/api/v1/onboarding/lookup-dni/45678912")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "found": True,
        "available": True,
        "nombres": "Rosa",
        "apellidos": "Mamani Quispe",
        "fuente": "MOCK",
    }


def test_lookup_rejects_short_dni(client: TestClient) -> None:
    assert client.get("/api/v1/onboarding/lookup-dni/1234").status_code == 422


def test_lookup_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dni_lookup, "allow_lookup", lambda ip, limit=20: False)
    assert client.get("/api/v1/onboarding/lookup-dni/45678912").status_code == 429


def test_apisperu_maps_names(live: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, headers: dict[str, str]) -> httpx.Response:
        assert url.endswith("/dni/12345678")
        assert headers["Authorization"] == "Bearer test-token-not-a-secret"
        assert "token=" not in url
        return httpx.Response(
            200,
            json={
                "dni": "12345678",
                "nombres": "JUAN CARLOS",
                "apellidoPaterno": "PEREZ",
                "apellidoMaterno": "GARCIA",
                "codVerifica": "3",
            },
        )

    monkeypatch.setattr(dni_lookup, "_http_get", fake_get)
    result = dni_lookup.lookup("12345678")
    assert result.found and result.person is not None
    assert result.person.nombres == "Juan Carlos"
    assert result.person.apellidos == "Perez Garcia"
    assert result.fuente == "APISPERU"


def test_apisperu_not_found(live: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dni_lookup,
        "_http_get",
        lambda url, headers: httpx.Response(404, json={"message": "not found"}),
    )
    result = dni_lookup.lookup("00000000")
    assert result.available and not result.found and result.person is None


def test_apisperu_down_degrades(live: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, headers: dict[str, str]) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(dni_lookup, "_http_get", boom)
    result = dni_lookup.lookup("12345678")
    assert not result.available and not result.found


def test_token_never_goes_in_query_string(live: None, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_get(url: str, headers: dict[str, str]) -> httpx.Response:
        seen["url"] = url
        seen["headers"] = headers
        return httpx.Response(200, json={"nombres": "A", "apellidoPaterno": "B"})

    monkeypatch.setattr(dni_lookup, "_http_get", fake_get)
    dni_lookup.lookup("87654321")
    assert "token=" not in seen["url"]
    assert seen["headers"]["Authorization"].startswith("Bearer ")
