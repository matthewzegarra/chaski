"""Consumer loans. The AI only suggests a score; the decision is always a Riesgos user's."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from chaski_common import audit, ledger
from chaski_common.auth import (
    CurrentUser,
    client_ip,
    deny,
    get_current_user,
    require_customer,
    require_roles,
)
from chaski_common.db import get_db
from chaski_common.models import Account, Customer, Loan, LoanInstallment, as_dict
from chaski_common.roles import Role
from chaski_common.schemas import ApiModel, Money, Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api import ia_client
from core_api.services import loan_math

router = APIRouter(prefix="/loans", tags=["préstamos"])

PORTFOLIO_ROLES = (Role.RIESGOS, Role.ADMIN, Role.DIRECCION)
BUCKETS = ((8, "Normal"), (30, "CPP"), (60, "Deficiente"), (120, "Dudoso"))


def bucket_for(dpd: int) -> str:
    return next((name for limit, name in BUCKETS if dpd <= limit), "Pérdida")


class QuoteOut(BaseModel):
    amount: Money
    term_months: int
    rate_tea: float
    monthly_payment: Money
    total_payment: Money


class LoanIn(BaseModel):
    amount: Decimal = Field(ge=500, le=100_000, decimal_places=2)
    term_months: int

    @field_validator("term_months")
    @classmethod
    def _term(cls, v: int) -> int:
        if v not in loan_math.TERMS:
            raise ValueError(f"Plazo no permitido: {loan_math.TERMS}")
        return v


class LoanOut(ApiModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    product: str
    amount: Money
    term_months: int
    rate_tea: float
    status: str
    days_past_due: int
    outstanding_balance: Money
    monthly_payment: Money
    ai_score: int | None
    ai_explanation: str | None
    decided_by: str | None
    decided_at: datetime | None
    disbursed_at: datetime | None
    created_at: datetime


class LoanConsoleOut(LoanOut):
    customer_name: str
    segment: str
    region: str
    monthly_income: Money | None
    bucket: str


class InstallmentOut(ApiModel):
    number: int
    due_date: Any
    amount: Money
    paid_at: datetime | None


class LoanDetailOut(LoanOut):
    installments: list[InstallmentOut]


class DecisionIn(BaseModel):
    decision: Literal["APROBADO", "RECHAZADO"]
    comment: str | None = Field(default=None, max_length=500)


def to_out(loan: Loan) -> dict[str, Any]:
    return {
        **as_dict(loan),
        "rate_tea": float(loan.rate_tea),
        "monthly_payment": loan_math.monthly_payment(loan.amount, loan.rate_tea, loan.term_months),
    }


def _score(db: Session, loan: Loan, customer: Customer, token: str) -> None:
    """Ask ia-api for a suggested score. Leaves the loan untouched if IA is unavailable."""
    history = db.execute(
        select(func.count(), func.coalesce(func.max(Loan.days_past_due), 0)).where(
            Loan.customer_id == customer.id, Loan.id != loan.id
        )
    ).one()
    current_debt = db.scalar(
        select(func.coalesce(func.sum(LoanInstallment.amount), 0))
        .join(Loan, Loan.id == LoanInstallment.loan_id)
        .where(
            Loan.customer_id == customer.id,
            Loan.status == "DESEMBOLSADO",
            LoanInstallment.number == 1,
        )
    )
    result = ia_client.score_loan(
        {
            "loan_id": str(loan.id),
            "monto": float(loan.amount),
            "plazo_meses": loan.term_months,
            "cuota_estimada": float(
                loan_math.monthly_payment(loan.amount, loan.rate_tea, loan.term_months)
            ),
            "ingreso_mensual": float(customer.monthly_income or 0),
            "deuda_mensual_actual": float(current_debt or 0),
            "segmento": customer.segment,
            "nivel_riesgo": customer.risk_level,
            "prestamos_previos": history[0],
            "max_dias_atraso_historico": history[1],
        },
        token,
    )
    if result and "score" in result:
        loan.ai_score = int(result["score"])
        loan.ai_explanation = str(result.get("explicacion") or "")[:2000]


@router.get("/quote", response_model=QuoteOut)
def quote(
    amount: Decimal = Query(ge=500, le=100_000),
    term_months: int = Query(),
    user: CurrentUser = Depends(require_customer),
    db: Session = Depends(get_db),
) -> QuoteOut:
    if term_months not in loan_math.TERMS:
        raise HTTPException(422, f"Plazo no permitido: {loan_math.TERMS}")
    customer = db.get(Customer, user.customer_id)
    assert customer is not None
    tea = loan_math.rate_for(customer.segment, customer.risk_level)
    payment = loan_math.monthly_payment(amount, tea, term_months)
    return QuoteOut(
        amount=amount, term_months=term_months, rate_tea=float(tea),
        monthly_payment=payment, total_payment=payment * term_months,
    )  # fmt: skip


@router.post("", response_model=LoanOut, status_code=201)
def request_loan(
    body: LoanIn, user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)
) -> dict[str, Any]:
    customer = db.get(Customer, user.customer_id)
    if customer is None or customer.kyc_status != "APROBADO":
        raise HTTPException(409, "Tu cuenta aún no está aprobada")
    if db.scalar(
        select(Loan.id).where(Loan.customer_id == customer.id, Loan.status == "SOLICITADO")
    ):
        raise HTTPException(409, "Ya tienes una solicitud en evaluación")
    loan = Loan(
        id=uuid.uuid4(),
        customer_id=customer.id,
        product="CONSUMO",
        amount=body.amount,
        term_months=body.term_months,
        rate_tea=loan_math.rate_for(customer.segment, customer.risk_level),
        status="SOLICITADO",
        days_past_due=0,
        outstanding_balance=Decimal(0),
        created_at=datetime.now(UTC),
    )
    db.add(loan)
    db.flush()
    _score(db, loan, customer, user.token)
    db.commit()
    return to_out(loan)


@router.get("/me", response_model=list[LoanOut])
def my_loans(
    user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Loan).where(Loan.customer_id == user.customer_id).order_by(Loan.created_at.desc())
    )
    return [to_out(loan) for loan in rows]


@router.get("", response_model=Page[LoanConsoleOut])
def list_loans(
    status: str | None = None,
    region: str | None = None,
    min_days_past_due: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _user: CurrentUser = Depends(require_roles(*PORTFOLIO_ROLES)),
    db: Session = Depends(get_db),
) -> Page[LoanConsoleOut]:
    conditions = []
    if status:
        conditions.append(Loan.status == status)
    if region:
        conditions.append(Customer.region == region)
    if min_days_past_due is not None:
        conditions.append(Loan.days_past_due >= min_days_past_due)
    base = select(Loan, Customer).join(Customer, Customer.id == Loan.customer_id).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(
            Loan.days_past_due.desc() if min_days_past_due is not None else Loan.created_at.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        LoanConsoleOut(
            **to_out(loan),
            customer_name=f"{c.first_name} {c.last_name}",
            segment=c.segment,
            region=c.region,
            monthly_income=c.monthly_income,
            bucket=bucket_for(loan.days_past_due),
        )
        for loan, c in rows
    ]
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/{loan_id}", response_model=LoanDetailOut)
def get_loan(
    loan_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Préstamo no encontrado")
    own = user.is_customer and loan.customer_id == user.customer_id
    if not own and not user.has_any(PORTFOLIO_ROLES):
        raise deny(request, user, resource="loan", resource_id=str(loan_id))
    installments = db.scalars(
        select(LoanInstallment)
        .where(LoanInstallment.loan_id == loan.id)
        .order_by(LoanInstallment.number)
    )
    return {
        **to_out(loan),
        "installments": [InstallmentOut.model_validate(i) for i in installments],
    }


@router.post("/{loan_id}/rescore", response_model=LoanOut)
def rescore(
    loan_id: uuid.UUID,
    user: CurrentUser = Depends(require_roles(Role.RIESGOS)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Préstamo no encontrado")
    customer = db.get(Customer, loan.customer_id)
    assert customer is not None
    _score(db, loan, customer, user.token)
    db.commit()
    return to_out(loan)


@router.post("/{loan_id}/decision", response_model=LoanOut)
def decide(
    loan_id: uuid.UUID,
    body: DecisionIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.RIESGOS)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    loan = db.get(Loan, loan_id, with_for_update=True)
    if loan is None:
        raise HTTPException(404, "Préstamo no encontrado")
    if loan.status != "SOLICITADO":
        raise HTTPException(409, "La solicitud ya fue resuelta")
    now = datetime.now(UTC)
    loan.decided_by = user.sub
    loan.decided_at = now
    if body.decision == "RECHAZADO":
        loan.status = "RECHAZADO"
    else:
        # Approved loans are disbursed immediately into the customer's soles account.
        account = db.scalars(
            select(Account)
            .where(
                Account.customer_id == loan.customer_id,
                Account.currency == "PEN",
                Account.status == "ACTIVA",
            )
            .order_by(Account.opened_at)
        ).first()
        if account is None:
            raise HTTPException(
                409, "El cliente no tiene una cuenta en soles activa para el desembolso"
            )
        ledger.deposit(
            db,
            account_id=account.id,
            amount=loan.amount,
            description="Desembolso de préstamo",
            at=now,
        )
        loan.status = "DESEMBOLSADO"
        loan.disbursed_at = now
        loan.outstanding_balance = loan.amount
        for number, due, amount in loan_math.schedule(
            loan.amount, loan.rate_tea, loan.term_months, now.date()
        ):
            db.add(LoanInstallment(loan_id=loan.id, number=number, due_date=due, amount=amount))
    db.commit()
    audit.record(
        actor=user,
        action=f"LOAN_{body.decision}",
        resource="loan",
        resource_id=str(loan.id),
        ip=client_ip(request),
        reason=body.comment,
    )
    return to_out(loan)
