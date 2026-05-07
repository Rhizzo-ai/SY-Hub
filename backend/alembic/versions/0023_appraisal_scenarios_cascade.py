"""appraisal_scenarios scenario_appraisal_id FK: ON DELETE RESTRICT -> CASCADE.

Chat 15 — Pre-2.4 cleanup, narrow FK fix only.

Migration 0022 created two FKs from `appraisal_scenarios` to `appraisals`,
both auto-named by Postgres (raw `CREATE TABLE` SQL, not `op.create_foreign_key`):

    appraisal_scenarios_scenario_appraisal_id_fkey         (this one — fixed here)
    appraisal_scenarios_parent_scenario_appraisal_id_fkey  (deferred — see Future_Tasks)

Both were originally ON DELETE RESTRICT. This migration changes only the first
one to ON DELETE CASCADE. The second is left untouched.

Rationale: a scenario row exists solely as metadata about the linked appraisal
revision. Deleting the appraisal must cascade-delete its scenario row; the
RESTRICT default blocked test teardown and any future "purge unsigned-off
appraisals" workflow.

Out of scope (deferred): the four other ON DELETE RESTRICT FKs in 0022
(`parent_scenario_appraisal_id`, both `appraisal_revisions` FKs,
`appraisal_decision_log.appraisal_id`). See SY_Homes_Future_Tasks.md.

Note on revision string: the Build Pack v5 §R2 specified
`0023_appraisal_scenarios_fk_cascade` (35 chars) but alembic_version.version_num
is varchar(32). Shortened by dropping the "_fk" segment — recorded as a
deviation in the §5 self-report. The file name follows the revision string,
keeping the convention that file basename == revision id.
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0023_appraisal_scenarios_cascade"
down_revision = "0022_appraisal_governance"
branch_labels = None
depends_on = None


_FK_NAME = "appraisal_scenarios_scenario_appraisal_id_fkey"


def upgrade() -> None:
    # Drop the auto-named RESTRICT FK and recreate with CASCADE.
    # Constraint name preserved byte-for-byte across drop/recreate so
    # pg_constraint identity stays stable for downstream tooling.
    op.drop_constraint(_FK_NAME, "appraisal_scenarios", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "appraisal_scenarios",
        "appraisals",
        ["scenario_appraisal_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Restore RESTRICT (the value §R0 step 5 of the Chat 15 Build Pack
    # recorded on the live DB and §R0 step 6 confirmed against the 0022
    # source).
    op.drop_constraint(_FK_NAME, "appraisal_scenarios", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "appraisal_scenarios",
        "appraisals",
        ["scenario_appraisal_id"],
        ["id"],
        ondelete="RESTRICT",
    )
