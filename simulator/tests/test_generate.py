from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest
from chaski_simulator.generate import Dataset, Generator
from chaski_simulator.gold import build_gold

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return Generator(seed=42, now=NOW).run()


def test_volumes(ds: Dataset) -> None:
    assert len(ds.customers) == 1000
    assert 1200 <= len(ds.accounts) <= 1400
    assert 800 <= len(ds.cards) <= 1000
    assert len(ds.loans) == 400
    assert 50_000 <= len(ds.transactions) <= 70_000
    assert len(ds.complaints) == 150


def test_same_seed_is_reproducible(ds: Dataset) -> None:
    again = Generator(seed=42, now=NOW).run()
    assert [c["document_number"] for c in again.customers] == [
        c["document_number"] for c in ds.customers
    ]
    assert len(again.transactions) == len(ds.transactions)


def test_dni_are_8_digits_and_unique(ds: Dataset) -> None:
    dnis = [c["document_number"] for c in ds.customers]
    assert all(len(d) == 8 and d.isdigit() for d in dnis)
    assert len(set(dnis)) == len(dnis)


def test_cards_never_hold_a_pan(ds: Dataset) -> None:
    for card in ds.cards:
        assert card["token"].startswith("tok_")
        assert len(card["last4"]) == 4
        assert not any(k in card for k in ("pan", "number", "card_number"))


def test_balances_never_negative(ds: Dataset) -> None:
    assert all(a["balance"] >= 0 for a in ds.accounts)


def test_exactly_three_prompt_injections(ds: Dataset) -> None:
    assert sum(c["ai_suspicious"] for c in ds.complaints) == 3


def test_human_review_rule(ds: Dataset) -> None:
    for c in ds.complaints:
        expected = c["ai_category"] == "FRAUDE" or c["ai_confidence"] < 0.8 or c["ai_suspicious"]
        assert c["requires_review"] == expected


def test_delinquency_varies_by_region(ds: Dataset) -> None:
    disbursed = [loan for loan in ds.loans if loan["status"] == "DESEMBOLSADO"]
    assert any(loan["days_past_due"] > 30 for loan in disbursed)
    assert Counter(loan["_region"] for loan in disbursed)["Lima"] > 0


def test_gold_tables_are_populated(ds: Dataset) -> None:
    gold = build_gold(ds)
    for table in (
        "gold.dim_date",
        "gold.dim_region",
        "gold.dim_product",
        "gold.dim_customer",
        "gold.fact_portfolio_daily",
        "gold.fact_profitability_monthly",
    ):
        assert gold[table], table
    products = {row[0] for row in gold["gold.fact_profitability_monthly"]}
    assert products == {"AHORRO_SOLES", "AHORRO_DOLARES", "PRESTAMO_CONSUMO", "TARJETA_CREDITO"}
