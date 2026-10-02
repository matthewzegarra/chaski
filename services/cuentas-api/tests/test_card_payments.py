from __future__ import annotations

from decimal import Decimal

from chaski_common.models import Account
from chaski_common.testing import customer_headers, make_account, make_card, make_customer
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _pay(client: TestClient, customer, card_id, amount="25.00", **kw):  # type: ignore[no-untyped-def]
    body = {"card_id": str(card_id), "amount": amount, "merchant": "Tottus", "city": "Lima", **kw}
    return client.post("/api/v1/card-payments", json=body, headers=customer_headers(customer))


def test_debit_card_payment(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="100.00")
    card = make_card(s, ana, acc)
    resp = _pay(client, ana, card.id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["card_last4"] == card.last4
    assert body["new_balance"] == 75.0
    assert "token" not in body
    s.expire_all()
    assert s.get(Account, acc.id).balance == Decimal("75.00")  # type: ignore[union-attr]


def test_blocked_card_is_rejected(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    card = make_card(s, ana, make_account(s, ana), status="BLOQUEADA")
    resp = _pay(client, ana, card.id)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "La tarjeta está bloqueada"


def test_credit_card_not_supported(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    card = make_card(s, ana)
    assert _pay(client, ana, card.id).status_code == 422


def test_insufficient_balance(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    card = make_card(s, ana, make_account(s, ana, balance="10.00"))
    assert _pay(client, ana, card.id).json()["detail"] == "Saldo insuficiente"


def test_other_customers_card_is_403(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    card = make_card(s, beto, make_account(s, beto))
    assert _pay(client, ana, card.id).status_code == 403


def test_unknown_card_is_404(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    assert _pay(client, ana, "00000000-0000-4000-8000-000000000000").status_code == 404


def test_optional_idempotency_key_replays(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="100.00")
    card = make_card(s, ana, acc)
    h = {**customer_headers(ana), "Idempotency-Key": "pos-terminal-0001"}
    body = {"card_id": str(card.id), "amount": "30.00", "merchant": "Wong"}
    first = client.post("/api/v1/card-payments", json=body, headers=h)
    second = client.post("/api/v1/card-payments", json=body, headers=h)
    assert first.json() == second.json()
    s.expire_all()
    assert s.get(Account, acc.id).balance == Decimal("70.00")  # type: ignore[union-attr]
