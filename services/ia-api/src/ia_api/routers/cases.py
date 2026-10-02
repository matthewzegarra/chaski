"""Use cases: complaint classification, loan scoring, assistant and KYC extraction."""

from __future__ import annotations

import json
import time
import uuid
from typing import Literal

from chaski_common.auth import CurrentUser, require_customer, require_roles
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ia_api import assistant, pipeline
from ia_api.prompts import Prompt, load_prompt
from ia_api.providers.docintel import get_docintel
from ia_api.scoring import Factor, LoanFacts, score_loan

router = APIRouter(tags=["ia"])

Category = Literal["FRAUDE", "COBRO_INDEBIDO", "TARJETA", "PRESTAMO", "CANAL_DIGITAL", "OTRO"]
Urgency = Literal["ALTA", "MEDIA", "BAJA"]
REVIEW_CONFIDENCE = 0.8


# ------------------------------------------------------------------ complaints (8.1)


class ComplaintIn(BaseModel):
    complaint_id: uuid.UUID | None = None
    asunto: str = Field(default="", max_length=200)
    texto: str = Field(min_length=1, max_length=4000)


class Classification(BaseModel):
    categoria: Category
    urgencia: Urgency
    confianza: float = Field(ge=0, le=1)
    motivo: str = Field(max_length=300)
    sospechosa: bool


class ClassificationOut(Classification):
    requiere_revision: bool
    bloqueada_por_shields: bool
    prompt_version: str


def requires_review(c: Classification) -> bool:
    return c.categoria == "FRAUDE" or c.confianza < REVIEW_CONFIDENCE or c.sospechosa


@router.post("/complaints/classify", response_model=ClassificationOut)
def classify_complaint(
    body: ComplaintIn,
    _user: CurrentUser = Depends(require_roles(Role.CLIENTE, Role.ATENCION, Role.ADMIN)),
) -> ClassificationOut:
    prompt = load_prompt("complaint_classifier")
    text = f"Asunto: {body.asunto}\n{body.texto}".strip()
    extra = {"complaint_id": str(body.complaint_id)} if body.complaint_id else {}
    try:
        outcome = pipeline.run_structured(
            use_case="complaint_classification",
            prompt=prompt,
            user_text=f"<queja>{text}</queja>",
            model=Classification,
            shield_text=text,
            confidence_field="confianza",
            extra_log=extra,
        )
    except pipeline.AiUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if outcome.blocked or outcome.output is None:
        result = Classification(
            categoria="OTRO", urgencia="ALTA", confianza=0.0, sospechosa=True,
            motivo="Prompt Shields detectó un posible intento de manipulación del sistema",
        )  # fmt: skip
    else:
        result = outcome.output
    return ClassificationOut(
        **result.model_dump(),
        requiere_revision=requires_review(result),
        bloqueada_por_shields=outcome.blocked,
        prompt_version=prompt.version,
    )


# ------------------------------------------------------------------ loan scoring (8.2)


class LoanExplanation(BaseModel):
    explicacion: str = Field(max_length=1200)


class ScoreOut(BaseModel):
    score: int
    recomendacion: Literal["APROBAR", "REVISAR", "RECHAZAR"]
    endeudamiento_pct: float | None
    factores: list[Factor]
    explicacion: str
    nota: str = "Sugerencia de la IA: la decisión final corresponde a Riesgos."


@router.post("/loans/score", response_model=ScoreOut)
def loan_score(
    facts: LoanFacts,
    _user: CurrentUser = Depends(require_roles(Role.CLIENTE, Role.RIESGOS)),
) -> ScoreOut:
    rules = score_loan(facts)
    payload = {
        "score": rules.score,
        "recomendacion": rules.recomendacion,
        "factores": [f.model_dump() for f in rules.factores],
    }
    explanation = " ".join(f.detalle + "." for f in rules.factores[:3])
    try:
        outcome = pipeline.run_structured(
            use_case="loan_explanation",
            prompt=load_prompt("loan_explainer"),
            user_text=json.dumps(payload, ensure_ascii=False),
            model=LoanExplanation,
            extra_log={"loan_id": facts.loan_id, "score": rules.score},
        )
        if outcome.output is not None:
            explanation = outcome.output.explicacion
    except pipeline.AiUnavailable:
        pass  # the rule-based factors are still a valid explanation
    return ScoreOut(
        score=rules.score,
        recomendacion=rules.recomendacion,
        endeudamiento_pct=rules.endeudamiento_pct,
        factores=rules.factores,
        explicacion=explanation,
    )


# ------------------------------------------------------------------ assistant (8.3)


@router.post("/assistant/chat", response_model=assistant.ChatOut)
def assistant_chat(
    body: assistant.ChatIn, user: CurrentUser = Depends(require_customer)
) -> assistant.ChatOut:
    return assistant.chat(user, body)


# ------------------------------------------------------------------ KYC


class KycOut(BaseModel):
    datos: dict[str, str]
    confianza: float
    modelo: str


MAX_IMAGE = 5 * 1024 * 1024
_KYC_PROMPT = Prompt(
    id="docintel-idDocument", version="2024-11-30", owner="onboarding", description="", text=""
)


@router.post("/kyc/extract", response_model=KycOut)
async def kyc_extract(
    image: UploadFile = File(),
    expected_document_number: str = Form(default=""),
    expected_first_name: str = Form(default=""),
    expected_last_name: str = Form(default=""),
    expected_birth_date: str = Form(default=""),
    _user: CurrentUser = Depends(require_roles(Role.OPERACIONES, Role.ATENCION, Role.ADMIN)),
) -> KycOut:
    data = await image.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "La imagen supera los 5 MB")
    expected = {
        "numero_documento": expected_document_number,
        "nombres": expected_first_name,
        "apellidos": expected_last_name,
        "fecha_nacimiento": expected_birth_date,
    }
    start = time.perf_counter()
    provider = get_docintel()
    try:
        result = provider.extract(data, image.content_type or "image/jpeg", expected)
    except Exception as exc:
        raise HTTPException(503, "No se pudo leer el documento") from exc
    # Only field names are stored: extracted values go back to core-api and are never logged.
    pipeline.record(
        use_case="kyc_extraction", prompt=_KYC_PROMPT, input_text=f"imagen {len(data)} bytes",
        output={"campos": sorted(result.datos), "modelo": result.modelo},
        latency_ms=int((time.perf_counter() - start) * 1000), result=None,
        confidence=result.confianza, provider=provider.name,
    )  # fmt: skip
    return KycOut(datos=result.datos, confianza=result.confianza, modelo=result.modelo)
