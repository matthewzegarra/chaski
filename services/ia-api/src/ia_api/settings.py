from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from chaski_common.settings import CommonSettings
from pydantic import SecretStr


def _default_prompts_dir() -> str:
    # Repo layout: services/ia-api/src/ia_api/settings.py -> <root>/genai/prompts
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "genai" / "prompts"
        if candidate.is_dir():
            return str(candidate)
    return "/app/genai/prompts"


class IaSettings(CommonSettings):
    ai_mode: Literal["mock", "azure"] = "mock"
    prompts_dir: str = _default_prompts_dir()

    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = None

    content_safety_endpoint: str | None = None
    content_safety_key: SecretStr | None = None
    docintel_endpoint: str | None = None
    docintel_key: SecretStr | None = None

    analytics_db_url: str | None = None
    nl2sql_db_url: str | None = None
    analytics_dialect: Literal["postgres", "tsql"] = "postgres"

    cuentas_api_url: str = "http://localhost:8001"
    core_api_url: str = "http://localhost:8002"


@lru_cache
def get_settings() -> IaSettings:
    return IaSettings()
