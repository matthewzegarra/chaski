"""HTTP client for ia-api. Every call degrades gracefully: on any failure it returns None
and the caller falls back to the human workflow (manual review, no score, etc.)."""

from __future__ import annotations

from typing import Any

import httpx
from chaski_common.logging import correlation_id_var, get_logger
from chaski_common.service_auth import service_token

from core_api.settings import get_settings

log = get_logger(__name__)
TIMEOUT = httpx.Timeout(20.0, connect=3.0)
# Document Intelligence polls the analysis and ia-api may be waking up from zero replicas.
KYC_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


def _post(
    path: str, token: str, timeout: httpx.Timeout = TIMEOUT, **kwargs: Any
) -> dict[str, Any] | None:
    url = f"{get_settings().ia_api_url}/api/v1{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if cid := correlation_id_var.get():
        headers["X-Correlation-ID"] = cid
    try:
        resp = httpx.post(url, headers=headers, timeout=timeout, **kwargs)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data
    except Exception as exc:
        log.warning("ia_api_call_failed", path=path, error_type=type(exc).__name__)
        return None


def kyc_extract(
    image: bytes, content_type: str, filename: str, expected: dict[str, str]
) -> dict[str, Any] | None:
    """`expected` (typed data) lets the local OCR mock simulate a reading; Azure ignores it."""
    # Anonymous onboarding: no user token to forward, use the service identity.
    try:
        token = service_token()
    except Exception as exc:  # identity misconfigured: degrade like any ia-api failure
        log.warning("service_token_failed", error_type=type(exc).__name__)
        return None
    return _post(
        "/kyc/extract",
        token,
        timeout=KYC_TIMEOUT,
        files={"image": (filename, image, content_type)},
        data={f"expected_{k}": v for k, v in expected.items()},
    )


def classify_complaint(
    complaint_id: str, subject: str, body: str, user_token: str
) -> dict[str, Any] | None:
    payload = {"complaint_id": complaint_id, "asunto": subject, "texto": body}
    return _post("/complaints/classify", user_token, json=payload)


def score_loan(payload: dict[str, Any], user_token: str) -> dict[str, Any] | None:
    return _post("/loans/score", user_token, json=payload)
