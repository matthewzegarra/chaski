"""Rule-based consumer-loan score (300-900). The LLM only explains it; Riesgos decides."""

from __future__ import annotations

from dataclasses import dataclass

from chaski_common.schemas import ApiModel
from pydantic import BaseModel, Field


class LoanFacts(BaseModel):
    loan_id: str | None = None
    monto: float = Field(gt=0)
    plazo_meses: int = Field(gt=0)
    cuota_estimada: float = Field(ge=0)
    ingreso_mensual: float = Field(ge=0)
    deuda_mensual_actual: float = Field(default=0, ge=0)
    segmento: str = "MASIVO"
    nivel_riesgo: str = "BAJO"
    prestamos_previos: int = Field(default=0, ge=0)
    max_dias_atraso_historico: int = Field(default=0, ge=0)


class Factor(ApiModel):
    factor: str
    impacto: int
    detalle: str


@dataclass
class ScoreResult:
    score: int
    recomendacion: str
    endeudamiento_pct: float | None
    factores: list[Factor]


def score_loan(f: LoanFacts) -> ScoreResult:
    factors: list[Factor] = []

    def add(name: str, impact: int, detail: str) -> None:
        factors.append(Factor(factor=name, impacto=impact, detalle=detail))

    dti: float | None = None
    if f.ingreso_mensual <= 0:
        add("Ingreso no declarado", -150, "El cliente no tiene un ingreso mensual registrado")
    else:
        dti = round((f.deuda_mensual_actual + f.cuota_estimada) / f.ingreso_mensual * 100, 1)
        if dti < 20:
            add("Endeudamiento", 120, f"La cuota total representa el {dti} % del ingreso")
        elif dti < 35:
            add("Endeudamiento", 60, f"La cuota total representa el {dti} % del ingreso")
        elif dti < 50:
            add("Endeudamiento", -40, f"La cuota total representa el {dti} % del ingreso")
        else:
            add(
                "Endeudamiento",
                -150,
                f"La cuota total representa el {dti} % del ingreso, por encima de 50 %",
            )

    if f.max_dias_atraso_historico == 0 and f.prestamos_previos > 0:
        add("Historial de pago", 60, f"Sin atrasos en {f.prestamos_previos} préstamos previos")
    elif f.max_dias_atraso_historico == 0:
        add("Historial de pago", 0, "Primer préstamo con el banco, sin historial")
    elif f.max_dias_atraso_historico <= 30:
        add("Historial de pago", -60, f"Tuvo atrasos de hasta {f.max_dias_atraso_historico} días")
    else:
        add("Historial de pago", -180, f"Tuvo atrasos de {f.max_dias_atraso_historico} días")

    risk = {"BAJO": 20, "MEDIO": -30, "ALTO": -80}.get(f.nivel_riesgo, 0)
    add("Nivel de riesgo", risk, f"Nivel de riesgo del cliente: {f.nivel_riesgo.lower()}")

    seg = {"PREFERENTE": 40, "PYME": 10, "MASIVO": 0}.get(f.segmento, 0)
    if seg:
        add("Segmento", seg, f"Cliente del segmento {f.segmento.lower()}")

    if f.plazo_meses > 48:
        add("Plazo", -20, f"Plazo largo de {f.plazo_meses} meses")

    score = max(300, min(900, 600 + sum(x.impacto for x in factors)))
    recommendation = "APROBAR" if score >= 650 else "REVISAR" if score >= 520 else "RECHAZAR"
    factors.sort(key=lambda x: abs(x.impacto), reverse=True)
    return ScoreResult(
        score=score, recomendacion=recommendation, endeudamiento_pct=dti, factores=factors
    )
