"""Entry point of the `caj-pipeline` Container Apps Jobs (python -m core_api.pipeline_job).

One run of the CHASKI ingestion flow (Phase 7), recorded in ops.pipeline_runs and
ops.quality_checks, which the console's Data Pipelines module shows:

1. Raw ingestion: per-record checks; bad records go to quarantine (pipeline_sim).
2. Table-level quality checks of the guide (etl/quality.py).
3. Data lake: bronze extract and silver transactions in Parquet (etl/lakehouse.py), plus the
   quarantined records as JSON, when a lake is configured (BLOB_ACCOUNT_URL or LAKE_DIR).
4. Data warehouse: gold layer merged into Azure SQL (etl/dw.py) when DW_SERVER/DW_DATABASE
   are set. Blocking quality failures skip this step, so bad data never reaches the DW.

Env: DATABASE_URL, PIPELINE_TRIGGER (MANUAL | PROGRAMADO), BLOB_ACCOUNT_URL or LAKE_DIR,
DW_SERVER, DW_DATABASE, AZURE_CLIENT_ID (managed identity).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

from chaski_common.db import get_engine
from chaski_common.logging import configure_logging, get_logger
from chaski_common.models import PipelineRun, QualityCheck, QuarantineRecord
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.etl import dw, lakehouse, quality
from core_api.etl.lake import Lake, get_lake
from core_api.services import pipeline_sim

log = get_logger(__name__)


def _export_quarantine(
    lake: Lake | None, run: PipelineRun, records: list[dict[str, Any]]
) -> str | None:
    if lake is None or not records:
        return None
    return lake.put(
        "quarantine",
        f"runs/{run.started_at:%Y/%m/%d}/{run.id}.json",
        json.dumps(records, ensure_ascii=False, default=str).encode(),
        "application/json",
    )


def run(db: Session, trigger: str, lake: Lake | None) -> dict[str, Any]:
    previous = db.scalar(
        select(func.max(PipelineRun.started_at)).where(PipelineRun.status != "FALLIDO")
    )
    run = pipeline_sim.run_local(db, trigger=trigger)
    summary: dict[str, Any] = {"run_id": str(run.id), "trigger": trigger}
    errors: list[str] = []

    # 2. Table-level checks.
    results = quality.run_checks(db)
    for r in results:
        db.add(QualityCheck(run_id=run.id, check_name=r.name, table_name=r.table,
                            passed=r.passed, failed_count=r.failed))  # fmt: skip
    blocking = [f"{r.table}.{r.name}" for r in results if r.blocking and not r.passed]
    summary["checks_failed"] = [f"{r.table}.{r.name}" for r in results if not r.passed]
    db.commit()

    # 3. Data lake.
    records = [
        {"raw_id": q.raw_id, "reason": q.reason, "payload": q.payload}
        for q in db.scalars(select(QuarantineRecord).where(QuarantineRecord.run_id == run.id))
    ]
    try:
        summary["quarantine_blob"] = _export_quarantine(lake, run, records)
        if lake is not None:
            since = previous or datetime(1970, 1, 1, tzinfo=UTC)
            summary["lake"] = lakehouse.export(db, lake, run.id, run.started_at, since)
    except Exception as exc:
        errors.append(f"lake: {type(exc).__name__}")
        log.exception("lake_export_failed")

    # 4. Data warehouse (never with blocking quality failures).
    target = dw.configured()
    if target and blocking:
        summary["dw"] = "omitido por checks bloqueantes: " + ", ".join(blocking)
    elif target:
        try:
            conn = dw.connect(*target)
            try:
                summary["dw"] = dw.load(db, conn)
            finally:
                conn.close()
        except Exception as exc:
            errors.append(f"dw: {type(exc).__name__}")
            log.exception("dw_load_failed")

    run.finished_at = datetime.now(UTC)
    if errors:
        run.status, run.error = "FALLIDO", "; ".join(errors)
    elif blocking and run.status == "EXITOSO":
        run.status = "CON_ALERTAS"
    db.commit()
    summary.update(status=run.status, rows_in=run.rows_in, rows_ok=run.rows_ok,
                   rows_quarantined=run.rows_quarantined)  # fmt: skip
    return summary


def main() -> int:
    configure_logging("pipeline-job", os.environ.get("LOG_LEVEL", "INFO"))
    trigger = os.environ.get("PIPELINE_TRIGGER", "MANUAL")
    with Session(get_engine(), expire_on_commit=False) as db:
        summary = run(db, trigger, get_lake())
    log.info("pipeline_run_finished", **summary)
    return 1 if summary["status"] == "FALLIDO" else 0


if __name__ == "__main__":
    sys.exit(main())
