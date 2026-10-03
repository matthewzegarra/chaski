from __future__ import annotations

import json
from pathlib import Path

from ia_api import evals


def test_labelled_datasets_have_the_expected_shape() -> None:
    complaints = evals._load("quejas_etiquetadas.jsonl")
    questions = evals._load("dataset.jsonl")
    assert len(complaints) == 60 and sum(r["inyeccion"] for r in complaints) == 5
    assert {r["categoria"] for r in complaints} == {
        "FRAUDE", "COBRO_INDEBIDO", "TARJETA", "PRESTAMO", "CANAL_DIGITAL", "OTRO"
    }  # fmt: skip
    assert len(questions) == 20


def test_mock_evaluation_report_and_quality_gate(db: None, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    assert evals.main(["--min-accuracy", "0.7", "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    quejas, asistente = report["quejas"], report["asistente"]
    assert report["proveedor"] == "mock" and quejas["errores"] == 0
    assert quejas["accuracy_categoria"] >= 0.7 and quejas["deteccion_inyeccion"] >= 0.6
    assert asistente["accuracy_herramienta"] >= 0.7
    # An impossible threshold fails the gate.
    assert evals.main(["--min-accuracy", "0.99", "--output", str(out)]) == 1
