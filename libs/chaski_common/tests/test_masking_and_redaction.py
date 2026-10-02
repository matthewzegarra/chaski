from __future__ import annotations

import pytest
from chaski_common.logging import redact, redact_event
from chaski_common.masking import mask_dni, mask_email, mask_phone


def test_mask_dni() -> None:
    assert mask_dni("12345678") == "****5678"
    assert mask_dni(None) is None


def test_mask_email() -> None:
    assert mask_email("maria.quispe@dominio.com") == "m***@dominio.com"


def test_mask_phone() -> None:
    assert mask_phone("987654123") == "***-***-123"
    assert mask_phone("+51 987 654 123") == "***-***-123"


@pytest.mark.parametrize(
    ("raw", "leak"),
    [
        ("DNI del cliente 45678912 validado", "45678912"),
        ("correo maria.quispe@gmail.com", "maria.quispe@gmail.com"),
        ("llamar al 987654321", "987654321"),
        ("tarjeta 4111111111111111 rechazada", "4111111111111111"),
        ("tarjeta 4111 1111 1111 1111 rechazada", "4111 1111 1111 1111"),
        ("celular +51 987 654 321", "987 654 321"),
    ],
)
def test_redact_removes_pii(raw: str, leak: str) -> None:
    assert leak not in redact(raw)
    assert "[REDACTED_" in redact(raw)


def test_redact_keeps_uuids_and_amounts() -> None:
    text = "cuenta 12345678-aaaa-4bbb-8ccc-1234567890ab monto 1234.56"
    assert redact(text) == text


def test_redact_event_walks_nested_values() -> None:
    event = {"event": "x", "payload": {"email": "a@b.com", "items": ["dni 12345678"]}}
    out = redact_event(None, "info", event)
    assert out["payload"]["email"] == "[REDACTED_EMAIL]"
    assert out["payload"]["items"] == ["dni [REDACTED_DNI]"]
