"""Business-day arithmetic for Peru (weekends + national holidays)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")

# (month, day) fixed national holidays.
_FIXED_HOLIDAYS = {
    (1, 1),  # Año Nuevo
    (5, 1),  # Día del Trabajo
    (6, 7),  # Batalla de Arica y Día de la Bandera
    (6, 29),  # San Pedro y San Pablo
    (7, 23),  # Día de la Fuerza Aérea
    (7, 28),  # Fiestas Patrias
    (7, 29),  # Fiestas Patrias
    (8, 6),  # Batalla de Junín
    (8, 30),  # Santa Rosa de Lima
    (10, 8),  # Combate de Angamos
    (11, 1),  # Todos los Santos
    (12, 8),  # Inmaculada Concepción
    (12, 9),  # Batalla de Ayacucho
    (12, 25),  # Navidad
}


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache
def holidays(year: int) -> frozenset[date]:
    easter = _easter(year)
    days = {date(year, m, d) for m, d in _FIXED_HOLIDAYS}
    days.add(easter - timedelta(days=3))  # Jueves Santo
    days.add(easter - timedelta(days=2))  # Viernes Santo
    return frozenset(days)


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year)


def add_business_days[T: (date, datetime)](start: T, days: int) -> T:
    """Return `start` moved forward `days` business days (keeps the time part for datetimes)."""
    current = start
    remaining = days
    while remaining > 0:
        current = current + timedelta(days=1)
        if is_business_day(current.date() if isinstance(current, datetime) else current):
            remaining -= 1
    return current


def business_days_between(start: date, end: date) -> int:
    """Business days in (start, end]. Negative if end < start."""
    if end < start:
        return -business_days_between(end, start)
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if is_business_day(current):
            count += 1
    return count


def regulatory_deadline(start: datetime, days: int) -> datetime:
    """End (23:59:59 Lima) of the `days`-th business day after `start`, counted on Lima's
    calendar. A complaint filed at 23:50 Lima on Thursday must not start counting on Friday
    just because it is already Friday in UTC."""
    local_day = start.astimezone(LIMA).date()
    due = add_business_days(local_day, days)
    return datetime.combine(due, time(23, 59, 59), LIMA)
