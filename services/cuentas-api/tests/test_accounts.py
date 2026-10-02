from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from chaski_common.models import AuditLog
from chaski_common.roles import Role
from chaski_common.testing import (
    customer_headers,
    headers,
    make_account,
    make_customer,
    make_tx,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/accounts/me").status_code == 401


def test_staff_role_cannot_use_customer_endpoints(client: TestClient) -> None:
    assert client.get("/api/v1/accounts/me", headers=headers(Role.ADMIN)).status_code == 403


def test_my_accounts_only_returns_own(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    mine = make_account(s, ana, balance="1500.50")
    make_account(s, beto)
    resp = client.get("/api/v1/accounts/me", headers=customer_headers(ana))
    assert resp.status_code == 200
    body = resp.json()
    assert [a["id"] for a in body] == [str(mine.id)]
    assert body[0]["balance"] == 1500.5


def test_balance(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana, balance="250.00")
    resp = client.get(f"/api/v1/accounts/{acc.id}/balance", headers=customer_headers(ana))
    assert resp.json()["balance"] == 250.0


def test_customer_cannot_read_other_customer_account_and_it_is_audited(
    client: TestClient, s: Session
) -> None:
    ana, beto = make_customer(s), make_customer(s)
    beto_acc = make_account(s, beto)
    for path in (
        f"/api/v1/accounts/{beto_acc.id}/balance",
        f"/api/v1/accounts/{beto_acc.id}/movements",
    ):
        assert client.get(path, headers=customer_headers(ana)).status_code == 403
    denied = s.scalars(select(AuditLog).where(AuditLog.allowed.is_(False))).all()
    assert len(denied) == 2
    assert {d.resource_id for d in denied} == {str(beto_acc.id)}
    assert all(d.actor_role == "Cliente" for d in denied)


def test_unknown_account_is_404(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    resp = client.get(
        "/api/v1/accounts/00000000-0000-4000-8000-000000000000/balance",
        headers=customer_headers(ana),
    )
    assert resp.status_code == 404


def test_movements_filters_and_pagination(client: TestClient, s: Session) -> None:
    ana = make_customer(s)
    acc = make_account(s, ana)
    now = datetime.now(UTC)
    for i in range(25):
        make_tx(s, acc, amount=Decimal(10 + i), created_at=now - timedelta(hours=i))
    make_tx(
        s,
        acc,
        type="DEPOSITO",
        amount=Decimal(999),
        channel="WEB",
        created_at=now - timedelta(days=10),
    )
    h = customer_headers(ana)

    page1 = client.get(f"/api/v1/accounts/{acc.id}/movements", headers=h).json()
    assert page1["total"] == 26 and len(page1["items"]) == 20
    assert page1["items"][0]["amount"] == 10.0  # newest first
    assert page1["items"][0]["direction"] == "DEBITO"

    page2 = client.get(f"/api/v1/accounts/{acc.id}/movements?page=2", headers=h).json()
    assert len(page2["items"]) == 6

    deposits = client.get(f"/api/v1/accounts/{acc.id}/movements?type=DEPOSITO", headers=h).json()
    assert deposits["total"] == 1 and deposits["items"][0]["direction"] == "CREDITO"

    since = (now - timedelta(days=2)).date().isoformat()
    recent = client.get(f"/api/v1/accounts/{acc.id}/movements?from={since}", headers=h).json()
    assert recent["total"] == 25

    until = (now - timedelta(days=5)).date().isoformat()
    old = client.get(f"/api/v1/accounts/{acc.id}/movements?to={until}", headers=h).json()
    assert old["total"] == 1
