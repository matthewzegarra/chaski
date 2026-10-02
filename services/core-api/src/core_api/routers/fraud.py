"""Chaski Guard: fraud alert inbox, resolution and the Fabric Activator webhook."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, require_roles
from chaski_common.db import get_db
from chaski_common.logging import get_logger
from chaski_common.models import Card, Customer, FraudAlert, Transaction
from chaski_common.roles import Role
from chaski_common.schemas import Money
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.settings import get_settings

router = APIRouter(prefix="/fraud", tags=["fraude"])
log = get_logger(__name__)
FRAUD_ROLES = (Role.FRAUDE, Role.ADMIN)


class AlertOut(BaseModel):
    id: uuid.UUID
    rule: str
    score: float
    source: str
    status: str
    details: dict[str, Any] | None
    created_at: datetime
    resolved_by: str | None
    resolved_at: datetime | None
    customer_id: uuid.UUID | None
    customer_name: str | None
    transaction_id: uuid.UUID | None
    tx_type: str | None
    tx_amount: Money | None
    tx_currency: str | None
    tx_channel: str | None
    merchant: str | None
    city: str | None
    card_id: uuid.UUID | None
    card_last4: str | None
    card_status: str | None


class ResolveIn(BaseModel):
    status: Literal["CONFIRMADA", "DESCARTADA"]
    block_card: bool = False


class ResolveOut(BaseModel):
    id: uuid.UUID
    status: str
    card_blocked: bool


class FabricAlertIn(BaseModel):
    rule: str = Field(min_length=2, max_length=80)
    score: Decimal = Field(ge=0, le=100)
    transaction_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    status: str | None = None,
    source: str | None = None,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 90),
    limit: int = Query(default=100, ge=1, le=500),
    _user: CurrentUser = Depends(require_roles(*FRAUD_ROLES)),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    conditions = []
    if status:
        conditions.append(FraudAlert.status == status)
    if source:
        conditions.append(FraudAlert.source == source)
    if since_hours:
        conditions.append(FraudAlert.created_at >= datetime.now(UTC) - timedelta(hours=since_hours))
    rows = db.execute(
        select(FraudAlert, Customer, Transaction, Card)
        .outerjoin(Customer, Customer.id == FraudAlert.customer_id)
        .outerjoin(Transaction, Transaction.id == FraudAlert.transaction_id)
        .outerjoin(Card, Card.id == Transaction.card_id)
        .where(*conditions)
        .order_by((FraudAlert.status != "ABIERTA"), FraudAlert.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AlertOut(
            id=a.id,
            rule=a.rule,
            score=float(a.score),
            source=a.source,
            status=a.status,
            details=a.details,
            created_at=a.created_at,
            resolved_by=a.resolved_by,
            resolved_at=a.resolved_at,
            customer_id=a.customer_id,
            customer_name=f"{c.first_name} {c.last_name}" if c else None,
            transaction_id=a.transaction_id,
            tx_type=t.type if t else None,
            tx_amount=t.amount if t else None,
            tx_currency=t.currency if t else None,
            tx_channel=t.channel if t else None,
            merchant=t.merchant if t else None,
            city=t.city if t else None,
            card_id=k.id if k else None,
            card_last4=k.last4 if k else None,
            card_status=k.status if k else None,
        )
        for a, c, t, k in rows
    ]


@router.post("/alerts/{alert_id}/resolve", response_model=ResolveOut)
def resolve(
    alert_id: uuid.UUID,
    body: ResolveIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*FRAUD_ROLES)),
    db: Session = Depends(get_db),
) -> ResolveOut:
    alert = db.get(FraudAlert, alert_id, with_for_update=True)
    if alert is None:
        raise HTTPException(404, "Alerta no encontrada")
    if alert.status != "ABIERTA":
        raise HTTPException(409, "La alerta ya fue resuelta")
    alert.status = body.status
    alert.resolved_by = user.sub
    alert.resolved_at = datetime.now(UTC)
    card_blocked = False
    if body.block_card and alert.transaction_id:
        tx = db.get(Transaction, alert.transaction_id)
        if tx and tx.card_id:
            card = db.get(Card, tx.card_id, with_for_update=True)
            if card:
                card.status = "BLOQUEADA"
                card_blocked = True
    db.commit()
    audit.record(
        actor=user,
        action=f"FRAUD_{body.status}" + ("_CARD_BLOCKED" if card_blocked else ""),
        resource="fraud_alert",
        resource_id=str(alert.id),
        ip=client_ip(request),
    )
    return ResolveOut(id=alert.id, status=alert.status, card_blocked=card_blocked)


@router.post("/webhook", status_code=202)
async def fabric_webhook(
    request: Request,
    x_chaski_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Receives alerts from Fabric Activator. Authenticated with HMAC-SHA256 over the raw body
    (`X-Chaski-Signature: sha256=<hex>`); the secret comes from Key Vault via env var."""
    secret = get_settings().fraud_webhook_secret
    if secret is None or not secret.get_secret_value():
        raise HTTPException(503, "Webhook no configurado")
    raw = await request.body()
    expected = sign(raw, secret.get_secret_value())
    if not x_chaski_signature or not hmac.compare_digest(expected, x_chaski_signature):
        audit.record_safely(
            actor=None,
            action="FRAUD_WEBHOOK",
            resource="fraud/webhook",
            allowed=False,
            ip=client_ip(request),
        )
        raise HTTPException(401, "Firma inválida")
    try:
        payload = FabricAlertIn.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, "Payload inválido") from exc
    tx = db.get(Transaction, payload.transaction_id) if payload.transaction_id else None
    customer_id = (
        payload.customer_id
        if payload.customer_id and db.get(Customer, payload.customer_id)
        else None
    )
    alert = FraudAlert(
        id=uuid.uuid4(),
        transaction_id=tx.id if tx else None,
        customer_id=customer_id,
        rule=payload.rule,
        score=payload.score,
        source="FABRIC",
        status="ABIERTA",
        details=payload.details,
        created_at=datetime.now(UTC),
    )
    db.add(alert)
    db.commit()
    log.info("fabric_alert_received", alert_id=str(alert.id), rule=payload.rule)
    return {"id": str(alert.id), "status": "ABIERTA"}
