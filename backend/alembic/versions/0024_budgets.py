"""0024 budgets — header, lines, line_items (Prompt 2.4A)

Revision ID: 0024_budgets
Revises: 0023_appraisal_scenarios_cascade

Creates the Budgets Core schema per Phase 1 brief lines 2711–2958.

Three tables:
  budgets             — versioned budget header per project, terminal Closed/Superseded.
  budget_lines        — one row per (budget, cost_code, cost_code_subcategory).
  budget_line_items   — optional breakdown rows under a budget_line.

Three enums:
  budget_status                    — Draft | Active | Locked | Superseded | Closed
  budget_line_ftc_method           — Manual | Budget_Remaining | Committed_Only | Percentage_Complete
  budget_line_variance_status      — Green | Amber | Red

Six straight indexes + two partial unique indexes:
  ix_budgets_project_is_current        (project_id, is_current)
  ix_budgets_status                    (status)
  ix_budgets_source_appraisal_id       (source_appraisal_id)
  ix_budget_lines_budget_id            (budget_id)
  ix_budget_lines_cost_code_id         (cost_code_id)
  ix_budget_lines_variance_attention   (variance_status, requires_attention)
  ix_budget_line_items_budget_line_id  (budget_line_id)
  uq_budgets_one_current_per_project   UNIQUE (project_id) WHERE is_current = true   [B3]
  uq_budget_lines_no_subcat_unique     UNIQUE (budget_id, cost_code_id) WHERE cost_code_subcategory_id IS NULL  [B6]

Plus the regular UniqueConstraint on (budget_id, cost_code_id, cost_code_subcategory_id)
covers the non-NULL-subcategory case. The two together close the Postgres NULLs-distinct gap.

Three updated_at triggers (one per table) reuse the global set_updated_at() function
installed in 0001_initial_entities.py.

Spec-reconciliation note (§R1)
------------------------------
Phase 1 brief lines 2711–2958 is canonical (Build Pack v3 locked decision 1).

Deviations from Build Pack v3 §R2 — locked-superseded by Chat 16 / Prompt 2.4A
decisions in this thread:

  - **B1 (locked)** — `tenant_id` column + ix_*_tenant_id index dropped from both
    `budgets` and `budget_lines`. Build Pack v3 added `tenant_id NOT NULL FK→tenants.id`;
    Phase 1 spec lists no such column. Tenant scoping uses the existing repo pattern
    from `app/routers/appraisals.py`: project-id resolution then `_visible_project_ids`
    visibility filter (Pattern α — see §R3 service helpers). The defensive
    `hasattr(project, "tenant_id")` no-op is retained in service helpers as
    future-proofing in case the schema gains the column later.

  - **C1 (locked)** — `AppraisalUnit` aggregation in `create_from_appraisal` deferred.
    Phase 1 spec line 2861 "aggregated per cost code if applicable" permits skip when
    AppraisalUnit lacks a cost-code linkage (which it currently does — see Phase 2
    backlog AppraisalUnit-aggregation defer entry).

  - **D1 (locked)** — `AppraisalCostLine` field mappings:
       cl.amount         (was effective_value),
       cl.label          (was line_description),
       getattr(cl, "cost_code_subcategory_id", None) — graceful as today AppraisalCostLine
       has no subcategory field,
       budget_line.entity_id = appraisal.project.primary_entity_id — single entity per
       project; per-line entity_id sourcing deferred (separate Phase 2 backlog entry).

  - **B5 (locked, expanded)** — `create_from_appraisal` guards both
       cl.cost_code_id is None (raise) and cl.amount is None (raise);
       cl.amount == 0 emits a non-blocking warning.

Out of scope (per Phase 2 backlog and Build Pack §R0): actuals, commitments, budget
changes, Xero, scheduling, idempotency keys, SystemConfig threshold columns,
programme task FK constraint (lands in Prompt 3.2). Frontend untouched.
"""
from alembic import op
import sqlalchemy as sa


revision = "0024_budgets"
down_revision = "0023_appraisal_scenarios_cascade"
branch_labels = None
depends_on = None


# --- enum value lists ---------------------------------------------------

BUDGET_STATUSES = ("Draft", "Active", "Locked", "Superseded", "Closed")
FTC_METHODS = ("Manual", "Budget_Remaining", "Committed_Only", "Percentage_Complete")
VARIANCE_STATUSES = ("Green", "Amber", "Red")


