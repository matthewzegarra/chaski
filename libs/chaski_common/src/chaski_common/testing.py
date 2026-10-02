"""Test factories shared by every service's test suite (never imported by app code)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from chaski_common.auth import issue_dev_token
from chaski_common.db import get_engine
from chaski_common.models import Account, Card, Customer, Transaction
from chaski_common.roles import Role


def session() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()


def make_customer(s: Session, **kw: Any) -> Customer:
    n = random.randint(10_000_000, 99_999_999)
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "document_number": str(n),
        "first_name": "María",
        "last_name": "Quispe Rojas",
        "email": f"maria{n}@dominio.com",
        "phone": "987654123",
        "birth_date": date(1990, 5, 17),
        "segment": "MASIVO",
        "region": "Lima",
        "kyc_status": "APROBADO",
        "monthly_income": Decimal("3500.00"),
    }
    data.update(kw)
    c = Customer(**data)
    s.add(c)
    s.commit()
    return c


def make_account(
    s: Session, customer: Customer, balance: str | Decimal = "1000.00", **kw: Any
) -> Account:
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "customer_id": customer.id,
        "number": f"200-{random.randint(3_000_000_000, 3_999_999_999)}",
        "product": "AHORRO_SOLES",
        "currency": "PEN",
        "balance": Decimal(balance),
    }
    data.update(kw)
    a = Account(**data)
    s.add(a)
    s.commit()
    return a


def make_card(s: Session, customer: Customer, account: Account | None = None, **kw: Any) -> Card:
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "customer_id": customer.id,
        "account_id": account.id if account else None,
        "type": "DEBITO" if account else "CREDITO",
        "token": f"tok_{uuid.uuid4().hex[:24]}",
        "last4": f"{random.randint(0, 9999):04d}",
        "brand": "VISA",
        "credit_limit": None if account else Decimal("5000.00"),
    }
    data.update(kw)
    c = Card(**data)
    s.add(c)
    s.commit()
    return c


def make_tx(s: Session, account: Account, **kw: Any) -> Transaction:
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account.id,
        "type": "PAGO_TARJETA",
        "amount": Decimal("50.00"),
        "currency": account.currency,
        "channel": "POS",
        "created_at": datetime.now(UTC),
    }
    data.update(kw)
    t = Transaction(**data)
    s.add(t)
    s.commit()
    return t


def headers(
    *roles: Role, customer_id: uuid.UUID | None = None, sub: str = "tester"
) -> dict[str, str]:
    token = issue_dev_token(sub=sub, name="Tester", roles=roles, customer_id=customer_id)
    return {"Authorization": f"Bearer {token}"}


def customer_headers(customer: Customer) -> dict[str, str]:
    return headers(Role.CLIENTE, customer_id=customer.id, sub=f"cliente-{customer.id}")
