"""Consumer-loan pricing and French amortisation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

BASE_TEA = {"MASIVO": Decimal("0.35"), "PREFERENTE": Decimal("0.18"), "PYME": Decimal("0.25")}
RISK_SPREAD = {"BAJO": Decimal("0"), "MEDIO": Decimal("0.05"), "ALTO": Decimal("0.10")}
TERMS = (6, 12, 18, 24, 36, 48, 60)
CENT = Decimal("0.01")


def rate_for(segment: str, risk_level: str) -> Decimal:
    return BASE_TEA.get(segment, BASE_TEA["MASIVO"]) + RISK_SPREAD.get(risk_level, Decimal("0"))


def monthly_rate(tea: Decimal) -> Decimal:
    return Decimal(str((1 + float(tea)) ** (1 / 12) - 1))


def monthly_payment(amount: Decimal, tea: Decimal, months: int) -> Decimal:
    i = monthly_rate(tea)
    payment = amount * i / (1 - (1 + i) ** -months)
    return payment.quantize(CENT, rounding=ROUND_HALF_UP)


def schedule(
    amount: Decimal, tea: Decimal, months: int, start: date
) -> list[tuple[int, date, Decimal]]:
    payment = monthly_payment(amount, tea, months)
    return [(k, start + timedelta(days=30 * k), payment) for k in range(1, months + 1)]
