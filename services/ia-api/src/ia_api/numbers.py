"""Number guard: every figure the model writes must come from the data it was given.

Used by the executive summary (prompt 8.4) and by the assistant ("nunca inventa saldos").
A text number is accepted when it matches some source value at a plausible rounding
(0-2 decimals, or expressed in thousands/millions), within a rounding tolerance.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

# 1,234,567.89 | 1234.5 | 12 | 3.5  (commas as thousands separators, dot as decimal mark)
_NUM_RE = re.compile(
    r"(?<![\w])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d|,\d)|(?<![\w.])(?<!\d,)\d+(?:\.\d+)?(?!\d)"
)


def extract_numbers(text: str) -> list[Decimal]:
    out: list[Decimal] = []
    for raw in _NUM_RE.findall(text):
        try:
            out.append(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            continue
    return out


def numbers_in(data: Any) -> list[Decimal]:
    """All numbers contained in a JSON-like structure (numbers and numeric text)."""
    found: list[Decimal] = []

    def walk(v: Any) -> None:
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, int | float | Decimal):
            found.append(Decimal(str(v)))
        elif isinstance(v, str):
            found.extend(extract_numbers(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list | tuple):
            for x in v:
                walk(x)

    walk(data)
    return found


def _representations(value: Decimal) -> set[Decimal]:
    reps = {value}
    for scale in (Decimal(1), Decimal(1000), Decimal(1_000_000)):
        scaled = value / scale
        for places in (0, 1, 2):
            reps.add(round(scaled, places))
    reps.add(abs(value))
    return reps


def unsupported_numbers(
    text: str, sources: Iterable[Decimal], *, always_ok: Iterable[int] = ()
) -> list[Decimal]:
    """Numbers in `text` that cannot be traced to `sources` (empty list = text is valid)."""
    candidates: set[Decimal] = set()
    for s in sources:
        candidates |= _representations(Decimal(s))
    allowed_small = {Decimal(i) for i in always_ok}
    bad = []
    for n in extract_numbers(text):
        if n in allowed_small:
            continue
        tolerance = max(Decimal("0.005"), abs(n) * Decimal("0.0005"))
        if not any(abs(n - c) <= tolerance for c in candidates):
            bad.append(n)
    return bad


def json_numbers(text: str) -> list[Decimal]:
    try:
        return numbers_in(json.loads(text))
    except (json.JSONDecodeError, TypeError):
        return extract_numbers(text)
