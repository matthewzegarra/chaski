"""Chaski Asistente (prompt 8.3).

- Tools call cuentas-api / core-api forwarding the customer's own JWT: the customer_id always
  comes from the token on the server, the model never chooses it (D10).
- block_card / create_complaint are never executed here: they return a `pending_action`
  that the app shows with a "Confirmar" button (D9).
- Number guard: if the final reply contains a figure that is not in any tool result, it is
  replaced by a reply composed from the tool data.
"""

from __future__ import annotations

import json
import time
import unicodedata
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from chaski_common.auth import CurrentUser
from chaski_common.logging import correlation_id_var, get_logger, redact
from pydantic import BaseModel, Field

from ia_api import pipeline
from ia_api.assistant_text import REFUSAL, TX_LABELS, compose
from ia_api.numbers import json_numbers, unsupported_numbers
from ia_api.prompts import load_prompt
from ia_api.providers.llm import LLMResult, get_llm
from ia_api.providers.safety import get_safety
from ia_api.settings import get_settings

log = get_logger(__name__)
LIMA = ZoneInfo("America/Lima")
MAX_ROUNDS = 3
MAX_HISTORY = 10


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)


class PendingAction(BaseModel):
    tool: str
    args: dict[str, str]
    summary: str


class ChatOut(BaseModel):
    reply: str
    pending_action: PendingAction | None = None
    data: dict[str, Any] | None = None


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Saldo disponible de las cuentas del cliente autenticado.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_movements",
            "description": "Últimos movimientos de la cuenta principal del cliente.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_charge",
            "description": "Busca un cargo en los movimientos recientes (por comercio o monto) y lo explica.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Comercio, monto o descripción del cargo"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "block_card",
            "description": "Prepara el bloqueo de una tarjeta del cliente. Requiere confirmación en la app.",
            "parameters": {
                "type": "object",
                "properties": {"card_last4": {"type": "string", "description": "Últimos 4 dígitos (opcional)"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_complaint",
            "description": "Prepara un reclamo. Requiere confirmación en la app.",
            "parameters": {
                "type": "object",
                "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
                "required": ["subject", "body"],
                "additionalProperties": False,
            },
        },
    },
]  # fmt: skip


class BankApi:
    """Calls the banking APIs as the customer (their own bearer token)."""

    def __init__(self, user: CurrentUser, transport: httpx.BaseTransport | None = None) -> None:
        s = get_settings()
        headers = {"Authorization": f"Bearer {user.token}"}
        if cid := correlation_id_var.get():
            headers["X-Correlation-ID"] = cid
        self.cuentas = httpx.Client(
            base_url=f"{s.cuentas_api_url}/api/v1", headers=headers, timeout=10, transport=transport
        )
        self.core = httpx.Client(
            base_url=f"{s.core_api_url}/api/v1", headers=headers, timeout=10, transport=transport
        )

    def accounts(self) -> list[dict[str, Any]]:
        r = self.cuentas.get("/accounts/me")
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    def movements(self, account_id: str, size: int) -> list[dict[str, Any]]:
        r = self.cuentas.get(f"/accounts/{account_id}/movements", params={"page_size": size})
        r.raise_for_status()
        items: list[dict[str, Any]] = r.json()["items"]
        return items

    def cards(self) -> list[dict[str, Any]]:
        r = self.core.get("/cards/me")
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data


