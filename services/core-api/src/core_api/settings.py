from __future__ import annotations

from functools import lru_cache
from typing import Literal

from chaski_common.settings import CommonSettings
from pydantic import SecretStr


class CoreSettings(CommonSettings):
    ia_api_url: str = "http://localhost:8003"
    cuentas_api_url: str = "http://localhost:8001"
    analytics_db_url: str | None = None
    analytics_dialect: Literal["postgres", "tsql"] = "postgres"

    fraud_webhook_secret: SecretStr | None = None
    key_vault_url: str | None = None

    blob_account_url: str | None = None
    blob_container: str = "kyc"
    uploads_dir: str = ".data/uploads"

    azure_subscription_id: str | None = None
    azure_resource_group: str | None = None
    pipeline_job_name: str | None = None

    github_repo: str | None = None
    github_token: SecretStr | None = None

    @property
    def pipeline_job_configured(self) -> bool:
        return bool(
            self.azure_subscription_id and self.azure_resource_group and self.pipeline_job_name
        )


@lru_cache
def get_settings() -> CoreSettings:
    return CoreSettings()
