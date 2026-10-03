"""DNI identity lookup (ApisPeru). The token never leaves the environment / Key Vault.

Local and CI use a deterministic mock so Docker Compose works without a third-party key.
Never log the DNI or the token; the shared redactor is a second line of defense.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from chaski_common.logging import get_logger

from core_api.settings import get_settings

log = get_logger(__name__)
TIMEOUT = httpx.Timeout(8.0, connect=3.0)
Fuente = Literal["APISPERU", "MOCK"]

# Matches the usual onboarding test / demo form so autofill lines up with OCR.
_MOCK_NAMES: dict[str, tuple[str, str]] = {
    "45678912": ("Rosa", "Mamani Quispe"),
}

_FIRST = ("Ana", "Luis", "Carmen", "Pedro", "Lucia", "Miguel", "Rosa", "Jorge")
_LAST = ("Quispe", "Mamani", "Torres", "Vargas", "Diaz", "Flores", "Rojas", "Castillo")


@dataclass(frozen=True)
class DniPerson:
    nombres: str
    apellidos: str
    fuente: Fuente
    numero_documento: str


@dataclass(frozen=True)
class DniLookupResult:
    person: DniPerson | None
    found: bool
    available: bool
    fuente: Fuente | None


def pretty_name(text: str) -> str:
    return " ".join(part.capitalize() for part in text.split())


def _mock_person(dni: str) -> DniPerson:
    if dni in _MOCK_NAMES:
        first, last = _MOCK_NAMES[dni]
        return DniPerson(nombres=first, apellidos=last, fuente="MOCK", numero_documento=dni)
    n = int(dni)
    return DniPerson(
        nombres=_FIRST[n % len(_FIRST)],
        apellidos=f"{_LAST[n % len(_LAST)]} {_LAST[(n // 8) % len(_LAST)]}",
        fuente="MOCK",
        numero_documento=dni,
    )


def _token() -> str | None:
    raw = get_settings().dni_lookup_token
    if raw is None:
        return None
    value = raw.get_secret_value().strip()
    return value or None


def uses_live_provider() -> bool:
    mode = get_settings().dni_lookup_mode
    if mode == "mock":
        return False
    return _token() is not None


def _http_get(url: str, headers: dict[str, str]) -> httpx.Response:
    return httpx.get(url, headers=headers, timeout=TIMEOUT)


def _from_apisperu(dni: str) -> DniLookupResult:
    token = _token()
    if not token:
        return DniLookupResult(person=None, found=False, available=False, fuente="APISPERU")
    base = get_settings().dni_lookup_base_url.rstrip("/")
    url = f"{base}/dni/{dni}"
    try:
        resp = _http_get(url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
    except Exception as exc:
        log.warning("dni_lookup_failed", error_type=type(exc).__name__, fuente="APISPERU")
        return DniLookupResult(person=None, found=False, available=False, fuente="APISPERU")
    if resp.status_code in {401, 403}:
        log.warning("dni_lookup_unauthorized", status=resp.status_code)
        return DniLookupResult(person=None, found=False, available=False, fuente="APISPERU")
    if resp.status_code == 404:
        return DniLookupResult(person=None, found=False, available=True, fuente="APISPERU")
    if resp.status_code >= 400:
        log.warning("dni_lookup_http_error", status=resp.status_code)
        return DniLookupResult(person=None, found=False, available=False, fuente="APISPERU")
    try:
        data: dict[str, Any] = resp.json()
    except Exception:
        return DniLookupResult(person=None, found=False, available=False, fuente="APISPERU")
    nombres = data.get("nombres")
    paterno = str(data.get("apellidoPaterno") or "").strip()
    materno = str(data.get("apellidoMaterno") or "").strip()
    apellidos = " ".join(p for p in (paterno, materno) if p)
    if not nombres or not apellidos:
        return DniLookupResult(person=None, found=False, available=True, fuente="APISPERU")
    person = DniPerson(
        nombres=pretty_name(str(nombres)),
        apellidos=pretty_name(apellidos),
        fuente="APISPERU",
        numero_documento=str(data.get("dni") or dni),
    )
    log.info("dni_lookup_ok", fuente="APISPERU")
    return DniLookupResult(person=person, found=True, available=True, fuente="APISPERU")


def lookup(dni: str) -> DniLookupResult:
    if uses_live_provider():
        return _from_apisperu(dni)
    person = _mock_person(dni)
    return DniLookupResult(person=person, found=True, available=True, fuente="MOCK")


def person_as_dict(person: DniPerson) -> dict[str, str]:
    return {
        "nombres": person.nombres,
        "apellidos": person.apellidos,
        "fuente": person.fuente,
        "numero_documento": person.numero_documento,
    }


_hits: dict[str, list[float]] = defaultdict(list)


def allow_lookup(ip: str, limit: int = 20) -> bool:
    """Tight cap for the public autofill route (on top of the global limiter)."""
    now = time.monotonic()
    recent = [t for t in _hits[ip] if now - t < 60]
    if len(recent) >= limit:
        _hits[ip] = recent
        return False
    recent.append(now)
    _hits[ip] = recent
    return True
