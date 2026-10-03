"""Loads the gold layer into the Azure SQL data warehouse (schema dw).

Idempotent: the DDL is re-applied (IF NOT EXISTS / CREATE OR ALTER) and every table is
loaded through a staging temp table and a MERGE, so a re-run never duplicates rows.
dim_customer is SCD type 2 (segment/region changes keep history).

Authentication: Entra ID token of the job's managed identity (no SQL passwords). The
identity is a database user created FROM EXTERNAL PROVIDER (infra/scripts/deploy.ps1
-Stage dwusers) with db_ddladmin, db_datareader and db_datawriter.

Env: DW_SERVER (e.g. sql-chaski-xxxx.database.windows.net), DW_DATABASE.
"""

from __future__ import annotations

import os
import struct
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

SQL_COPT_SS_ACCESS_TOKEN = 1256


@dataclass(frozen=True)
class Table:
    name: str
    source: str  # PostgreSQL query over the gold schema
    columns: tuple[str, ...]
    keys: tuple[str, ...]


TABLES: tuple[Table, ...] = (
    Table(
        "dim_date",
        "SELECT date_key, date, year, quarter, month, month_name, day_of_week, is_weekend"
        " FROM gold.dim_date",
        ("date_key", "date", "year", "quarter", "month", "month_name", "day_of_week", "is_weekend"),
        ("date_key",),
    ),
    Table(
        "dim_region",
        "SELECT region_id, name, macro_region FROM gold.dim_region",
        ("region_id", "name", "macro_region"),
        ("region_id",),
    ),
    Table(
        "dim_product",
        "SELECT product_id, code, name, family FROM gold.dim_product",
        ("product_id", "code", "name", "family"),
        ("product_id",),
    ),
    Table(
        "dim_delinquency_bucket",
        "SELECT bucket_id, name, min_days, max_days FROM gold.dim_delinquency_bucket",
        ("bucket_id", "name", "min_days", "max_days"),
        ("bucket_id",),
    ),
    Table(
        "fact_profitability_monthly",
        "SELECT product, segment, region, month, interest_income, fees, funding_cost,"
        " provisions, margin FROM gold.fact_profitability_monthly",
        (
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
        ("product", "segment", "region", "month"),
    ),
    Table(
        "fact_portfolio_daily",
        "SELECT loan_id, date, outstanding_balance, days_past_due, bucket, region, segment"
        " FROM gold.fact_portfolio_daily",
        ("loan_id", "date", "outstanding_balance", "days_past_due", "bucket", "region", "segment"),
        ("loan_id", "date"),
    ),
)

CUSTOMER_SOURCE = (
    "SELECT customer_id, segment, region, age_band, kyc_status, created_month, total_balance,"
    " active_loans FROM gold.dim_customer"
)
CUSTOMER_COLUMNS = (
    "customer_id", "segment", "region", "age_band", "kyc_status", "created_month",
    "total_balance", "active_loans",
)  # fmt: skip


def _q(name: str) -> str:
    return f"[{name}]"


# SQL below is built only from the constant table specs of this module (never from data),
# so the string construction flagged by S608 is safe.
def merge_sql(table: Table) -> str:
    on = " AND ".join(f"t.{_q(k)} = s.{_q(k)}" for k in table.keys)
    non_keys = [c for c in table.columns if c not in table.keys]
    update = ", ".join(f"t.{_q(c)} = s.{_q(c)}" for c in non_keys)
    cols = ", ".join(_q(c) for c in table.columns)
    vals = ", ".join(f"s.{_q(c)}" for c in table.columns)
    matched = f" WHEN MATCHED THEN UPDATE SET {update}" if non_keys else ""
    return (
        f"MERGE dw.{table.name} AS t USING #stage AS s ON {on}{matched}"  # noqa: S608
        f" WHEN NOT MATCHED BY TARGET THEN INSERT ({cols}) VALUES ({vals});"
    )


SCD2_SQL = (
    # Close the current version when a type-2 attribute changed.
    "UPDATE d SET valid_to = SYSUTCDATETIME(), is_current = 0 FROM dw.dim_customer d"
    " JOIN #stage s ON s.customer_id = d.customer_id"
    " WHERE d.is_current = 1 AND (d.segment <> s.segment OR d.region <> s.region);"
    # Type-1 attributes are overwritten on the current version.
    " UPDATE d SET kyc_status = s.kyc_status, age_band = s.age_band,"
    " total_balance = s.total_balance, active_loans = s.active_loans"
    " FROM dw.dim_customer d JOIN #stage s ON s.customer_id = d.customer_id WHERE d.is_current = 1;"
    # New customers and new versions.
    " INSERT INTO dw.dim_customer (customer_id, segment, region, age_band, kyc_status,"
    " created_month, total_balance, active_loans, valid_from, valid_to, is_current)"
    " SELECT s.customer_id, s.segment, s.region, s.age_band, s.kyc_status, s.created_month,"
    " s.total_balance, s.active_loans, SYSUTCDATETIME(), NULL, 1 FROM #stage s"
    " WHERE NOT EXISTS (SELECT 1 FROM dw.dim_customer d"
    " WHERE d.customer_id = s.customer_id AND d.is_current = 1);"
)


def ddl_batches() -> list[str]:
    script = files("core_api.etl").joinpath("dw_ddl.sql").read_text(encoding="utf-8")
    batches: list[str] = []
    current: list[str] = []
    for line in script.splitlines():
        if line.strip().upper() == "GO":
            batches.append("\n".join(current))
            current = []
        else:
            current.append(line)
    batches.append("\n".join(current))

    def has_code(batch: str) -> bool:
        return any(ln.strip() and not ln.strip().startswith("--") for ln in batch.splitlines())

    return [b for b in batches if has_code(b)]


def _value(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, Decimal):
        return v
    return v


def connect(server: str, database: str) -> Any:
    """pyodbc connection with the managed identity's Entra token. Retries while the
    serverless database resumes from auto-pause."""
    import pyodbc
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    raw = token.encode("utf-16-le")
    attrs = {SQL_COPT_SS_ACCESS_TOKEN: struct.pack(f"<I{len(raw)}s", len(raw), raw)}
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{server},1433;Database={database};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60"
    )
    for attempt in range(5):
        try:
            return pyodbc.connect(conn_str, attrs_before=attrs)
        except pyodbc.Error:
            if attempt == 4:
                raise
            time.sleep(20)  # serverless resume


