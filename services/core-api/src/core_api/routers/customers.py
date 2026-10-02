from __future__ import annotations

import uuid
from datetime import date, datetime

from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, require_customer, require_roles
from chaski_common.db import get_db
from chaski_common.masking import mask_dni, mask_email, mask_phone
from chaski_common.models import Account, Card, Complaint, Customer, Loan
from chaski_common.roles import PII_REVEAL_ROLES, Role
from chaski_common.schemas import ApiModel, Money, Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/customers", tags=["clientes"])

CUSTOMER_READERS = (Role.ADMIN, Role.ATENCION, Role.OPERACIONES, Role.RIESGOS, Role.FRAUDE)


class CustomerMasked(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    document_type: str
    document_number: str
    email: str
    phone: str | None
    segment: str
    region: str
    kyc_status: str
    risk_level: str
    created_at: datetime


class AccountBrief(ApiModel):
    id: uuid.UUID
    number: str
    product: str
    currency: str
    balance: Money
    status: str


class CardBrief(ApiModel):
    id: uuid.UUID
    type: str
    brand: str
    last4: str
    status: str


class LoanBrief(ApiModel):
    id: uuid.UUID
    amount: Money
    status: str
    days_past_due: int
    outstanding_balance: Money
    created_at: datetime


class CustomerDetail(CustomerMasked):
    monthly_income: Money | None
    accounts: list[AccountBrief]
    cards: list[CardBrief]
    loans: list[LoanBrief]
    open_complaints: int


class CustomerSelf(ApiModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    document_number: str
    email: str
    phone: str | None
    segment: str
    region: str
    kyc_status: str


class RevealIn(BaseModel):
    reason: str = Field(min_length=10, max_length=300)


class RevealOut(BaseModel):
    id: uuid.UUID
    document_number: str
    email: str
    phone: str | None
    birth_date: date | None


def masked(c: Customer) -> CustomerMasked:
    return CustomerMasked(
        id=c.id,
        first_name=c.first_name,
        last_name=c.last_name,
        document_type=c.document_type,
        document_number=mask_dni(c.document_number) or "",
        email=mask_email(c.email) or "",
        phone=mask_phone(c.phone),
        segment=c.segment,
        region=c.region,
        kyc_status=c.kyc_status,
        risk_level=c.risk_level,
        created_at=c.created_at,
    )


@router.get("", response_model=Page[CustomerMasked])
def list_customers(
    q: str | None = Query(default=None, max_length=60),
    kyc_status: str | None = None,
    segment: str | None = None,
    region: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _user: CurrentUser = Depends(require_roles(*CUSTOMER_READERS)),
    db: Session = Depends(get_db),
) -> Page[CustomerMasked]:
    conditions = []
    if q:
        term = q.strip()
        if term.isdigit():
            conditions.append(Customer.document_number == term)
        else:
            like = f"%{term}%"
            conditions.append(or_(Customer.first_name.ilike(like), Customer.last_name.ilike(like)))
    if kyc_status:
        conditions.append(Customer.kyc_status == kyc_status)
    if segment:
        conditions.append(Customer.segment == segment)
    if region:
        conditions.append(Customer.region == region)
    total = db.scalar(select(func.count()).select_from(Customer).where(*conditions)) or 0
    rows = db.scalars(
        select(Customer)
        .where(*conditions)
        .order_by(Customer.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=[masked(c) for c in rows], page=page, page_size=page_size, total=total)


@router.get("/me", response_model=CustomerSelf)
def me(user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)) -> Customer:
    customer = db.get(Customer, user.customer_id)
    if customer is None:
        raise HTTPException(404, "Cliente no encontrado")
    return customer


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(
    customer_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CUSTOMER_READERS)),
    db: Session = Depends(get_db),
) -> CustomerDetail:
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, "Cliente no encontrado")
    audit.record(
        actor=user,
        action="VIEW_CUSTOMER",
        resource="customer",
        resource_id=str(c.id),
        pii_accessed=False,
        ip=client_ip(request),
    )
    open_complaints = db.scalar(
        select(func.count()).where(Complaint.customer_id == c.id, Complaint.status != "RESUELTA")
    )
    return CustomerDetail(
        **masked(c).model_dump(),
        monthly_income=c.monthly_income,
        accounts=[
            AccountBrief.model_validate(a)
            for a in db.scalars(select(Account).where(Account.customer_id == c.id))
        ],
        cards=[
            CardBrief.model_validate(k)
            for k in db.scalars(select(Card).where(Card.customer_id == c.id))
        ],
        loans=[
            LoanBrief.model_validate(loan)
            for loan in db.scalars(
                select(Loan).where(Loan.customer_id == c.id).order_by(Loan.created_at.desc())
            )
        ],
        open_complaints=open_complaints or 0,
    )


@router.post("/{customer_id}/reveal-pii", response_model=RevealOut)
def reveal_pii(
    customer_id: uuid.UUID,
    body: RevealIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PII_REVEAL_ROLES)),
    db: Session = Depends(get_db),
) -> RevealOut:
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, "Cliente no encontrado")
    # Fail closed: if the audit record cannot be written, the PII is not returned.
    audit.record(
        actor=user,
        action="REVEAL_PII",
        resource="customer",
        resource_id=str(c.id),
        pii_accessed=True,
        ip=client_ip(request),
        reason=body.reason,
    )
    return RevealOut(
        id=c.id,
        document_number=c.document_number,
        email=c.email,
        phone=c.phone,
        birth_date=c.birth_date,
    )
