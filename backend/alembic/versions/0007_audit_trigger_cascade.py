"""0007 audit_log trigger allows FK-cascade SET NULL

Revision ID: 0007_audit_log_trigger_cascade_allow
Revises: 0006_audit_log

Problem: the append-only trigger from 0006 also blocked UPDATEs fired by
`ON DELETE SET NULL` on the actor_user_id / impersonator_user_id /
entity_id / session_id FKs. That meant deleting any referenced row (even
soft-hiding an entity) failed with "audit_log is append-only".

Fix: preserve the append-only guarantee against DIRECT UPDATE/DELETE,
but allow cascade-driven UPDATEs by checking `pg_trigger_depth()`. When
the statement is the top-level SQL (depth 1), the trigger fires as before.
When Postgres is firing the trigger on behalf of a FK referential action,
depth > 1 and we let the row mutate silently.

The purge job still works because it bypasses via
`ALTER TABLE audit_log DISABLE TRIGGER USER` — that short-circuits this
function entirely.
"""
from alembic import op


revision = "0007_audit_trigger_cascade"
down_revision = "0006_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_no_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Allow UPDATEs/DELETEs that cascade via referential actions
            -- (pg_trigger_depth > 1 means this trigger is firing on behalf
            -- of another statement, typically a FK ON DELETE SET NULL).
            IF pg_trigger_depth() > 1 THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked';
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_no_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked';
        END;
        $$ LANGUAGE plpgsql;
    """)
