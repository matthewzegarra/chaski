"""Transfers and card payments.

Each operation: (1) posts to the database, (2) runs the fraud rules engine,
(3) publishes the event to Eventstream when configured (in the background).
"""

from __future__ import annotations

import uuid
from typing import Any

from chaski_common import events, fraud, ledger
from chaski_common.auth import CurrentUser, deny, require_customer
from chaski_common.db import get_db
from chaski_common.logging import get_logger
from chaski_common.models import Account, Card, Transaction
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cuentas_api import idempotency
from cuentas_api.schemas import CardPaymentIn, ReceiptOut, TransferIn

router = APIRouter(tags=["pagos"])
log = get_logger(__name__)


def _run_fraud_and_publish(
    db: Session, tx: Transaction, customer_id: uuid.UUID, background: BackgroundTasks
) -> None:
    """After commit: evaluate rules in their own transaction, then publish the event."""
    try:
        alerts = fraud.evaluate(db, tx, customer_id)
        db.commit()
    except Exception:
        db.rollback()
        alerts = []
        log.exception("fraud_evaluation_failed", transaction_id=str(tx.id))
    if alerts:
        log.info("fraud_alerts_created", transaction_id=str(tx.id), rules=[a.rule for a in alerts])
    background.add_task(
        events.publish, [events.transaction_event(tx, customer_id, [a.rule for a in alerts])]
    )


def _execute(
    *,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session,
    user: CurrentUser,
    body: BaseModel,
    key: str | None,
    post: Any,
) -> dict[str, Any]:
    assert user.customer_id is not None
    req_hash = idempotency.request_hash(body)
    if key and (stored := idempotency.find(db, user.customer_id, key, req_hash)) is not None:
        response.headers["Idempotent-Replayed"] = "true"
        return stored
    try:
        tx, receipt = post()
    except ledger.NotOwner as exc:
        db.rollback()
        raise deny(request, user, resource="payment", detail=exc.detail) from exc
    except ledger.LedgerError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.detail) from exc
    payload = jsonable_encoder(receipt)
    if key:
        idempotency.store(db, user.customer_id, key, req_hash, payload)
    try:
        db.commit()
    except IntegrityError:
        # Same key sent concurrently: the other request won, replay its result.
        db.rollback()
        stored = idempotency.find(db, user.customer_id, key or "", req_hash)
        if stored is None:
            raise
        response.headers["Idempotent-Replayed"] = "true"
        return stored
    _run_fraud_and_publish(db, tx, user.customer_id, background)
    return payload


@router.post("/transfers", response_model=ReceiptOut, status_code=201)
def create_transfer(
    body: TransferIn,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_customer),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    key = idempotency.validate_key(idempotency_key, required=True)
    assert user.customer_id is not None
    customer_id = user.customer_id

    def post() -> tuple[Transaction, ReceiptOut]:
        result = ledger.transfer(
            db,
            customer_id=customer_id,
            from_account_id=body.from_account_id,
            to_account_number=body.to_account_number,
            amount=body.amount,
            description=body.description,
        )
        tx = result.out_tx
        return tx, ReceiptOut(
            transaction_id=tx.id,
            operation="TRANSFERENCIA",
            amount=tx.amount,
            currency=tx.currency,
            from_account_number=result.source.number,
            to_account_number=body.to_account_number,
            internal=result.internal,
            new_balance=result.source.balance,
            created_at=tx.created_at,
        )

    return _execute(
        request=request, response=response, background=background, db=db, user=user,
        body=body, key=key, post=post,
    )  # fmt: skip


@router.post("/card-payments", response_model=ReceiptOut, status_code=201)
def create_card_payment(
    body: CardPaymentIn,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_customer),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    key = idempotency.validate_key(idempotency_key, required=False)
    assert user.customer_id is not None
    customer_id = user.customer_id

    def post() -> tuple[Transaction, ReceiptOut]:
        tx = ledger.card_payment(
            db,
            customer_id=customer_id,
            card_id=body.card_id,
            amount=body.amount,
            merchant=body.merchant,
            city=body.city,
            channel=body.channel,
        )
        card = db.get(Card, body.card_id)
        account = db.get(Account, tx.account_id)
        assert card is not None and account is not None
        return tx, ReceiptOut(
            transaction_id=tx.id,
            operation="PAGO_TARJETA",
            amount=tx.amount,
            currency=tx.currency,
            card_last4=card.last4,
            merchant=tx.merchant,
            new_balance=account.balance,
            created_at=tx.created_at,
        )

    return _execute(
        request=request, response=response, background=background, db=db, user=user,
        body=body, key=key, post=post,
    )  # fmt: skip
