"""Analytics, security, devops and dev-identity endpoints."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from chaski_common.models import AuditLog
from chaski_common.roles import Role
from chaski_common.testing import headers, make_account, make_customer
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


@pytest.fixture
def gold(db: None) -> Iterator[None]:
    """chaski_app can only read gold, so the fixture writes with the admin role."""
    engine = create_engine(os.environ["MIGRATIONS_DATABASE_URL"])  # admin, set by root conftest
    month = date.today().replace(day=1)
    today = date.today()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE gold.fact_profitability_monthly, gold.fact_portfolio_daily"))
        conn.execute(
            text(
                """
                INSERT INTO gold.fact_profitability_monthly VALUES
                ('PRESTAMO_CONSUMO', 'MASIVO', 'Lima', :m, 1000, 100, 200, 50, 850),
                ('PRESTAMO_CONSUMO', 'PYME', 'Cusco', :m, 500, 50, 100, 25, 425),
                ('AHORRO_SOLES', 'MASIVO', 'Lima', :m, 300, 20, 100, 0, 220)
                """
            ),
            {"m": month},
        )
        for i, (dpd, bucket, region) in enumerate(
            [(0, "Normal", "Lima"), (45, "Deficiente", "Loreto")]
        ):
            for d in (today - timedelta(days=1), today):
                conn.execute(
                    text(
                        "INSERT INTO gold.fact_portfolio_daily VALUES (:id, :d, 1000, :dpd, :b, :r, 'MASIVO')"
                    ),
                    {"id": uuid.UUID(int=i + 1), "d": d, "dpd": dpd, "b": bucket, "r": region},
                )
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE gold.fact_profitability_monthly, gold.fact_portfolio_daily"))
    engine.dispose()


def test_profitability(client: TestClient, gold: None) -> None:
    by_product = client.get(
        "/api/v1/analytics/profitability", headers=headers(Role.DIRECCION)
    ).json()
    rows = {r["dimension"]: r for r in by_product["by_dimension"]}
    assert rows["PRESTAMO_CONSUMO"]["margen"] == 1275.0
    by_region = client.get(
        "/api/v1/analytics/profitability?dimension=region", headers=headers(Role.MARKETING)
    ).json()
    assert {r["dimension"] for r in by_region["by_dimension"]} == {"Lima", "Cusco"}
    assert (
        client.get(
            "/api/v1/analytics/profitability?dimension=1;drop", headers=headers(Role.ADMIN)
        ).status_code
        == 422
    )
    assert (
        client.get("/api/v1/analytics/profitability", headers=headers(Role.ATENCION)).status_code
        == 403
    )


def test_delinquency(client: TestClient, gold: None) -> None:
    body = client.get("/api/v1/analytics/delinquency", headers=headers(Role.RIESGOS)).json()
    assert [b["bucket"] for b in body["by_bucket"]] == ["Normal", "Deficiente"]
    regions = {r["region"]: r for r in body["by_region"]}
    assert regions["Loreto"]["mora_pct"] == 100.0 and regions["Lima"]["mora_pct"] == 0.0
    assert len(body["trend"]) == 2 and body["trend"][-1]["mora_pct"] == 50.0


def test_audit_log_filters(client: TestClient, s: Session) -> None:
    client.get("/api/v1/customers", headers=headers(Role.MARKETING, sub="milagros"))
    client.post(
        "/api/v1/security/denied-route",
        json={"route": "/riesgos/prestamos", "module": "prestamos"},
        headers=headers(Role.MARKETING, sub="milagros"),
    )
    page = client.get(
        "/api/v1/security/audit?allowed=false&actor=milag", headers=headers(Role.TI)
    ).json()
    assert page["total"] == 2
    assert {i["resource"] for i in page["items"]} == {"/api/v1/customers", "ui:prestamos"}
    summary = client.get("/api/v1/security/summary", headers=headers(Role.ADMIN)).json()
    assert summary["denegados_24h"] == 2
    assert client.get("/api/v1/security/audit", headers=headers(Role.FRAUDE)).status_code == 403


def test_secrets_metadata_never_returns_values(client: TestClient, s: Session) -> None:
    body = client.get("/api/v1/security/secrets-metadata", headers=headers(Role.TI)).json()
    assert body["source"] == "mock" and body["secrets"]
    for secret in body["secrets"]:
        assert "value" not in secret
        assert secret["status"] in {"OK", "POR_ROTAR", "VENCIDO", "SIN_EXPIRACION"}
    assert any(sec["status"] == "POR_ROTAR" for sec in body["secrets"])


def test_devops_mock(client: TestClient, s: Session) -> None:
    body = client.get("/api/v1/devops/deployments", headers=headers(Role.TI)).json()
    assert body["source"] == "mock" and set(body["versions"]) == {"DEV", "TEST", "PROD"}
    assert (
        client.get("/api/v1/devops/deployments", headers=headers(Role.DIRECCION)).status_code == 403
    )


def test_dev_token_and_users(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    make_account(s, c)
    users = client.get("/api/v1/dev/users").json()
    assert len(users["staff"]) == 8
    assert users["customers"][0]["customer_id"] == str(c.id)

    tok = client.post(
        "/api/v1/dev/token", json={"name": "María", "roles": ["Cliente"], "customer_id": str(c.id)}
    ).json()["access_token"]
    me = client.get("/api/v1/customers/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200

    bad = client.post("/api/v1/dev/token", json={"name": "X", "roles": ["Cliente"]})
    assert bad.status_code == 422
    assert (
        client.post("/api/v1/dev/token", json={"name": "X", "roles": ["Root"]}).status_code == 422
    )


def test_dev_endpoints_hidden_outside_dev_mode(
    client: TestClient, s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core_api.settings import get_settings

    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant")
    monkeypatch.setenv("ENTRA_AUDIENCE", "api://chaski")
    get_settings.cache_clear()
    assert client.get("/api/v1/dev/users").status_code == 404
    assert (
        client.post("/api/v1/dev/token", json={"name": "x", "roles": ["Admin"]}).status_code == 404
    )


def test_health_and_ready(client: TestClient, s: Session) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    assert s.scalars(select(AuditLog)).first() is None
