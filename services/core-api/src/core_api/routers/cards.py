from __future__ import annotations

import uuid
from typing import Literal

from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, deny, get_current_user, require_customer
from chaski_common.db import get_db
from chaski_common.models import Card
from chaski_common.roles import Role
from chaski_common.schemas import ApiModel, Money
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/cards", tags=["tarjetas"])

STAFF_CARD_ROLES = (Role.FRAUDE, Role.ATENCION, Role.ADMIN)


class CardOut(ApiModel):
    """Never exposes the token: last4 is all the UI needs."""

    id: uuid.UUID
    account_id: uuid.UUID | None
    type: str
    brand: str
    last4: str
    credit_limit: Money | None
    status: str


@router.get("/me", response_model=list[CardOut])
def my_cards(
    user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)
) -> list[Card]:
    return list(
        db.scalars(
            select(Card).where(Card.customer_id == user.customer_id).order_by(Card.created_at)
        )
    )


def set_card_status(
    db: Session,
    request: Request,
    user: CurrentUser,
    card_id: uuid.UUID,
    status: Literal["ACTIVA", "BLOQUEADA"],
) -> Card:
    card = db.get(Card, card_id, with_for_update=True)
    if card is None:
        raise HTTPException(404, "Tarjeta no encontrada")
    own = user.is_customer and card.customer_id == user.customer_id
    if not own and not user.has_any(STAFF_CARD_ROLES):
        raise deny(request, user, resource="card", resource_id=str(card_id))
    card.status = status
    db.commit()
    audit.record(
        actor=user,
        action="CARD_BLOCK" if status == "BLOQUEADA" else "CARD_UNBLOCK",
        resource="card",
        resource_id=str(card.id),
        ip=client_ip(request),
    )
    return card


@router.post("/{card_id}/block", response_model=CardOut)
def block(
    card_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Card:
    return set_card_status(db, request, user, card_id, "BLOQUEADA")


@router.post("/{card_id}/unblock", response_model=CardOut)
def unblock(
    card_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Card:
    return set_card_status(db, request, user, card_id, "ACTIVA")
