"""Centro de Operaciones (KPIs) and Data Pipelines."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, require_roles
from chaski_common.db import get_db
from chaski_common.logging import get_logger
from chaski_common.models import PipelineRun, QualityCheck, QuarantineRecord
from chaski_common.roles import STAFF_ROLES, Role
from chaski_common.schemas import ApiModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core_api.services import pipeline_sim
from core_api.settings import get_settings

router = APIRouter(prefix="/ops", tags=["operaciones"])
log = get_logger(__name__)
PIPELINE_ROLES = (Role.TI, Role.ADMIN)

# "Today" is the calendar day in Lima. Ranges on created_at keep the indexes usable.
_KPIS = text(
    """
    WITH d AS (
      SELECT date_trunc('day', now() AT TIME ZONE 'America/Lima')
               AT TIME ZONE 'America/Lima' AS start
    ),
    tx AS (
      SELECT count(*) AS n,
             coalesce(sum(CASE WHEN currency = 'USD' THEN amount * 3.75 ELSE amount END), 0)
               AS amount
      FROM core.transactions, d WHERE created_at >= d.start
    ),
    lo AS (
      SELECT coalesce(sum(outstanding_balance), 0) AS portfolio,
             coalesce(sum(outstanding_balance) FILTER (WHERE days_past_due > 30), 0) AS overdue,
             count(*) FILTER (WHERE status = 'SOLICITADO') AS pending
      FROM core.loans WHERE status IN ('DESEMBOLSADO', 'SOLICITADO')
    ),
    co AS (
      SELECT count(*) AS open,
             count(*) FILTER (WHERE due_at < now() + interval '3 days') AS due_soon
      FROM core.complaints WHERE status <> 'RESUELTA'
    )
    SELECT tx.n AS tx_count, tx.amount AS tx_amount,
           (SELECT count(*) FROM core.customers, d WHERE created_at >= d.start) AS new_customers,
           lo.portfolio, lo.overdue, lo.pending AS loans_pending,
           (SELECT count(*) FROM ops.fraud_alerts WHERE status = 'ABIERTA') AS open_alerts,
           co.open AS open_complaints, co.due_soon AS complaints_due_soon,
           (SELECT count(*) FROM core.customers WHERE kyc_status = 'PENDIENTE') AS kyc_pending
    FROM tx, lo, co
    """
)

_BY_HOUR = text(
    """
    SELECT extract(hour FROM created_at AT TIME ZONE 'America/Lima')::int AS hora,
           count(*) AS cantidad,
           coalesce(sum(CASE WHEN currency = 'USD' THEN amount * 3.75 ELSE amount END), 0)
             AS monto
    FROM core.transactions
    WHERE created_at >= (CAST(:day AS date)::timestamp AT TIME ZONE 'America/Lima')
      AND created_at < ((CAST(:day AS date) + 1)::timestamp AT TIME ZONE 'America/Lima')
    GROUP BY 1 ORDER BY 1
    """
)


class KpisOut(BaseModel):
    transacciones_hoy: int
    monto_transado_hoy: float
    clientes_nuevos_hoy: int
    cartera_total: float
    mora_pct: float
    alertas_abiertas: int
    quejas_abiertas: int
    quejas_por_vencer: int
    prestamos_por_revisar: int
    onboarding_pendiente: int
    generado_en: datetime


class PipelineRunOut(ApiModel):
    id: uuid.UUID
    flow_name: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    rows_in: int
    rows_ok: int
    rows_quarantined: int
    error: str | None


class QualityCheckOut(ApiModel):
    check_name: str
    table_name: str
    passed: bool
    failed_count: int


class QuarantineOut(ApiModel):
    id: int
    run_id: uuid.UUID | None
    table_name: str
    reason: str
    payload: dict[str, Any]
    created_at: datetime


@router.get("/kpis", response_model=KpisOut)
def kpis(
    _user: CurrentUser = Depends(require_roles(*STAFF_ROLES)), db: Session = Depends(get_db)
) -> KpisOut:
    r = db.execute(_KPIS).one()
    portfolio = float(r.portfolio)
    return KpisOut(
        transacciones_hoy=r.tx_count,
        monto_transado_hoy=round(float(r.tx_amount), 2),
        clientes_nuevos_hoy=r.new_customers,
        cartera_total=round(portfolio, 2),
        mora_pct=round(float(r.overdue) / portfolio * 100, 2) if portfolio else 0.0,
        alertas_abiertas=r.open_alerts,
        quejas_abiertas=r.open_complaints,
        quejas_por_vencer=r.complaints_due_soon,
        prestamos_por_revisar=r.loans_pending,
        onboarding_pendiente=r.kyc_pending,
        generado_en=datetime.now(UTC),
    )


@router.get("/transactions-by-hour")
def transactions_by_hour(
    day: date | None = None,
    _user: CurrentUser = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    if day is None:
        day = db.scalar(text("SELECT (now() AT TIME ZONE 'America/Lima')::date"))
    found = {r.hora: r for r in db.execute(_BY_HOUR, {"day": day})}
    return [
        {"hora": h, "cantidad": found[h].cantidad if h in found else 0,
         "monto": round(float(found[h].monto), 2) if h in found else 0.0}
        for h in range(24)
    ]  # fmt: skip


@router.get("/pipelines", response_model=list[PipelineRunOut])
def pipelines(
    limit: int = Query(default=20, ge=1, le=100),
    _user: CurrentUser = Depends(require_roles(*PIPELINE_ROLES)),
    db: Session = Depends(get_db),
) -> list[PipelineRun]:
    return list(
        db.scalars(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit))
    )


@router.get("/pipelines/{run_id}/checks", response_model=list[QualityCheckOut])
def pipeline_checks(
    run_id: uuid.UUID,
    _user: CurrentUser = Depends(require_roles(*PIPELINE_ROLES)),
    db: Session = Depends(get_db),
) -> list[QualityCheck]:
    if db.get(PipelineRun, run_id) is None:
        raise HTTPException(404, "Corrida no encontrada")
    return list(
        db.scalars(
            select(QualityCheck).where(QualityCheck.run_id == run_id).order_by(QualityCheck.id)
        )
    )


@router.get("/quarantine", response_model=list[QuarantineOut])
def quarantine(
    limit: int = Query(default=50, ge=1, le=500),
    _user: CurrentUser = Depends(require_roles(*PIPELINE_ROLES)),
    db: Session = Depends(get_db),
) -> list[QuarantineRecord]:
    return list(
        db.scalars(
            select(QuarantineRecord).order_by(QuarantineRecord.created_at.desc()).limit(limit)
        )
    )


def _start_container_apps_job() -> str:
    """Starts the pipeline Container Apps Job via ARM using the app's Managed Identity."""
    from azure.identity import DefaultAzureCredential

    s = get_settings()
    token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token
    url = (
        f"https://management.azure.com/subscriptions/{s.azure_subscription_id}"
        f"/resourceGroups/{s.azure_resource_group}/providers/Microsoft.App/jobs/"
        f"{s.pipeline_job_name}/start?api-version=2024-03-01"
    )
    resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, json={}, timeout=20)
    resp.raise_for_status()
    return str(resp.json().get("name", "iniciado"))


@router.post("/pipelines/run", status_code=202)
def run_pipeline(
    request: Request,
    user: CurrentUser = Depends(require_roles(*PIPELINE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    if settings.pipeline_job_configured:
        try:
            execution = _start_container_apps_job()
        except Exception as exc:
            log.exception("pipeline_job_start_failed")
            raise HTTPException(502, "No se pudo iniciar el job del pipeline en Azure") from exc
        result: dict[str, Any] = {"mode": "azure", "execution": execution}
    else:
        run = pipeline_sim.run_local(db)
        db.commit()
        result = {
            "mode": "local",
            "run": PipelineRunOut.model_validate(run).model_dump(mode="json"),
        }
    audit.record(actor=user, action="PIPELINE_RUN", resource="pipeline", ip=client_ip(request))
    return result
