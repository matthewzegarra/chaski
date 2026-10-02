"""Local-only identity helpers (AUTH_MODE=dev). Return 404 in any other mode."""

from __future__ import annotations

import uuid
from typing import Any

from chaski_common.auth import issue_dev_token
from chaski_common.db import get_db
from chaski_common.models import Account, Customer
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from core_api.settings import get_settings

router = APIRouter(prefix="/dev", tags=["dev"])

TTL = 8 * 3600
STAFF_PERSONAS = [
    {"sub": "admin.demo", "name": "Andrea Salazar", "roles": [Role.ADMIN]},
    {"sub": "operaciones.demo", "name": "Óscar Medina", "roles": [Role.OPERACIONES]},
    {"sub": "atencion.demo", "name": "Lucía Paredes", "roles": [Role.ATENCION]},
    {"sub": "riesgos.demo", "name": "Renzo Cárdenas", "roles": [Role.RIESGOS]},
    {"sub": "fraude.demo", "name": "Fiorella Vásquez", "roles": [Role.FRAUDE]},
    {"sub": "direccion.demo", "name": "Diego Valdivia", "roles": [Role.DIRECCION]},
    {"sub": "marketing.demo", "name": "Milagros Ríos", "roles": [Role.MARKETING]},
    {"sub": "ti.demo", "name": "Tomás Ccahuana", "roles": [Role.TI]},
]


def _require_dev() -> None:
    if get_settings().auth_mode != "dev":
        raise HTTPException(404, "Not Found")


class DevTokenIn(BaseModel):
    sub: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    roles: list[Role] = Field(min_length=1)
    customer_id: uuid.UUID | None = None


class DevTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int = TTL


@router.post("/token", response_model=DevTokenOut, dependencies=[Depends(_require_dev)])
def dev_token(body: DevTokenIn, db: Session = Depends(get_db)) -> DevTokenOut:
    if Role.CLIENTE in body.roles and (
        body.customer_id is None or db.get(Customer, body.customer_id) is None
    ):
        raise HTTPException(422, "El rol Cliente requiere un customer_id existente")
    sub = body.sub or (f"cliente-{body.customer_id}" if body.customer_id else body.name)
    token = issue_dev_token(
        sub=sub, name=body.name, roles=body.roles, customer_id=body.customer_id, ttl_seconds=TTL
    )
    return DevTokenOut(access_token=token)


@router.get("/users", dependencies=[Depends(_require_dev)])
def dev_users(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Personas for the local user/role selector."""
    has_account = exists().where(Account.customer_id == Customer.id)
    approved = db.scalars(
        select(Customer)
        .where(Customer.kyc_status == "APROBADO", has_account)
        .order_by(Customer.created_at.desc())
        .limit(6)
    ).all()
    pending = db.scalars(
        select(Customer)
        .where(Customer.kyc_status == "PENDIENTE")
        .order_by(Customer.created_at.desc())
        .limit(2)
    ).all()
    customers = [
        {
            "customer_id": str(c.id),
            "name": f"{c.first_name} {c.last_name}",
            "segment": c.segment,
            "kyc_status": c.kyc_status,
        }
        for c in [*approved, *pending]
    ]
    staff: list[dict[str, object]] = [
        {"sub": p["sub"], "name": p["name"], "roles": [str(r) for r in p["roles"]]}
        for p in STAFF_PERSONAS
    ]
    return {"staff": staff, "customers": customers}
