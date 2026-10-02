"""ops schema: audit, fraud alerts, pipelines, quality, AI interactions, idempotency.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    op.execute(
        """
        CREATE TABLE ops.audit_log (
            id             bigserial PRIMARY KEY,
            actor_id       text NOT NULL,
            actor_role     text,
            action         text NOT NULL,
            resource       text NOT NULL,
            resource_id    text,
            pii_accessed   boolean NOT NULL DEFAULT false,
            allowed        boolean NOT NULL DEFAULT true,
            ip             text,
            reason         text,
            correlation_id text,
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_audit_created ON ops.audit_log (created_at DESC);
        CREATE INDEX ix_audit_denied ON ops.audit_log (created_at DESC) WHERE NOT allowed;

        CREATE TABLE ops.fraud_alerts (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id uuid REFERENCES core.transactions (id),
            customer_id    uuid REFERENCES core.customers (id),
            rule           text NOT NULL,
            score          numeric(5,2) NOT NULL,
            source         text NOT NULL CHECK (source IN ('RULES', 'FABRIC')),
            status         text NOT NULL DEFAULT 'ABIERTA'
                           CHECK (status IN ('ABIERTA', 'CONFIRMADA', 'DESCARTADA')),
            details        jsonb,
            resolved_by    text,
            resolved_at    timestamptz,
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_fraud_status ON ops.fraud_alerts (status, created_at DESC);

        CREATE TABLE ops.pipeline_runs (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            flow_name        text NOT NULL,
            status           text NOT NULL
                             CHECK (status IN ('EN_CURSO', 'EXITOSO', 'CON_ALERTAS', 'FALLIDO')),
            trigger          text NOT NULL DEFAULT 'PROGRAMADO',
            started_at       timestamptz NOT NULL DEFAULT now(),
            finished_at      timestamptz,
            rows_in          integer NOT NULL DEFAULT 0,
            rows_ok          integer NOT NULL DEFAULT 0,
            rows_quarantined integer NOT NULL DEFAULT 0,
            error            text
        );
        CREATE INDEX ix_runs_started ON ops.pipeline_runs (started_at DESC);

        CREATE TABLE ops.quality_checks (
            id           bigserial PRIMARY KEY,
            run_id       uuid NOT NULL REFERENCES ops.pipeline_runs (id) ON DELETE CASCADE,
            check_name   text NOT NULL,
            table_name   text NOT NULL,
            passed       boolean NOT NULL,
            failed_count integer NOT NULL DEFAULT 0
        );
        CREATE INDEX ix_checks_run ON ops.quality_checks (run_id);

        CREATE TABLE ops.raw_ingest (
            id           bigserial PRIMARY KEY,
            source       text NOT NULL,
            payload      jsonb NOT NULL,
            received_at  timestamptz NOT NULL DEFAULT now(),
            processed_at timestamptz
        );
        CREATE INDEX ix_raw_pending ON ops.raw_ingest (id) WHERE processed_at IS NULL;

        CREATE TABLE ops.quarantine_records (
            id         bigserial PRIMARY KEY,
            run_id     uuid REFERENCES ops.pipeline_runs (id) ON DELETE SET NULL,
            raw_id     bigint REFERENCES ops.raw_ingest (id) ON DELETE SET NULL,
            table_name text NOT NULL,
            reason     text NOT NULL,
            payload    jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE ops.ai_interactions (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            use_case           text NOT NULL,
            prompt_id          text NOT NULL,
            prompt_version     text NOT NULL,
            input_redacted     text,
            output             jsonb,
            latency_ms         integer,
            tokens_in          integer,
            tokens_out         integer,
            confidence         numeric(4,3),
            blocked_by_shields boolean NOT NULL DEFAULT false,
            human_override     boolean,
            provider           text,
            created_at         timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_ai_usecase ON ops.ai_interactions (use_case, created_at DESC);

        CREATE TABLE ops.idempotency_keys (
            customer_id   uuid NOT NULL,
            key           text NOT NULL,
            request_hash  text NOT NULL,
            status_code   integer NOT NULL,
            response_json jsonb NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, key)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS ops CASCADE")
