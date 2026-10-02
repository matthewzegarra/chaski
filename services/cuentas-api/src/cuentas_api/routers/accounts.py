from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from chaski_common.auth import CurrentUser, deny, require_customer
from chaski_common.db import get_db
from chaski_common.models import Account, Transaction, as_dict
from chaski_common.schemas import Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cuentas_api.schemas import AccountOut, BalanceOut, MovementOut

router = APIRouter(prefix="/accounts", tags=["cuentas"])

CREDIT_TYPES = {"DEPOSITO", "TRANSFERENCIA_IN", "INTERES"}
TxType = Literal[
    "DEPOSITO",
    "RETIRO",
    "TRANSFERENCIA_IN",
    "TRANSFERENCIA_OUT",
    "PAGO_TARJETA",
    "PAGO_SERVICIO",
    "COMISION",
    "INTERES",
]


def owned_account(
    request: Request, account_id: uuid.UUID, user: CurrentUser, db: Session
) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Cuenta no encontrada")
    if account.customer_id != user.customer_id:
        raise deny(request, user, resource="account", resource_id=str(account_id))
    return account


def to_movement(tx: Transaction) -> MovementOut:
    out = MovementOut.model_validate(
        {**as_dict(tx), "direction": "CREDITO" if tx.type in CREDIT_TYPES else "DEBITO"}
    )
    return out


@router.get("/me", response_model=list[AccountOut], summary="Cuentas del cliente autenticado")
def my_accounts(
    user: CurrentUser = Depends(require_customer), db: Session = Depends(get_db)
) -> list[Account]:
    return list(
        db.scalars(
            select(Account)
            .where(Account.customer_id == user.customer_id)
            .order_by(Account.opened_at)
        )
    )


@router.get("/{account_id}/balance", response_model=BalanceOut)
def balance(
    account_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_customer),
    db: Session = Depends(get_db),
) -> BalanceOut:
    account = owned_account(request, account_id, user, db)
    return BalanceOut(
        account_id=account.id,
        currency=account.currency,
        balance=account.balance,
        as_of=datetime.now(UTC),
    )


@router.get("/{account_id}/movements", response_model=Page[MovementOut])
def movements(
    account_id: uuid.UUID,
    request: Request,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    type: TxType | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_customer),
    db: Session = Depends(get_db),
) -> Page[MovementOut]:
    owned_account(request, account_id, user, db)
    conditions = [Transaction.account_id == account_id]
    if from_:
        conditions.append(Transaction.created_at >= datetime.combine(from_, time.min, UTC))
    if to:
        conditions.append(
            Transaction.created_at < datetime.combine(to + timedelta(days=1), time.min, UTC)
        )
    if type:
        conditions.append(Transaction.type == type)
    total = db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
    rows = db.scalars(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.created_at.desc(), Transaction.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=[to_movement(t) for t in rows], page=page, page_size=page_size, total=total)
