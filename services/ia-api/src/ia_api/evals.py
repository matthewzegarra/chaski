"""Offline evaluation of the CHASKI GenAI use cases (Phase 9.3).

    python -m ia_api.evals [--min-accuracy 0.7] [--output results.json]

Runs the labelled datasets of genai/evals/ through the same code paths as production:
- quejas_etiquetadas.jsonl (60): complaint classifier via pipeline.run_structured, which
  includes Prompt Shields. Metrics: category and urgency accuracy, per-category precision
  and recall, injection detection rate, suspicious false-positive rate, human-review rate,
  latency (avg, p95).
- dataset.jsonl (20): assistant tool selection on the first turn (no tool is executed), and
  refusal of out-of-scope or manipulative requests.

Uses the configured provider (AI_MODE=mock locally and in CI, azure in the caj-ai-evals
job). Every call is recorded in ops.ai_interactions under use_case="evaluacion_*" so the
console's "Salud de IA" keeps them apart from production traffic. The JSON report is also
written to the data lake (silver/ai-evals/) when BLOB_ACCOUNT_URL is set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaski_common.logging import configure_logging, get_logger

from ia_api import pipeline
from ia_api.assistant import TOOLS
from ia_api.prompts import load_prompt
from ia_api.providers.llm import get_llm
from ia_api.providers.safety import get_safety
from ia_api.routers.cases import Classification, requires_review
from ia_api.settings import get_settings

log = get_logger(__name__)


def _datasets_dir() -> Path:
    return Path(get_settings().prompts_dir).parent / "evals"


def _load(name: str) -> list[dict[str, Any]]:
    path = _datasets_dir() / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, round(0.95 * len(ordered)) - 1)] if ordered else 0


def eval_complaints() -> dict[str, Any]:
    prompt = load_prompt("complaint_classifier")
    rows = _load("quejas_etiquetadas.jsonl")
    hits = urgency_hits = review = errors = 0
    injection_total = injection_caught = clean_total = clean_flagged = 0
    latencies: list[int] = []
    predicted: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    expected: Counter[str] = Counter()
    misses: list[dict[str, str]] = []
    for row in rows:
        text = f"Asunto: {row['asunto']}\n{row['texto']}"
        start = time.perf_counter()
        try:
            outcome = pipeline.run_structured(
                use_case="evaluacion_quejas",
                prompt=prompt,
                user_text=f"<queja>{text}</queja>",
                model=Classification,
                shield_text=text,
                confidence_field="confianza",
                extra_log={"dataset_id": row["id"]},
                schema_name="complaint_classification",
            )
        except pipeline.AiUnavailable:
            errors += 1
            continue
        latencies.append(int((time.perf_counter() - start) * 1000))
        result = outcome.output
        suspicious = outcome.blocked or (result is not None and result.sospechosa)
        if row["inyeccion"]:
            injection_total += 1
            injection_caught += int(suspicious)
            review += 1  # blocked or suspicious always go to the human queue
            continue
        clean_total += 1
        clean_flagged += int(suspicious)
        if result is None:
            continue
        expected[row["categoria"]] += 1
        predicted[result.categoria] += 1
        review += int(requires_review(result))
        if result.categoria == row["categoria"]:
            hits += 1
            correct[row["categoria"]] += 1
        else:
            misses.append(
                {"id": row["id"], "esperada": row["categoria"], "predicha": result.categoria}
            )
        urgency_hits += int(result.urgencia == row["urgencia"])

    per_category = {
        cat: {
            "precision": round(correct[cat] / predicted[cat], 3) if predicted[cat] else None,
            "recall": round(correct[cat] / expected[cat], 3) if expected[cat] else None,
            "soporte": expected[cat],
        }
        for cat in sorted(expected)
    }
    return {
        "prompt_version": prompt.version,
        "total": len(rows),
        "accuracy_categoria": round(hits / clean_total, 3) if clean_total else 0.0,
        "accuracy_urgencia": round(urgency_hits / clean_total, 3) if clean_total else 0.0,
        "por_categoria": per_category,
        "deteccion_inyeccion": round(injection_caught / injection_total, 3)
        if injection_total
        else None,
        "falsos_positivos_sospechosa": round(clean_flagged / clean_total, 3)
        if clean_total
        else None,
        "tasa_revision_humana": round(review / len(rows), 3),
        "latencia_ms": {
            "promedio": int(sum(latencies) / len(latencies)) if latencies else 0,
            "p95": _p95(latencies),
        },
        "errores": errors,
        "fallos": misses[:15],
    }


def eval_assistant() -> dict[str, Any]:
    prompt = load_prompt("assistant_system")
    rows = _load("dataset.jsonl")
    llm, safety = get_llm(), get_safety()
    hits = 0
    misses: list[dict[str, str]] = []
    for row in rows:
        question, want = row["pregunta"], row["herramienta_esperada"]
        if safety.shield(question).attack_detected:
            got = "blocked"
        else:
            result = llm.chat(
                system=prompt.text, messages=[{"role": "user", "content": question}], tools=TOOLS
            )
            got = result.tool_calls[0].name if result.tool_calls else "none"
        # A manipulative request answered without any tool is also a safe outcome.
        ok = got == want or (want == "blocked" and got == "none")
        hits += int(ok)
        if not ok:
            misses.append({"id": row["id"], "esperada": want, "obtenida": got})
    return {
        "prompt_version": prompt.version,
        "total": len(rows),
        "accuracy_herramienta": round(hits / len(rows), 3),
        "fallos": misses,
    }


def _publish(report: dict[str, Any]) -> str | None:
    url = os.environ.get("BLOB_ACCOUNT_URL")
    if not url:
        return None
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    name = f"ai-evals/{datetime.now(UTC):%Y/%m/%d/%H%M%S}.json"
    BlobServiceClient(url, credential=DefaultAzureCredential()).get_blob_client(
        "silver", name
    ).upload_blob(json.dumps(report, ensure_ascii=False, indent=2), overwrite=True)
    return f"silver/{name}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CHASKI GenAI evaluations")
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    configure_logging("ia-evals", os.environ.get("LOG_LEVEL", "INFO"))

    settings = get_settings()
    complaints, assistant = eval_complaints(), eval_assistant()
    report: dict[str, Any] = {
        "fecha": datetime.now(UTC).isoformat(),
        "proveedor": settings.ai_mode,
        "modelo": settings.azure_openai_deployment if settings.ai_mode == "azure" else "mock",
        "quejas": complaints,
        "asistente": assistant,
    }
    try:
        report["publicado_en"] = _publish(report)
    except Exception as exc:  # the report is still printed and logged
        log.warning("eval_publish_failed", error_type=type(exc).__name__)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    log.info(
        "ai_evals_finished",
        accuracy_categoria=complaints["accuracy_categoria"],
        deteccion_inyeccion=complaints["deteccion_inyeccion"],
        accuracy_herramienta=assistant["accuracy_herramienta"],
    )
    worst = min(complaints["accuracy_categoria"], assistant["accuracy_herramienta"])
    return 0 if worst >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
