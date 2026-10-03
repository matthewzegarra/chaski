-- CHASKI analytical data warehouse (Azure SQL, schema dw). Idempotent: run by every
-- pipeline execution before loading. Star schema: dimensions + two facts, SCD2 customers,
-- Spanish-named views for Power BI / NL2SQL and a ROLLUP example (totals by product/region).
IF SCHEMA_ID('dw') IS NULL EXEC('CREATE SCHEMA dw');
GO
IF OBJECT_ID('dw.dim_date') IS NULL
CREATE TABLE dw.dim_date (
    date_key     int          NOT NULL PRIMARY KEY,
    [date]       date         NOT NULL UNIQUE,
    [year]       smallint     NOT NULL,
    [quarter]    smallint     NOT NULL,
    [month]      smallint     NOT NULL,
    month_name   nvarchar(20) NOT NULL,
    day_of_week  smallint     NOT NULL,
    is_weekend   bit          NOT NULL
);
GO
IF OBJECT_ID('dw.dim_region') IS NULL
CREATE TABLE dw.dim_region (
    region_id    smallint     NOT NULL PRIMARY KEY,
    name         nvarchar(40) NOT NULL UNIQUE,
    macro_region nvarchar(20) NOT NULL
);
GO
IF OBJECT_ID('dw.dim_product') IS NULL
CREATE TABLE dw.dim_product (
    product_id smallint     NOT NULL PRIMARY KEY,
    code       nvarchar(30) NOT NULL UNIQUE,
    name       nvarchar(60) NOT NULL,
    family     nvarchar(10) NOT NULL
);
GO
IF OBJECT_ID('dw.dim_delinquency_bucket') IS NULL
CREATE TABLE dw.dim_delinquency_bucket (
    bucket_id smallint     NOT NULL PRIMARY KEY,
    name      nvarchar(20) NOT NULL UNIQUE,
    min_days  int          NOT NULL,
    max_days  int          NULL
);
GO
-- SCD type 2: a change of segment or region closes the current row and opens a new one.
IF OBJECT_ID('dw.dim_customer') IS NULL
CREATE TABLE dw.dim_customer (
    customer_key  int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    customer_id   uniqueidentifier  NOT NULL,
    segment       nvarchar(20)      NOT NULL,
    region        nvarchar(40)      NOT NULL,
    age_band      nvarchar(20)      NOT NULL,
    kyc_status    nvarchar(20)      NOT NULL,
    created_month date              NOT NULL,
    total_balance decimal(16,2)     NOT NULL,
    active_loans  int               NOT NULL,
    valid_from    datetime2         NOT NULL,
    valid_to      datetime2         NULL,
    is_current    bit               NOT NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_dim_customer_current')
CREATE UNIQUE INDEX ux_dim_customer_current ON dw.dim_customer (customer_id) WHERE is_current = 1;
GO
IF OBJECT_ID('dw.fact_profitability_monthly') IS NULL
CREATE TABLE dw.fact_profitability_monthly (
    product         nvarchar(30)  NOT NULL,
    segment         nvarchar(20)  NOT NULL,
    region          nvarchar(40)  NOT NULL,
    [month]         date          NOT NULL,
    interest_income decimal(16,2) NOT NULL,
    fees            decimal(16,2) NOT NULL,
    funding_cost    decimal(16,2) NOT NULL,
    provisions      decimal(16,2) NOT NULL,
    margin          decimal(16,2) NOT NULL,
    CONSTRAINT pk_fact_profitability PRIMARY KEY (product, segment, region, [month])
);
GO
IF OBJECT_ID('dw.fact_portfolio_daily') IS NULL
CREATE TABLE dw.fact_portfolio_daily (
    loan_id             uniqueidentifier NOT NULL,
    [date]              date             NOT NULL,
    outstanding_balance decimal(14,2)    NOT NULL,
    days_past_due       int              NOT NULL,
    bucket              nvarchar(20)     NOT NULL,
    region              nvarchar(40)     NOT NULL,
    segment             nvarchar(20)     NOT NULL,
    CONSTRAINT pk_fact_portfolio PRIMARY KEY (loan_id, [date])
);
GO
CREATE OR ALTER VIEW dw.v_rentabilidad AS
SELECT [month] AS mes, product AS producto, segment AS segmento, region,
       interest_income AS ingresos_intereses, fees AS comisiones, funding_cost AS costo_fondeo,
       provisions AS provisiones, margin AS margen
FROM dw.fact_profitability_monthly;
GO
CREATE OR ALTER VIEW dw.v_morosidad AS
SELECT [date] AS fecha, region, segment AS segmento, bucket,
       count(*) AS prestamos, sum(outstanding_balance) AS saldo,
       sum(CASE WHEN days_past_due > 30 THEN outstanding_balance ELSE 0 END) AS saldo_vencido_30
FROM dw.fact_portfolio_daily
GROUP BY [date], region, segment, bucket;
GO
CREATE OR ALTER VIEW dw.v_clientes_resumen AS
SELECT region, segment AS segmento, count(*) AS clientes,
       sum(CASE WHEN kyc_status = 'APROBADO' THEN 1 ELSE 0 END) AS clientes_activos,
       sum(total_balance) AS saldo_total, round(avg(total_balance), 2) AS saldo_promedio,
       sum(active_loans) AS prestamos_activos
FROM dw.dim_customer
WHERE is_current = 1
GROUP BY region, segment;
GO
-- ROLLUP: margin per product and region plus subtotals per product and the grand total.
CREATE OR ALTER VIEW dw.v_rentabilidad_rollup AS
SELECT coalesce(product, '(Total)') AS producto,
       coalesce(region, '(Total)')  AS region,
       sum(margin)                  AS margen,
       GROUPING(product)            AS es_total_producto,
       GROUPING(region)             AS es_total_region
FROM dw.fact_profitability_monthly
GROUP BY ROLLUP (product, region);
