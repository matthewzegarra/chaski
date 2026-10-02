"""Money movements. Every function runs inside the caller's transaction and locks the
affected accounts with SELECT ... FOR UPDATE (always in id order to avoid deadlocks)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from chaski_common.models import Account, Card, Transaction


class LedgerError(Exception):
    status_code = 422

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(LedgerError):
    status_code = 404


class NotOwner(LedgerError):
    """Resource belongs to another customer (callers turn it into an audited 403)."""

    status_code = 403


@dataclass
class PostedTransfer:
    out_tx: Transaction
    in_tx: Transaction | None
    source: Account

    @property
    def internal(self) -> bool:
        return self.in_tx is not None


def _lock(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Account]:
    rows = session.scalars(
        select(Account).where(Account.id.in_(sorted(ids))).order_by(Account.id).with_for_update()
    ).all()
    return {a.id: a for a in rows}


def transfer(
    session: Session,
    *,
    customer_id: uuid.UUID,
    from_account_id: uuid.UUID,
    to_account_number: str,
    amount: Decimal,
    description: str | None = None,
    channel: str = "APP",
    at: datetime | None = None,
) -> PostedTransfer:
    at = at or datetime.now(UTC)
    dst_id = session.scalar(select(Account.id).where(Account.number == to_account_number))
    locked = _lock(session, [from_account_id, *([dst_id] if dst_id else [])])
    src = locked.get(from_account_id)
    if src is None:
        raise NotFound("Cuenta de origen no encontrada")
    if src.customer_id != customer_id:
        raise NotOwner("La cuenta de origen no te pertenece")
    if src.status != "ACTIVA":
        raise LedgerError("La cuenta de origen no está activa")
    if src.number == to_account_number:
        raise LedgerError("No puedes transferir a la misma cuenta")
    dst = locked.get(dst_id) if dst_id else None
    if dst is not None:
        if dst.status != "ACTIVA":
            raise LedgerError("La cuenta de destino no está activa")
        if dst.currency != src.currency:
            raise LedgerError("Las cuentas deben tener la misma moneda")
    if src.balance < amount:
        raise LedgerError("Saldo insuficiente")

    src.balance -= amount
    out_tx = Transaction(
        id=uuid.uuid4(),
        account_id=src.id,
        type="TRANSFERENCIA_OUT",
        amount=amount,
        currency=src.currency,
        channel=channel,
        counterparty_account=to_account_number,
        description=description,
        created_at=at,
    )
    session.add(out_tx)
    in_tx = None
    if dst is not None:
        dst.balance += amount
        in_tx = Transaction(
            id=uuid.uuid4(),
            account_id=dst.id,
            type="TRANSFERENCIA_IN",
            amount=amount,
            currency=dst.currency,
            channel=channel,
            counterparty_account=src.number,
            description=description,
            created_at=at,
        )
        session.add(in_tx)
    session.flush()
    return PostedTransfer(out_tx=out_tx, in_tx=in_tx, source=src)


def card_payment(
    session: Session,
    *,
    customer_id: uuid.UUID,
    card_id: uuid.UUID,
    amount: Decimal,
    merchant: str,
    city: str | None,
    channel: str,
    at: datetime | None = None,
) -> Transaction:
    card = session.get(Card, card_id)
    if card is None:
        raise NotFound("Tarjeta no encontrada")
    if card.customer_id != customer_id:
        raise NotOwner("La tarjeta no te pertenece")
    if card.status != "ACTIVA":
        raise LedgerError("La tarjeta está bloqueada")
    if card.type != "DEBITO" or card.account_id is None:
        raise LedgerError("Por ahora solo se aceptan pagos con tarjeta de débito")
    account = _lock(session, [card.account_id])[card.account_id]
    if account.status != "ACTIVA":
        raise LedgerError("La cuenta asociada no está activa")
    if account.balance < amount:
        raise LedgerError("Saldo insuficiente")
    account.balance -= amount
    tx = Transaction(
        id=uuid.uuid4(),
        account_id=account.id,
        card_id=card.id,
        type="PAGO_TARJETA",
        amount=amount,
        currency=account.currency,
        channel=channel,
        merchant=merchant,
        city=city,
        created_at=at or datetime.now(UTC),
    )
    session.add(tx)
    session.flush()
    return tx


def deposit(
    session: Session,
    *,
    account_id: uuid.UUID,
    amount: Decimal,
    description: str,
    channel: str = "WEB",
    at: datetime | None = None,
) -> Transaction:
    account = _lock(session, [account_id])[account_id]
    account.balance += amount
    tx = Transaction(
        id=uuid.uuid4(),
        account_id=account.id,
        type="DEPOSITO",
        amount=amount,
        currency=account.currency,
        channel=channel,
        description=description,
        created_at=at or datetime.now(UTC),
    )
    session.add(tx)
    session.flush()
    return tx
