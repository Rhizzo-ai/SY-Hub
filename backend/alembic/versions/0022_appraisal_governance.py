"""appraisal_governance

Revision ID: 0022_appraisal_governance
Revises: 0021_appraisal_retrofit
Create Date: 2026-05-04

Phase C of Prompt 2.3 v6:
    C.1 CREATE TYPE appraisal_revision_reason_enum (8 values)
    C.2 CREATE TYPE decision_type_enum (6 values)
    C.3 CREATE TABLE appraisal_revisions (CHECK constraints, indexes,
        UNIQUE on appraisal_id_to)
    C.4 CREATE TABLE appraisal_scenarios (CHECK constraint, indexes,
        two UNIQUEs)
    C.5 CREATE FUNCTION + TRIGGER validate_scenario_parent
        (BEFORE INSERT/UPDATE)
    C.6 Backfill appraisal_scenarios with Base rows (one per
        appraisal_group_id)
    C.7 CREATE TABLE appraisal_decision_log (multi-column CHECKs,
        indexes, self-FK)
    C.8 CREATE FUNCTION + TRIGGERS reject_decision_log_mutation
        (BEFORE UPDATE/DELETE)
    C.9 INSERT system_config row 'appraisal_decisions_required_threshold'=3

R0 verifications applied:
    - pgcrypto is available → gen_random_uuid() kept (matches 0019).
    - Audit-log immutability pattern in 0006 is DB triggers → drafted triggers
      replicate it (function name reject_decision_log_mutation; AUDIT is
      audit_log_no_modify — deliberately distinct).
    - system_config schema deviates from spec's assumed column set. Actual
      columns (from 1.7 migration 0015):
          config_key, config_value, value_type, category, description,
          is_system_locked, minimum_role_to_edit, default_value
      C.9 INSERT corrected accordingly. value_type enum label is 'Integer'
      (NOT 'int'); category is 'Appraisal'; minimum_role_to_edit resolved
      via subquery on roles.code='super_admin'.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0022_appraisal_governance"
down_revision = "0021_appraisal_retrofit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----- C.1 appraisal_revision_reason_enum -----
    op.execute(
        """
        CREATE TYPE appraisal_revision_reason_enum AS ENUM (
            'GDV_Updated',
            'Costs_Updated',
            'Planning_Change',
            'Finance_Terms_Change',
            'Market_Change',
            'Scope_Change',
            'Error_Correction',
            'Other'
        )
        """
    )

    # ----- C.2 decision_type_enum -----
    op.execute(
        """
        CREATE TYPE decision_type_enum AS ENUM (
            'Go',
            'No_Go',
            'Defer',
            'Request_Revision',
            'Conditional_Go',
            'Correction'
        )
        """
    )

    # ----- C.3 appraisal_revisions -----
    op.execute(
        """
        CREATE TABLE appraisal_revisions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            from_version integer NOT NULL,
            to_version integer NOT NULL,
            appraisal_id_from uuid NOT NULL REFERENCES appraisals(id) ON DELETE RESTRICT,
            appraisal_id_to uuid NOT NULL REFERENCES appraisals(id) ON DELETE RESTRICT,
            revision_reason appraisal_revision_reason_enum NOT NULL,
            summary_of_changes text NOT NULL,
            delta_gdv numeric(14,2) NOT NULL DEFAULT 0,
            delta_total_cost numeric(14,2) NOT NULL DEFAULT 0,
            delta_profit numeric(14,2) NOT NULL DEFAULT 0,
            revised_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_appraisal_revisions_summary_min_length
                CHECK (length(trim(summary_of_changes)) >= 10),
            CONSTRAINT ck_appraisal_revisions_version_sequence
                CHECK (to_version = from_version + 1),
            CONSTRAINT ck_appraisal_revisions_distinct_endpoints
                CHECK (appraisal_id_from <> appraisal_id_to)
        )
        """
    )
    op.create_index(
        "ix_appraisal_revisions_from",
        "appraisal_revisions",
        ["appraisal_id_from"],
    )
    op.create_index(
        "ix_appraisal_revisions_to",
        "appraisal_revisions",
        ["appraisal_id_to"],
    )
    op.create_index(
        "ix_appraisal_revisions_to_created",
        "appraisal_revisions",
        ["appraisal_id_to", sa.text("created_at DESC")],
    )
    op.create_index(
        "uq_appraisal_revisions_to",
        "appraisal_revisions",
        ["appraisal_id_to"],
        unique=True,
    )

    # ----- C.4 appraisal_scenarios -----
    op.execute(
        """
        CREATE TABLE appraisal_scenarios (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            appraisal_group_id uuid NOT NULL,
            scenario_appraisal_id uuid NOT NULL REFERENCES appraisals(id) ON DELETE RESTRICT,
            parent_scenario_appraisal_id uuid REFERENCES appraisals(id) ON DELETE RESTRICT,
            scenario_label appraisal_scenario_enum NOT NULL,
            scenario_description text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            CONSTRAINT ck_appraisal_scenarios_description_min_length
                CHECK (length(trim(scenario_description)) >= 10),
            CONSTRAINT ck_appraisal_scenarios_base_parent_xor
                CHECK (
                    (scenario_label = 'Base' AND parent_scenario_appraisal_id IS NULL)
                    OR
                    (scenario_label <> 'Base' AND parent_scenario_appraisal_id IS NOT NULL)
                )
        )
        """
    )
    op.create_index(
        "ix_appraisal_scenarios_group",
        "appraisal_scenarios",
        ["appraisal_group_id"],
    )
    op.create_index(
        "ix_appraisal_scenarios_appraisal",
        "appraisal_scenarios",
        ["scenario_appraisal_id"],
    )
    op.create_index(
        "ix_appraisal_scenarios_parent",
        "appraisal_scenarios",
        ["parent_scenario_appraisal_id"],
    )
    op.create_index(
        "uq_appraisal_scenarios_appraisal",
        "appraisal_scenarios",
        ["scenario_appraisal_id"],
        unique=True,
    )
    op.create_index(
        "uq_appraisal_scenarios_group_label",
        "appraisal_scenarios",
        ["appraisal_group_id", "scenario_label"],
        unique=True,
    )

    # ----- C.5 Parent-validation trigger -----
    op.execute(
        """
        CREATE FUNCTION validate_scenario_parent() RETURNS trigger AS $$
        DECLARE parent_scenario text;
        BEGIN
            IF NEW.parent_scenario_appraisal_id IS NOT NULL THEN
                SELECT scenario::text INTO parent_scenario FROM appraisals
                 WHERE id = NEW.parent_scenario_appraisal_id;
                IF parent_scenario IS NULL OR parent_scenario != 'Base' THEN
                    RAISE EXCEPTION 'parent_scenario_appraisal_id must reference an appraisal where scenario=Base';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_scenarios_validate_parent
            BEFORE INSERT OR UPDATE ON appraisal_scenarios
            FOR EACH ROW EXECUTE FUNCTION validate_scenario_parent()
        """
    )

    # ----- C.6 Backfill appraisal_scenarios Base rows -----
    # One row per appraisal_group_id, pointing at the originating Base v1
    # (lowest version_number with scenario='Base' in the group).
    op.execute(
        """
        INSERT INTO appraisal_scenarios (
            appraisal_group_id,
            scenario_appraisal_id,
            parent_scenario_appraisal_id,
            scenario_label,
            scenario_description,
            created_at,
            created_by_user_id
        )
        SELECT
            a.appraisal_group_id,
            a.id,
            NULL,
            'Base',
            'Base scenario (auto-backfilled at 2.3 retrofit)',
            a.created_at,
            a.created_by_user_id
        FROM appraisals a
        WHERE a.scenario = 'Base'
          AND a.version_number = (
            SELECT MIN(version_number) FROM appraisals b
            WHERE b.appraisal_group_id = a.appraisal_group_id
              AND b.scenario = 'Base'
          )
        """
    )

    # Assertion: row count = distinct appraisal_group_id count.
    op.execute(
        """
        DO $$
        DECLARE backfilled int; expected int;
        BEGIN
            SELECT COUNT(*) INTO backfilled FROM appraisal_scenarios;
            SELECT COUNT(DISTINCT appraisal_group_id) INTO expected FROM appraisals;
            IF backfilled <> expected THEN
                RAISE EXCEPTION 'appraisal_scenarios backfill: expected % rows (one per group), got %',
                    expected, backfilled;
            END IF;
        END $$
        """
    )

    # ----- C.7 appraisal_decision_log -----
    op.execute(
        """
        CREATE TABLE appraisal_decision_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            appraisal_id uuid NOT NULL REFERENCES appraisals(id) ON DELETE RESTRICT,
            appraisal_version integer NOT NULL,
            decision_type decision_type_enum NOT NULL,
            decision_maker_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            decision_date date NOT NULL,
            decision_rationale text NOT NULL,
            conditions text,
            key_assumptions_challenged text,
            supporting_documents jsonb NOT NULL DEFAULT '[]'::jsonb,
            correction_of_decision_id uuid REFERENCES appraisal_decision_log(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_decision_log_rationale_min_length
                CHECK (length(trim(decision_rationale)) >= 10),
            CONSTRAINT ck_decision_log_conditional_go_requires_conditions
                CHECK (
                    (decision_type = 'Conditional_Go'
                        AND conditions IS NOT NULL
                        AND length(trim(conditions)) > 0)
                    OR
                    (decision_type <> 'Conditional_Go' AND conditions IS NULL)
                ),
            CONSTRAINT ck_decision_log_correction_requires_reference
                CHECK (
                    (decision_type = 'Correction' AND correction_of_decision_id IS NOT NULL)
                    OR
                    (decision_type <> 'Correction' AND correction_of_decision_id IS NULL)
                ),
            CONSTRAINT ck_decision_log_supporting_documents_is_array
                CHECK (jsonb_typeof(supporting_documents) = 'array')
        )
        """
    )
    op.create_index(
        "ix_decision_log_appraisal",
        "appraisal_decision_log",
        ["appraisal_id"],
    )
    op.create_index(
        "ix_decision_log_date_desc",
        "appraisal_decision_log",
        [sa.text("decision_date DESC")],
    )
    op.create_index(
        "ix_decision_log_appraisal_date_created",
        "appraisal_decision_log",
        ["appraisal_id", sa.text("decision_date DESC"), sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_decision_log_decision_maker",
        "appraisal_decision_log",
        ["decision_maker_user_id"],
    )
    op.execute(
        """
        CREATE INDEX ix_decision_log_correction_of
            ON appraisal_decision_log (correction_of_decision_id)
            WHERE correction_of_decision_id IS NOT NULL
        """
    )

    # ----- C.8 Decision-log immutability -----
    op.execute(
        """
        CREATE FUNCTION reject_decision_log_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'appraisal_decision_log is append-only — UPDATE/DELETE forbidden';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_decision_log_no_update
            BEFORE UPDATE ON appraisal_decision_log
            FOR EACH ROW EXECUTE FUNCTION reject_decision_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_decision_log_no_delete
            BEFORE DELETE ON appraisal_decision_log
            FOR EACH ROW EXECUTE FUNCTION reject_decision_log_mutation()
        """
    )

    # ----- C.9 system_config nudge threshold -----
    # Schema corrected per R0: config_key/config_value + required columns
    # (category, description NOT NULL, minimum_role_to_edit FK, default_value).
    op.execute(
        """
        INSERT INTO system_config (
            config_key,
            config_value,
            value_type,
            category,
            description,
            is_system_locked,
            minimum_role_to_edit,
            default_value
        )
        SELECT
            'appraisal_decisions_required_threshold',
            '3',
            'Integer'::system_config_value_type,
            'Appraisal'::system_config_category,
            'Number of distinct decision-makers required to log Go/No_Go/Defer on a current Approved Base appraisal before the nudge banner clears.',
            false,
            (SELECT id FROM roles WHERE code = 'super_admin'),
            '3'
        WHERE NOT EXISTS (
            SELECT 1 FROM system_config WHERE config_key = 'appraisal_decisions_required_threshold'
        )
        """
    )


def downgrade() -> None:
    # Reverse order per spec C.10.

    # 1. Drop system_config row.
    op.execute(
        """
        DELETE FROM system_config
         WHERE config_key = 'appraisal_decisions_required_threshold'
        """
    )

    # 2. Drop immutability triggers + function.
    op.execute("DROP TRIGGER IF EXISTS trg_decision_log_no_delete ON appraisal_decision_log")
    op.execute("DROP TRIGGER IF EXISTS trg_decision_log_no_update ON appraisal_decision_log")
    op.execute("DROP FUNCTION IF EXISTS reject_decision_log_mutation()")

    # 3. Drop appraisal_decision_log.
    op.execute("DROP INDEX IF EXISTS ix_decision_log_correction_of")
    op.drop_index("ix_decision_log_decision_maker", table_name="appraisal_decision_log")
    op.drop_index("ix_decision_log_appraisal_date_created", table_name="appraisal_decision_log")
    op.drop_index("ix_decision_log_date_desc", table_name="appraisal_decision_log")
    op.drop_index("ix_decision_log_appraisal", table_name="appraisal_decision_log")
    op.drop_table("appraisal_decision_log")

    # 4. Drop parent-validation trigger + function.
    op.execute("DROP TRIGGER IF EXISTS trg_scenarios_validate_parent ON appraisal_scenarios")
    op.execute("DROP FUNCTION IF EXISTS validate_scenario_parent()")

    # 5. Drop appraisal_scenarios.
    op.drop_index("uq_appraisal_scenarios_group_label", table_name="appraisal_scenarios")
    op.drop_index("uq_appraisal_scenarios_appraisal", table_name="appraisal_scenarios")
    op.drop_index("ix_appraisal_scenarios_parent", table_name="appraisal_scenarios")
    op.drop_index("ix_appraisal_scenarios_appraisal", table_name="appraisal_scenarios")
    op.drop_index("ix_appraisal_scenarios_group", table_name="appraisal_scenarios")
    op.drop_table("appraisal_scenarios")

    # 6. Drop appraisal_revisions.
    op.drop_index("uq_appraisal_revisions_to", table_name="appraisal_revisions")
    op.drop_index("ix_appraisal_revisions_to_created", table_name="appraisal_revisions")
    op.drop_index("ix_appraisal_revisions_to", table_name="appraisal_revisions")
    op.drop_index("ix_appraisal_revisions_from", table_name="appraisal_revisions")
    op.drop_table("appraisal_revisions")

    # 7. Drop new enums.
    op.execute("DROP TYPE IF EXISTS decision_type_enum")
    op.execute("DROP TYPE IF EXISTS appraisal_revision_reason_enum")
