"""Entry point of the `caj-pipeline` Container Apps Job (python -m core_api.pipeline_job).

Runs the same ingestion flow that the console simulates locally (services/pipeline_sim.py):
pending raw rows are validated by the quality checks, bad rows go to quarantine and the run
is recorded in ops.pipeline_runs / ops.quality_checks, which the console shows. When a data
lake is configured (BLOB_ACCOUNT_URL) the quarantined records of the run are also written
to the `quarantine` container for later analysis.

Env: DATABASE_URL, PIPELINE_TRIGGER (MANUAL | PROGRAMADO), BLOB_ACCOUNT_URL (optional),
AZURE_CLIENT_ID (managed identity used for the lake).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from chaski_common.db import get_engine
from chaski_common.logging import configure_logging, get_logger
from chaski_common.models import PipelineRun, QuarantineRecord
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.services import pipeline_sim

log = get_logger(__name__)


def _export_quarantine(run: PipelineRun, records: list[dict[str, Any]]) -> str | None:
    account_url = os.environ.get("BLOB_ACCOUNT_URL")
    if not account_url or not records:
        return None
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings

    blob_name = f"runs/{run.started_at:%Y/%m/%d}/{run.id}.json"
    client = BlobServiceClient(account_url, credential=DefaultAzureCredential())
    client.get_blob_client("quarantine", blob_name).upload_blob(
        json.dumps(records, ensure_ascii=False, default=str),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    return f"quarantine/{blob_name}"


def main() -> int:
    configure_logging("pipeline-job", os.environ.get("LOG_LEVEL", "INFO"))
    trigger = os.environ.get("PIPELINE_TRIGGER", "MANUAL")
    with Session(get_engine(), expire_on_commit=False) as db:
        run = pipeline_sim.run_local(db, trigger=trigger)
        db.commit()
        records = [
            {"raw_id": q.raw_id, "reason": q.reason, "payload": q.payload}
            for q in db.scalars(select(QuarantineRecord).where(QuarantineRecord.run_id == run.id))
        ]
    try:
        exported = _export_quarantine(run, records)
    except Exception as exc:  # the run is already recorded; the lake copy is best effort
        log.warning("quarantine_export_failed", error_type=type(exc).__name__)
        exported = None
    log.info(
        "pipeline_run_finished",
        run_id=str(run.id),
        status=run.status,
        trigger=trigger,
        rows_in=run.rows_in,
        rows_ok=run.rows_ok,
        rows_quarantined=run.rows_quarantined,
        quarantine_blob=exported,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
