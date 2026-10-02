"""Digital onboarding: personal data + DNI photo -> AI extraction -> human KYC decision."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, require_roles
from chaski_common.db import get_db
from chaski_common.masking import mask_dni
from chaski_common.models import Customer, KycDocument
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api import ia_client, storage
from core_api.routers.customers import CustomerMasked, masked
from core_api.services.issuance import open_starter_products

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

REGIONS = ("Lima", "Arequipa", "La Libertad", "Piura", "Cusco", "Junín", "Lambayeque", "Loreto")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_email = TypeAdapter(EmailStr)


class OnboardingOut(BaseModel):
    customer_id: uuid.UUID
    kyc_status: str
    extracted: dict[str, Any] | None
    confidence: float | None
    checks: dict[str, bool | None]
    message: str


class PendingOut(BaseModel):
    customer: CustomerMasked
    document_id: uuid.UUID | None
    extracted: dict[str, Any] | None
    confidence: float | None
    checks: dict[str, bool | None]


class DecisionIn(BaseModel):
    decision: Literal["APROBADO", "RECHAZADO"]
    reason: str | None = Field(default=None, max_length=300)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().upper()


def compare(customer: Customer, extracted: dict[str, Any] | None) -> dict[str, bool | None]:
    """Typed data vs data read from the DNI (None = could not be read)."""
    if not extracted:
        return {"dni_coincide": None, "nombres_coinciden": None, "fecha_nacimiento_coincide": None}
    names = extracted.get("nombres")
    surnames = extracted.get("apellidos")
    birth = extracted.get("fecha_nacimiento")
    return {
        "dni_coincide": extracted.get("numero_documento") == customer.document_number
        if extracted.get("numero_documento")
        else None,
        "nombres_coinciden": (
            _norm(f"{names} {surnames}") == _norm(f"{customer.first_name} {customer.last_name}")
        )
        if names and surnames
        else None,
        "fecha_nacimiento_coincide": (
            birth == customer.birth_date.isoformat() if birth and customer.birth_date else None
        ),
    }


def masked_extraction(extracted: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extracted:
        return extracted
    out = dict(extracted)
    if out.get("numero_documento"):
        out["numero_documento"] = mask_dni(str(out["numero_documento"]))
    return out


async def _read_image(upload: UploadFile) -> tuple[bytes, str]:
    content_type = (upload.content_type or "").lower()
    if content_type not in IMAGE_SIGNATURES:
        raise HTTPException(422, "La foto del DNI debe ser JPG, PNG o WEBP")
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "La imagen supera los 5 MB")
    if not data.startswith(IMAGE_SIGNATURES[content_type]):
        raise HTTPException(422, "El archivo no es una imagen válida")
    return data, content_type


@router.post("", response_model=OnboardingOut, status_code=201)
async def start_onboarding(
    first_name: str = Form(min_length=1, max_length=60),
    last_name: str = Form(min_length=1, max_length=80),
    document_number: str = Form(pattern=r"^\d{8}$"),
    birth_date: date = Form(),
    email: str = Form(max_length=120),
    phone: str = Form(pattern=r"^9\d{8}$"),
    region: str = Form(),
    monthly_income: Decimal | None = Form(default=None, ge=0, le=1_000_000),
    dni_image: UploadFile = File(),
    db: Session = Depends(get_db),
) -> OnboardingOut:
    """Public endpoint (the person is not a customer yet). Protected by the rate limiter."""
    try:
        _email.validate_python(email)
    except ValidationError as exc:
        raise HTTPException(422, "Correo electrónico inválido") from exc
    if region not in REGIONS:
        raise HTTPException(422, "Región no válida")
    today = datetime.now(UTC).date()
    age = (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )
    if age < 18:
        raise HTTPException(422, "Debes ser mayor de edad")
    if db.scalar(select(Customer.id).where(Customer.document_number == document_number)):
        raise HTTPException(409, "Ya existe un cliente con ese documento")
    image, content_type = await _read_image(dni_image)

    customer = Customer(
        id=uuid.uuid4(),
        document_type="DNI",
        document_number=document_number,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email.strip().lower(),
        phone=phone,
        birth_date=birth_date,
        region=region,
        kyc_status="PENDIENTE",
        monthly_income=monthly_income,
    )
    db.add(customer)
    db.flush()

    doc_id = uuid.uuid4()
    blob_path = storage.save_kyc_image(
        f"kyc/{customer.id}/{doc_id}.{EXT[content_type]}", image, content_type
    )
    result = ia_client.kyc_extract(image, content_type, f"{doc_id}.{EXT[content_type]}")
    extracted = result.get("datos") if result else None
    confidence = result.get("confianza") if result else None
    db.add(
        KycDocument(
            id=doc_id,
            customer_id=customer.id,
            blob_path=blob_path,
            extracted_json=extracted,
            extraction_confidence=Decimal(str(confidence)) if confidence is not None else None,
        )
    )
    db.commit()
    return OnboardingOut(
        customer_id=customer.id,
        kyc_status=customer.kyc_status,
        extracted=extracted,
        confidence=confidence,
        checks=compare(customer, extracted),
        message="Tu solicitud está en revisión. Te avisaremos cuando se apruebe.",
    )


@router.get("/pending", response_model=list[PendingOut])
def pending(
    _user: CurrentUser = Depends(require_roles(Role.ATENCION, Role.ADMIN)),
    db: Session = Depends(get_db),
) -> list[PendingOut]:
    customers = db.scalars(
        select(Customer).where(Customer.kyc_status == "PENDIENTE").order_by(Customer.created_at)
    ).all()
    out = []
    for c in customers:
        doc = db.scalars(
            select(KycDocument)
            .where(KycDocument.customer_id == c.id)
            .order_by(KycDocument.created_at.desc())
        ).first()
        extracted = doc.extracted_json if doc else None
        out.append(
            PendingOut(
                customer=masked(c),
                document_id=doc.id if doc else None,
                extracted=masked_extraction(extracted),
                confidence=float(doc.extraction_confidence)
                if doc and doc.extraction_confidence
                else None,
                checks=compare(c, extracted),
            )
        )
    return out


@router.post("/{customer_id}/decision", response_model=CustomerMasked)
def decide(
    customer_id: uuid.UUID,
    body: DecisionIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.ATENCION, Role.ADMIN)),
    db: Session = Depends(get_db),
) -> CustomerMasked:
    customer = db.get(Customer, customer_id, with_for_update=True)
    if customer is None:
        raise HTTPException(404, "Cliente no encontrado")
    if customer.kyc_status != "PENDIENTE":
        raise HTTPException(409, "La solicitud ya fue resuelta")
    customer.kyc_status = body.decision
    customer.kyc_decided_by = user.sub
    customer.kyc_decided_at = datetime.now(UTC)
    if body.decision == "APROBADO":
        open_starter_products(db, customer)
    db.commit()
    audit.record(
        actor=user,
        action=f"KYC_{body.decision}",
        resource="customer",
        resource_id=str(customer.id),
        ip=client_ip(request),
        reason=body.reason,
    )
    return masked(customer)
