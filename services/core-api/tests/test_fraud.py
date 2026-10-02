from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from chaski_common.models import AuditLog, Card, FraudAlert
from chaski_common.roles import Role
from chaski_common.testing import headers, make_account, make_card, make_customer, make_tx
from core_api.routers.fraud import sign
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

SECRET = "test-webhook-secret"


def _alert(s: Session, **kw) -> FraudAlert:  # type: ignore[no-untyped-def]
    c = make_customer(s)
    acc = make_account(s, c)
    card = make_card(s, c, acc)
    tx = make_tx(s, acc, card_id=card.id, merchant="Ripley", city="Lima")
    alert = FraudAlert(
        id=uuid.uuid4(), transaction_id=tx.id, customer_id=c.id, rule="R2_MONTO_ATIPICO",
        score=Decimal("88"), source="RULES", status="ABIERTA", details={"descripcion": "x"}, **kw,
    )  # fmt: skip
    s.add(alert)
    s.commit()
    return alert


def test_list_alerts_with_context(client: TestClient, s: Session) -> None:
    alert = _alert(s)
    items = client.get("/api/v1/fraud/alerts?status=ABIERTA", headers=headers(Role.FRAUDE)).json()
    assert items[0]["id"] == str(alert.id)
    assert items[0]["merchant"] == "Ripley" and items[0]["card_status"] == "ACTIVA"
    assert client.get("/api/v1/fraud/alerts", headers=headers(Role.ATENCION)).status_code == 403


def test_confirm_and_block_card(client: TestClient, s: Session) -> None:
    alert = _alert(s)
    url = f"/api/v1/fraud/alerts/{alert.id}/resolve"
    resp = client.post(
        url, json={"status": "CONFIRMADA", "block_card": True}, headers=headers(Role.FRAUDE)
    )
    assert resp.json() == {"id": str(alert.id), "status": "CONFIRMADA", "card_blocked": True}
    s.expire_all()
    assert s.scalars(select(Card)).one().status == "BLOQUEADA"
    assert (
        client.post(url, json={"status": "DESCARTADA"}, headers=headers(Role.FRAUDE)).status_code
        == 409
    )


def test_webhook_with_valid_signature(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    raw = json.dumps(
        {
            "rule": "FABRIC_ANOMALIA",
            "score": 91.5,
            "customer_id": str(c.id),
            "details": {"modelo": "kql"},
        }
    )
    resp = client.post(
        "/api/v1/fraud/webhook",
        content=raw,
        headers={
            "X-Chaski-Signature": sign(raw.encode(), SECRET),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    alert = s.scalars(select(FraudAlert)).one()
    assert (
        alert.source == "FABRIC" and alert.customer_id == c.id and alert.score == Decimal("91.50")
    )


def test_webhook_rejects_bad_signature_and_audits(client: TestClient, s: Session) -> None:
    raw = b'{"rule": "X1", "score": 50}'
    for sig in (None, "sha256=deadbeef", sign(raw, "otro-secreto")):
        h = {"X-Chaski-Signature": sig} if sig else {}
        assert client.post("/api/v1/fraud/webhook", content=raw, headers=h).status_code == 401
    assert s.scalars(select(FraudAlert)).first() is None
    assert len(s.scalars(select(AuditLog).where(AuditLog.allowed.is_(False))).all()) == 3


def test_webhook_rejects_tampered_body(client: TestClient, s: Session) -> None:
    signature = sign(b'{"rule": "X1", "score": 50}', SECRET)
    resp = client.post(
        "/api/v1/fraud/webhook",
        content=b'{"rule": "X1", "score": 99}',
        headers={"X-Chaski-Signature": signature},
    )
    assert resp.status_code == 401


def test_webhook_invalid_payload(client: TestClient, s: Session) -> None:
    raw = b'{"score": 500}'
    resp = client.post(
        "/api/v1/fraud/webhook", content=raw, headers={"X-Chaski-Signature": sign(raw, SECRET)}
    )
    assert resp.status_code == 422


def test_webhook_not_configured(
    client: TestClient, s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core_api.settings import get_settings

    monkeypatch.setenv("FRAUD_WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    assert client.post("/api/v1/fraud/webhook", content=b"{}").status_code == 503
