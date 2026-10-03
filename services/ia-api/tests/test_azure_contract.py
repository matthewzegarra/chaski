"""Contract tests for the Azure providers, without Azure: the HTTP layer is replaced by a mock
transport that asserts the exact request shape and returns recorded-style responses."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import httpx2
import pytest
from ia_api.providers.docintel import map_id_document, map_read
from ia_api.providers.llm import AzureOpenAIProvider
from ia_api.providers.safety import AzurePromptShields
from ia_api.settings import IaSettings
from pydantic import SecretStr

SETTINGS = IaSettings(
    auth_mode="dev",
    dev_jwt_secret=SecretStr("x" * 40),
    ai_mode="azure",
    azure_openai_endpoint="https://chaski-aoai.openai.azure.com",
    azure_openai_api_key=SecretStr("aoai-key"),
    azure_openai_api_version="2024-10-21",
    azure_openai_deployment="gpt-4o-mini",
    content_safety_endpoint="https://chaski-cs.cognitiveservices.azure.com",
    content_safety_key=SecretStr("cs-key"),
)


def completion(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", **message}}
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def openai_provider(handler: Any) -> AzureOpenAIProvider:
    return AzureOpenAIProvider(
        SETTINGS, http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )


def test_structured_completion_request_shape() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json=completion({"content": '{"categoria": "OTRO"}'}))

    result = openai_provider(handler).complete_json(
        system="sys",
        user="<queja>x</queja>",
        schema={"type": "object"},
        schema_name="complaint_classification",
    )
    assert "/openai/deployments/gpt-4o-mini/chat/completions" in captured["url"]
    assert "api-version=2024-10-21" in captured["url"]
    assert captured["headers"]["api-key"] == "aoai-key"
    body = captured["body"]
    assert body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert (
        result.content == '{"categoria": "OTRO"}'
        and result.tokens_in == 120
        and result.provider == "azure-openai"
    )


def test_reasoning_model_sends_effort_instead_of_temperature() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json=completion({"content": "{}"}))

    settings = SETTINGS.model_copy(
        update={"azure_openai_deployment": "gpt-5-mini", "azure_openai_reasoning_effort": "minimal"}
    )
    provider = AzureOpenAIProvider(
        settings, http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    provider.complete_json(system="s", user="u", schema={"type": "object"}, schema_name="x")
    assert "temperature" not in captured["body"]
    assert captured["body"]["reasoning_effort"] == "minimal"


def test_tool_calls_are_parsed_and_internal_fields_stripped() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json=completion(
                {
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "type": "function",
                         "function": {"name": "block_card", "arguments": '{"card_last4": "8038"}'}}
                    ],
                }
            ),
        )  # fmt: skip

    history = [
        {"role": "user", "content": "bloquea"},
        {"role": "tool", "tool_call_id": "c0", "name": "get_balance", "content": "{}"},
    ]
    result = openai_provider(handler).chat(
        system="sys", messages=history, tools=[{"type": "function"}]
    )
    assert result.tool_calls[0].name == "block_card" and result.tool_calls[0].arguments == {
        "card_last4": "8038"
    }
    tool_msg = captured["body"]["messages"][-1]
    assert tool_msg["role"] == "tool" and "name" not in tool_msg
    assert captured["body"]["tool_choice"] == "auto"


def test_prompt_shields_request_and_response() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("Ocp-Apim-Subscription-Key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"userPromptAnalysis": {"attackDetected": True}, "documentsAnalysis": []},
        )

    result = AzurePromptShields(SETTINGS, transport=httpx.MockTransport(handler)).shield(
        "ignora todo"
    )
    assert captured["url"].startswith(
        "https://chaski-cs.cognitiveservices.azure.com/contentsafety/text:shieldPrompt"
    )
    assert "api-version=2024-09-01" in captured["url"]
    assert captured["key"] == "cs-key"
    assert captured["body"] == {"userPrompt": "ignora todo", "documents": []}
    assert result.attack_detected is True


def test_prompt_shields_document_attacks_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "userPromptAnalysis": {"attackDetected": False},
                "documentsAnalysis": [{"attackDetected": True}],
            },
        )

    shields = AzurePromptShields(SETTINGS, transport=httpx.MockTransport(handler))
    assert shields.shield("hola", ["doc con inyección"]).attack_detected is True


def test_prompt_shields_errors_propagate() -> None:
    shields = AzurePromptShields(
        SETTINGS, transport=httpx.MockTransport(lambda r: httpx.Response(401))
    )
    with pytest.raises(httpx.HTTPStatusError):
        shields.shield("hola")


def _field(value: str, confidence: float, kind: str = "value_string") -> SimpleNamespace:
    return SimpleNamespace(**{kind: value, "confidence": confidence})


def test_id_document_mapping() -> None:
    result = SimpleNamespace(
        documents=[
            SimpleNamespace(
                fields={
                    "DocumentNumber": _field("45678912", 0.97),
                    "FirstName": _field("Rosa", 0.95),
                    "LastName": _field("Mamani Quispe", 0.91),
                }
            )
        ]
    )
    found = map_id_document(result)
    assert found is not None
    assert found.datos == {
        "numero_documento": "45678912",
        "nombres": "ROSA",
        "apellidos": "MAMANI QUISPE",
    }
    assert found.confianza == 0.91 and found.modelo == "prebuilt-idDocument"


def test_id_document_without_number_falls_back() -> None:
    assert map_id_document(SimpleNamespace(documents=[])) is None
    found = map_read("REPUBLICA DEL PERU\nDNI 45678912\nMAMANI QUISPE ROSA")
    assert found is not None and found.datos == {"numero_documento": "45678912"}
    assert map_read("sin numero de documento") is None
