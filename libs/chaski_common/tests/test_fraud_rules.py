from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from chaski_common.fraud import (
    r1_velocity,
    r2_atypical_amount,
    r3_city_jump,
    r4_new_beneficiary,
)


def test_r1_triggers_above_five() -> None:
    assert r1_velocity(5) is None
    hit = r1_velocity(6)
    assert hit is not None and hit.rule == "R1_VELOCIDAD"


def test_r2_requires_history_and_3x() -> None:
    assert r2_atypical_amount(Decimal(1000), Decimal(100), history=2) is None
    assert r2_atypical_amount(Decimal(300), Decimal(100), history=5) is None
    hit = r2_atypical_amount(Decimal(301), Decimal(100), history=5)
    assert hit is not None and hit.details["veces"] == 3.0
    assert r2_atypical_amount(Decimal(100), None, history=5) is None


def test_r2_score_is_capped() -> None:
    hit = r2_atypical_amount(Decimal(100000), Decimal(1), history=5)
    assert hit is not None and hit.score == Decimal("99.00")


def test_r3_city_and_window() -> None:
    assert r3_city_jump("Cusco", "Lima", timedelta(minutes=10)) is not None
    assert r3_city_jump("Lima", "lima ", timedelta(minutes=10)) is None
    assert r3_city_jump("Cusco", "Lima", timedelta(minutes=31)) is None
    assert r3_city_jump(None, "Lima", timedelta(minutes=1)) is None


def test_r4_threshold() -> None:
    assert r4_new_beneficiary(Decimal(5000), True) is None
    assert r4_new_beneficiary(Decimal("5000.01"), False) is None
    assert r4_new_beneficiary(Decimal("5000.01"), True) is not None
