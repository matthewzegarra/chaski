"""Executive summary (8.4), NL2SQL "Pregúntale al banco" (8.5) and AI health metrics."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

from chaski_common.auth import CurrentUser, require_roles
from chaski_common.db import get_engine
from chaski_common.logging import get_logger
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, text

from ia_api import nl2sql, pipeline
from ia_api.numbers import numbers_in, unsupported_numbers
from ia_api.prompts import load_prompt
from ia_api.settings import get_settings

router = APIRouter(tags=["ia"])
log = get_logger(__name__)
MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
    "octubre", "noviembre", "diciembre",
)  # fmt: skip
NL2SQL_TIMEOUT_MS = 10_000


@lru_cache
def analytics_engine() -> Engine:
    url = get_settings().analytics_db_url
    return create_engine(url, pool_pre_ping=True) if url else get_engine()


@lru_cache
def readonly_engine() -> Engine:
    s = get_settings()
    url = s.nl2sql_db_url or s.analytics_db_url
    if not url:
        raise RuntimeError("NL2SQL_DB_URL is not configured")
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date | datetime):
        return v.isoformat()
    return v


def _rows(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [
            {k: _jsonable(v) for k, v in r._mapping.items()}
            for r in conn.execute(text(sql), params or {})
        ]


# ------------------------------------------------------------------ executive summary


def _money(v: float) -> str:
    return f"S/ {v:,.2f}"


def _millions(v: float) -> str:
    return f"S/ {v / 1_000_000:,.2f} M"


def compute_kpis(today: date | None = None) -> dict[str, Any]:
    """KPIs of the last complete month, with portable SQL over the gold views."""
    eng = analytics_engine()
    today = today or date.today()
    month_start = today.replace(day=1)
    months = [
        r["mes"] for r in _rows(eng, "SELECT DISTINCT mes FROM gold.v_rentabilidad ORDER BY mes")
    ]
    closed = [m for m in months if date.fromisoformat(m) < month_start]
    if len(closed) < 2:
        raise HTTPException(409, "No hay suficientes meses cerrados en gold para el resumen")
    current, previous = closed[-1], closed[-2]
    margins = {
        r["mes"]: r["margen"]
        for r in _rows(
            eng,
            "SELECT mes, sum(margen) AS margen FROM gold.v_rentabilidad "
            "WHERE mes IN (:a, :b) GROUP BY mes",
            {"a": current, "b": previous},
        )
    }
    by_product = _rows(
        eng,
        "SELECT producto, sum(margen) AS margen FROM gold.v_rentabilidad WHERE mes = :m "
        "GROUP BY producto ORDER BY sum(margen) DESC",
        {"m": current},
    )
    latest = _rows(eng, "SELECT max(fecha) AS fecha FROM gold.v_morosidad")[0]["fecha"]
    mora = _rows(
        eng,
        "SELECT sum(saldo_vencido_30) AS vencido, sum(saldo) AS saldo FROM gold.v_morosidad WHERE fecha = :d",
        {"d": latest},
    )[0]
    regions = _rows(
        eng,
        "SELECT region, sum(saldo_vencido_30) AS vencido, sum(saldo) AS saldo FROM gold.v_morosidad "
        "WHERE fecha = :d GROUP BY region",
        {"d": latest},
    )
    clients = _rows(eng, "SELECT sum(clientes) AS clientes FROM gold.v_clientes_resumen")[0][
        "clientes"
    ]

    margin, prev_margin = float(margins[current]), float(margins[previous])
    variation = round((margin - prev_margin) / abs(prev_margin) * 100, 1) if prev_margin else 0.0
    mora_pct = (
        round(float(mora["vencido"]) / float(mora["saldo"]) * 100, 2) if mora["saldo"] else 0.0
    )
    worst = max(
        regions, key=lambda r: (float(r["vencido"]) / float(r["saldo"])) if r["saldo"] else 0
    )
    worst_pct = (
        round(float(worst["vencido"]) / float(worst["saldo"]) * 100, 2) if worst["saldo"] else 0.0
    )
    month = date.fromisoformat(current)
    top = by_product[0]
    return {
        "periodo": f"{MONTHS[month.month - 1]} de {month.year}",
        "anio": month.year,
        "margen_mes": round(margin, 2),
        "margen_mes_anterior": round(prev_margin, 2),
        "variacion_margen_pct": variation,
        "producto_top": top["producto"],
        "margen_producto_top": round(float(top["margen"]), 2),
        "mora_pct": mora_pct,
        "umbral_mora_dias": 30,  # mora = saldo con más de 30 días de atraso / saldo total
        "fecha_mora": latest,
        "region_mayor_mora": worst["region"],
        "mora_region_top_pct": worst_pct,
        "clientes": int(clients or 0),
        "texto": {
            "periodo": f"{MONTHS[month.month - 1]} de {month.year}",
            "margen_mes": _millions(margin),
            "variacion_margen_abs_pct": f"{abs(variation):.1f} %",
            "margen_producto_top": _money(float(top["margen"])),
            "mora_pct": f"{mora_pct:.2f} %",
            "mora_region_top_pct": f"{worst_pct:.2f} %",
            "clientes": f"{int(clients or 0):,}",
        },
    }


class SummaryText(BaseModel):
    resumen: str = Field(max_length=3000)


class SummaryOut(BaseModel):
    resumen: str
    kpis: dict[str, Any]
    valido: bool
    numeros_no_validados: list[float]
    requiere_revision: bool
    publicado: bool


def validate_summary(summary: str, kpis: dict[str, Any]) -> list[float]:
    """Numbers in the summary that are not backed by a KPI (empty list = valid)."""
    return [float(n) for n in unsupported_numbers(summary, numbers_in(kpis))]


@router.post("/reports/executive-summary", response_model=SummaryOut)
def executive_summary(
    _user: CurrentUser = Depends(require_roles(Role.DIRECCION, Role.ADMIN)),
) -> SummaryOut:
    kpis = compute_kpis()
    try:
        outcome = pipeline.run_structured(
            use_case="executive_summary",
            prompt=load_prompt("executive_summary"),
            user_text=json.dumps(kpis, ensure_ascii=False, default=str),
            model=SummaryText,
        )
    except pipeline.AiUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    assert outcome.output is not None
    bad = validate_summary(outcome.output.resumen, kpis)
    if bad:
        log.warning("executive_summary_rejected", unsupported=len(bad))
    return SummaryOut(
        resumen=outcome.output.resumen,
        kpis=kpis,
        valido=not bad,
        numeros_no_validados=bad,
        requiere_revision=bool(bad),
        publicado=not bad,
    )


# ------------------------------------------------------------------ NL2SQL


class AskIn(BaseModel):
    pregunta: str = Field(min_length=3, max_length=500)


class GeneratedSql(BaseModel):
    sql: str = Field(max_length=4000)
    grafico: str = Field(pattern="^(bar|line|table)$")
    explicacion: str = Field(max_length=500)


class AskOut(BaseModel):
    respuesta: str
    columnas: list[str]
    filas: list[dict[str, Any]]
    grafico: str
    sql: str


def execute_readonly(sql: str) -> list[dict[str, Any]]:
    engine = readonly_engine()
    with engine.connect() as conn, conn.begin():
        if engine.dialect.name == "postgresql":
            conn.execute(text(f"SET LOCAL statement_timeout = {NL2SQL_TIMEOUT_MS}"))
        result = conn.execute(text(sql))
        return [
            {k: _jsonable(v) for k, v in r._mapping.items()}
            for r in result.fetchmany(nl2sql.MAX_ROWS)
        ]


@router.post("/analytics/ask", response_model=AskOut)
def ask(
    body: AskIn,
    _user: CurrentUser = Depends(
        require_roles(Role.DIRECCION, Role.RIESGOS, Role.MARKETING, Role.ADMIN)
    ),
) -> AskOut:
    try:
        outcome = pipeline.run_structured(
            use_case="nl2sql",
            prompt=load_prompt("nl2sql"),
            user_text=body.pregunta,
            model=GeneratedSql,
            shield_text=body.pregunta,
        )
    except pipeline.AiUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if outcome.blocked or outcome.output is None:
        raise HTTPException(422, "La pregunta fue bloqueada por Prompt Shields")
    generated = outcome.output
    if not generated.sql.strip():
        return AskOut(
            respuesta=generated.explicacion, columnas=[], filas=[], grafico="table", sql=""
        )
    try:
        safe = nl2sql.validate_sql(generated.sql, dialect=get_settings().analytics_dialect)
    except nl2sql.UnsafeSQL as exc:
        log.warning("nl2sql_rejected", reason=str(exc))
        raise HTTPException(422, f"Consulta rechazada por seguridad: {exc}") from exc
    try:
        rows = execute_readonly(safe)
    except Exception as exc:
        log.warning("nl2sql_execution_failed", error_type=type(exc).__name__)
        raise HTTPException(422, "No se pudo ejecutar la consulta generada") from exc
    columns = list(rows[0].keys()) if rows else []
    answer = (
        f"{generated.explicacion} Encontré {len(rows)} resultado{'s' if len(rows) != 1 else ''}."
    )
    return AskOut(
        respuesta=answer, columnas=columns, filas=rows, grafico=generated.grafico, sql=safe
    )


# ------------------------------------------------------------------ AI health


@router.get("/ai/health-metrics")
def health_metrics(
    _user: CurrentUser = Depends(require_roles(Role.TI, Role.ADMIN)),
) -> dict[str, Any]:
    eng = get_engine()
    since = datetime.now().astimezone() - timedelta(days=90)
    by_case = _rows(
        eng,
        """
        SELECT use_case,
               count(*) AS llamadas,
               round(avg(latency_ms)) AS latencia_promedio_ms,
               round(CAST(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS numeric)) AS latencia_p95_ms,
               count(*) FILTER (WHERE blocked_by_shields) AS bloqueos_shields,
               max(prompt_version) AS version_prompt,
               max(prompt_id) AS prompt_id,
               string_agg(DISTINCT provider, ', ') AS proveedores
        FROM ops.ai_interactions WHERE created_at >= :since
        GROUP BY use_case ORDER BY use_case
        """,
        {"since": since},
    )
    quality = _rows(
        eng,
        """
        SELECT count(*) FILTER (WHERE status = 'RESUELTA' AND ai_category IS NOT NULL) AS resueltas,
               count(*) FILTER (WHERE status = 'RESUELTA' AND ai_category = final_category) AS aciertos,
               count(*) AS total,
               count(*) FILTER (WHERE ai_category IS NULL OR ai_category = 'FRAUDE'
                                OR ai_confidence < 0.8 OR ai_suspicious) AS a_revision,
               count(*) FILTER (WHERE ai_suspicious) AS sospechosas
        FROM core.complaints WHERE created_at >= :since
        """,
        {"since": since},
    )[0]
    overrides = _rows(
        eng,
        "SELECT count(*) FILTER (WHERE human_override) AS corregidas, count(human_override) AS revisadas "
        "FROM ops.ai_interactions WHERE use_case = 'complaint_classification' AND created_at >= :since",
        {"since": since},
    )[0]
    weekly = _rows(
        eng,
        "SELECT count(*) AS bloqueos FROM ops.ai_interactions WHERE blocked_by_shields "
        "AND created_at >= :week",
        {"week": datetime.now().astimezone() - timedelta(days=7)},
    )[0]
    resolved = quality["resueltas"] or 0
    total = quality["total"] or 0
    return {
        "ventana_dias": 90,
        "precision_ia_vs_humano_pct": round(quality["aciertos"] / resolved * 100, 1)
        if resolved
        else None,
        "quejas_resueltas_evaluadas": resolved,
        "tasa_revision_manual_pct": round(quality["a_revision"] / total * 100, 1)
        if total
        else None,
        "quejas_sospechosas": quality["sospechosas"],
        "correcciones_humanas": overrides["corregidas"],
        "bloqueos_prompt_shields_7d": weekly["bloqueos"],
        "por_caso_de_uso": by_case,
        "modo": get_settings().ai_mode,
    }
