"""Bulk-loads a Dataset into Postgres with COPY."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from chaski_simulator.generate import Dataset
from chaski_simulator.gold import build_gold

CORE_OPS_TABLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "customers",
        "core.customers",
        (
            "id",
            "document_type",
            "document_number",
            "first_name",
            "last_name",
            "email",
            "phone",
            "birth_date",
            "segment",
            "region",
            "kyc_status",
            "risk_level",
            "monthly_income",
            "kyc_decided_by",
            "kyc_decided_at",
            "created_at",
        ),
    ),
    (
        "accounts",
        "core.accounts",
        ("id", "customer_id", "number", "product", "currency", "balance", "status", "opened_at"),
    ),
    (
        "cards",
        "core.cards",
        (
            "id",
            "customer_id",
            "account_id",
            "type",
            "token",
            "last4",
            "brand",
            "credit_limit",
            "status",
            "created_at",
        ),
    ),
    (
        "loans",
        "core.loans",
        (
            "id",
            "customer_id",
            "product",
            "amount",
            "term_months",
            "rate_tea",
            "status",
            "days_past_due",
            "outstanding_balance",
            "ai_score",
            "ai_explanation",
            "decided_by",
            "decided_at",
            "disbursed_at",
            "created_at",
        ),
    ),
    (
        "installments",
        "core.loan_installments",
        ("loan_id", "number", "due_date", "amount", "paid_at"),
    ),
    (
        "transactions",
        "core.transactions",
        (
            "id",
            "account_id",
            "card_id",
            "type",
            "amount",
            "currency",
            "channel",
            "merchant",
            "city",
            "counterparty_account",
            "description",
            "created_at",
        ),
    ),
    (
        "complaints",
        "core.complaints",
        (
            "id",
            "customer_id",
            "subject",
            "body",
            "channel",
            "status",
            "ai_category",
            "ai_urgency",
            "ai_confidence",
            "ai_reason",
            "ai_suspicious",
            "requires_review",
            "final_category",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "due_at",
        ),
    ),
    (
        "kyc_documents",
        "core.kyc_documents",
        ("id", "customer_id", "blob_path", "extracted_json", "extraction_confidence", "created_at"),
    ),
    (
        "fraud_alerts",
        "ops.fraud_alerts",
        (
            "id",
            "transaction_id",
            "customer_id",
            "rule",
            "score",
            "source",
            "status",
            "details",
            "resolved_by",
            "resolved_at",
            "created_at",
        ),
    ),
    (
        "pipeline_runs",
        "ops.pipeline_runs",
        (
            "id",
            "flow_name",
            "status",
            "trigger",
            "started_at",
            "finished_at",
            "rows_in",
            "rows_ok",
            "rows_quarantined",
            "error",
        ),
    ),
    (
        "quality_checks",
        "ops.quality_checks",
        ("run_id", "check_name", "table_name", "passed", "failed_count"),
    ),
    (
        "quarantine",
        "ops.quarantine_records",
        ("run_id", "raw_id", "table_name", "reason", "payload", "created_at"),
    ),
    (
        "ai_interactions",
        "ops.ai_interactions",
        (
            "id",
            "use_case",
            "prompt_id",
            "prompt_version",
            "input_redacted",
            "output",
            "latency_ms",
            "tokens_in",
            "tokens_out",
            "confidence",
            "blocked_by_shields",
            "human_override",
            "provider",
            "created_at",
        ),
    ),
)

GOLD_COLUMNS: dict[str, tuple[str, ...]] = {
    "gold.dim_date": (
        "date_key",
        "date",
        "year",
        "quarter",
        "month",
        "month_name",
        "day_of_week",
        "is_weekend",
    ),
    "gold.dim_region": ("region_id", "name", "macro_region"),
    "gold.dim_product": ("product_id", "code", "name", "family"),
    "gold.dim_customer": (
        "customer_id",
        "segment",
        "region",
        "age_band",
        "kyc_status",
        "created_month",
        "total_balance",
        "active_loans",
    ),
    "gold.fact_portfolio_daily": (
        "loan_id",
        "date",
        "outstanding_balance",
        "days_past_due",
        "bucket",
        "region",
        "segment",
    ),
    "gold.fact_profitability_monthly": (
        "product",
        "segment",
        "region",
        "month",
        "interest_income",
        "fees",
        "funding_cost",
        "provisions",
        "margin",
    ),
}

TRUNCATE_SQL = """
TRUNCATE
  core.customers, core.accounts, core.cards, core.loans, core.loan_installments,
  core.transactions, core.complaints, core.kyc_documents,
  ops.audit_log, ops.fraud_alerts, ops.pipeline_runs, ops.quality_checks, ops.raw_ingest,
  ops.quarantine_records, ops.ai_interactions, ops.idempotency_keys,
  gold.dim_date, gold.dim_region, gold.dim_product, gold.dim_customer,
  gold.fact_portfolio_daily, gold.fact_profitability_monthly
RESTART IDENTITY CASCADE
"""


def _adapt(value: Any) -> Any:
    return Jsonb(value) if isinstance(value, dict) else value


def _copy(
    cur: psycopg.Cursor[Any], table: str, cols: Sequence[str], rows: Iterable[Sequence[Any]]
) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row([_adapt(v) for v in row])
            n += 1
    return n


def to_psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def load(ds: Dataset, url: str, *, reset: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    gold = build_gold(ds)
    with psycopg.connect(to_psycopg_url(url)) as conn, conn.cursor() as cur:
        if reset:
            cur.execute(TRUNCATE_SQL)
        else:
            cur.execute("SELECT count(*) FROM core.customers")
            row = cur.fetchone()
            if row and row[0] > 0:
                raise SystemExit("The database already has data. Use --reset to reload it.")
        for attr, table, cols in CORE_OPS_TABLES:
            records = getattr(ds, attr)
            counts[table] = _copy(cur, table, cols, ([r[c] for c in cols] for r in records))
        for table, rows in gold.items():
            counts[table] = _copy(cur, table, GOLD_COLUMNS[table], rows)
        cur.execute("ANALYZE")
    return counts
