from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from chaski_common.models import FraudAlert, Loan, QuarantineRecord
from chaski_common.roles import Role
from chaski_common.testing import headers, make_account, make_customer, make_tx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_kpis(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    acc = make_account(s, c)
    make_tx(s, acc, amount=Decimal("100"))
    make_tx(s, acc, amount=Decimal("50"), created_at=datetime.now(UTC) - timedelta(days=3))
    s.add_all(
        [
            Loan(customer_id=c.id, amount=Decimal(1000), term_months=12, rate_tea=Decimal("0.3"),
                 status="DESEMBOLSADO", outstanding_balance=Decimal(800), days_past_due=45),
            Loan(customer_id=c.id, amount=Decimal(1000), term_months=12, rate_tea=Decimal("0.3"),
                 status="DESEMBOLSADO", outstanding_balance=Decimal(200), days_past_due=0),
        ]
    )  # fmt: skip
    s.commit()
    k = client.get("/api/v1/ops/kpis", headers=headers(Role.OPERACIONES)).json()
    assert k["transacciones_hoy"] == 1
    assert k["monto_transado_hoy"] == 100.0
    assert k["clientes_nuevos_hoy"] == 1
    assert k["cartera_total"] == 1000.0 and k["mora_pct"] == 80.0
    assert client.get("/api/v1/ops/kpis", headers=headers(Role.CLIENTE)).status_code == 403


def test_transactions_by_hour(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    make_tx(s, make_account(s, c))
    hours = client.get("/api/v1/ops/transactions-by-hour", headers=headers(Role.DIRECCION)).json()
    assert len(hours) == 24 and sum(h["cantidad"] for h in hours) == 1


def test_bad_record_goes_to_quarantine(client: TestClient, s: Session) -> None:
    make_account(s, make_customer(s))
    admin = headers(Role.ADMIN)
    assert client.post("/api/v1/demo/inject-bad-record", headers=admin).json()["inserted"] == 3
    result = client.post("/api/v1/ops/pipelines/run", headers=headers(Role.TI)).json()
    run = result["run"]
    assert result["mode"] == "local"
    assert run["status"] == "CON_ALERTAS" and run["rows_quarantined"] == 1

    checks = client.get(f"/api/v1/ops/pipelines/{run['id']}/checks", headers=admin).json()
    failed = {c["check_name"] for c in checks if not c["passed"]}
    assert failed == {"montos_positivos", "moneda_valida", "fecha_no_futura", "cuenta_existe"}

    quarantine = client.get("/api/v1/ops/quarantine", headers=admin).json()
    assert len(quarantine) == 1 and quarantine[0]["payload"]["currency"] == "XXX"
    assert len(client.get("/api/v1/ops/pipelines", headers=admin).json()) == 1

    # Second run has nothing pending.
    second = client.post("/api/v1/ops/pipelines/run", headers=admin).json()["run"]
    assert second["status"] == "EXITOSO" and second["rows_quarantined"] == 0
    assert s.scalar(select(QuarantineRecord.reason)).startswith("Falló:")


def test_pipeline_permissions(client: TestClient, s: Session) -> None:
    assert (
        client.post("/api/v1/ops/pipelines/run", headers=headers(Role.OPERACIONES)).status_code
        == 403
    )
    assert client.get("/api/v1/ops/pipelines", headers=headers(Role.MARKETING)).status_code == 403


def test_fraud_burst_triggers_r1(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    make_account(s, c, balance="5000.00")
    resp = client.post("/api/v1/demo/fraud-burst", json={}, headers=headers(Role.ADMIN))
    assert resp.status_code == 200
    body = resp.json()
    assert body["transfers"] == 8 and "R1_VELOCIDAD" in body["alerts"]
    assert (
        s.scalars(select(FraudAlert).where(FraudAlert.rule == "R1_VELOCIDAD")).one().source
        == "RULES"
    )


def test_demo_is_admin_only_and_needs_demo_mode(
    client: TestClient, s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        client.post("/api/v1/demo/inject-bad-record", headers=headers(Role.TI)).status_code == 403
    )
    from core_api.settings import get_settings

    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    assert (
        client.post("/api/v1/demo/inject-bad-record", headers=headers(Role.ADMIN)).status_code
        == 404
    )
