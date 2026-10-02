from __future__ import annotations

from collections.abc import Iterator

import pytest
from azure.identity import ClientAssertionCredential, DefaultAzureCredential
from chaski_common import service_auth
from chaski_common.settings import get_common_settings


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ENTRA_AUDIENCE", "22222222-2222-2222-2222-222222222222")
    get_common_settings.cache_clear()
    service_auth._credential.cache_clear()
    yield
    get_common_settings.cache_clear()
    service_auth._credential.cache_clear()


def test_same_tenant_uses_managed_identity_directly() -> None:
    assert isinstance(service_auth._credential(), DefaultAzureCredential)


def test_cross_tenant_exchanges_a_managed_identity_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENTRA_SERVICE_CLIENT_ID", "33333333-3333-3333-3333-333333333333")
    monkeypatch.setenv("AZURE_CLIENT_ID", "44444444-4444-4444-4444-444444444444")
    get_common_settings.cache_clear()
    assert isinstance(service_auth._credential(), ClientAssertionCredential)
