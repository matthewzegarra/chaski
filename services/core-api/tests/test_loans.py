from __future__ import annotations

from decimal import Decimal
from typing import Any

from chaski_common.models import Account, LoanInstallment, Transaction
from chaski_common.roles import Role
from chaski_common.testing import customer_headers, headers, make_account, make_customer
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _request(client: TestClient, customer, amount: str = "10000", term: int = 24):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/loans",
        json={"amount": amount, "term_months": term},
        headers=customer_headers(customer),
    )


def test_quote_uses_segment_rate(client: TestClient, s: Session) -> None:
    c = make_customer(s, segment="PREFERENTE", risk_level="BAJO")
    q = client.get(
        "/api/v1/loans/quote?amount=10000&term_months=12", headers=customer_headers(c)
    ).json()
    assert q["rate_tea"] == 0.18
    assert 910 < q["monthly_payment"] < 920
    assert (
        client.get(
            "/api/v1/loans/quote?amount=10000&term_months=7", headers=customer_headers(c)
        ).status_code
        == 422
    )


def test_request_without_ia_has_no_score(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    resp = _request(client, c)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "SOLICITADO" and body["ai_score"] is None
    assert body["monthly_payment"] > 0


def test_request_with_ia_score(client: TestClient, s: Session, ia: dict[str, Any]) -> None:
    ia["responses"]["/loans/score"] = {"score": 712, "explicacion": "Ingresos estables y sin mora."}
    c = make_customer(s)
    body = _request(client, c).json()
    assert body["ai_score"] == 712
    sent = ia["calls"][0][1]["json"]
    assert sent["ingreso_mensual"] == 3500.0 and sent["plazo_meses"] == 24
    assert "document_number" not in sent and "email" not in sent


def test_request_rules(client: TestClient, s: Session) -> None:
    pending = make_customer(s, kyc_status="PENDIENTE")
    assert _request(client, pending).status_code == 409
    c = make_customer(s)
    assert _request(client, c).status_code == 201
    assert _request(client, c).status_code == 409  # one application at a time
    assert _request(client, c, amount="100").status_code == 422


def test_only_riesgos_decides(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    loan_id = _request(client, c).json()["id"]
    url = f"/api/v1/loans/{loan_id}/decision"
    for role in (Role.ADMIN, Role.ATENCION, Role.DIRECCION):
        assert (
            client.post(url, json={"decision": "APROBADO"}, headers=headers(role)).status_code
            == 403
        )
    assert (
        client.post(url, json={"decision": "APROBADO"}, headers=customer_headers(c)).status_code
        == 403
    )


def test_approval_disburses_into_soles_account(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    acc = make_account(s, c, balance="100.00")
    loan_id = _request(client, c, amount="5000", term=12).json()["id"]
    resp = client.post(
        f"/api/v1/loans/{loan_id}/decision",
        json={"decision": "APROBADO", "comment": "Cumple política"},
        headers=headers(Role.RIESGOS, sub="renzo"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DESEMBOLSADO" and body["decided_by"] == "renzo"
    assert body["outstanding_balance"] == 5000.0
    s.expire_all()
    assert s.get(Account, acc.id).balance == Decimal("5100.00")  # type: ignore[union-attr]
    assert s.scalar(select(func.count()).select_from(LoanInstallment)) == 12
    assert s.scalars(select(Transaction)).one().description == "Desembolso de préstamo"

    again = client.post(
        f"/api/v1/loans/{loan_id}/decision",
        json={"decision": "RECHAZADO"},
        headers=headers(Role.RIESGOS),
    )
    assert again.status_code == 409


def test_rejection_and_missing_account(client: TestClient, s: Session) -> None:
    c = make_customer(s)
    loan_id = _request(client, c).json()["id"]
    resp = client.post(
        f"/api/v1/loans/{loan_id}/decision",
        json={"decision": "APROBADO"},
        headers=headers(Role.RIESGOS),
    )
    assert resp.status_code == 409  # no soles account to disburse to
    resp = client.post(
        f"/api/v1/loans/{loan_id}/decision",
        json={"decision": "RECHAZADO"},
        headers=headers(Role.RIESGOS),
    )
    assert resp.json()["status"] == "RECHAZADO"


def test_console_list_and_detail_permissions(client: TestClient, s: Session) -> None:
    ana, beto = make_customer(s), make_customer(s)
    loan_id = _request(client, ana).json()["id"]
    page = client.get("/api/v1/loans?status=SOLICITADO", headers=headers(Role.RIESGOS)).json()
    assert page["total"] == 1 and page["items"][0]["bucket"] == "Normal"
    assert client.get("/api/v1/loans", headers=headers(Role.MARKETING)).status_code == 403
    assert client.get(f"/api/v1/loans/{loan_id}", headers=customer_headers(ana)).status_code == 200
    assert client.get(f"/api/v1/loans/{loan_id}", headers=customer_headers(beto)).status_code == 403
    assert len(client.get("/api/v1/loans/me", headers=customer_headers(ana)).json()) == 1


def test_rescore(client: TestClient, s: Session, ia: dict[str, Any]) -> None:
    c = make_customer(s)
    loan_id = _request(client, c).json()["id"]
    ia["responses"]["/loans/score"] = {"score": 640, "explicacion": "Endeudamiento moderado."}
    resp = client.post(f"/api/v1/loans/{loan_id}/rescore", headers=headers(Role.RIESGOS))
    assert resp.json()["ai_score"] == 640
