"""Chaski Insights. Reads the gold views from ANALYTICS_DB_URL (local Postgres `gold`, or Azure
SQL in Azure). Queries use portable SQL only (no LIMIT/TOP, no dialect-specific functions)."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Literal

from chaski_common.auth import CurrentUser, require_roles
from chaski_common.db import get_engine
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, create_engine, text

from core_api.settings import get_settings

router = APIRouter(prefix="/analytics", tags=["analítica"])
ANALYTICS_ROLES = (Role.DIRECCION, Role.RIESGOS, Role.MARKETING, Role.ADMIN)
DIMENSIONS = {"product": "producto", "segment": "segmento", "region": "region"}


@lru_cache
def analytics_engine() -> Engine:
    url = get_settings().analytics_db_url
    return create_engine(url, pool_pre_ping=True) if url else get_engine()


def _rows(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    with analytics_engine().connect() as conn:
        return [
            {k: (float(v) if hasattr(v, "is_finite") else v) for k, v in r._mapping.items()}
            for r in conn.execute(text(sql), params)
        ]


@router.get("/profitability")
def profitability(
    dimension: Literal["product", "segment", "region"] = "product",
    months: int = Query(default=6, ge=1, le=24),
    _user: CurrentUser = Depends(require_roles(*ANALYTICS_ROLES)),
) -> dict[str, Any]:
    col = DIMENSIONS[dimension]  # allow-listed column name, never user text
    since = (date.today().replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    params = {"since": since}
    by_dimension = _rows(
        f"""
        SELECT {col} AS dimension,
               sum(ingresos_intereses) AS ingresos_intereses, sum(comisiones) AS comisiones,
               sum(costo_fondeo) AS costo_fondeo, sum(provisiones) AS provisiones,
               sum(margen) AS margen
        FROM gold.v_rentabilidad WHERE mes >= :since
        GROUP BY {col} ORDER BY sum(margen) DESC
        """,  # noqa: S608 - {col} comes from the DIMENSIONS allow-list
        params,
    )
    monthly = _rows(
        """
        SELECT mes, sum(ingresos_intereses + comisiones) AS ingresos, sum(margen) AS margen
        FROM gold.v_rentabilidad WHERE mes >= :since
        GROUP BY mes ORDER BY mes
        """,
        params,
    )
    return {
        "dimension": dimension,
        "since": since,
        "by_dimension": by_dimension,
        "monthly": monthly,
    }


@router.get("/delinquency")
def delinquency(
    days: int = Query(default=90, ge=7, le=180),
    _user: CurrentUser = Depends(require_roles(*ANALYTICS_ROLES)),
) -> dict[str, Any]:
    latest = _rows("SELECT max(fecha) AS fecha FROM gold.v_morosidad", {})[0]["fecha"]
    if latest is None:
        return {"fecha": None, "by_bucket": [], "by_region": [], "trend": []}
    by_bucket = _rows(
        """
        SELECT bucket, sum(prestamos) AS prestamos, sum(saldo) AS saldo
        FROM gold.v_morosidad WHERE fecha = :d GROUP BY bucket
        """,
        {"d": latest},
    )
    order = ["Normal", "CPP", "Deficiente", "Dudoso", "Pérdida"]
    by_bucket.sort(key=lambda r: order.index(r["bucket"]) if r["bucket"] in order else 99)
    by_region = _rows(
        """
        SELECT region, sum(saldo) AS saldo, sum(saldo_vencido_30) AS saldo_vencido_30
        FROM gold.v_morosidad WHERE fecha = :d GROUP BY region ORDER BY region
        """,
        {"d": latest},
    )
    for r in by_region:
        r["mora_pct"] = round(r["saldo_vencido_30"] / r["saldo"] * 100, 2) if r["saldo"] else 0.0
    trend = _rows(
        """
        SELECT fecha, sum(saldo_vencido_30) AS saldo_vencido_30, sum(saldo) AS saldo
        FROM gold.v_morosidad WHERE fecha >= :since GROUP BY fecha ORDER BY fecha
        """,
        {"since": latest - timedelta(days=days)},
    )
    for r in trend:
        r["mora_pct"] = round(r["saldo_vencido_30"] / r["saldo"] * 100, 2) if r["saldo"] else 0.0
    return {"fecha": latest, "by_bucket": by_bucket, "by_region": by_region, "trend": trend}