def _attach_updated_at_trigger(table: str) -> None:
    """Attach the global set_updated_at() trigger function to a table.

    The function itself was installed by 0001_initial_entities.py.
    """
    op.execute(f"""
        CREATE TRIGGER trg_{table}_updated_at
        BEFORE UPDATE ON {table}
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)


def upgrade() -> None:
    budget_status_enum = sa.Enum(*BUDGET_STATUSES, name="budget_status")
    ftc_method_enum = sa.Enum(*FTC_METHODS, name="budget_line_ftc_method")
    variance_status_enum = sa.Enum(*VARIANCE_STATUSES, name="budget_line_variance_status")

    # ===== budgets ========================================================
    op.create_table(
        "budgets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # B1: NO tenant_id column. Tenant scoping via project join + _visible_project_ids.
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_appraisal_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("appraisals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("version_label", sa.String(50), nullable=False, server_default="Original"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("status", budget_status_enum, nullable=False, server_default="Draft"),
        sa.Column("created_from_appraisal_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        # Cached aggregates — recomputed by services, not by ORM listeners.
        sa.Column("total_budget", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_actuals", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_committed_not_invoiced", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("total_forecast_to_complete", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("forecast_final_cost", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("variance_vs_budget", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("variance_pct", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("summary_refreshed_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("notes", sa.Text),
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_budgets_project_is_current", "budgets",
                    ["project_id", "is_current"])
    op.create_index("ix_budgets_status", "budgets", ["status"])
    op.create_index("ix_budgets_source_appraisal_id", "budgets",
                    ["source_appraisal_id"])
    # B1: ix_budgets_tenant_id REMOVED.

    # B3: at most one is_current=true budget per project (DB-enforced)
    op.create_index(
        "uq_budgets_one_current_per_project",
        "budgets", ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    # ===== budget_lines ===================================================
    op.create_table(
        "budget_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # B1: NO tenant_id column.
        sa.Column("budget_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_code_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cost_code_subcategory_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_code_subcategories.id", ondelete="RESTRICT")),
        sa.Column("line_description", sa.String(255), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False),
        # Figures
        sa.Column("original_budget", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("approved_changes", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("current_budget", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("actuals_to_date", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("actuals_this_period", sa.Numeric(14, 2),
                  server_default="0"),
        sa.Column("last_actual_posted_at", sa.DateTime(timezone=True)),
        sa.Column("committed_value", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("invoiced_against_commitment", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("committed_not_invoiced", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("forecast_to_complete", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("ftc_method", ftc_method_enum,
                  nullable=False, server_default="Budget_Remaining"),
        sa.Column("forecast_final_cost", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("variance_value", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("variance_pct", sa.Numeric(6, 3),
                  nullable=False, server_default="0"),
        sa.Column("variance_status", variance_status_enum,
                  nullable=False, server_default="Green"),
        sa.Column("percentage_complete", sa.Numeric(5, 2), server_default="0"),
        # Programme integration — FK constraint added in Prompt 3.2 (B7 locked).
        sa.Column("linked_programme_task_id",
                  sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requires_attention", sa.Boolean,
                  nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        # Regular unique constraint — covers the non-NULL-subcategory case.
        # Postgres treats NULLs as distinct under regular UNIQUE, so the partial
        # index below is required for the NULL-subcategory case (B6).
        sa.UniqueConstraint("budget_id", "cost_code_id", "cost_code_subcategory_id",
                            name="uq_budget_lines_budget_cost_subcat"),
    )
    op.create_index("ix_budget_lines_budget_id", "budget_lines", ["budget_id"])
    op.create_index("ix_budget_lines_cost_code_id", "budget_lines", ["cost_code_id"])
    op.create_index("ix_budget_lines_variance_attention", "budget_lines",
                    ["variance_status", "requires_attention"])
    # B1: ix_budget_lines_tenant_id REMOVED.

    # B6: closes the NULL-subcategory uniqueness gap.
    op.create_index(
        "uq_budget_lines_no_subcat_unique",
        "budget_lines", ["budget_id", "cost_code_id"],
        unique=True,
        postgresql_where=sa.text("cost_code_subcategory_id IS NULL"),
    )

    # ===== budget_line_items =============================================
    op.create_table(
        "budget_line_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("budget_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("budget_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 4)),
        sa.Column("unit", sa.String(20)),
        sa.Column("rate", sa.Numeric(14, 4)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_budget_line_items_budget_line_id", "budget_line_items",
                    ["budget_line_id"])

    # Updated-at triggers — one per new table.
    for t in ("budgets", "budget_lines", "budget_line_items"):
        _attach_updated_at_trigger(t)


def downgrade() -> None:
    # Partial unique indexes are explicitly dropped; regular indexes go with
    # their tables.
    op.drop_index("uq_budget_lines_no_subcat_unique", table_name="budget_lines")
    op.drop_index("uq_budgets_one_current_per_project", table_name="budgets")

    for t in ("budget_line_items", "budget_lines", "budgets"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_updated_at ON {t};")
        op.drop_table(t)

    for enum_name in ("budget_line_variance_status",
                      "budget_line_ftc_method",
                      "budget_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
