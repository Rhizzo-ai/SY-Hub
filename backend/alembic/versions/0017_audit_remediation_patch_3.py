"""0017 Patch #3 — End-of-Foundation audit remediation

Revision ID: 0017_audit_remediation_patch_3
Revises: 0016_system_config_seed

Rollup for Patch #3:
  - Revokes and deletes 6 orphan permission rows
    (cost_codes.{create,edit,delete}, system_config.edit,
     notifications.{view,edit}).
  - Retires cost_code SER-10 and points its replaced_by_code_id at SER-06
    (same section; SER-06 has broader scope).
  - Adds `Seed_Run` value to the `audit_action` enum.

Historical audit rows are NOT backfilled — we honour the append-only
contract from Prompt 1.4 strictly. Going forward, the two lifespan-time
seed modules (`seed_rbac.py`, `seed_system_config.py`) emit
`action='Seed_Run'` instead of `action='Create'` + `metadata.kind='seed_run'`.
The three historical alembic migrations (0012, 0013, 0014) now also
emit `Seed_Run` on fresh-DB runs, each adding an idempotent
`ALTER TYPE ADD VALUE IF NOT EXISTS` inside an autocommit block BEFORE
their audit emission.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "0017_audit_remediation_patch_3"
down_revision = "0016_system_config_seed"
branch_labels = None
depends_on = None


ORPHAN_CODES = [
    "cost_codes.create",
    "cost_codes.edit",
    "cost_codes.delete",
    "system_config.edit",
    "notifications.view",
    "notifications.edit",
]


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------
    # Item 5: extend audit_action enum with 'Seed_Run'.
    # Postgres disallows ALTER TYPE ADD VALUE + subsequent use in the
    # same transaction — use an autocommit block for the DDL.
    # ---------------------------------------------------------
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Seed_Run'"
        )

    # ---------------------------------------------------------
    # Items 1-3: revoke grants, then delete orphan permission rows.
    # No routes reference these codes; grants are inert but present
    # via super_admin → ALL and director → ALL-minus-exclusions.
    # ---------------------------------------------------------
    perm_ids = [
        row[0] for row in bind.execute(
            text("SELECT id FROM permissions WHERE code = ANY(:codes)"),
            {"codes": ORPHAN_CODES},
        ).all()
    ]
    if perm_ids:
        bind.execute(
            text("DELETE FROM role_permissions WHERE permission_id = ANY(:ids)"),
            {"ids": perm_ids},
        )
        bind.execute(
            text("DELETE FROM permissions WHERE id = ANY(:ids)"),
            {"ids": perm_ids},
        )

    # ---------------------------------------------------------
    # Item 4: retire SER-10, redirect to SER-06.
    # Same section, identical flags. SER-06 has broader scope
    # ("Lifts & access") vs SER-10's narrower "Lift installation".
    # ---------------------------------------------------------
    ser06 = bind.execute(
        text("SELECT id FROM cost_codes WHERE code = 'SER-06'")
    ).first()
    ser10 = bind.execute(
        text("SELECT id, status FROM cost_codes WHERE code = 'SER-10'")
    ).first()
    if ser06 and ser10 and ser10[1] != "Retired":
        bind.execute(text("""
            UPDATE cost_codes
               SET status = 'Retired',
                   retired_at = now(),
                   retired_reason = :reason,
                   replaced_by_code_id = :ser06_id
             WHERE id = :ser10_id
        """), {
            "reason": "Patch #3: duplicate of SER-06 "
                     "(Lifts & access). SER-06 has broader scope.",
            "ser06_id": str(ser06[0]),
            "ser10_id": str(ser10[0]),
        })

    # Summary audit row for Patch #3 (uses the new Seed_Run action).
    bind.execute(text("""
        INSERT INTO audit_log
            (action, resource_type, resource_id, actor_user_id,
             metadata_json, field_changes)
        VALUES
            ('Seed_Run', 'migration', gen_random_uuid(), NULL,
             CAST(:meta AS jsonb), '[]'::jsonb)
    """), {"meta":
           '{"kind":"patch_3_run",'
           f'"orphan_perms_deleted":{len(perm_ids)},'
           '"retired_cost_codes":["SER-10"],'
           '"audit_enum_added":["Seed_Run"]}'})


def downgrade() -> None:
    """Irreversible in practice.

    - `ALTER TYPE REMOVE VALUE` is not supported by Postgres.
    - Restoring deleted permission rows with stable IDs would break any
      audit-log references to those IDs (none currently, but the
      contract forbids rewriting history).
    - SER-10 retirement is reversible (set status='Active', clear
      retired_* + replaced_by_code_id).

    We restore only the reversible slice; the enum value stays and the
    orphan permission rows do not reappear. If full reversal is needed,
    clone from the pre-patch DB snapshot.
    """
    bind = op.get_bind()
    ser10 = bind.execute(
        text("SELECT id FROM cost_codes WHERE code = 'SER-10'")
    ).first()
    if ser10:
        bind.execute(text("""
            UPDATE cost_codes
               SET status = 'Active',
                   retired_at = NULL,
                   retired_reason = NULL,
                   replaced_by_code_id = NULL
             WHERE id = :ser10_id
        """), {"ser10_id": str(ser10[0])})
