"""Prompt Shields (Azure AI Content Safety) to detect prompt-injection / jailbreak attempts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from ia_api.settings import IaSettings, get_settings

API_VERSION = "2024-09-01"


@dataclass(frozen=True)
class ShieldResult:
    attack_detected: bool
    provider: str


class SafetyProvider(Protocol):
    name: str

    def shield(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult: ...


class AzurePromptShields:
    name = "azure-content-safety"

    def __init__(self, settings: IaSettings, transport: httpx.BaseTransport | None = None) -> None:
        if not settings.content_safety_endpoint:
            raise RuntimeError("CONTENT_SAFETY_ENDPOINT is required in AI_MODE=azure")
        self.url = f"{settings.content_safety_endpoint.rstrip('/')}/contentsafety/text:shieldPrompt"
        self.key = settings.content_safety_key
        self.http = httpx.Client(timeout=10, transport=transport)

    def _headers(self) -> dict[str, str]:
        if self.key:
            return {"Ocp-Apim-Subscription-Key": self.key.get_secret_value()}
        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}

    def shield(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult:
        resp = self.http.post(
            self.url,
            params={"api-version": API_VERSION},
            headers=self._headers(),
            json={"userPrompt": user_prompt, "documents": documents or []},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        attack = bool(body.get("userPromptAnalysis", {}).get("attackDetected")) or any(
            d.get("attackDetected") for d in body.get("documentsAnalysis", [])
        )
        return ShieldResult(attack_detected=attack, provider=self.name)


_INJECTION_PATTERNS = [
    r"ignora(r)?\s+(todas?\s+)?(las|tus|mis)?\s*(instrucciones|reglas|indicaciones)",
    r"olvida\s+(todo|tus|las)\s+(instrucciones|reglas)",
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"\bsystem\s*:",
    r"(prompt|mensaje)\s+del\s+sistema",
    r"nueva\s+instrucci[oó]n",
    r"sin\s+restricciones",
    r"(act[uú]a|comp[oó]rtate)\s+como",
    r"eres\s+ahora",
    r"</?\s*(queja|system|instrucciones)\s*>",
    r"jailbreak|do anything now|\bdan\b",
    r"(muestra|devuelve|revela)\s+(el|los|tu)\s+(prompt|saldo y el dni|dni de todos)",
    r"marca\s+sospechosa\s*=\s*false",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


class MockPromptShields:
    """Heuristic stand-in for local development: flags classic injection phrasings."""

    name = "mock-shields"

    def shield(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult:
        texts = [user_prompt, *(documents or [])]
        return ShieldResult(
            attack_detected=any(_INJECTION_RE.search(_plain(t)) for t in texts),
            provider=self.name,
        )


@lru_cache
def get_safety() -> SafetyProvider:
    settings = get_settings()
    if settings.ai_mode == "azure":
        return AzurePromptShields(settings)
    return MockPromptShields()
