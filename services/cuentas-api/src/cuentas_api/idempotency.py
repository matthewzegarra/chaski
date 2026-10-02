"""Idempotency-Key handling: same key + same body replays the stored response;
same key + different body is a 409."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from chaski_common.models import IdempotencyKey
from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

KEY_MIN, KEY_MAX = 8, 64


def validate_key(key: str | None, *, required: bool) -> str | None:
    if key is None or key == "":
        if required:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "El header Idempotency-Key es obligatorio"
            )
        return None
    if not (KEY_MIN <= len(key) <= KEY_MAX) or not key.replace("-", "").isalnum():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Idempotency-Key inválido (8 a 64 caracteres alfanuméricos)",
        )
    return key


def request_hash(body: BaseModel) -> str:
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def find(
    session: Session, customer_id: uuid.UUID, key: str, req_hash: str
) -> dict[str, Any] | None:
    row = session.get(IdempotencyKey, (customer_id, key))
    if row is None:
        return None
    if row.request_hash != req_hash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este Idempotency-Key ya se usó con datos distintos",
        )
    return row.response_json


def store(
    session: Session, customer_id: uuid.UUID, key: str, req_hash: str, response: dict[str, Any]
) -> None:
    session.add(
        IdempotencyKey(
            customer_id=customer_id,
            key=key,
            request_hash=req_hash,
            status_code=201,
            response_json=response,
        )
    )
