"""Deterministic mock of the LLM, faithful to the same contract as AzureOpenAIProvider.

It never invents numbers: every figure it writes is copied from its input JSON or from tool
results, so the same validators that guard the real model also pass for the mock.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from ia_api.assistant_text import REFUSAL, compose
from ia_api.providers.llm import LLMResult, ToolCall
from ia_api.providers.safety import _INJECTION_RE


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.lower()


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ------------------------------------------------------------------ complaints

_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "FRAUDE": [
        ("no reconozco", 4), ("no hice", 4), ("no autorice", 4), ("fraude", 4), ("robaron", 4),
        ("suplant", 4), ("alguien entro", 4), ("haciendose pasar", 4), ("me llamaron diciendo", 3),
        ("hackearon", 4), ("que no conozco", 3), ("no fui yo", 4),
    ],
    "COBRO_INDEBIDO": [
        ("comision", 3), ("cobro", 2), ("cobraron", 2), ("cargo", 1), ("duplicad", 3),
        ("dos veces", 3), ("seguro", 2), ("devolucion", 2), ("mantenimiento", 2),
    ],
    "TARJETA": [
        ("tarjeta", 1), ("bloquead", 2), ("no llega", 3), ("rechazad", 2), ("reactiven", 2),
        ("entrega", 1),
    ],
    "PRESTAMO": [
        ("prestamo", 3), ("cuota", 3), ("cronograma", 3), ("desembols", 3), ("vencida", 2),
    ],
    "CANAL_DIGITAL": [
        ("app", 2), ("aplicacion", 2), ("se cierra", 3), ("clave", 2), ("contrasena", 2),
        ("no puedo ingresar", 3), ("error", 2), ("la web", 2), ("pagina", 1),
    ],
}  # fmt: skip
_URGENCY = {
    "FRAUDE": "ALTA",
    "COBRO_INDEBIDO": "MEDIA",
    "TARJETA": "MEDIA",
    "PRESTAMO": "MEDIA",
    "CANAL_DIGITAL": "BAJA",
    "OTRO": "BAJA",
}
_REASON = {
    "FRAUDE": "El cliente reporta operaciones que no reconoce",
    "COBRO_INDEBIDO": "El cliente reclama un cargo que considera incorrecto",
    "TARJETA": "El problema está relacionado con el funcionamiento de su tarjeta",
    "PRESTAMO": "El reclamo trata sobre cuotas o pagos de su préstamo",
    "CANAL_DIGITAL": "El cliente reporta un problema con la app o la web",
    "OTRO": "Consulta general sin un problema de producto específico",
}


def classify(text: str) -> dict[str, Any]:
    if _INJECTION_RE.search(text):
        return {
            "categoria": "OTRO",
            "urgencia": "ALTA",
            "confianza": 0.2,
            "motivo": "El texto intenta dar instrucciones al sistema",
            "sospechosa": True,
        }
    plain = _plain(text)
    scores = {cat: sum(w for kw, w in kws if kw in plain) for cat, kws in _KEYWORDS.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top == 0:
        return {"categoria": "OTRO", "urgencia": "BAJA", "confianza": 0.62,
                "motivo": _REASON["OTRO"], "sospechosa": False}  # fmt: skip
    confidence = round(min(0.97, 0.6 + 0.08 * (top - second)), 2)
    return {
        "categoria": best,
        "urgencia": _URGENCY[best],
        "confianza": confidence,
        "motivo": _REASON[best],
        "sospechosa": False,
    }


# ------------------------------------------------------------------ nl2sql

_MORA = "round(sum(saldo_vencido_30) / nullif(sum(saldo), 0) * 100, 2)"
_LATEST = "fecha = (SELECT max(fecha) FROM gold.v_morosidad)"


def nl2sql(question: str) -> dict[str, Any]:
    q = _plain(question)
    if any(w in q for w in ("borra", "elimina", "delete", "drop", "actualiza", "update", "insert")):
        return {"sql": "", "grafico": "table",
                "explicacion": "Solo puedo responder preguntas de consulta; no modifico datos."}  # fmt: skip
    if "mora" in q or "morosidad" in q or "atraso" in q:
        if any(
            w in q
            for w in ("evolucion", "tendencia", "historico", "en el tiempo", "por dia", "diaria")
        ):
            return {
                "sql": f"SELECT fecha, {_MORA} AS mora_pct FROM gold.v_morosidad "
                "GROUP BY fecha ORDER BY fecha",
                "grafico": "line",
                "explicacion": "Mora diaria (saldo con más de 30 días de atraso sobre el saldo total).",
            }
        if "segmento" in q:
            dim = "segmento"
        elif "bucket" in q or "categoria" in q or "calificacion" in q:
            return {
                "sql": "SELECT bucket, sum(prestamos) AS prestamos, round(sum(saldo), 2) AS saldo "
                f"FROM gold.v_morosidad WHERE {_LATEST} GROUP BY bucket ORDER BY saldo DESC",
                "grafico": "bar",
                "explicacion": "Préstamos y saldo por calificación SBS a la fecha más reciente.",
            }
        else:
            dim = "region"
        return {
            "sql": f"SELECT {dim}, {_MORA} AS mora_pct FROM gold.v_morosidad "
            f"WHERE {_LATEST} GROUP BY {dim} ORDER BY mora_pct DESC",
            "grafico": "bar",
            "explicacion": f"Mora por {dim} a la fecha más reciente.",
        }
    if any(w in q for w in ("margen", "rentab", "ingreso", "ganan", "utilidad")):
        measure = "round(sum(margen), 2) AS margen"
        if "ingreso" in q:
            measure = "round(sum(ingresos_intereses + comisiones), 2) AS ingresos"
        alias = measure.split(" AS ")[1]
        if any(w in q for w in ("mes", "mensual", "evolucion", "tendencia")):
            return {"sql": f"SELECT mes, {measure} FROM gold.v_rentabilidad GROUP BY mes ORDER BY mes",
                    "grafico": "line", "explicacion": f"Evolución mensual de {alias}."}  # fmt: skip
        dim = "segmento" if "segmento" in q else "region" if "region" in q else "producto"
        return {
            "sql": f"SELECT {dim}, {measure} FROM gold.v_rentabilidad GROUP BY {dim} ORDER BY {alias} DESC",
            "grafico": "bar",
            "explicacion": f"{alias.capitalize()} acumulado por {dim}.",
        }
    if "cliente" in q or "saldo" in q:
        dim = "segmento" if "segmento" in q else "region"
        col = (
            "round(sum(saldo_total), 2) AS saldo_total"
            if "saldo" in q
            else "sum(clientes) AS clientes"
        )
        alias = col.split(" AS ")[1]
        return {
            "sql": f"SELECT {dim}, {col} FROM gold.v_clientes_resumen GROUP BY {dim} ORDER BY {alias} DESC",
            "grafico": "bar",
            "explicacion": f"{alias.replace('_', ' ').capitalize()} por {dim}.",
        }
    return {"sql": "", "grafico": "table",
            "explicacion": "No puedo responder esa pregunta con los datos de rentabilidad, morosidad y clientes."}  # fmt: skip


# ------------------------------------------------------------------ texts from JSON facts


def loan_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    factors = payload.get("factores", [])[:3]
    parts = [f["detalle"].rstrip(".") for f in factors]
    rec = {"APROBAR": "favorable", "REVISAR": "a revisar", "RECHAZAR": "desfavorable"}.get(
        payload.get("recomendacion", ""), "a revisar"
    )
    text = f"La evaluación por reglas es {rec}. " + ". ".join(parts) + "."
    return {"explicacion": text + " La decisión final corresponde al analista de Riesgos."}


def executive_summary(k: dict[str, Any]) -> dict[str, Any]:
    t = k["texto"]
    direction = "creció" if k["variacion_margen_pct"] >= 0 else "disminuyó"
    text = (
        f"En {t['periodo']}, el margen financiero fue de {t['margen_mes']}, "
        f"lo que {direction} {t['variacion_margen_abs_pct']} frente al mes anterior. "
        f"El producto más rentable fue {t['producto_top']} con un margen de {t['margen_producto_top']}. "
        f"La morosidad mayor a {k['umbral_mora_dias']} días se ubica en {t['mora_pct']}, con {k['region_mayor_mora']} "
        f"como la región más afectada ({t['mora_region_top_pct']}). "
        f"La cartera de clientes suma {t['clientes']} clientes. "
        f"Recomendamos reforzar la cobranza temprana en {k['region_mayor_mora']} y priorizar el "
        f"crecimiento de {t['producto_top']}."
    )
    return {"resumen": text}


# ------------------------------------------------------------------ assistant


def _last_user(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""


def _intent(text: str) -> tuple[str | None, dict[str, Any]]:
    q = _plain(text)
    last4 = re.search(r"(?<!\d)(\d{4})(?!\d)", q)
    if "bloque" in q and ("tarjeta" in q or "card" in q):
        return "block_card", {"card_last4": last4.group(1)} if last4 else {}
    if any(w in q for w in ("reclamo", "queja", "reclamar", "denunciar")):
        return "create_complaint", {
            "subject": "Reclamo registrado por Chaski Asistente",
            "body": text.strip(),
        }
    if any(
        w in q
        for w in (
            "que es",
            "explica",
            "por que me cobraron",
            "no reconozco",
            "cargo de",
            "cobro de",
        )
    ):
        return "explain_charge", {"query": text.strip()}
    if any(w in q for w in ("movimiento", "ultimos", "gastos", "compras", "historial")):
        return "list_movements", {"limit": 5}
    if any(w in q for w in ("saldo", "cuanto tengo", "dinero disponible", "disponible")):
        return "get_balance", {}
    return None, {}


class MockProvider:
    name = "mock"

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], schema_name: str
    ) -> LLMResult:
        if schema_name == "complaint_classification":
            match = re.search(r"<queja>(.*)</queja>", user, re.S)
            out = classify(match.group(1) if match else user)
        elif schema_name == "nl2sql":
            out = nl2sql(user)
        elif schema_name == "loan_explanation":
            out = loan_explanation(json.loads(user))
        elif schema_name == "executive_summary":
            out = executive_summary(json.loads(user))
        else:
            raise ValueError(f"Mock has no behaviour for {schema_name}")
        content = json.dumps(out, ensure_ascii=False)
        return LLMResult(
            content=content,
            tokens_in=_tokens(system + user),
            tokens_out=_tokens(content),
            provider=self.name,
        )

    def chat(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResult:
        # After tool results arrive, answer from them (never from memory).
        if messages and messages[-1].get("role") == "tool":
            tool_msgs = []
            for m in reversed(messages):
                if m.get("role") != "tool":
                    break
                tool_msgs.append(m)
            last = tool_msgs[0]
            reply = compose(str(last.get("name")), json.loads(last.get("content") or "{}"))
            return LLMResult(
                content=reply,
                tokens_in=_tokens(str(messages)),
                tokens_out=_tokens(reply),
                provider=self.name,
            )
        text = _last_user(messages)
        tool, args = _intent(text)
        if tool is None:
            greeting = any(w in _plain(text) for w in ("hola", "buenas", "buenos dias", "gracias"))
            reply = "¡Hola! ¿En qué te ayudo con tus cuentas?" if greeting else REFUSAL
            return LLMResult(
                content=reply,
                tokens_in=_tokens(text),
                tokens_out=_tokens(reply),
                provider=self.name,
            )
        call = ToolCall(id=f"call_{tool}", name=tool, arguments=args)
        return LLMResult(
            content=None,
            tool_calls=[call],
            tokens_in=_tokens(text),
            tokens_out=8,
            provider=self.name,
        )
