"""Opens the starter products of a customer approved in onboarding."""

from __future__ import annotations

import secrets
import uuid

from chaski_common.models import Account, Card, Customer
from sqlalchemy import select
from sqlalchemy.orm import Session


def _new_account_number(db: Session) -> str:
    while True:
        number = f"200-{3_000_000_000 + secrets.randbelow(1_000_000_000)}"
        if not db.scalar(select(Account.id).where(Account.number == number)):
            return number


def open_starter_products(db: Session, customer: Customer) -> tuple[Account, Card]:
    """Savings account in soles + a debit card. The card is a token: no PAN is ever generated."""
    account = Account(
        id=uuid.uuid4(),
        customer_id=customer.id,
        number=_new_account_number(db),
        product="AHORRO_SOLES",
        currency="PEN",
    )
    db.add(account)
    db.flush()
    card = Card(
        id=uuid.uuid4(),
        customer_id=customer.id,
        account_id=account.id,
        type="DEBITO",
        token=f"tok_{secrets.token_hex(12)}",
        last4=f"{secrets.randbelow(10_000):04d}",
        brand="VISA",
    )
    db.add(card)
    db.flush()
    return account, card
