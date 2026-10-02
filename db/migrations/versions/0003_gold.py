"""gold schema (local stand-in for Azure SQL): dimensions, facts and NL2SQL views.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS gold")
    op.execute(
        """
        CREATE TABLE gold.dim_date (
            date_key    integer PRIMARY KEY,
            date        date NOT NULL UNIQUE,
            year        smallint NOT NULL,
            quarter     smallint NOT NULL,
            month       smallint NOT NULL,
            month_name  text NOT NULL,
            day_of_week smallint NOT NULL,
            is_weekend  boolean NOT NULL
        );

        CREATE TABLE gold.dim_region (
            region_id    smallint PRIMARY KEY,
            name         text NOT NULL UNIQUE,
            macro_region text NOT NULL
        );

        CREATE TABLE gold.dim_product (
            product_id smallint PRIMARY KEY,
            code       text NOT NULL UNIQUE,
            name       text NOT NULL,
            family     text NOT NULL CHECK (family IN ('PASIVO', 'ACTIVO'))
        );

        CREATE TABLE gold.dim_customer (
            customer_id   uuid PRIMARY KEY,
            segment       text NOT NULL,
            region        text NOT NULL,
            age_band      text NOT NULL,
            kyc_status    text NOT NULL,
            created_month date NOT NULL,
            total_balance numeric(16,2) NOT NULL DEFAULT 0,
            active_loans  integer NOT NULL DEFAULT 0
        );

        CREATE TABLE gold.dim_delinquency_bucket (
            bucket_id smallint PRIMARY KEY,
            name      text NOT NULL UNIQUE,
            min_days  integer NOT NULL,
            max_days  integer
        );
        INSERT INTO gold.dim_delinquency_bucket VALUES
            (1, 'Normal', 0, 8),
            (2, 'CPP', 9, 30),
            (3, 'Deficiente', 31, 60),
            (4, 'Dudoso', 61, 120),
            (5, 'Pérdida', 121, NULL);

        CREATE TABLE gold.fact_profitability_monthly (
            product         text NOT NULL,
            segment         text NOT NULL,
            region          text NOT NULL,
            month           date NOT NULL,
            interest_income numeric(16,2) NOT NULL DEFAULT 0,
            fees            numeric(16,2) NOT NULL DEFAULT 0,
            funding_cost    numeric(16,2) NOT NULL DEFAULT 0,
            provisions      numeric(16,2) NOT NULL DEFAULT 0,
            margin          numeric(16,2) NOT NULL DEFAULT 0,
            PRIMARY KEY (product, segment, region, month)
        );

        CREATE TABLE gold.fact_portfolio_daily (
            loan_id             uuid NOT NULL,
            date                date NOT NULL,
            outstanding_balance numeric(14,2) NOT NULL,
            days_past_due       integer NOT NULL,
            bucket              text NOT NULL,
            region              text NOT NULL,
            segment             text NOT NULL,
            PRIMARY KEY (loan_id, date)
        );
        CREATE INDEX ix_portfolio_date ON gold.fact_portfolio_daily (date);

        -- Views exposed to NL2SQL ("Pregúntale al banco"). Spanish column names on purpose.
        CREATE VIEW gold.v_rentabilidad AS
        SELECT month              AS mes,
               product            AS producto,
               segment            AS segmento,
               region             AS region,
               interest_income    AS ingresos_intereses,
               fees               AS comisiones,
               funding_cost       AS costo_fondeo,
               provisions         AS provisiones,
               margin             AS margen
        FROM gold.fact_profitability_monthly;

        CREATE VIEW gold.v_morosidad AS
        SELECT date                     AS fecha,
               region                   AS region,
               segment                  AS segmento,
               bucket                   AS bucket,
               count(*)                 AS prestamos,
               sum(outstanding_balance) AS saldo,
               sum(CASE WHEN days_past_due > 30 THEN outstanding_balance ELSE 0 END)
                                        AS saldo_vencido_30
        FROM gold.fact_portfolio_daily
        GROUP BY date, region, segment, bucket;

        CREATE VIEW gold.v_clientes_resumen AS
        SELECT region                          AS region,
               segment                         AS segmento,
               count(*)                        AS clientes,
               count(*) FILTER (WHERE kyc_status = 'APROBADO') AS clientes_activos,
               sum(total_balance)              AS saldo_total,
               round(avg(total_balance), 2)    AS saldo_promedio,
               sum(active_loans)               AS prestamos_activos
        FROM gold.dim_customer
        GROUP BY region, segment;
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS gold CASCADE")
