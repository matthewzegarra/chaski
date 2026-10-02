"""Modo Demo. Only available with DEMO_MODE=true and the Admin role (404 otherwise)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from chaski_common import audit, events, fraud, ledger
from chaski_common.auth import CurrentUser, client_ip, require_roles
from chaski_common.db import get_db
from chaski_common.models import Account, AuditLog, Customer, RawIngest
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.settings import get_settings

router = APIRouter(prefix="/demo", tags=["demo"])
BURST_SIZE = 8
BURST_WINDOW = timedelta(seconds=60)


def _require_demo() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(404, "Not Found")


class FraudBurstIn(BaseModel):
    customer_id: uuid.UUID | None = None


@router.post("/inject-bad-record", dependencies=[Depends(_require_demo)])
def inject_bad_record(
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Adds raw rows to ops.raw_ingest: one corrupt (goes to quarantine) and two valid ones."""
    account = db.scalars(select(Account).where(Account.status == "ACTIVA").limit(1)).first()
    now = datetime.now(UTC)
    good = [
        {
            "transaction_id": str(uuid.uuid4()),
            "account_id": str(account.id) if account else None,
            "amount": round(random.uniform(10, 300), 2),
            "currency": "PEN",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
        }
        for _ in range(2)
    ]
    bad = {
        "transaction_id": str(uuid.uuid4()),
        "account_id": str(uuid.uuid4()),
        "amount": -150.0,
        "currency": "XXX",
        "created_at": (now + timedelta(days=3)).isoformat(),
    }
    rows = [RawIngest(source="demo", payload=p) for p in [*good, bad]]
    db.add_all(rows)
    db.commit()
    audit.record(
        actor=user, action="DEMO_INJECT_BAD_RECORD", resource="raw_ingest", ip=client_ip(request)
    )
    return {
        "inserted": len(rows),
        "corrupt_raw_id": rows[-1].id,
        "message": (
            "Se insertó un registro corrupto. Ejecuta el pipeline para enviarlo a cuarentena."
        ),
    }


@router.post("/fraud-burst", dependencies=[Depends(_require_demo)])
def fraud_burst(
    body: FraudBurstIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """8 transfers from the same customer within 60 s, through the real ledger and fraud engine."""
    query = (
        select(Account)
        .join(Customer, Customer.id == Account.customer_id)
        .where(Account.currency == "PEN", Account.status == "ACTIVA", Account.balance >= 1500)
    )
    if body.customer_id:
        query = query.where(Account.customer_id == body.customer_id)
    account = db.scalars(query.order_by(Account.balance.desc()).limit(1)).first()
    if account is None:
        raise HTTPException(409, "No hay una cuenta con saldo suficiente para la demo")
    start = datetime.now(UTC) - BURST_WINDOW
    step = BURST_WINDOW / BURST_SIZE
    rules: list[str] = []
    published = []
    for i in range(BURST_SIZE):
        posted = ledger.transfer(
            db,
            customer_id=account.customer_id,
            from_account_id=account.id,
            to_account_number=f"{random.randint(10**19, 10**20 - 1)}",
            amount=Decimal(random.randint(80, 180)),
            description="Demo: ráfaga de transferencias",
            at=start + step * (i + 1),
        )
        db.commit()
        alerts = fraud.evaluate(db, posted.out_tx, account.customer_id)
        db.commit()
        rules += [a.rule for a in alerts]
        published.append(
            events.transaction_event(posted.out_tx, account.customer_id, [a.rule for a in alerts])
        )
    events.publish(published)
    audit.record(
        actor=user, action="DEMO_FRAUD_BURST", resource="customer",
        resource_id=str(account.customer_id), ip=client_ip(request),
    )  # fmt: skip
    return {"customer_id": str(account.customer_id), "transfers": BURST_SIZE, "alerts": rules}


@router.post("/forbidden-access", dependencies=[Depends(_require_demo)])
def forbidden_access(
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Entra-mode stand-in for "Probar acceso indebido": records exactly the audit entry a
    Marketing user gets when calling reveal-pii (with AUTH_MODE=dev the console makes the real
    call with a Marketing token instead)."""
    customer_id = db.scalar(select(Customer.id).limit(1))
    path = f"/api/v1/customers/{customer_id}/reveal-pii"
    marketing = CurrentUser(
        sub="demo.marketing", name="Demo Marketing", roles=frozenset({Role.MARKETING}),
        customer_id=None, token="",
    )  # fmt: skip
    audit.record(
        actor=marketing, action=f"POST {path}", resource=path, allowed=False,
        ip=client_ip(request), reason=f"Simulación desde Modo Demo por {user.sub}",
    )  # fmt: skip
    entry = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).one()
    return {
        "status_code": 403,
        "detail": "No tienes permiso para realizar esta acción",
        "simulated": True,
        "audit": {
            "id": entry.id,
            "actor_id": entry.actor_id,
            "actor_role": entry.actor_role,
            "action": entry.action,
            "allowed": entry.allowed,
            "created_at": entry.created_at.isoformat(),
        },
    }
