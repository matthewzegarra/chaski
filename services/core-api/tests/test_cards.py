from __future__ import annotations

from chaski_common.models import AuditLog
from chaski_common.roles import Role
from chaski_common.testing import customer_headers, headers, make_account, make_card, make_customer
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_my_cards_never_expose_token(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    make_card(s, c, make_account(s, c))
    cards = client.get("/api/v1/cards/me", headers=customer_headers(c)).json()
    assert len(cards) == 1
    assert "token" not in cards[0] and len(cards[0]["last4"]) == 4


def test_customer_blocks_and_unblocks_own_card(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    card = make_card(s, c, make_account(s, c))
    h = customer_headers(c)
    assert client.post(f"/api/v1/cards/{card.id}/block", headers=h).json()["status"] == "BLOQUEADA"
    assert client.post(f"/api/v1/cards/{card.id}/unblock", headers=h).json()["status"] == "ACTIVA"
    actions = [a.action for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["CARD_BLOCK", "CARD_UNBLOCK"]


def test_customer_cannot_block_someone_elses_card(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    card = make_card(s, beto, make_account(s, beto))
    assert (
        client.post(f"/api/v1/cards/{card.id}/block", headers=customer_headers(ana)).status_code
        == 403
    )


def test_staff_roles(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    card = make_card(s, c, make_account(s, c))
    assert (
        client.post(f"/api/v1/cards/{card.id}/block", headers=headers(Role.FRAUDE)).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/cards/{card.id}/unblock", headers=headers(Role.MARKETING)).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/cards/00000000-0000-4000-8000-000000000000/block", headers=headers(Role.ADMIN)
        ).status_code
        == 404
    )