def _input_sizes(cur: Any, columns: tuple[str, ...]) -> list[Any]:
    """Exact parameter types read from #stage. pyodbc cannot describe parameters of a temp
    table, so fast_executemany would otherwise infer them from the first row and fail on a
    later, longer value ('Converting decimal loses precision' / right truncation)."""
    import pyodbc

    cols = ", ".join(_q(c) for c in columns)
    cur.execute(f"SELECT TOP 0 {cols} FROM #stage")  # noqa: S608
    sizes: list[Any] = []
    for _name, type_code, _display, internal, precision, scale, _null in cur.description:
        if type_code is Decimal:
            sizes.append((pyodbc.SQL_DECIMAL, precision, scale))
        elif type_code is str:
            sizes.append((pyodbc.SQL_WVARCHAR, internal or 0, 0))
        else:
            sizes.append(None)
    cur.fetchall()
    return sizes


def _load(cur: Any, columns: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    cols = ", ".join(_q(c) for c in columns)
    sizes = _input_sizes(cur, columns)
    cur.fast_executemany = True
    cur.setinputsizes(sizes)
    cur.executemany(f"INSERT INTO #stage ({cols}) VALUES ({placeholders})", rows)  # noqa: S608


def load(db: Session, conn: Any) -> dict[str, int]:
    """Applies the DDL and merges every gold table. Returns rows loaded per table."""
    cur = conn.cursor()
    for batch in ddl_batches():
        cur.execute(batch)
    conn.commit()

    counts: dict[str, int] = {}
    for table in TABLES:
        rows = [tuple(_value(v) for v in r) for r in db.execute(text(table.source))]
        cols = ", ".join(_q(c) for c in table.columns)
        cur.execute(f"SELECT TOP 0 {cols} INTO #stage FROM dw.{table.name}")  # noqa: S608
        if rows:
            _load(cur, table.columns, rows)
        cur.execute(merge_sql(table))
        cur.execute("DROP TABLE #stage")
        conn.commit()
        counts[table.name] = len(rows)

    rows = [tuple(_value(v) for v in r) for r in db.execute(text(CUSTOMER_SOURCE))]
    cols = ", ".join(_q(c) for c in CUSTOMER_COLUMNS)
    cur.execute(f"SELECT TOP 0 {cols} INTO #stage FROM dw.dim_customer")  # noqa: S608
    if rows:
        _load(cur, CUSTOMER_COLUMNS, rows)
    cur.execute(SCD2_SQL)
    cur.execute("DROP TABLE #stage")
    conn.commit()
    counts["dim_customer"] = len(rows)
    return counts


def configured() -> tuple[str, str] | None:
    server, database = os.environ.get("DW_SERVER"), os.environ.get("DW_DATABASE")
    return (server, database) if server and database else None
