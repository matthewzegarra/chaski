from __future__ import annotations

import uuid

import jwt
import pytest
from chaski_common.app import create_app
from chaski_common.auth import (
    CurrentUser,
    decode_token,
    issue_dev_token,
    require_customer,
    require_roles,
)
from chaski_common.roles import Role, parse_roles
from chaski_common.settings import CommonSettings
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _settings(**overrides: object) -> CommonSettings:
    base: dict[str, object] = {"auth_mode": "dev", "dev_jwt_secret": "x" * 40, "chaski_env": "DEV"}
    base.update(overrides)
    return CommonSettings(**base)  # type: ignore[arg-type]


def test_dev_mode_is_refused_in_prod() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        _settings(chaski_env="PROD")


def test_dev_mode_requires_long_secret() -> None:
    with pytest.raises(ValueError, match="DEV_JWT_SECRET"):
        _settings(dev_jwt_secret="short")


def test_entra_mode_requires_tenant_and_audience() -> None:
    with pytest.raises(ValueError, match="ENTRA_TENANT_ID"):
        CommonSettings(auth_mode="entra")


def test_dev_token_roundtrip() -> None:
    s = _settings()
    cid = uuid.uuid4()
    token = issue_dev_token(sub="u1", name="Ana", roles=[Role.CLIENTE], customer_id=cid, settings=s)
    claims = decode_token(token, s)
    assert claims["roles"] == ["Cliente"]
    assert claims["customer_id"] == str(cid)


def test_token_signed_with_other_secret_is_rejected() -> None:
    token = issue_dev_token(sub="u1", name="Ana", roles=[Role.ADMIN], settings=_settings())
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(token, _settings(dev_jwt_secret="y" * 40))


def test_parse_roles_ignores_unknown() -> None:
    assert parse_roles(["Admin", "SuperUser", 3]) == frozenset({Role.ADMIN})
    assert parse_roles("Admin") == frozenset()


# ---- endpoint-level authorization (writes to ops.audit_log)

router = APIRouter()


@router.get("/riesgos-only")
def riesgos_only(user: CurrentUser = Depends(require_roles(Role.RIESGOS))) -> dict[str, str]:
    return {"user": user.sub}


@router.get("/me")
def me(user: CurrentUser = Depends(require_customer)) -> dict[str, str]:
    return {"customer_id": str(user.customer_id)}


@pytest.fixture
def client(db: None) -> TestClient:
    return TestClient(create_app(title="t", description="t", routers=[router]))


def _bearer(roles: list[Role], customer_id: uuid.UUID | None = None) -> dict[str, str]:
    token = issue_dev_token(sub="tester", name="Tester", roles=roles, customer_id=customer_id)
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/riesgos-only").status_code == 401


def test_role_allowed(client: TestClient) -> None:
    assert client.get("/api/v1/riesgos-only", headers=_bearer([Role.RIESGOS])).status_code == 200


def test_role_denied_is_audited(client: TestClient, migrated_db: str) -> None:
    resp = client.get("/api/v1/riesgos-only", headers=_bearer([Role.MARKETING]))
    assert resp.status_code == 403
    with create_engine(migrated_db).connect() as conn:
        row = conn.execute(
            text("SELECT actor_role, allowed, action FROM ops.audit_log ORDER BY id DESC LIMIT 1")
        ).one()
    assert row.actor_role == "Marketing"
    assert row.allowed is False
    assert row.action == "GET /api/v1/riesgos-only"


def test_customer_endpoint_requires_customer_claim(client: TestClient) -> None:
    assert client.get("/api/v1/me", headers=_bearer([Role.CLIENTE])).status_code == 403
    cid = uuid.uuid4()
    resp = client.get("/api/v1/me", headers=_bearer([Role.CLIENTE], cid))
    assert resp.json() == {"customer_id": str(cid)}


def test_security_headers_and_correlation_id(client: TestClient) -> None:
    resp = client.get("/health", headers={"X-Correlation-ID": "abc12345-test"})
    assert resp.headers["X-Correlation-ID"] == "abc12345-test"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


@router.get("/boom")
def boom() -> None:
    raise RuntimeError("unexpected")


def test_unhandled_errors_keep_cors_headers(client: TestClient) -> None:
    resp = client.get("/api/v1/boom", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Error interno"
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
