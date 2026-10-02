"""JWT authentication and role-based authorization.

AUTH_MODE=entra validates Entra ID tokens (RS256, JWKS, issuer, audience).
AUTH_MODE=dev validates HS256 tokens issued by core-api's /dev/token (local only).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chaski_common import audit
from chaski_common.roles import Role, parse_roles
from chaski_common.settings import CommonSettings, get_common_settings

DEV_ISSUER = "chaski-dev"
DEV_AUDIENCE = "chaski-api"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    name: str
    roles: frozenset[Role]
    customer_id: uuid.UUID | None
    token: str

    def has_any(self, roles: Iterable[Role]) -> bool:
        return bool(self.roles & set(roles))

    @property
    def roles_str(self) -> str:
        return ",".join(sorted(r.value for r in self.roles))

    @property
    def is_customer(self) -> bool:
        return Role.CLIENTE in self.roles


def issue_dev_token(
    *,
    sub: str,
    name: str,
    roles: Iterable[Role],
    customer_id: uuid.UUID | None = None,
    ttl_seconds: int = 8 * 3600,
    settings: CommonSettings | None = None,
) -> str:
    settings = settings or get_common_settings()
    if settings.auth_mode != "dev" or settings.dev_jwt_secret is None:
        raise RuntimeError("Dev tokens can only be issued when AUTH_MODE=dev")
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": DEV_ISSUER,
        "aud": DEV_AUDIENCE,
        "sub": sub,
        "name": name,
        "roles": [r.value for r in roles],
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if customer_id:
        claims["customer_id"] = str(customer_id)
    return jwt.encode(claims, settings.dev_jwt_secret.get_secret_value(), algorithm="HS256")


@lru_cache
def _jwks_client(tenant_id: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        cache_keys=True,
        lifespan=3600,
    )


def decode_token(token: str, settings: CommonSettings | None = None) -> dict[str, Any]:
    settings = settings or get_common_settings()
    if settings.auth_mode == "dev":
        assert settings.dev_jwt_secret is not None
        return jwt.decode(
            token,
            settings.dev_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=DEV_AUDIENCE,
            issuer=DEV_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    assert settings.entra_tenant_id is not None
    signing_key = _jwks_client(settings.entra_tenant_id).get_signing_key_from_jwt(token)
    claims: dict[str, Any] = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.entra_audience,
        options={"require": ["exp", "iss", "aud"], "verify_iss": False},
    )
    if claims.get("iss") not in settings.entra_issuers_list:
        raise jwt.InvalidIssuerError("Invalid issuer")
    return claims


def user_from_claims(claims: dict[str, Any], token: str) -> CurrentUser:
    raw_cid = claims.get("customer_id") or claims.get("extension_customer_id")
    customer_id: uuid.UUID | None = None
    if raw_cid:
        try:
            customer_id = uuid.UUID(str(raw_cid))
        except ValueError:
            customer_id = None
    return CurrentUser(
        sub=str(claims.get("oid") or claims.get("sub")),
        name=str(claims.get("name") or claims.get("preferred_username") or "desconocido"),
        roles=parse_roles(claims.get("roles")),
        customer_id=customer_id,
        token=token,
    )


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return user_from_claims(claims, credentials.credentials)


def deny(
    request: Request,
    user: CurrentUser | None,
    *,
    resource: str | None = None,
    resource_id: str | None = None,
    detail: str = "No tienes permiso para realizar esta acción",
) -> HTTPException:
    """Audit a denied access and build the 403 to raise."""
    audit.record_safely(
        actor=user,
        action=f"{request.method} {request.url.path}",
        resource=resource or request.url.path,
        resource_id=resource_id,
        allowed=False,
        ip=client_ip(request),
    )
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


def require_roles(*roles: Role) -> Callable[..., CurrentUser]:
    """Dependency factory: the caller must hold at least one of `roles`. Denials are audited."""
    allowed = frozenset(roles)

    def dependency(request: Request, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.roles & allowed:
            raise deny(request, user)
        return user

    return dependency


def require_customer(
    request: Request, user: CurrentUser = Depends(get_current_user)
) -> CurrentUser:
    """Dependency for customer-facing endpoints: role Cliente with a customer_id claim."""
    if Role.CLIENTE not in user.roles or user.customer_id is None:
        raise deny(request, user)
    return user
