"""Service-to-service tokens, used when a call has no end-user token to forward
(e.g. anonymous onboarding calling ia-api).

dev:   short-lived HS256 token with role Operaciones.
entra: token for the API audience with the Operaciones application role.
       - Same tenant: the Managed Identity itself holds the role (DefaultAzureCredential).
       - Identity tenant different from the Azure tenant (ENTRA_SERVICE_CLIENT_ID set): the
         Managed Identity gets an assertion for api://AzureADTokenExchange and exchanges it
         for a token of the chaski-services app, which trusts that identity through a
         federated credential. No secrets either way.
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
    settings = get_common_settings()
    if settings.entra_service_client_id and settings.entra_tenant_id:
        from azure.identity import ClientAssertionCredential, ManagedIdentityCredential

        mi = ManagedIdentityCredential(client_id=settings.azure_client_id)

        def assertion() -> str:
            return str(mi.get_token("api://AzureADTokenExchange/.default").token)

        return ClientAssertionCredential(
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_service_client_id,
            func=assertion,
        )
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
