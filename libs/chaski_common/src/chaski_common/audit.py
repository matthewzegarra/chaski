"""Audit trail in ops.audit_log.

Records are written in their own transaction so they survive a rollback of the request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from chaski_common.db import get_engine
from chaski_common.logging import correlation_id_var, get_logger

if TYPE_CHECKING:
    from chaski_common.auth import CurrentUser

log = get_logger(__name__)

_INSERT = text(
    """
    INSERT INTO ops.audit_log
        (actor_id, actor_role, action, resource, resource_id, pii_accessed, allowed, ip,
         reason, correlation_id)
    VALUES
        (:actor_id, :actor_role, :action, :resource, :resource_id, :pii_accessed, :allowed, :ip,
         :reason, :correlation_id)
    """
)


def record(
    *,
    actor: CurrentUser | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    pii_accessed: bool = False,
    allowed: bool = True,
    ip: str | None = None,
    reason: str | None = None,
) -> None:
    """Write an audit record. Raises on failure so PII access can fail closed."""
    with get_engine().begin() as conn:
        conn.execute(
            _INSERT,
            {
                "actor_id": actor.sub if actor else "anonymous",
                "actor_role": actor.roles_str if actor else None,
                "action": action,
                "resource": resource,
                "resource_id": resource_id,
                "pii_accessed": pii_accessed,
                "allowed": allowed,
                "ip": ip,
                "reason": reason,
                "correlation_id": correlation_id_var.get(),
            },
        )


def record_safely(**kwargs: object) -> None:
    """Best-effort variant used on denial paths: never masks the original 403."""
    try:
        record(**kwargs)  # type: ignore[arg-type]
    except Exception:
        log.exception("audit_write_failed", action=kwargs.get("action"))
