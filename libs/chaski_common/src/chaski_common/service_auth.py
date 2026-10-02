"""Service-to-service tokens, used when a call has no end-user token to forward
(e.g. anonymous onboarding calling ia-api).

dev:   short-lived HS256 token with role Operaciones.
entra: Managed Identity token for the API audience; the identity must be assigned the
       Operaciones app role in Entra ID.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

from chaski_common.auth import issue_dev_token
from chaski_common.roles import Role
from chaski_common.settings import get_common_settings

_cache: dict[str, tuple[str, float]] = {}


@lru_cache
def _credential() -> Any:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def service_token() -> str:
    settings = get_common_settings()
    cached = _cache.get("token")
    if cached and cached[1] - 60 > time.time():
        return cached[0]
    if settings.auth_mode == "dev":
        token = issue_dev_token(
            sub=f"svc-{settings.service_name}",
            name=settings.service_name,
            roles=[Role.OPERACIONES],
            ttl_seconds=300,
        )
        expires = time.time() + 300
    else:
        access = _credential().get_token(f"{settings.entra_audience}/.default")
        token, expires = access.token, float(access.expires_on)
    _cache["token"] = (token, expires)
    return token