def _date(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(LIMA).strftime("%d/%m/%Y")


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _movement(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "fecha": _date(m["created_at"]),
        "descripcion": m.get("merchant")
        or m.get("description")
        or TX_LABELS.get(m["type"], m["type"]),
        "tipo": m["type"],
        "tipo_flujo": m["direction"],
        "monto": m["amount"],
        "moneda": m["currency"],
        "comercio": m.get("merchant"),
        "ciudad": m.get("city"),
        "canal": m["channel"],
    }


def run_tool(
    api: BankApi, name: str, args: dict[str, Any]
) -> tuple[dict[str, Any], PendingAction | None]:
    try:
        if name == "get_balance":
            accounts = api.accounts()
            return {
                "cuentas": [
                    {"numero": a["number"], "producto": "Ahorros " + ("soles" if a["currency"] == "PEN" else "dólares"),
                     "moneda": a["currency"], "saldo": a["balance"]}
                    for a in accounts
                ]
            }, None  # fmt: skip
        if name in ("list_movements", "explain_charge"):
            accounts = api.accounts()
            main = next(
                (a for a in accounts if a["currency"] == "PEN"), accounts[0] if accounts else None
            )
            if main is None:
                return {"error": "No encontré cuentas a tu nombre."}, None
            limit = int(args.get("limit", 5)) if name == "list_movements" else 30
            items = [_movement(m) for m in api.movements(main["id"], max(1, min(limit, 30)))]
            if name == "list_movements":
                return {"movimientos": items}, None
            query = _plain(str(args.get("query", "")))
            words = [w for w in query.replace(",", " ").split() if len(w) > 3]
            amounts = {
                w for w in query.replace("s/", " ").split() if w.replace(".", "", 1).isdigit()
            }
            matches = [
                m for m in items
                if (m["comercio"] and _plain(m["comercio"]) in query)
                or any(w in _plain(str(m["descripcion"])) for w in words)
                or f"{float(m['monto']):.2f}" in amounts or f"{float(m['monto']):g}" in amounts
            ]  # fmt: skip
            return {"coincidencias": matches[:3]}, None
        if name == "block_card":
            cards = [c for c in api.cards() if c["status"] == "ACTIVA"]
            last4 = str(args.get("card_last4") or "")
            if last4:
                cards = [c for c in cards if c["last4"] == last4]
            if not cards:
                return {"error": "No encontré una tarjeta activa con esos datos."}, None
            card = cards[0]
            label = f"{card['brand']} {'débito' if card['type'] == 'DEBITO' else 'crédito'} •••• {card['last4']}"
            summary = f"Bloquear la tarjeta {label}"
            return {"pending": True, "summary": summary}, PendingAction(
                tool="block_card", args={"card_id": card["id"]}, summary=summary
            )
        if name == "create_complaint":
            subject = str(args.get("subject") or "Reclamo")[:120]
            body = str(args.get("body") or "")[:2000]
            if len(body) < 10:
                return {
                    "error": "Cuéntame un poco más del problema para registrar el reclamo."
                }, None
            summary = f"Registrar el reclamo «{subject}»"
            return {"pending": True, "summary": summary}, PendingAction(
                tool="create_complaint", args={"subject": subject, "body": body}, summary=summary
            )
    except httpx.HTTPError as exc:
        log.warning("assistant_tool_failed", tool=name, error_type=type(exc).__name__)
        return {
            "error": "No pude consultar tus datos en este momento. Intenta en unos minutos."
        }, None
    return {"error": REFUSAL}, None


def chat(user: CurrentUser, body: ChatIn, api: BankApi | None = None) -> ChatOut:
    prompt = load_prompt("assistant_system")
    start = time.perf_counter()
    history = [m.model_dump() for m in body.messages[-MAX_HISTORY:]]
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    redacted_history = [{**m, "content": redact(m["content"])} for m in history]
    safety = get_safety()

    if safety.shield(redact(last_user)).attack_detected:
        reply = "No puedo procesar ese mensaje. Puedo ayudarte con tu saldo, movimientos, tarjetas o reclamos."
        pipeline.record(
            use_case="assistant", prompt=prompt, input_text=redact(last_user), output={"reply": reply},
            latency_ms=int((time.perf_counter() - start) * 1000), result=None, blocked=True, provider=safety.name,
        )  # fmt: skip
        return ChatOut(reply=reply)

    api = api or BankApi(user)
    llm = get_llm()
    messages: list[dict[str, Any]] = list(redacted_history)
    pending: PendingAction | None = None
    last_tool: tuple[str, dict[str, Any]] | None = None
    tool_numbers: list[Any] = []
    result: LLMResult | None = None
    reply = REFUSAL
    for _ in range(MAX_ROUNDS):
        result = llm.chat(system=prompt.text, messages=messages, tools=TOOLS)
        if not result.tool_calls:
            reply = result.content or REFUSAL
            break
        messages.append(
            {
                "role": "assistant",
                "content": result.content,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in result.tool_calls
                ],
            }
        )
        for call in result.tool_calls:
            data, action = run_tool(api, call.name, call.arguments)
            pending = action or pending
            last_tool = (call.name, data)
            content = json.dumps(data, ensure_ascii=False, default=str)
            tool_numbers.extend(json_numbers(content))
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": content}
            )
    else:
        reply = compose(*last_tool) if last_tool else REFUSAL

    # Number guard: the reply may only contain figures that came from tools or from the customer.
    allowed = tool_numbers + json_numbers(json.dumps([m["content"] for m in history]))
    bad = unsupported_numbers(reply, allowed, always_ok=range(0, 11))
    if bad:
        log.warning("assistant_reply_numbers_replaced", count=len(bad))
        reply = compose(*last_tool) if last_tool else REFUSAL
    if pending and "Confirmar" not in reply:
        reply = f"{reply}\n\nPara continuar, presiona «Confirmar»."

    pipeline.record(
        use_case="assistant", prompt=prompt, input_text=redact(last_user),
        output={"reply": redact(reply), "tool": last_tool[0] if last_tool else None,
                "pending_action": pending.tool if pending else None, "numbers_replaced": bool(bad)},
        latency_ms=int((time.perf_counter() - start) * 1000), result=result, provider=llm.name,
    )  # fmt: skip
    return ChatOut(reply=reply, pending_action=pending)
