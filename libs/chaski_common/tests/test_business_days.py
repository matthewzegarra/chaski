from __future__ import annotations

from datetime import UTC, date, datetime

from chaski_common.business_days import (
    LIMA,
    add_business_days,
    business_days_between,
    holidays,
    is_business_day,
    regulatory_deadline,
)


def test_weekends_are_not_business_days() -> None:
    assert not is_business_day(date(2026, 10, 3))  # Saturday
    assert not is_business_day(date(2026, 10, 4))  # Sunday
    assert is_business_day(date(2026, 10, 5))


def test_fixed_and_easter_holidays() -> None:
    h = holidays(2026)
    assert date(2026, 7, 28) in h
    assert date(2026, 4, 2) in h  # Jueves Santo 2026
    assert date(2026, 4, 3) in h  # Viernes Santo 2026


def test_add_15_business_days_skips_weekends_and_holidays() -> None:
    # Thu 2026-10-01 + 15 business days; Oct 8 (Angamos) is a holiday.
    assert add_business_days(date(2026, 10, 1), 15) == date(2026, 10, 23)


def test_add_business_days_keeps_time() -> None:
    start = datetime(2026, 10, 2, 15, 30, tzinfo=UTC)  # Friday
    assert add_business_days(start, 1) == datetime(2026, 10, 5, 15, 30, tzinfo=UTC)


def test_business_days_between() -> None:
    assert business_days_between(date(2026, 10, 2), date(2026, 10, 5)) == 1
    assert business_days_between(date(2026, 10, 5), date(2026, 10, 2)) == -1


def test_regulatory_deadline_uses_lima_calendar() -> None:
    # Thu 2026-10-01 23:50 Lima is already Fri 04:50 UTC; counting starts from Thursday.
    filed = datetime(2026, 10, 2, 4, 50, tzinfo=UTC)
    due = regulatory_deadline(filed, 15)
    assert due.astimezone(LIMA).date() == date(2026, 10, 23)  # a Friday, never a weekend
    assert (due.hour, due.minute) == (23, 59)
