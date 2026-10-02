"""Chaski Guard: local fraud rules engine (source=RULES).

Rules are pure functions over pre-computed features so they are trivial to unit test;
`evaluate` gathers the features with SQL and persists one alert per rule hit.
Fabric sends its own alerts (source=FABRIC) through core-api's webhook.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chaski_common.models import Account, FraudAlert, Transaction

USD_PEN = Decimal("3.75")
R1_MAX_TRANSFERS = 5
R1_WINDOW = timedelta(minutes=2)
R2_FACTOR = Decimal(3)
R2_MIN_HISTORY = 3
R3_WINDOW = timedelta(minutes=30)
R4_THRESHOLD_PEN = Decimal(5000)
DEBIT_TYPES = ("TRANSFERENCIA_OUT", "PAGO_TARJETA", "PAGO_SERVICIO", "RETIRO")


@dataclass(frozen=True)
class RuleHit:
    rule: str
    score: Decimal
    description: str
    details: dict[str, Any] = field(default_factory=dict)


def r1_velocity(transfers_in_window: int) -> RuleHit | None:
    if transfers_in_window > R1_MAX_TRANSFERS:
        return RuleHit(
            "R1_VELOCIDAD",
            Decimal("85.00"),
            "Más de 5 transferencias en 2 minutos",
            {"transferencias_2min": transfers_in_window},
        )
    return None


def r2_atypical_amount(amount: Decimal, avg_30d: Decimal | None, history: int) -> RuleHit | None:
    if history < R2_MIN_HISTORY or not avg_30d or avg_30d <= 0:
        return None
    ratio = amount / avg_30d
    if ratio > R2_FACTOR:
        score = min(Decimal("99.00"), Decimal(50) + ratio * 5).quantize(Decimal("0.01"))
        return RuleHit(
            "R2_MONTO_ATIPICO",
            score,
            "Monto mayor a 3 veces el promedio de 30 días",
            {
                "monto": float(amount),
                "promedio_30d": round(float(avg_30d), 2),
                "veces": round(float(ratio), 1),
            },
        )
    return None


def r3_city_jump(city: str | None, last_city: str | None, gap: timedelta | None) -> RuleHit | None:
    if not city or not last_city or gap is None:
        return None
    if city.strip().lower() != last_city.strip().lower() and gap < R3_WINDOW:
        return RuleHit(
            "R3_CIUDAD_DISTINTA",
            Decimal("80.00"),
            "Pago en ciudad distinta en menos de 30 minutos",
            {
                "ciudad": city,
                "ciudad_anterior": last_city,
                "minutos": round(gap.total_seconds() / 60, 1),
            },
        )
    return None


def r4_new_beneficiary(amount_pen: Decimal, is_new_beneficiary: bool) -> RuleHit | None:
    if is_new_beneficiary and amount_pen > R4_THRESHOLD_PEN:
        return RuleHit(
            "R4_BENEFICIARIO_NUEVO",
            Decimal("75.00"),
            "Transferencia mayor a S/ 5,000 a beneficiario nuevo",
            {"monto_pen": float(amount_pen)},
        )
    return None


def evaluate(session: Session, tx: Transaction, customer_id: uuid.UUID) -> list[FraudAlert]:
    """Run R1-R4 for a freshly posted transaction. Adds alerts to the session (caller commits)."""
    account_ids = select(Account.id).where(Account.customer_id == customer_id)
    mine = Transaction.account_id.in_(account_ids)
    hits: list[RuleHit] = []

    if tx.type == "TRANSFERENCIA_OUT":
        count = session.scalar(
            select(func.count()).where(
                mine,
                Transaction.type == "TRANSFERENCIA_OUT",
                Transaction.created_at > tx.created_at - R1_WINDOW,
                Transaction.created_at <= tx.created_at,
            )
        )
        hit = r1_velocity(count or 0)
        # One R1 alert per burst: skip if the customer already has one in the window.
        if hit and not session.scalar(
            select(func.count()).where(
                FraudAlert.customer_id == customer_id,
                FraudAlert.rule == hit.rule,
                FraudAlert.created_at > tx.created_at - R1_WINDOW,
            )
        ):
            hits.append(hit)

        previous = session.scalar(
            select(func.count()).where(
                mine,
                Transaction.type == "TRANSFERENCIA_OUT",
                Transaction.counterparty_account == tx.counterparty_account,
                Transaction.id != tx.id,
            )
        )
        amount_pen = tx.amount * (USD_PEN if tx.currency == "USD" else 1)
        if hit4 := r4_new_beneficiary(amount_pen, not previous):
            hits.append(hit4)

    if tx.type in DEBIT_TYPES:
        avg, n = session.execute(
            select(func.avg(Transaction.amount), func.count()).where(
                mine,
                Transaction.type.in_(DEBIT_TYPES),
                Transaction.currency == tx.currency,
                Transaction.created_at >= tx.created_at - timedelta(days=30),
                Transaction.created_at < tx.created_at,
                Transaction.id != tx.id,
            )
        ).one()
        if hit2 := r2_atypical_amount(tx.amount, avg, n):
            hits.append(hit2)

    if tx.type == "PAGO_TARJETA" and tx.city:
        last = session.execute(
            select(Transaction.city, Transaction.created_at)
            .where(mine, Transaction.city.is_not(None), Transaction.id != tx.id)
            .where(Transaction.created_at <= tx.created_at)
            .order_by(Transaction.created_at.desc())
            .limit(1)
        ).first()
        if last and (hit3 := r3_city_jump(tx.city, last.city, tx.created_at - last.created_at)):
            hits.append(hit3)

    alerts = [
        FraudAlert(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            customer_id=customer_id,
            rule=h.rule,
            score=h.score,
            source="RULES",
            status="ABIERTA",
            details={"descripcion": h.description, **h.details},
            created_at=tx.created_at,
        )
        for h in hits
    ]
    session.add_all(alerts)
    session.flush()
    return alerts
