"""Bronze and silver layers of the data lake (Parquet, partitioned by run date).

Data minimisation (Ley 29733): only analytical columns leave the core database. No DNI,
names, e-mails or phones; cards only by product attributes (no token, no last4).

bronze/<table>/dt=YYYY-MM-DD/<run_id>.parquet   raw extract (transactions incremental)
silver/transactions/dt=YYYY-MM-DD/<run_id>.parquet   deduplicated, typed, valid rows only
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import text
from sqlalchemy.orm import Session

from core_api.etl.lake import Lake

EXTRACTS: dict[str, str] = {
    "customers": """
        SELECT id, segment, region, kyc_status, risk_level,
               date_trunc('month', created_at)::date AS created_month,
               extract(year FROM age(birth_date))::int AS age
        FROM core.customers""",
    "accounts": """
        SELECT id, customer_id, product, currency, balance, status, opened_at
        FROM core.accounts""",
    "loans": """
        SELECT id, customer_id, product, amount, term_months, rate_tea, status, days_past_due,
               outstanding_balance, created_at
        FROM core.loans""",
    "transactions": """
        SELECT id, account_id, type, amount, currency, channel, city, created_at
        FROM core.transactions WHERE created_at > :since""",
}
VALID_CURRENCIES = {"PEN", "USD"}


def _plain(value: Any) -> Any:
    return str(value) if isinstance(value, uuid.UUID) else value


def _to_parquet(rows: list[dict[str, Any]]) -> bytes:
    table = pa.Table.from_pylist([{k: _plain(v) for k, v in r.items()} for r in rows])
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()


def export(
    db: Session, lake: Lake, run_id: uuid.UUID, run_date: datetime, since: datetime
) -> dict[str, int]:
    """Writes bronze for every table and silver for transactions. Returns rows per dataset."""
    partition = f"dt={run_date:%Y-%m-%d}/{run_id}.parquet"
    counts: dict[str, int] = {}
    tx_rows: list[dict[str, Any]] = []
    for name, sql in EXTRACTS.items():
        rows = [dict(r) for r in db.execute(text(sql), {"since": since}).mappings()]
        counts[f"bronze.{name}"] = len(rows)
        if rows:
            lake.put("bronze", f"{name}/{partition}", _to_parquet(rows), "application/octet-stream")
        if name == "transactions":
            tx_rows = rows

    seen: set[str] = set()
    silver: list[dict[str, Any]] = []
    for r in tx_rows:
        key = str(r["id"])
        if key in seen or r["currency"] not in VALID_CURRENCIES or Decimal(r["amount"]) <= 0:
            continue
        seen.add(key)
        silver.append(r)
    counts["silver.transactions"] = len(silver)
    if silver:
        lake.put(
            "silver", f"transactions/{partition}", _to_parquet(silver), "application/octet-stream"
        )
    return counts
