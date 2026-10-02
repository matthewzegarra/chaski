from __future__ import annotations

from chaski_common.models import AuditLog
from chaski_common.roles import Role
from chaski_common.testing import customer_headers, headers, make_account, make_customer
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _last_audit(s: Session) -> AuditLog:
    s.expire_all()
    return s.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()  # type: ignore[return-value]


def test_list_is_masked_for_every_role(client: TestClient, s: Session) -> None:
    c = make_customer(s, document_number="45678912", email="maria.q@dominio.com", phone="987654123")
    for role in (Role.ATENCION, Role.ADMIN, Role.RIESGOS, Role.FRAUDE, Role.OPERACIONES):
        item = client.get("/api/v1/customers", headers=headers(role)).json()["items"][0]
        assert item["id"] == str(c.id)
        assert item["document_number"] == "****8912"
        assert item["email"] == "m***@dominio.com"
        assert item["phone"] == "***-***-123"


def test_marketing_and_clients_cannot_list_customers_and_it_is_audited(
    client: TestClient, s: Session
) -> None:
    c = make_customer(s)
    assert client.get("/api/v1/customers", headers=headers(Role.MARKETING)).status_code == 403
    assert client.get("/api/v1/customers", headers=customer_headers(c)).status_code == 403
    denied = s.scalars(select(AuditLog).where(AuditLog.allowed.is_(False))).all()
    assert {d.actor_role for d in denied} == {"Marketing", "Cliente"}


def test_search_by_dni_and_name(client: TestClient, s: Session) -> None:
    make_customer(s, document_number="11112222", first_name="Rosa")
    make_customer(s, document_number="33334444", first_name="Elmer")
    h = headers(Role.ATENCION)
    assert client.get("/api/v1/customers?q=33334444", headers=h).json()["total"] == 1
    assert (
        client.get("/api/v1/customers?q=ros", headers=h).json()["items"][0]["first_name"] == "Rosa"
    )


def test_detail_is_masked_and_audited(client: TestClient, s: Session) -> None:
    c = make_customer(s, document_number="45678912")
    make_account(s, c)
    resp = client.get(f"/api/v1/customers/{c.id}", headers=headers(Role.ATENCION, sub="lucia"))
    body = resp.json()
    assert body["document_number"] == "****8912"
    assert len(body["accounts"]) == 1
    entry = _last_audit(s)
    assert (entry.action, entry.actor_id, entry.pii_accessed) == ("VIEW_CUSTOMER", "lucia", False)


def test_reveal_pii_requires_reason_and_is_audited(client: TestClient, s: Session) -> None:
    c = make_customer(s, document_number="45678912", email="maria.q@dominio.com")
    h = headers(Role.ATENCION, sub="lucia")
    url = f"/api/v1/customers/{c.id}/reveal-pii"
    assert client.post(url, json={"reason": "corto"}, headers=h).status_code == 422

    resp = client.post(url, json={"reason": "Cliente llamó para validar su identidad"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["document_number"] == "45678912"
    assert resp.json()["email"] == "maria.q@dominio.com"
    entry = _last_audit(s)
    assert entry.action == "REVEAL_PII" and entry.pii_accessed and entry.allowed
    assert entry.reason == "Cliente llamó para validar su identidad"


def test_only_atencion_and_admin_can_reveal(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    body = {"reason": "Necesito ver los datos completos"}
    for role in (Role.RIESGOS, Role.FRAUDE, Role.MARKETING, Role.TI):
        resp = client.post(f"/api/v1/customers/{c.id}/reveal-pii", json=body, headers=headers(role))
        assert resp.status_code == 403
    assert (
        client.post(
            f"/api/v1/customers/{c.id}/reveal-pii", json=body, headers=headers(Role.ADMIN)
        ).status_code
        == 200
    )


def test_customer_sees_own_profile(client: TestClient, s: Session) -> None:
    c = make_customer(s, document_number="45678912")
    body = client.get("/api/v1/customers/me", headers=customer_headers(c)).json()
    assert body["document_number"] == "45678912"


def test_unknown_customer_404(client: TestClient, s: Session) -> None:
    resp = client.get(
        "/api/v1/customers/00000000-0000-4000-8000-000000000000", headers=headers(Role.ADMIN)
    )
    assert resp.status_code == 404
