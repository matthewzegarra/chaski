from __future__ import annotations

import uuid
from decimal import Decimal

from chaski_common.models import Account, AuditLog, IdempotencyKey, Transaction
from chaski_common.testing import customer_headers, make_account, make_customer
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _post(client: TestClient, customer, body: dict, key: str | None = None):  # type: ignore[no-untyped-def]
    h = customer_headers(customer)
    if key is not False:
        h["Idempotency-Key"] = key or str(uuid.uuid4())
    return client.post("/api/v1/transfers", json=body, headers=h)


def _balance(s: Session, account: Account) -> Decimal:
    s.expire_all()
    return s.get(Account, account.id).balance  # type: ignore[union-attr]


def test_internal_transfer_moves_money_and_returns_receipt(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    src = make_account(s, ana, balance="1000.00")
    dst = make_account(s, beto, balance="10.00")
    resp = _post(
        client,
        ana,
        {"from_account_id": str(src.id), "to_account_number": dst.number, "amount": "150.25"},
    )
    assert resp.status_code == 201, resp.text
    receipt = resp.json()
    assert receipt["operation"] == "TRANSFERENCIA"
    assert receipt["internal"] is True
    assert receipt["new_balance"] == 849.75
    assert _balance(s, src) == Decimal("850.00")  # deliberately wrong (CI red test)
    assert _balance(s, dst) == Decimal("160.25")
    types = set(s.scalars(select(Transaction.type)))
    assert types == {"TRANSFERENCIA_OUT", "TRANSFERENCIA_IN"}


def test_external_transfer_to_cci(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana, balance="500.00")
    resp = _post(
        client, ana, {"from_account_id": str(src.id), "to_account_number": "0" * 20, "amount": 100}
    )
    assert resp.status_code == 201
    assert resp.json()["internal"] is False


def test_idempotency_key_is_mandatory(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana)
    resp = _post(
        client,
        ana,
        {"from_account_id": str(src.id), "to_account_number": "0" * 20, "amount": 1},
        key=False,
    )  # type: ignore[arg-type]
    assert resp.status_code == 400
    assert "Idempotency-Key" in resp.json()["detail"]


def test_invalid_idempotency_key(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana)
    body = {"from_account_id": str(src.id), "to_account_number": "0" * 20, "amount": 1}
    assert _post(client, ana, body, key="short").status_code == 400


def test_same_key_same_body_is_replayed_once(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana, balance="1000.00")
    body = {"from_account_id": str(src.id), "to_account_number": "0" * 20, "amount": "100.00"}
    first = _post(client, ana, body, key="key-abc-12345")
    second = _post(client, ana, body, key="key-abc-12345")
    assert first.status_code == second.status_code == 201
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert first.json() == second.json()
    assert _balance(s, src) == Decimal("900.00")  # debited only once
    assert s.scalar(select(func.count()).select_from(Transaction)) == 1
    assert s.scalar(select(func.count()).select_from(IdempotencyKey)) == 1


def test_same_key_different_body_is_409(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana, balance="1000.00")
    body = {"from_account_id": str(src.id), "to_account_number": "0" * 20, "amount": "100.00"}
    assert _post(client, ana, body, key="key-xyz-12345").status_code == 201
    resp = _post(client, ana, {**body, "amount": "200.00"}, key="key-xyz-12345")
    assert resp.status_code == 409
    assert _balance(s, src) == Decimal("900.00")


def test_keys_are_scoped_per_customer(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    a_src, b_src = make_account(s, ana), make_account(s, beto)
    to = {"to_account_number": "0" * 20, "amount": "5.00"}
    assert (
        _post(
            client, ana, {"from_account_id": str(a_src.id), **to}, key="shared-key-001"
        ).status_code
        == 201
    )
    assert (
        _post(
            client, beto, {"from_account_id": str(b_src.id), **to}, key="shared-key-001"
        ).status_code
        == 201
    )


def test_insufficient_balance(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana, balance="50.00")
    resp = _post(
        client,
        ana,
        {"from_account_id": str(src.id), "to_account_number": "0" * 20, "amount": "50.01"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Saldo insuficiente"
    assert _balance(s, src) == Decimal("50.00")


def test_cannot_transfer_from_someone_elses_account(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    beto_acc = make_account(s, beto, balance="1000.00")
    resp = _post(
        client,
        ana,
        {"from_account_id": str(beto_acc.id), "to_account_number": "0" * 20, "amount": 10},
    )
    assert resp.status_code == 403
    assert _balance(s, beto_acc) == Decimal("1000.00")
    assert (
        s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.allowed.is_(False))) == 1
    )


def test_validation_errors(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    src = make_account(s, ana)
    base = {"from_account_id": str(src.id), "to_account_number": "0" * 20}
    assert _post(client, ana, {**base, "amount": "-5"}).status_code == 422
    assert _post(client, ana, {**base, "amount": "1.001"}).status_code == 422
    assert _post(client, ana, {**base, "to_account_number": "abc", "amount": 1}).status_code == 422
    same = {**base, "to_account_number": src.number, "amount": 1}
    assert _post(client, ana, same).json()["detail"] == "No puedes transferir a la misma cuenta"


def test_currency_mismatch_and_inactive_accounts(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    pen = make_account(s, ana, balance="500")
    usd = make_account(s, ana, product="AHORRO_DOLARES", currency="USD", number="210-3000000001")
    blocked = make_account(s, ana, status="BLOQUEADA", number="200-3000000002")
    r1 = _post(
        client, ana, {"from_account_id": str(pen.id), "to_account_number": usd.number, "amount": 1}
    )
    assert r1.json()["detail"] == "Las cuentas deben tener la misma moneda"
    r2 = _post(
        client,
        ana,
        {"from_account_id": str(blocked.id), "to_account_number": "0" * 20, "amount": 1},
    )
    assert r2.json()["detail"] == "La cuenta de origen no está activa"
    r3 = _post(
        client,
        ana,
        {"from_account_id": str(pen.id), "to_account_number": blocked.number, "amount": 1},
    )
    assert r3.json()["detail"] == "La cuenta de destino no está activa"
