"""SQLAlchemy 2 ORM models mirroring db/migrations (core and ops schemas)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012
        uuid.UUID: UUID(as_uuid=True),
        Decimal: Numeric(14, 2),
        dict[str, Any]: JSONB,
    }


def as_dict(obj: Base) -> dict[str, Any]:
    """Column values of a mapped object (unset/unloaded columns included as None)."""
    return {attr.key: getattr(obj, attr.key) for attr in obj.__mapper__.column_attrs}


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


def _now() -> Mapped[datetime]:
    return mapped_column(server_default=text("now()"))


# ---------------------------------------------------------------- core


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    document_type: Mapped[str] = mapped_column(server_default="DNI")
    document_number: Mapped[str]
    first_name: Mapped[str]
    last_name: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str | None]
    birth_date: Mapped[date | None]
    segment: Mapped[str] = mapped_column(server_default="MASIVO")
    region: Mapped[str]
    kyc_status: Mapped[str] = mapped_column(server_default="PENDIENTE")
    risk_level: Mapped[str] = mapped_column(server_default="BAJO")
    monthly_income: Mapped[Decimal | None]
    kyc_decided_by: Mapped[str | None]
    kyc_decided_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _now()


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.customers.id"))
    number: Mapped[str] = mapped_column(String, unique=True)
    product: Mapped[str]
    currency: Mapped[str]
    balance: Mapped[Decimal] = mapped_column(server_default="0")
    status: Mapped[str] = mapped_column(server_default="ACTIVA")
    opened_at: Mapped[datetime] = _now()


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.customers.id"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.accounts.id"))
    type: Mapped[str]
    token: Mapped[str] = mapped_column(unique=True)
    last4: Mapped[str] = mapped_column(String(4))
    brand: Mapped[str]
    credit_limit: Mapped[Decimal | None]
    status: Mapped[str] = mapped_column(server_default="ACTIVA")
    created_at: Mapped[datetime] = _now()


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.customers.id"))
    product: Mapped[str] = mapped_column(server_default="CONSUMO")
    amount: Mapped[Decimal]
    term_months: Mapped[int]
    rate_tea: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    status: Mapped[str] = mapped_column(server_default="SOLICITADO")
    days_past_due: Mapped[int] = mapped_column(server_default="0")
    outstanding_balance: Mapped[Decimal] = mapped_column(server_default="0")
    ai_score: Mapped[int | None]
    ai_explanation: Mapped[str | None]
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]
    disbursed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _now()


class LoanInstallment(Base):
    __tablename__ = "loan_installments"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.loans.id"), primary_key=True)
    number: Mapped[int] = mapped_column(primary_key=True)
    due_date: Mapped[date]
    amount: Mapped[Decimal]
    paid_at: Mapped[datetime | None]


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.accounts.id"))
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.cards.id"))
    type: Mapped[str]
    amount: Mapped[Decimal]
    currency: Mapped[str]
    channel: Mapped[str]
    merchant: Mapped[str | None]
    city: Mapped[str | None]
    counterparty_account: Mapped[str | None]
    description: Mapped[str | None]
    created_at: Mapped[datetime] = _now()


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.customers.id"))
    subject: Mapped[str]
    body: Mapped[str]
    channel: Mapped[str] = mapped_column(server_default="APP")
    status: Mapped[str] = mapped_column(server_default="NUEVA")
    ai_category: Mapped[str | None]
    ai_urgency: Mapped[str | None]
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    ai_reason: Mapped[str | None]
    ai_suspicious: Mapped[bool] = mapped_column(server_default="false")
    requires_review: Mapped[bool] = mapped_column(server_default="true")
    final_category: Mapped[str | None]
    reviewed_by: Mapped[str | None]
    reviewed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _now()
    due_at: Mapped[datetime]


class KycDocument(Base):
    __tablename__ = "kyc_documents"
    __table_args__ = {"schema": "core"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.customers.id"))
    blob_path: Mapped[str]
    extracted_json: Mapped[dict[str, Any] | None]
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = _now()


# ---------------------------------------------------------------- ops


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[str]
    actor_role: Mapped[str | None]
    action: Mapped[str]
    resource: Mapped[str]
    resource_id: Mapped[str | None]
    pii_accessed: Mapped[bool] = mapped_column(server_default="false")
    allowed: Mapped[bool] = mapped_column(server_default="true")
    ip: Mapped[str | None]
    reason: Mapped[str | None]
    correlation_id: Mapped[str | None]
    created_at: Mapped[datetime] = _now()


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.transactions.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.customers.id"))
    rule: Mapped[str]
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    source: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="ABIERTA")
    details: Mapped[dict[str, Any] | None]
    resolved_by: Mapped[str | None]
    resolved_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _now()


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    flow_name: Mapped[str]
    status: Mapped[str]
    trigger: Mapped[str] = mapped_column(server_default="PROGRAMADO")
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None]
    rows_in: Mapped[int] = mapped_column(server_default="0")
    rows_ok: Mapped[int] = mapped_column(server_default="0")
    rows_quarantined: Mapped[int] = mapped_column(server_default="0")
    error: Mapped[str | None]


class QualityCheck(Base):
    __tablename__ = "quality_checks"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ops.pipeline_runs.id"))
    check_name: Mapped[str]
    table_name: Mapped[str]
    passed: Mapped[bool]
    failed_count: Mapped[int] = mapped_column(server_default="0")


class RawIngest(Base):
    __tablename__ = "raw_ingest"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str]
    payload: Mapped[dict[str, Any]]
    received_at: Mapped[datetime] = _now()
    processed_at: Mapped[datetime | None]


class QuarantineRecord(Base):
    __tablename__ = "quarantine_records"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ops.pipeline_runs.id"))
    raw_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ops.raw_ingest.id"))
    table_name: Mapped[str]
    reason: Mapped[str]
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _now()


class AiInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = _pk()
    use_case: Mapped[str]
    prompt_id: Mapped[str]
    prompt_version: Mapped[str]
    input_redacted: Mapped[str | None]
    output: Mapped[dict[str, Any] | None]
    latency_ms: Mapped[int | None]
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    blocked_by_shields: Mapped[bool] = mapped_column(server_default="false")
    human_override: Mapped[bool | None]
    provider: Mapped[str | None]
    created_at: Mapped[datetime] = _now()


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = {"schema": "ops"}  # noqa: RUF012

    customer_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    request_hash: Mapped[str]
    status_code: Mapped[int]
    response_json: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _now()
