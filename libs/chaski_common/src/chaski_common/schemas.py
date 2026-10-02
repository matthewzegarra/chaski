"""Shared Pydantic types."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Money is validated as an exact Decimal and serialized to JSON as a number (charts need it).
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
PositiveAmount = Annotated[
    Decimal,
    Field(gt=0, le=Decimal("100000"), max_digits=12, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
