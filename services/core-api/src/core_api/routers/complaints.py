"""Complaints. The AI classifies; FRAUDE, low confidence or suspicious text go to mandatory
human review. Due date = 15 business days (regulatory response window)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, require_customer, require_roles
from chaski_common.business_days import add_business_days, business_days_between
from chaski_common.db import get_db
from chaski_common.models import AiInteraction, Complaint, Customer, as_dict
from chaski_common.roles import Role
from chaski_common.schemas import ApiModel, Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core_api import ia_client

router = APIRouter(prefix="/complaints", tags=["quejas"])

Category = Literal["FRAUDE", "COBRO_INDEBIDO", "TARJETA", "PRESTAMO", "CANAL_DIGITAL", "OTRO"]
CATEGORIES = ("FRAUDE", "COBRO_INDEBIDO", "TARJETA", "PRESTAMO", "CANAL_DIGITAL", "OTRO")
REVIEW_CONFIDENCE = 0.8
RESPONSE_DAYS = 15


def needs_human_review(category: str | None, confidence: float | None, suspicious: bool) -> bool:
    return (
        category in (None, "FRAUDE")
        or confidence is None
        or confidence < REVIEW_CONFIDENCE
        or suspicious
    )


class ComplaintIn(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=10, max_length=2000)
    channel: Literal["APP", "WEB"] = "APP"


class ComplaintCustomerOut(ApiModel):
    id: uuid.UUID
    subject: str
    body: str
    channel: str
    status: str
    category: str | None
    created_at: datetime
    due_at: datetime


class ComplaintConsoleOut(ApiModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    subject: str
    body: str
    channel: str
    status: str
    ai_category: str | None
    ai_urgency: str | None
    ai_confidence: float | None
    ai_reason: str | None
    ai_suspicious: bool
    requires_review: bool
    final_category: str | None
    reviewed_by: str | None
    created_at: datetime
    due_at: datetime
    business_days_left: int


class ReviewIn(BaseModel):
    final_category: Category
    status: Literal["EN_REVISION", "RESUELTA"] = "RESUELTA"


def customer_view(c: Complaint) -> ComplaintCustomerOut:
    return ComplaintCustomerOut(
        id=c.id, subject=c.subject, body=c.body, channel=c.channel, status=c.status,
        category=c.final_category or (c.ai_category if not c.ai_suspicious else None),
        created_at=c.created_at, due_at=c.due_at,
    )  # fmt: skip


def console_view(c: Complaint, customer: Customer) -> ComplaintConsoleOut:
    return ComplaintConsoleOut(
        **as_dict(c),
        customer_name=f"{customer.first_name} {customer.last_name}",
        business_days_left=business_days_between(datetime.now(UTC).date(), c.due_at.date()),
    )


@router.post("", response_model=ComplaintCustomerOut, status_code=201)
def create_complaint(
    body: ComplaintIn, user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)
) -> ComplaintCustomerOut:
    now = datetime.now(UTC)
    complaint_id = uuid.uuid4()
    result = ia_client.classify_complaint(str(complaint_id), body.subject, body.body, user.token)
    category = result.get("categoria") if result else None
    if category not in CATEGORIES:
        category = None
    confidence = (
        float(result["confianza"]) if result and result.get("confianza") is not None else None
    )
    suspicious = bool(result.get("sospechosa")) if result else False
    complaint = Complaint(
        id=complaint_id,
        customer_id=user.customer_id,
        subject=body.subject,
        body=body.body,
        channel=body.channel,
        status="NUEVA",
        ai_category=category,
        ai_urgency=result.get("urgencia") if result else None,
        ai_confidence=Decimal(str(round(confidence, 3))) if confidence is not None else None,
        ai_reason=result.get("motivo") if result else None,
        ai_suspicious=suspicious,
        requires_review=needs_human_review(category, confidence, suspicious),
        created_at=now,
        due_at=add_business_days(now, RESPONSE_DAYS),
    )
    db.add(complaint)
    db.commit()
    return customer_view(complaint)


@router.get("/me", response_model=list[ComplaintCustomerOut])
def my_complaints(
    user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)
) -> list[ComplaintCustomerOut]:
    rows = db.scalars(
        select(Complaint)
        .where(Complaint.customer_id == user.customer_id)
        .order_by(Complaint.created_at.desc())
    )
    return [customer_view(c) for c in rows]


@router.get("", response_model=Page[ComplaintConsoleOut])
def list_complaints(
    status: str | None = None,
    requires_review: bool | None = None,
    category: str | None = None,
    suspicious: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _user: CurrentUser = Depends(require_roles(Role.ATENCION, Role.ADMIN)),
    db: Session = Depends(get_db),
) -> Page[ComplaintConsoleOut]:
    conditions = []
    if status:
        conditions.append(Complaint.status == status)
    if requires_review is not None:
        conditions.append(Complaint.requires_review.is_(requires_review))
    if category:
        conditions.append(
            func.coalesce(Complaint.final_category, Complaint.ai_category) == category
        )
    if suspicious is not None:
        conditions.append(Complaint.ai_suspicious.is_(suspicious))
    total = db.scalar(select(func.count()).select_from(Complaint).where(*conditions)) or 0
    rows = db.execute(
        select(Complaint, Customer)
        .join(Customer, Customer.id == Complaint.customer_id)
        .where(*conditions)
        .order_by(
            (Complaint.status == "RESUELTA"), Complaint.requires_review.desc(), Complaint.due_at
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[console_view(c, cu) for c, cu in rows], page=page, page_size=page_size, total=total
    )


@router.post("/{complaint_id}/review", response_model=ComplaintConsoleOut)
def review(
    complaint_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.ATENCION, Role.ADMIN)),
    db: Session = Depends(get_db),
) -> ComplaintConsoleOut:
    complaint = db.get(Complaint, complaint_id, with_for_update=True)
    if complaint is None:
        raise HTTPException(404, "Queja no encontrada")
    complaint.final_category = body.final_category
    complaint.status = body.status
    complaint.reviewed_by = user.sub
    complaint.reviewed_at = datetime.now(UTC)
    if body.status == "RESUELTA":
        complaint.requires_review = False
    # Feeds the "IA vs humano" accuracy metric.
    db.execute(
        update(AiInteraction)
        .where(
            AiInteraction.use_case == "complaint_classification",
            AiInteraction.output["complaint_id"].astext == str(complaint.id),
        )
        .values(human_override=complaint.ai_category != body.final_category)
    )
    db.commit()
    audit.record(
        actor=user,
        action="COMPLAINT_REVIEW",
        resource="complaint",
        resource_id=str(complaint.id),
        ip=client_ip(request),
    )
    customer = db.get(Customer, complaint.customer_id)
    assert customer is not None
    return console_view(complaint, customer)
