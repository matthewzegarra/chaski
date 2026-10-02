"""DNI extraction with Azure AI Document Intelligence.

1. `prebuilt-idDocument` (structured fields with confidence).
2. If it fails or finds no document number: `prebuilt-read` + regex for an 8-digit DNI.
The mock simulates an OCR reading of the data the applicant typed (see D39).
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Protocol

from chaski_common.logging import get_logger

from ia_api.settings import IaSettings, get_settings

log = get_logger(__name__)
DNI_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")


@dataclass
class Extraction:
    datos: dict[str, str]
    confianza: float
    modelo: str


class DocIntelProvider(Protocol):
    name: str

    def extract(self, image: bytes, content_type: str, expected: dict[str, str]) -> Extraction: ...


def _value(field: Any) -> str | None:
    if field is None:
        return None
    for attr in ("value_string", "value_date", "content"):
        v = getattr(field, attr, None)
        if v:
            return v.isoformat() if isinstance(v, date) else str(v)
    return None


def map_id_document(result: Any) -> Extraction | None:
    """Maps a prebuilt-idDocument result to our fields (None when no document was found)."""
    docs = getattr(result, "documents", None) or []
    if not docs:
        return None
    fields = docs[0].fields or {}
    mapping = {
        "numero_documento": "DocumentNumber",
        "nombres": "FirstName",
        "apellidos": "LastName",
        "fecha_nacimiento": "DateOfBirth",
        "fecha_expiracion": "DateOfExpiration",
    }
    datos: dict[str, str] = {}
    confidences: list[float] = []
    for ours, theirs in mapping.items():
        f = fields.get(theirs)
        v = _value(f)
        if v:
            datos[ours] = v.upper() if ours in ("nombres", "apellidos") else v
            confidences.append(float(getattr(f, "confidence", 0) or 0))
    if "numero_documento" not in datos:
        return None
    return Extraction(
        datos=datos, confianza=round(min(confidences), 3), modelo="prebuilt-idDocument"
    )


def map_read(content: str) -> Extraction | None:
    """Fallback over plain OCR text: the first 8-digit number is taken as the DNI."""
    match = DNI_RE.search(content or "")
    if not match:
        return None
    return Extraction(
        datos={"numero_documento": match.group(1)}, confianza=0.6, modelo="prebuilt-read+regex"
    )


class AzureDocIntel:
    name = "azure-docintel"

    def __init__(self, settings: IaSettings) -> None:
        from azure.ai.documentintelligence import DocumentIntelligenceClient

        if not settings.docintel_endpoint:
            raise RuntimeError("DOCINTEL_ENDPOINT is required in AI_MODE=azure")
        if settings.docintel_key:
            from azure.core.credentials import AzureKeyCredential

            credential: Any = AzureKeyCredential(settings.docintel_key.get_secret_value())
        else:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self.client = DocumentIntelligenceClient(settings.docintel_endpoint, credential)

    def extract(self, image: bytes, content_type: str, expected: dict[str, str]) -> Extraction:
        try:
            poller = self.client.begin_analyze_document(
                "prebuilt-idDocument", body=io.BytesIO(image), content_type=content_type
            )
            found = map_id_document(poller.result())
            if found:
                return found
        except Exception as exc:
            log.warning("docintel_id_document_failed", error_type=type(exc).__name__)
        poller = self.client.begin_analyze_document(
            "prebuilt-read", body=io.BytesIO(image), content_type=content_type
        )
        found = map_read(getattr(poller.result(), "content", ""))
        if found:
            return found
        return Extraction(datos={}, confianza=0.0, modelo="prebuilt-read+regex")


class MockDocIntel:
    """Simulates OCR: "reads" what the applicant typed. Deterministic per image: about 1 in 5
    images comes back with a misread DNI digit and lower confidence, so the analyst's
    mismatch flags can be demonstrated."""

    name = "mock-docintel"

    def extract(self, image: bytes, content_type: str, expected: dict[str, str]) -> Extraction:
        digest = hashlib.sha256(image).digest()
        noisy = digest[0] % 5 == 0
        datos = {k: v for k, v in expected.items() if v}
        if "nombres" in datos:
            datos["nombres"] = datos["nombres"].upper()
        if "apellidos" in datos:
            datos["apellidos"] = datos["apellidos"].upper()
        dni = datos.get("numero_documento")
        if noisy and dni and len(dni) == 8:
            datos["numero_documento"] = dni[:-1] + str((int(dni[-1]) + 3) % 10)
        confidence = 0.62 + (digest[1] % 10) / 100 if noisy else 0.88 + (digest[1] % 11) / 100
        if not datos:
            return Extraction(datos={}, confianza=0.0, modelo="mock")
        return Extraction(datos=datos, confianza=round(confidence, 3), modelo="mock")


@lru_cache
def get_docintel() -> DocIntelProvider:
    settings = get_settings()
    if settings.ai_mode == "azure":
        return AzureDocIntel(settings)
    return MockDocIntel()
