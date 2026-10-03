"""Table-level quality checks of the guide (section 7.2), on top of the per-record checks of
the raw ingestion (services/pipeline_sim.py). Each check returns how many rows fail; the
results are stored in ops.quality_checks for the run.

`volumen_diario` is informative: it never blocks the run (synthetic days can be quiet).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# 13-19 consecutive digits ([0-9]{13,19}) = possible card number (PAN) in free text.


@dataclass(frozen=True)
class Check:
    name: str
    table: str
    sql: str
    blocking: bool = True


CHECKS: tuple[Check, ...] = (
    Check(
        "claves_unicas_no_nulas",
        "core.accounts",
        "SELECT count(*) - count(DISTINCT number) + count(*) FILTER (WHERE number IS NULL)"
        " FROM core.accounts",
    ),
    Check(
        "saldo_no_negativo", "core.accounts", "SELECT count(*) FROM core.accounts WHERE balance < 0"
    ),
    Check(
        "dias_atraso_no_negativos",
        "core.loans",
        "SELECT count(*) FROM core.loans WHERE days_past_due < 0",
    ),
    Check(
        "bucket_consistente",
        "gold.fact_portfolio_daily",
        """
        SELECT count(*) FROM gold.fact_portfolio_daily f
        JOIN gold.dim_delinquency_bucket b ON b.name = f.bucket
        WHERE f.days_past_due < b.min_days
           OR (b.max_days IS NOT NULL AND f.days_past_due > b.max_days)
        """,
    ),
    Check(
        "integridad_tarjeta_cuenta",
        "core.cards",
        "SELECT count(*) FROM core.cards c LEFT JOIN core.accounts a ON a.id = c.account_id"
        " WHERE c.account_id IS NOT NULL AND a.id IS NULL",
    ),
    Check(
        "sin_pan",
        "core.transactions",
        """
        SELECT count(*) FROM core.transactions
        WHERE coalesce(merchant, '') ~ '[0-9]{13,19}' OR coalesce(description, '') ~ '[0-9]{13,19}'
           OR coalesce(city, '') ~ '[0-9]{13,19}'
        """,
    ),
    Check(
        "sin_pan",
        "core.complaints",
        "SELECT count(*) FROM core.complaints"
        " WHERE subject ~ '[0-9]{13,19}' OR body ~ '[0-9]{13,19}'",
    ),
    Check(
        "volumen_diario",
        "core.transactions",
        """
        WITH daily AS (
            SELECT created_at::date AS d, count(*) AS n FROM core.transactions
            WHERE created_at >= now() - interval '31 days' GROUP BY 1
        ), base AS (SELECT avg(n) AS avg_n FROM daily WHERE d < current_date)
        SELECT CASE WHEN base.avg_n IS NULL THEN 0
                    WHEN coalesce((SELECT n FROM daily WHERE d = current_date - 1), 0)
                         NOT BETWEEN base.avg_n * 0.5 AND base.avg_n * 1.5 THEN 1 ELSE 0 END
        FROM base
        """,
        blocking=False,
    ),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    table: str
    failed: int
    blocking: bool

    @property
    def passed(self) -> bool:
        return self.failed == 0


def run_checks(db: Session) -> list[CheckResult]:
    return [
        CheckResult(c.name, c.table, int(db.execute(text(c.sql)).scalar() or 0), c.blocking)
        for c in CHECKS
    ]
