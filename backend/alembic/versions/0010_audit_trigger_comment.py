"""0010 audit_log_no_modify defense-in-depth comment

Revision ID: 0010_audit_trigger_comment
Revises: 0009_retro_fks_to_proj

Audit Remediation Patch #2, finding M1 (2026-04-23).

Embeds a safety-boundary comment directly into the `audit_log_no_modify`
plpgsql function so future readers (DBAs, auditors, contributors) see
the carve-out's exact assumptions in `\\df+ audit_log_no_modify`.

No behavioural change. The function body still:
  - Allows UPDATE/DELETE at pg_trigger_depth() > 1 (FK referential actions)
  - Raises on direct user UPDATE/DELETE at depth 1
"""
from alembic import op


revision = "0010_audit_trigger_comment"
down_revision = "0009_retro_fks_to_proj"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_no_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            -- ---------------------------------------------------------------
            -- AUDIT LOG APPEND-ONLY GUARD — safety boundary
            -- ---------------------------------------------------------------
            -- The pg_trigger_depth() > 1 carve-out admits ONLY mutations
            -- that originate from FK referential actions (ON DELETE SET
            -- NULL on audit_log.actor_user_id, impersonator_user_id,
            -- entity_id, session_id, project_id).
            --
            -- Postgres increments trigger_depth only when a trigger calls
            -- another trigger via referential cascade. User-issued
            -- UPDATE/DELETE runs at depth 1 and the EXCEPTION below fires.
            --
            -- DO NOT add additional triggers on audit_log that would mutate
            -- other rows of audit_log — that would also run at depth > 1
            -- and silently bypass this guard. If such a trigger is needed,
            -- replace this guard with logic that inspects TG_OP and the
            -- referencing FK explicitly (e.g. via the trigger arguments).
            --
            -- Retention purges bypass this guard via
            -- `ALTER TABLE audit_log DISABLE TRIGGER USER` inside a bounded
            -- transaction (see app/services/audit_retention.py).
            -- ---------------------------------------------------------------
            IF pg_trigger_depth() > 1 THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked';
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Restore the un-commented version from 0007.
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_no_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked';
        END;
        $$ LANGUAGE plpgsql;
    """)
