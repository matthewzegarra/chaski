"""Deterministic replies built only from tool results. Used by the mock LLM and as the safe
fallback when a real model's reply contains a number that did not come from a tool."""

from __future__ import annotations

from typing import Any

TX_LABELS = {
    "DEPOSITO": "Depósito",
    "RETIRO": "Retiro",
    "TRANSFERENCIA_IN": "Transferencia recibida",
    "TRANSFERENCIA_OUT": "Transferencia enviada",
    "PAGO_TARJETA": "Pago con tarjeta",
    "PAGO_SERVICIO": "Pago de servicio",
    "COMISION": "Comisión",
    "INTERES": "Intereses",
}
SYMBOL = {"PEN": "S/", "USD": "US$"}
REFUSAL = (
    "Solo puedo ayudarte con tus cuentas en Chaski: saldo, movimientos, explicar un cargo, "
    "bloquear tu tarjeta o registrar un reclamo."
)


def money(amount: Any, currency: str = "PEN") -> str:
    return f"{SYMBOL.get(currency, currency)} {float(amount):,.2f}"


def compose(tool: str, result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])
    if tool == "get_balance":
        accounts = result.get("cuentas", [])
        if not accounts:
            return "No encontré cuentas activas a tu nombre."
        lines = [
            f"• {a['producto']} {a['numero']}: {money(a['saldo'], a['moneda'])}" for a in accounts
        ]
        return "Este es tu saldo disponible:\n" + "\n".join(lines)
    if tool == "list_movements":
        items = result.get("movimientos", [])
        if not items:
            return "No encontré movimientos recientes."
        lines = [
            f"• {m['fecha']} · {m['descripcion']}: {'+' if m['tipo_flujo'] == 'CREDITO' else '-'}"
            f"{money(m['monto'], m['moneda'])}"
            for m in items
        ]
        return "Tus últimos movimientos:\n" + "\n".join(lines)
    if tool == "explain_charge":
        matches = result.get("coincidencias", [])
        if not matches:
            return (
                "No encontré un cargo que coincida en tus últimos movimientos. "
                "Si no lo reconoces, puedo registrar un reclamo por ti."
            )
        m = matches[0]
        detail = TX_LABELS.get(m["tipo"], m["tipo"]).lower()
        where = f" en {m['comercio']}" if m.get("comercio") else ""
        city = f" ({m['ciudad']})" if m.get("ciudad") else ""
        return (
            f"El cargo de {money(m['monto'], m['moneda'])} del {m['fecha']} corresponde a un "
            f"{detail}{where}{city} por el canal {m['canal']}. "
            "Si no lo reconoces, puedo bloquear tu tarjeta o registrar un reclamo."
        )
    if tool in ("block_card", "create_complaint"):
        return f"{result.get('summary', 'Acción preparada')}. Para continuar, presiona «Confirmar»."
    return REFUSAL
