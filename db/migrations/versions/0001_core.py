"""core schema: customers, accounts, cards, loans, transactions, complaints, KYC.

Revision ID: 0001
Revises:
Create Date: 2026-10-01
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute(
        """
        CREATE TABLE core.customers (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_type   text NOT NULL DEFAULT 'DNI'
                            CHECK (document_type IN ('DNI', 'CE', 'PASAPORTE')),
            document_number text NOT NULL,
            first_name      text NOT NULL,
            last_name       text NOT NULL,
            email           text NOT NULL,
            phone           text,
            birth_date      date,
            segment         text NOT NULL DEFAULT 'MASIVO'
                            CHECK (segment IN ('MASIVO', 'PREFERENTE', 'PYME')),
            region          text NOT NULL,
            kyc_status      text NOT NULL DEFAULT 'PENDIENTE'
                            CHECK (kyc_status IN ('PENDIENTE', 'APROBADO', 'RECHAZADO')),
            risk_level      text NOT NULL DEFAULT 'BAJO'
                            CHECK (risk_level IN ('BAJO', 'MEDIO', 'ALTO')),
            monthly_income  numeric(14,2),
            kyc_decided_by  text,
            kyc_decided_at  timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (document_type, document_number)
        );
        CREATE INDEX ix_customers_kyc_status ON core.customers (kyc_status);
        CREATE INDEX ix_customers_region ON core.customers (region);
        CREATE INDEX ix_customers_created_at ON core.customers (created_at);

        CREATE TABLE core.accounts (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id uuid NOT NULL REFERENCES core.customers (id),
            number      text NOT NULL UNIQUE,
            product     text NOT NULL CHECK (product IN ('AHORRO_SOLES', 'AHORRO_DOLARES')),
            currency    text NOT NULL CHECK (currency IN ('PEN', 'USD')),
            balance     numeric(14,2) NOT NULL DEFAULT 0 CHECK (balance >= 0),
            status      text NOT NULL DEFAULT 'ACTIVA'
                        CHECK (status IN ('ACTIVA', 'BLOQUEADA', 'CERRADA')),
            opened_at   timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_accounts_customer ON core.accounts (customer_id);

        CREATE TABLE core.cards (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id  uuid NOT NULL REFERENCES core.customers (id),
            account_id   uuid REFERENCES core.accounts (id),
            type         text NOT NULL CHECK (type IN ('DEBITO', 'CREDITO')),
            token        text NOT NULL UNIQUE,
            last4        char(4) NOT NULL CHECK (last4 ~ '^[0-9]{4}$'),
            brand        text NOT NULL CHECK (brand IN ('VISA', 'MASTERCARD', 'AMEX')),
            credit_limit numeric(14,2),
            status       text NOT NULL DEFAULT 'ACTIVA' CHECK (status IN ('ACTIVA', 'BLOQUEADA')),
            created_at   timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_cards_customer ON core.cards (customer_id);

        CREATE TABLE core.loans (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id         uuid NOT NULL REFERENCES core.customers (id),
            product             text NOT NULL DEFAULT 'CONSUMO' CHECK (product IN ('CONSUMO')),
            amount              numeric(14,2) NOT NULL CHECK (amount > 0),
            term_months         integer NOT NULL CHECK (term_months BETWEEN 1 AND 120),
            rate_tea            numeric(6,4) NOT NULL,
            status              text NOT NULL DEFAULT 'SOLICITADO'
                                CHECK (status IN ('SOLICITADO', 'APROBADO', 'RECHAZADO',
                                                  'DESEMBOLSADO', 'CANCELADO')),
            days_past_due       integer NOT NULL DEFAULT 0 CHECK (days_past_due >= 0),
            outstanding_balance numeric(14,2) NOT NULL DEFAULT 0,
            ai_score            integer CHECK (ai_score BETWEEN 0 AND 1000),
            ai_explanation      text,
            decided_by          text,
            decided_at          timestamptz,
            disbursed_at        timestamptz,
            created_at          timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_loans_customer ON core.loans (customer_id);
        CREATE INDEX ix_loans_status ON core.loans (status);

        CREATE TABLE core.loan_installments (
            loan_id  uuid NOT NULL REFERENCES core.loans (id) ON DELETE CASCADE,
            number   integer NOT NULL,
            due_date date NOT NULL,
            amount   numeric(14,2) NOT NULL,
            paid_at  timestamptz,
            PRIMARY KEY (loan_id, number)
        );

        CREATE TABLE core.transactions (
            id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id           uuid NOT NULL REFERENCES core.accounts (id),
            card_id              uuid REFERENCES core.cards (id),
            type                 text NOT NULL
                                 CHECK (type IN ('DEPOSITO', 'RETIRO', 'TRANSFERENCIA_IN',
                                                 'TRANSFERENCIA_OUT', 'PAGO_TARJETA',
                                                 'PAGO_SERVICIO', 'COMISION', 'INTERES')),
            amount               numeric(14,2) NOT NULL CHECK (amount > 0),
            currency             text NOT NULL CHECK (currency IN ('PEN', 'USD')),
            channel              text NOT NULL CHECK (channel IN ('APP', 'WEB', 'POS', 'ATM')),
            merchant             text,
            city                 text,
            counterparty_account text,
            description          text,
            created_at           timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_tx_account_created ON core.transactions (account_id, created_at DESC);
        CREATE INDEX ix_tx_created ON core.transactions (created_at);
        CREATE INDEX ix_tx_card ON core.transactions (card_id) WHERE card_id IS NOT NULL;

        CREATE TABLE core.complaints (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id     uuid NOT NULL REFERENCES core.customers (id),
            subject         text NOT NULL,
            body            text NOT NULL,
            channel         text NOT NULL DEFAULT 'APP'
                            CHECK (channel IN ('APP', 'WEB', 'AGENCIA', 'TELEFONO')),
            status          text NOT NULL DEFAULT 'NUEVA'
                            CHECK (status IN ('NUEVA', 'EN_REVISION', 'RESUELTA')),
            ai_category     text,
            ai_urgency      text CHECK (ai_urgency IN ('ALTA', 'MEDIA', 'BAJA')),
            ai_confidence   numeric(4,3),
            ai_reason       text,
            ai_suspicious   boolean NOT NULL DEFAULT false,
            requires_review boolean NOT NULL DEFAULT true,
            final_category  text,
            reviewed_by     text,
            reviewed_at     timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now(),
            due_at          timestamptz NOT NULL
        );
        CREATE INDEX ix_complaints_customer ON core.complaints (customer_id);
        CREATE INDEX ix_complaints_status ON core.complaints (status, due_at);

        CREATE TABLE core.kyc_documents (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id           uuid NOT NULL REFERENCES core.customers (id),
            blob_path             text NOT NULL,
            extracted_json        jsonb,
            extraction_confidence numeric(4,3),
            created_at            timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_kyc_customer ON core.kyc_documents (customer_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")
