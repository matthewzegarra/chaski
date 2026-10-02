"""Fraud rules R1-R4 triggered through the real API, plus event publishing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from chaski_common import events
from chaski_common.models import FraudAlert
from chaski_common.testing import customer_headers, make_account, make_card, make_customer, make_tx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _alerts(s: Session) -> list[FraudAlert]:
    s.expire_all()
    return list(s.scalars(select(FraudAlert).order_by(FraudAlert.created_at)))


def _transfer(client: TestClient, customer, account, to: str, amount: str):  # type: ignore[no-untyped-def]
    h = {**customer_headers(customer), "Idempotency-Key": str(uuid.uuid4())}
    body = {"from_account_id": str(account.id), "to_account_number": to, "amount": amount}
    return client.post("/api/v1/transfers", json=body, headers=h)


def test_r1_velocity_one_alert_per_burst(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="5000.00")
    for _ in range(8):
        assert _transfer(client, ana, acc, "0" * 20, "10.00").status_code == 201
    r1 = [a for a in _alerts(s) if a.rule == "R1_VELOCIDAD"]
    assert len(r1) == 1
    assert r1[0].source == "RULES" and r1[0].status == "ABIERTA"
    assert r1[0].details["transferencias_2min"] == 6


def test_r2_atypical_amount(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="9000.00")
    for i in range(4):
        make_tx(
            s, acc, amount=Decimal("100.00"), created_at=datetime.now(UTC) - timedelta(days=i + 1)
        )
    card = make_card(s, ana, acc)
    client.post(
        "/api/v1/card-payments",
        json={"card_id": str(card.id), "amount": "450.00", "merchant": "Ripley"},
        headers=customer_headers(ana),
    )
    rules = [a.rule for a in _alerts(s)]
    assert rules == ["R2_MONTO_ATIPICO"]


def test_r2_needs_history(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="9000.00")
    card = make_card(s, ana, acc)
    client.post(
        "/api/v1/card-payments",
        json={"card_id": str(card.id), "amount": "4000.00", "merchant": "Ripley"},
        headers=customer_headers(ana),
    )
    assert _alerts(s) == []


def test_r3_city_jump(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="900.00")
    card = make_card(s, ana, acc)
    make_tx(s, acc, city="Lima", created_at=datetime.now(UTC) - timedelta(minutes=10))
    resp = client.post(
        "/api/v1/card-payments",
        json={"card_id": str(card.id), "amount": "20.00", "merchant": "Tambo", "city": "Iquitos"},
        headers=customer_headers(ana),
    )
    assert resp.status_code == 201
    alerts = _alerts(s)
    assert [a.rule for a in alerts] == ["R3_CIUDAD_DISTINTA"]
    assert alerts[0].details["ciudad_anterior"] == "Lima"


def test_r3_not_triggered_after_30_minutes(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="900.00")
    card = make_card(s, ana, acc)
    make_tx(s, acc, city="Lima", created_at=datetime.now(UTC) - timedelta(minutes=45))
    client.post(
        "/api/v1/card-payments",
        json={"card_id": str(card.id), "amount": "20.00", "merchant": "Tambo", "city": "Cusco"},
        headers=customer_headers(ana),
    )
    assert _alerts(s) == []


def test_r4_new_beneficiary_over_5000(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="20000.00")
    _transfer(client, ana, acc, "1" * 20, "6000.00")
    assert [a.rule for a in _alerts(s)] == ["R4_BENEFICIARIO_NUEVO"]
    # A second transfer to the same (now known) beneficiary does not alert again.
    _transfer(client, ana, acc, "1" * 20, "6000.00")
    assert [a.rule for a in _alerts(s)] == ["R4_BENEFICIARIO_NUEVO"]


def test_event_is_published_without_pii(
    client: TestClient, s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(events, "publish", lambda evts: published.extend(evts))
    ana = make_customer(s)
    acc = make_account(s, ana, balance="20000.00")
    _transfer(client, ana, acc, "1" * 20, "6000.00")
    assert len(published) == 1
    event = published[0]
    assert event["event_type"] == "transaction.created"
    assert event["rules_triggered"] == ["R4_BENEFICIARIO_NUEVO"]
    flat = str(event)
    assert ana.document_number not in flat and ana.email not in flat
