"""Entra ID App Roles used across CHASKI."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "Admin"
    OPERACIONES = "Operaciones"
    ATENCION = "Atencion"
    RIESGOS = "Riesgos"
    FRAUDE = "Fraude"
    DIRECCION = "Direccion"
    MARKETING = "Marketing"
    TI = "TI"
    CLIENTE = "Cliente"


STAFF_ROLES: frozenset[Role] = frozenset(r for r in Role if r is not Role.CLIENTE)
# Roles allowed to reveal unmasked PII (always with a reason, always audited).
PII_REVEAL_ROLES: frozenset[Role] = frozenset({Role.ATENCION, Role.ADMIN})


def parse_roles(raw: object) -> frozenset[Role]:
    """Keep only known roles from a token claim; unknown values are ignored."""
    if not isinstance(raw, list | tuple):
        return frozenset()
    known = {r.value: r for r in Role}
    return frozenset(known[v] for v in raw if isinstance(v, str) and v in known)
