"""LLM providers. `AzureOpenAIProvider` talks to Azure OpenAI; `MockProvider` (mock_llm.py)
reproduces the same contract deterministically so everything works without Azure."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol, cast

from ia_api.settings import IaSettings, get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int | None = None
    tokens_out: int | None = None
    provider: str = "mock"


class LLMProvider(Protocol):
    name: str

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], schema_name: str
    ) -> LLMResult: ...

    def chat(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResult: ...


class AzureOpenAIProvider:
    """Azure OpenAI chat completions, deterministic sampling, strict JSON schema output.

    temperature 0, or AZURE_OPENAI_REASONING_EFFORT for reasoning models (gpt-5 family).

    Authenticates with AZURE_OPENAI_API_KEY when set, otherwise with Managed Identity
    (DefaultAzureCredential) through an Entra ID token provider.
    """

    name = "azure-openai"

    def __init__(self, settings: IaSettings, http_client: Any = None) -> None:
        from openai import AzureOpenAI

        if not (settings.azure_openai_endpoint and settings.azure_openai_deployment):
            raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT are required")
        kwargs: dict[str, Any] = {
            "azure_endpoint": settings.azure_openai_endpoint,
            "api_version": settings.azure_openai_api_version,
            "timeout": 30,
            "max_retries": 2,
        }
        if settings.azure_openai_api_key:
            kwargs["api_key"] = settings.azure_openai_api_key.get_secret_value()
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
        if http_client is not None:
            kwargs["http_client"] = http_client
        self.client = AzureOpenAI(**kwargs)
        self.deployment = settings.azure_openai_deployment
        # Reasoning models (gpt-5 family) reject `temperature`; they take an effort level.
        effort = settings.azure_openai_reasoning_effort
        self.sampling: dict[str, Any] = (
            {"reasoning_effort": effort} if effort else {"temperature": 0}
        )

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], schema_name: str
    ) -> LLMResult:
        resp = self.client.chat.completions.create(
            model=self.deployment,
            **self.sampling,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )
        return self._result(resp)

    def chat(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResult:
        # "name" on tool messages is internal bookkeeping (the mock uses it): drop it.
        sent = [
            {"role": "system", "content": system},
            *(
                {k: v for k, v in m.items() if not (m.get("role") == "tool" and k == "name")}
                for m in messages
            ),
        ]
        resp = self.client.chat.completions.create(
            model=self.deployment,
            **self.sampling,
            messages=cast(Any, sent),
            tools=cast(Any, tools),
            tool_choice="auto",
        )
        return self._result(resp)

    def _result(self, resp: Any) -> LLMResult:
        msg = resp.choices[0].message
        calls = [
            ToolCall(
                id=c.id, name=c.function.name, arguments=json.loads(c.function.arguments or "{}")
            )
            for c in (msg.tool_calls or [])
        ]
        usage = getattr(resp, "usage", None)
        return LLMResult(
            content=msg.content,
            tool_calls=calls,
            tokens_in=getattr(usage, "prompt_tokens", None),
            tokens_out=getattr(usage, "completion_tokens", None),
            provider=self.name,
        )


@lru_cache
def get_llm() -> LLMProvider:
    settings = get_settings()
    if settings.ai_mode == "azure":
        return AzureOpenAIProvider(settings)
    from ia_api.providers.mock_llm import MockProvider

    return MockProvider()
