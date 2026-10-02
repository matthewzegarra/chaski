"""PII masking for API responses."""

from __future__ import annotations


def mask_dni(value: str | None) -> str | None:
    if not value:
        return value
    return "****" + value[-4:]


def mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_phone(value: str | None) -> str | None:
    if not value:
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    return "***-***-" + digits[-3:]
