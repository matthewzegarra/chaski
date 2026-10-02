"""Least-privilege grants for chaski_app and chaski_readonly (only if the roles exist).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chaski_app') THEN
                GRANT USAGE ON SCHEMA core, ops, gold TO chaski_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, ops
                    TO chaski_app;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core, ops TO chaski_app;
                GRANT SELECT ON ALL TABLES IN SCHEMA gold TO chaski_app;
                ALTER DEFAULT PRIVILEGES IN SCHEMA core, ops
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO chaski_app;
                ALTER DEFAULT PRIVILEGES IN SCHEMA core, ops
                    GRANT USAGE, SELECT ON SEQUENCES TO chaski_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chaski_readonly') THEN
                -- NL2SQL can only read the three allow-listed views, nothing else.
                GRANT USAGE ON SCHEMA gold TO chaski_readonly;
                GRANT SELECT ON gold.v_rentabilidad, gold.v_morosidad, gold.v_clientes_resumen
                    TO chaski_readonly;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chaski_app') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA core, ops, gold FROM chaski_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chaski_readonly') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA gold FROM chaski_readonly;
            END IF;
        END
        $$;
        """
    )
