from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from azure.identity import CertificateCredential, DefaultAzureCredential
from chaski_common import service_auth
from chaski_common.settings import get_common_settings
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _self_signed_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "chaski-services")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return (key_pem + cert.public_bytes(serialization.Encoding.PEM)).decode()


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


def test_cross_tenant_uses_the_key_vault_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTRA_SERVICE_CLIENT_ID", "33333333-3333-3333-3333-333333333333")
    monkeypatch.setenv("ENTRA_SERVICE_CERTIFICATE", _self_signed_pem())
    get_common_settings.cache_clear()
    assert isinstance(service_auth._credential(), CertificateCredential)


def test_client_id_without_certificate_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTRA_SERVICE_CLIENT_ID", "33333333-3333-3333-3333-333333333333")
    get_common_settings.cache_clear()
    assert isinstance(service_auth._credential(), DefaultAzureCredential)
