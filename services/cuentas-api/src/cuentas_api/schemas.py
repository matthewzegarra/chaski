from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from chaski_common.schemas import ApiModel, Money, PositiveAmount
from pydantic import BaseModel, Field

ACCOUNT_NUMBER_PATTERN = r"^(\d{3}-\d{10}|\d{20})$"  # internal number or 20-digit CCI


class AccountOut(ApiModel):
    id: uuid.UUID
    number: str
    product: str
    currency: str
    balance: Money
    status: str
    opened_at: datetime


class BalanceOut(BaseModel):
    account_id: uuid.UUID
    currency: str
    balance: Money
    as_of: datetime


class MovementOut(ApiModel):
    id: uuid.UUID
    account_id: uuid.UUID
    card_id: uuid.UUID | None
    type: str
    direction: Literal["CREDITO", "DEBITO"]
    amount: Money
    currency: str
    channel: str
    merchant: str | None
    city: str | None
    counterparty_account: str | None
    description: str | None
    created_at: datetime


class TransferIn(BaseModel):
    from_account_id: uuid.UUID
    to_account_number: str = Field(pattern=ACCOUNT_NUMBER_PATTERN)
    amount: PositiveAmount
    description: str | None = Field(default=None, max_length=140)


class CardPaymentIn(BaseModel):
    card_id: uuid.UUID
    amount: PositiveAmount
    merchant: str = Field(min_length=2, max_length=80)
    city: str | None = Field(default=None, max_length=60)
    channel: Literal["POS", "WEB"] = "POS"


class ReceiptOut(BaseModel):
    """Comprobante shown to the customer."""

    transaction_id: uuid.UUID
    operation: str
    amount: Money
    currency: str
    from_account_number: str | None = None
    to_account_number: str | None = None
    card_last4: str | None = None
    merchant: str | None = None
    internal: bool | None = None
    new_balance: Money
    created_at: datetime
