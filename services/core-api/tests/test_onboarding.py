from __future__ import annotations

from typing import Any

from chaski_common.models import Account, Card, Customer, KycDocument
from chaski_common.roles import Role
from chaski_common.testing import customer_headers, headers, make_customer
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

FORM = {
    "first_name": "Rosa",
    "last_name": "Mamani Quispe",
    "document_number": "45678912",
    "birth_date": "1994-03-21",
    "email": "rosa.mamani@gmail.com",
    "phone": "987654321",
    "region": "Cusco",
    "monthly_income": "2800",
}


def _start(
    client: TestClient,
    form: dict[str, str] | None = None,
    image: bytes = PNG,
    ctype: str = "image/png",
):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/onboarding", data=form or FORM, files={"dni_image": ("dni.png", image, ctype)}
    )


def test_onboarding_without_ia_creates_pending_customer(
    client: TestClient, s: Session, ia: dict[str, Any]
) -> None:
    resp = _start(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kyc_status"] == "PENDIENTE"
    assert body["extracted"] is None
    customer = s.get(Customer, body["customer_id"])
    assert customer is not None and customer.document_number == "45678912"
    doc = s.scalars(select(KycDocument)).one()
    assert doc.blob_path.startswith("file://kyc/")
    assert doc.extracted_json is not None
    assert doc.extracted_json["consulta_fuente"] == "MOCK"
    assert "nombres" not in doc.extracted_json  # OCR unavailable; only the lookup snapshot
    assert ia["calls"][0][0] == "/kyc/extract"


def test_onboarding_survives_service_identity_failure(
    client: TestClient, s: Session, ia: dict[str, Any], monkeypatch: Any
) -> None:
    from core_api import ia_client

    def broken() -> str:
        raise RuntimeError("AADSTS700236")

    monkeypatch.setattr(ia_client, "service_token", broken)
    resp = _start(client)
    assert resp.status_code == 201, resp.text
    assert resp.json()["extracted"] is None
    assert ia["calls"] == []


def test_onboarding_with_ia_extraction_compares_fields(
    client: TestClient, s: Session, ia: dict[str, Any]
) -> None:
    ia["responses"]["/kyc/extract"] = {
        "datos": {
            "numero_documento": "45678912",
            "nombres": "ROSA",
            "apellidos": "MAMANI QUISPE",
            "fecha_nacimiento": "1994-03-21",
        },
        "confianza": 0.94,
    }
    body = _start(client).json()
    assert body["confidence"] == 0.94
    assert body["lookup"] == {
        "nombres": "Rosa",
        "apellidos": "Mamani Quispe",
        "fuente": "MOCK",
    }
    assert body["checks"] == {
        "dni_coincide": True,
        "nombres_coinciden": True,
        "fecha_nacimiento_coincide": True,
        "consulta_nombres_coinciden": True,
        "consulta_ocr_coinciden": True,
    }


def test_validations(client: TestClient, s: Session) -> None:
    assert _start(client, image=b"not an image").status_code == 422
    assert _start(client, ctype="application/pdf").status_code == 422
    assert _start(client, {**FORM, "birth_date": "2015-01-01"}).status_code == 422
    assert _start(client, {**FORM, "document_number": "1234"}).status_code == 422
    assert _start(client, {**FORM, "region": "Marte"}).status_code == 422
    assert _start(client, {**FORM, "email": "no-es-correo"}).status_code == 422
    assert _start(client, image=PNG + b"\x00" * (5 * 1024 * 1024)).status_code == 413


def test_duplicate_document_is_409(client: TestClient, s: Session) -> None:
    make_customer(s, document_number="45678912")
    assert _start(client).status_code == 409


def test_pending_inbox_is_masked_and_decision_opens_products(
    client: TestClient, s: Session, ia: dict[str, Any]
) -> None:
    ia["responses"]["/kyc/extract"] = {
        "datos": {"numero_documento": "45678913", "nombres": "ROSA", "apellidos": "MAMANI QUISPE"},
        "confianza": 0.71,
    }
    customer_id = _start(client).json()["customer_id"]
    h = headers(Role.ATENCION, sub="lucia")

    inbox = client.get("/api/v1/onboarding/pending", headers=h).json()
    assert len(inbox) == 1
    item = inbox[0]
    assert item["customer"]["document_number"] == "****8912"
    assert item["extracted"]["numero_documento"] == "****8913"
    assert item["lookup"]["fuente"] == "MOCK"
    assert item["checks"]["dni_coincide"] is False  # flagged for the analyst
    assert item["checks"]["consulta_nombres_coinciden"] is True

    resp = client.post(
        f"/api/v1/onboarding/{customer_id}/decision", json={"decision": "APROBADO"}, headers=h
    )
    assert resp.status_code == 200 and resp.json()["kyc_status"] == "APROBADO"
    assert s.scalars(select(Account).where(Account.customer_id == customer_id)).one().balance == 0
    card = s.scalars(select(Card).where(Card.customer_id == customer_id)).one()
    assert card.token.startswith("tok_") and len(card.last4) == 4

    again = client.post(
        f"/api/v1/onboarding/{customer_id}/decision", json={"decision": "RECHAZADO"}, headers=h
    )
    assert again.status_code == 409


def test_reject_and_permissions(client: TestClient, s: Session) -> None:
    pending = make_customer(s, kyc_status="PENDIENTE")
    url = f"/api/v1/onboarding/{pending.id}/decision"
    assert (
        client.post(url, json={"decision": "APROBADO"}, headers=headers(Role.RIESGOS)).status_code
        == 403
    )
    assert (
        client.post(
            url, json={"decision": "APROBADO"}, headers=customer_headers(pending)
        ).status_code
        == 403
    )
    resp = client.post(url, json={"decision": "RECHAZADO"}, headers=headers(Role.ADMIN))
    assert resp.json()["kyc_status"] == "RECHAZADO"
    assert s.scalars(select(Account).where(Account.customer_id == pending.id)).first() is None
