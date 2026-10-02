"""Seguridad y Auditoría: audit log, denied UI routes and Key Vault secret metadata."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from chaski_common import audit
from chaski_common.auth import CurrentUser, client_ip, get_current_user, require_roles
from chaski_common.db import get_db
from chaski_common.logging import get_logger
from chaski_common.models import AuditLog
from chaski_common.roles import Role
from chaski_common.schemas import ApiModel, Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.settings import get_settings

router = APIRouter(prefix="/security", tags=["seguridad"])
log = get_logger(__name__)
SECURITY_ROLES = (Role.ADMIN, Role.TI)


class AuditOut(ApiModel):
    id: int
    actor_id: str
    actor_role: str | None
    action: str
    resource: str
    resource_id: str | None
    pii_accessed: bool
    allowed: bool
    ip: str | None
    reason: str | None
    correlation_id: str | None
    created_at: datetime


class DeniedRouteIn(BaseModel):
    route: str = Field(min_length=1, max_length=200)
    module: str = Field(min_length=1, max_length=80)


class SecretMetadata(BaseModel):
    name: str
    enabled: bool
    version: str | None
    created_on: datetime | None
    updated_on: datetime | None
    expires_on: datetime | None
    days_to_expiry: int | None
    status: str


@router.get("/audit", response_model=Page[AuditOut])
def audit_log(
    allowed: bool | None = None,
    pii_accessed: bool | None = None,
    actor: str | None = Query(default=None, max_length=120),
    action: str | None = Query(default=None, max_length=120),
    since: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _user: CurrentUser = Depends(require_roles(*SECURITY_ROLES)),
    db: Session = Depends(get_db),
) -> Page[AuditOut]:
    conditions: list[Any] = []
    if allowed is not None:
        conditions.append(AuditLog.allowed.is_(allowed))
    if pii_accessed is not None:
        conditions.append(AuditLog.pii_accessed.is_(pii_accessed))
    if actor:
        conditions.append(AuditLog.actor_id.ilike(f"%{actor}%"))
    if action:
        conditions.append(AuditLog.action.ilike(f"%{action}%"))
    if since:
        conditions.append(AuditLog.created_at >= datetime.combine(since, time.min, UTC))
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[AuditOut.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/summary")
def summary(
    _user: CurrentUser = Depends(require_roles(*SECURITY_ROLES)), db: Session = Depends(get_db)
) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(hours=24)
    recent = AuditLog.created_at >= since
    return {
        "denegados_24h": db.scalar(select(func.count()).where(recent, AuditLog.allowed.is_(False)))
        or 0,
        "accesos_pii_24h": db.scalar(
            select(func.count()).where(recent, AuditLog.pii_accessed.is_(True))
        )
        or 0,
        "eventos_24h": db.scalar(select(func.count()).where(recent)) or 0,
    }


@router.post("/denied-route", status_code=202)
def denied_route(
    body: DeniedRouteIn, request: Request, user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    """The web apps report when a user opens a route their role cannot see."""
    audit.record_safely(
        actor=user,
        action=f"VIEW {body.route}",
        resource=f"ui:{body.module}",
        allowed=False,
        ip=client_ip(request),
    )
    return {"status": "registrado"}


def _mock_secrets() -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    specs = [
        ("postgres-app-password", 80, 365),
        ("postgres-readonly-password", 80, 365),
        ("azure-openai-api-key", 150, 180),
        ("content-safety-key", 150, 180),
        ("docintel-key", 150, 180),
        ("fraud-webhook-secret", 20, 90),
        ("eventstream-connection-string", 175, 180),
        ("github-readonly-token", 85, 90),
    ]
    return [
        {
            "name": name, "enabled": True, "version": hashlib.sha256(name.encode()).hexdigest()[:8],
            "created_on": now - timedelta(days=age), "updated_on": now - timedelta(days=age),
            "expires_on": now - timedelta(days=age) + timedelta(days=ttl),
        }
        for name, age, ttl in specs
    ]  # fmt: skip


def _keyvault_secrets(vault_url: str) -> list[dict[str, Any]]:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    # list_properties_of_secrets never returns secret values.
    return [
        {
            "name": p.name, "enabled": bool(p.enabled), "version": p.version,
            "created_on": p.created_on, "updated_on": p.updated_on, "expires_on": p.expires_on,
        }
        for p in client.list_properties_of_secrets()
    ]  # fmt: skip


@router.get("/secrets-metadata")
def secrets_metadata(
    _user: CurrentUser = Depends(require_roles(*SECURITY_ROLES)),
) -> dict[str, Any]:
    vault = get_settings().key_vault_url
    try:
        raw = _keyvault_secrets(vault) if vault else _mock_secrets()
    except Exception as exc:
        log.exception("keyvault_list_failed")
        raise HTTPException(502, "No se pudo leer Key Vault") from exc
    now = datetime.now(UTC)
    items = []
    for s in raw:
        days = (s["expires_on"] - now).days if s["expires_on"] else None
        status = (
            "SIN_EXPIRACION"
            if days is None
            else "VENCIDO"
            if days < 0
            else "POR_ROTAR"
            if days <= 30
            else "OK"
        )
        items.append(SecretMetadata(**s, days_to_expiry=days, status=status))
    items.sort(key=lambda m: (m.days_to_expiry is None, m.days_to_expiry or 0))
    return {
        "source": "keyvault" if vault else "mock",
        "secrets": [i.model_dump(mode="json") for i in items],
    }
