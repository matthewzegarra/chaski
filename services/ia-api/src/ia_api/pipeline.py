"""Common pipeline for every AI call (prompt section 8):

redact PII -> Prompt Shields -> LLM (temperature 0, JSON schema) -> validate schema
-> record in ops.ai_interactions (prompt id/version, latency, tokens, confidence, shields).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from chaski_common.db import get_engine
from chaski_common.logging import get_logger, redact
from chaski_common.models import AiInteraction
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ia_api.prompts import Prompt
from ia_api.providers.llm import LLMResult, get_llm
from ia_api.providers.safety import get_safety

log = get_logger(__name__)
MAX_STORED_INPUT = 4000


class AiUnavailable(RuntimeError):
    """The model failed or returned something that does not match the schema."""


@dataclass
class Outcome[T: BaseModel]:
    output: T | None
    blocked: bool
    interaction_id: uuid.UUID
    provider: str
    latency_ms: int


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic schema adapted to OpenAI strict mode (all fields required, no extra keys)."""
    schema = model.model_json_schema()

    def fix(node: dict[str, Any]) -> None:
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])
        for value in node.values():
            if isinstance(value, dict):
                fix(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        fix(item)

    fix(schema)
    for definition in schema.get("$defs", {}).values():
        fix(definition)
    return schema


def record(
    *,
    use_case: str,
    prompt: Prompt,
    input_text: str,
    output: dict[str, Any] | None,
    latency_ms: int,
    result: LLMResult | None,
    confidence: float | None = None,
    blocked: bool = False,
    provider: str,
) -> uuid.UUID:
    interaction_id = uuid.uuid4()
    with Session(get_engine()) as db:
        db.add(
            AiInteraction(
                id=interaction_id,
                use_case=use_case,
                prompt_id=prompt.id,
                prompt_version=prompt.version,
                input_redacted=redact(input_text)[:MAX_STORED_INPUT],
                output=output,
                latency_ms=latency_ms,
                tokens_in=result.tokens_in if result else None,
                tokens_out=result.tokens_out if result else None,
                confidence=Decimal(str(round(confidence, 3))) if confidence is not None else None,
                blocked_by_shields=blocked,
                provider=provider,
            )
        )
        db.commit()
    return interaction_id


def run_structured[T: BaseModel](
    *,
    use_case: str,
    prompt: Prompt,
    user_text: str,
    model: type[T],
    shield_text: str | None = None,
    confidence_field: str | None = None,
    extra_log: dict[str, Any] | None = None,
    schema_name: str | None = None,
) -> Outcome[T]:
    """Runs one structured completion through the full pipeline.

    If Prompt Shields flags `shield_text`, the model is NOT called: output is None and
    `blocked` is True, and the caller decides the safe fallback.
    """
    start = time.perf_counter()
    redacted = redact(user_text)
    safety = get_safety()
    if shield_text is not None and safety.shield(redact(shield_text)).attack_detected:
        latency = int((time.perf_counter() - start) * 1000)
        iid = record(
            use_case=use_case, prompt=prompt, input_text=redacted,
            output={"blocked": True, **(extra_log or {})}, latency_ms=latency, result=None,
            blocked=True, provider=safety.name,
        )  # fmt: skip
        log.warning("prompt_shields_blocked", use_case=use_case)
        return Outcome(
            output=None, blocked=True, interaction_id=iid, provider=safety.name, latency_ms=latency
        )

    llm = get_llm()
    try:
        result = llm.complete_json(
            system=prompt.text,
            user=redacted,
            schema=strict_schema(model),
            schema_name=schema_name or use_case,
        )
        parsed = model.model_validate(json.loads(result.content or "{}"))
    except (ValidationError, json.JSONDecodeError) as exc:
        log.warning("llm_output_invalid", use_case=use_case, error_type=type(exc).__name__)
        raise AiUnavailable("La respuesta del modelo no cumple el esquema") from exc
    except Exception as exc:
        log.warning("llm_call_failed", use_case=use_case, error_type=type(exc).__name__)
        raise AiUnavailable("El servicio de IA no está disponible") from exc

    latency = int((time.perf_counter() - start) * 1000)
    output = parsed.model_dump(mode="json")
    confidence = output.get(confidence_field) if confidence_field else None
    iid = record(
        use_case=use_case, prompt=prompt, input_text=redacted,
        output={**output, **(extra_log or {})}, latency_ms=latency, result=result,
        confidence=confidence, provider=llm.name,
    )  # fmt: skip
    return Outcome(
        output=parsed, blocked=False, interaction_id=iid, provider=llm.name, latency_ms=latency
    )
