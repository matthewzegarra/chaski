from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from chaski_common.models import FraudAlert, Loan, PipelineRun, QuarantineRecord
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


def test_pipeline_job_runs_checks_and_writes_the_lake(
    client: TestClient, s: Session, monkeypatch: Any, tmp_path: Any
) -> None:
    import json

    import pyarrow.parquet as pq
    from core_api import pipeline_job

    account = make_account(s, make_customer(s))
    make_tx(s, account, amount=Decimal("120.50"))
    s.commit()
    client.post("/api/v1/demo/inject-bad-record", headers=headers(Role.ADMIN))
    monkeypatch.setenv("PIPELINE_TRIGGER", "PROGRAMADO")
    monkeypatch.setenv("LAKE_DIR", str(tmp_path))
    monkeypatch.delenv("BLOB_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("DW_SERVER", raising=False)

    assert pipeline_job.main() == 0
    runs = client.get("/api/v1/ops/pipelines", headers=headers(Role.TI)).json()
    assert len(runs) == 1 and runs[0]["status"] == "CON_ALERTAS"
    assert s.scalar(select(PipelineRun.trigger)) == "PROGRAMADO"

    checks = client.get(f"/api/v1/ops/pipelines/{runs[0]['id']}/checks", headers=headers(Role.TI))
    names = {(c["table_name"], c["check_name"]) for c in checks.json()}
    assert ("core.accounts", "saldo_no_negativo") in names
    assert ("core.transactions", "sin_pan") in names

    quarantine = list((tmp_path / "quarantine").rglob("*.json"))
    assert json.loads(quarantine[0].read_text())[0]["payload"]["currency"] == "XXX"
    bronze_tx = list((tmp_path / "bronze" / "transactions").rglob("*.parquet"))
    silver_tx = list((tmp_path / "silver" / "transactions").rglob("*.parquet"))
    assert pq.read_table(bronze_tx[0]).num_rows >= 1 and silver_tx
    customers = pq.read_table(next((tmp_path / "bronze" / "customers").rglob("*.parquet")))
    # Data minimisation: no direct identifiers leave the core database.
    assert not {"document_number", "email", "phone", "first_name"} & set(customers.column_names)


def test_pan_in_free_text_fails_the_blocking_check(s: Session) -> None:
    from core_api.etl import quality

    account = make_account(s, make_customer(s))
    tx = make_tx(s, account, amount=Decimal("10"))
    tx.description = "pago tarjeta 4111111111111111"
    s.commit()
    result = {(r.table, r.name): r for r in quality.run_checks(s)}
    pan = result[("core.transactions", "sin_pan")]
    assert pan.failed == 1 and pan.blocking and not pan.passed


def test_dw_merge_and_ddl_are_idempotent_sql() -> None:
    from core_api.etl import dw

    sql = dw.merge_sql(dw.TABLES[-1])
    assert sql.startswith("MERGE dw.fact_portfolio_daily AS t USING #stage AS s")
    assert "t.[loan_id] = s.[loan_id] AND t.[date] = s.[date]" in sql
    assert "WHEN NOT MATCHED BY TARGET THEN INSERT" in sql
    batches = dw.ddl_batches()
    assert any("GROUP BY ROLLUP" in b for b in batches)
    assert all("CREATE TABLE" not in b or "IS NULL" in b for b in batches)


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


def test_forbidden_access_demo_writes_a_denied_audit_entry(client: TestClient, s: Session) -> None:
    make_customer(s)
    body = client.post(
        "/api/v1/demo/forbidden-access", headers=headers(Role.ADMIN, sub="andrea")
    ).json()
    assert body["status_code"] == 403 and body["simulated"] is True
    assert body["audit"]["actor_role"] == "Marketing" and body["audit"]["allowed"] is False
    assert body["audit"]["action"].endswith("/reveal-pii")
