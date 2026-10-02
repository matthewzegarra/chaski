"""Settings shared by every service. Values come only from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "chaski"
    service_version: str = "0.1.0"
    chaski_env: Literal["DEV", "TEST", "PROD"] = "DEV"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://chaski_app:chaski_app_local@localhost:5432/chaski"

    auth_mode: Literal["dev", "entra"] = "dev"
    dev_jwt_secret: SecretStr | None = None
    entra_tenant_id: str | None = None
    entra_audience: str | None = None
    # Comma-separated list. Defaults to the v1 and v2 issuers of the tenant.
    entra_issuers: str | None = None
    # Service-to-service across tenants: chaski-services app id + the Managed Identity
    # (AZURE_CLIENT_ID) whose assertion it trusts. See service_auth.py.
    entra_service_client_id: str | None = None
    azure_client_id: str | None = None

    allowed_origins: str = "http://localhost:3000,http://localhost:3001"
    rate_limit_per_minute: int = 300

    demo_mode: bool = False
    eventstream_connection_string: str | None = None
    eventstream_name: str | None = None
    applicationinsights_connection_string: str | None = None

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def entra_issuers_list(self) -> list[str]:
        if self.entra_issuers:
            return [i.strip() for i in self.entra_issuers.split(",") if i.strip()]
        tenant = self.entra_tenant_id
        return [
            f"https://login.microsoftonline.com/{tenant}/v2.0",
            f"https://sts.windows.net/{tenant}/",
        ]

    @model_validator(mode="after")
    def _check_auth(self) -> CommonSettings:
        if self.auth_mode == "dev":
            if self.chaski_env == "PROD":
                raise ValueError("AUTH_MODE=dev is not allowed when CHASKI_ENV=PROD")
            if self.dev_jwt_secret is None or len(self.dev_jwt_secret.get_secret_value()) < 32:
                raise ValueError("DEV_JWT_SECRET must be set (>= 32 chars) when AUTH_MODE=dev")
        if self.auth_mode == "entra" and not (self.entra_tenant_id and self.entra_audience):
            raise ValueError("ENTRA_TENANT_ID and ENTRA_AUDIENCE are required when AUTH_MODE=entra")
        return self


@lru_cache
def get_common_settings() -> CommonSettings:
    return CommonSettings()
