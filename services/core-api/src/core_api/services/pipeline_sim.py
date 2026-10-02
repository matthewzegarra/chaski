"""Local stand-in for the Prefect pipeline: validates pending raw rows, quarantines bad ones
and records the run with its quality checks (same tables the real pipeline writes)."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from chaski_common.models import (
    Account,
    PipelineRun,
    QualityCheck,
    QuarantineRecord,
    RawIngest,
    Transaction,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

FLOW_NAME = "ingesta_transacciones_diaria"
TABLE = "silver.transactions"
CHECKS = (
    "ids_no_nulos",
    "montos_positivos",
    "moneda_valida",
    "fecha_no_futura",
    "sin_duplicados",
    "cuenta_existe",
)


def _failed_checks(payload: dict[str, Any], seen: Counter[str], accounts: set[str]) -> list[str]:
    failed = []
    if not payload.get("transaction_id") or not payload.get("account_id"):
        failed.append("ids_no_nulos")
    try:
        if Decimal(str(payload.get("amount"))) <= 0:
            failed.append("montos_positivos")
    except (InvalidOperation, ValueError):
        failed.append("montos_positivos")
    if payload.get("currency") not in ("PEN", "USD"):
        failed.append("moneda_valida")
    try:
        if datetime.fromisoformat(str(payload.get("created_at"))) > datetime.now(UTC):
            failed.append("fecha_no_futura")
    except ValueError:
        failed.append("fecha_no_futura")
    if seen[str(payload.get("transaction_id"))] > 1:
        failed.append("sin_duplicados")
    if str(payload.get("account_id")) not in accounts:
        failed.append("cuenta_existe")
    return failed


def run_local(db: Session, trigger: str = "MANUAL") -> PipelineRun:
    started = datetime.now(UTC)
    run = PipelineRun(
        id=uuid.uuid4(), flow_name=FLOW_NAME, status="EN_CURSO", trigger=trigger, started_at=started
    )
    db.add(run)
    db.flush()

    raw_rows = db.scalars(
        select(RawIngest).where(RawIngest.processed_at.is_(None)).order_by(RawIngest.id)
    ).all()
    ids = Counter(str(r.payload.get("transaction_id")) for r in raw_rows)
    account_ids = {str(r.payload.get("account_id")) for r in raw_rows}
    known = {
        str(a) for a in db.scalars(select(Account.id).where(Account.id.in_(_uuids(account_ids))))
    }
    failures: Counter[str] = Counter()
    quarantined = 0
    for row in raw_rows:
        failed = _failed_checks(row.payload, ids, known)
        failures.update(failed)
        if failed:
            quarantined += 1
            db.add(
                QuarantineRecord(
                    run_id=run.id, raw_id=row.id, table_name=TABLE,
                    reason="Falló: " + ", ".join(failed), payload=row.payload,
                )
            )  # fmt: skip
        row.processed_at = started

    # Transactions posted by the APIs since the previous run are ingested too.
    last = db.scalar(
        select(func.max(PipelineRun.started_at)).where(
            PipelineRun.id != run.id, PipelineRun.status != "FALLIDO"
        )
    )
    streamed = (
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.created_at > (last or started))
        )
        or 0
    )

    run.rows_in = len(raw_rows) + streamed
    run.rows_quarantined = quarantined
    run.rows_ok = run.rows_in - quarantined
    run.status = "CON_ALERTAS" if quarantined else "EXITOSO"
    run.finished_at = datetime.now(UTC)
    for name in CHECKS:
        db.add(
            QualityCheck(
                run_id=run.id, check_name=name, table_name=TABLE,
                passed=failures[name] == 0, failed_count=failures[name],
            )
        )  # fmt: skip
    db.flush()
    return run


def _uuids(values: set[str]) -> list[uuid.UUID]:
    out = []
    for v in values:
        try:
            out.append(uuid.UUID(v))
        except ValueError:
            continue
    return out
