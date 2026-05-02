"""0019 Track 2 — Appraisals Core (Prompt 2.2)

Revision ID: 0019_appraisals_core
Revises: 0018_sdlt_appraisal_defaults

Creates the four tables that back the commercial appraisal engine:

- `appraisals`                 — header + cached KPIs + RLV
- `appraisal_units`            — unit mix (house types, quantities, GDV/unit)
- `appraisal_cost_lines`       — cost line items w/ auto_source enum
- `appraisal_finance_model`    — debt/equity facilities + interest model

Also seeds two new RBAC permissions:
- `appraisals.submit`          — submit a Draft for approval
- `appraisals.view_financials` — see gated money fields (RLV, hurdles, margins)

All tables are tenant-isolated via `project_id -> projects.tenant_id`.
Every table carries created_at / updated_at with the shared
`set_updated_at()` trigger.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


revision = "0019_appraisals_core"
down_revision = "0018_sdlt_appraisal_defaults"
branch_labels = None
depends_on = None


APPRAISAL_STATES = ("Draft", "Submitted", "Approved", "Rejected", "Superseded")
UNIT_TYPES = ("Detached", "Semi_Detached", "Terraced", "Flat", "Bungalow",
              "Commercial", "Other")
TENURE_TYPES = ("Open_Market", "Affordable_Rent", "Shared_Ownership",
                "Social_Rent", "Build_To_Rent", "Private_Rent")
AUTO_SOURCES = (
    "Manual",
    "Percentage_Of_GDV",
    "Percentage_Of_Build_Cost",
    "Percentage_Of_Land",
    "SDLT_Engine",
    "Finance_Engine",
    "RLV_Engine",
)
COST_CATEGORIES = ("Acquisition", "Construction", "Professional_Fees",
                   "Statutory", "Finance", "Contingency", "Sales", "Other")
FINANCE_TYPES = ("Debt", "Equity", "Mezzanine", "Grant")
INTEREST_MODES = ("Simple_Monthly", "Compound_Monthly", "Rolled_Up", "Serviced")


def upgrade() -> None:
    # ---- enums ---------------------------------------------------------
    state_enum = sa.Enum(*APPRAISAL_STATES, name="appraisal_state",
                         create_type=True)
    unit_type_enum = sa.Enum(*UNIT_TYPES, name="appraisal_unit_type",
                             create_type=True)
    tenure_enum = sa.Enum(*TENURE_TYPES, name="appraisal_unit_tenure",
                          create_type=True)
    auto_src_enum = sa.Enum(*AUTO_SOURCES, name="appraisal_cost_auto_source",
                            create_type=True)
    cat_enum = sa.Enum(*COST_CATEGORIES, name="appraisal_cost_category",
                       create_type=True)
    fin_type_enum = sa.Enum(*FINANCE_TYPES, name="appraisal_finance_type",
                            create_type=True)
    int_mode_enum = sa.Enum(*INTEREST_MODES, name="appraisal_interest_mode",
                            create_type=True)

    # ---- appraisals ----------------------------------------------------
    op.create_table(
        "appraisals",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("previous_version_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("appraisals.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state", state_enum, nullable=False, server_default="Draft"),
        sa.Column("reference_date", sa.Date, nullable=False),
        # Land / purchase
        sa.Column("land_purchase_price", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("sdlt_category", sa.String(40), nullable=False,
                  server_default="Residential_Standard"),
        sa.Column("developer_relief", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        # Overall financial params
        sa.Column("contingency_pct", sa.Numeric(6, 3), nullable=False,
                  server_default="5.000"),
        sa.Column("target_profit_on_cost_pct", sa.Numeric(6, 3), nullable=False,
                  server_default="20.000"),
        sa.Column("target_profit_on_gdv_pct", sa.Numeric(6, 3), nullable=False,
                  server_default="17.000"),
        sa.Column("project_duration_months", sa.Integer, nullable=False,
                  server_default="18"),
        # Cached KPIs — recomputed on every save, never authoritative on their own.
        sa.Column("total_gdv", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_acquisition_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_build_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_professional_fees", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_statutory_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_finance_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_contingency", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_sales_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_other_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_profit", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("profit_on_cost_pct", sa.Numeric(8, 4), nullable=False,
                  server_default="0"),
        sa.Column("profit_on_gdv_pct", sa.Numeric(8, 4), nullable=False,
                  server_default="0"),
        # RLV
        sa.Column("rlv_enabled", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("rlv_target_basis", sa.String(16), nullable=False,
                  server_default="on_cost"),  # on_cost | on_gdv
        sa.Column("rlv_target_value", sa.Numeric(6, 3), nullable=False,
                  server_default="20.000"),
        sa.Column("rlv_computed_land_value", sa.Numeric(14, 2)),
        sa.Column("rlv_iterations", sa.Integer),
        sa.Column("rlv_converged", sa.Boolean),
        sa.Column("rlv_computed_at", sa.DateTime(timezone=True)),
        # Workflow
        sa.Column("submitted_by_user_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_user_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("computation_metadata", JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_stale", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_by_user_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "version",
                            name="uq_appraisals_project_version"),
        sa.CheckConstraint(
            "rlv_target_basis IN ('on_cost','on_gdv')",
            name="ck_appraisals_rlv_basis",
        ),
    )
    op.create_index("ix_appraisals_project", "appraisals", ["project_id"])
    op.create_index("ix_appraisals_state", "appraisals", ["state"])
    op.create_index(
        "ix_appraisals_project_state", "appraisals", ["project_id", "state"],
    )
    op.execute(
        "CREATE TRIGGER trg_appraisals_updated_at "
        "BEFORE UPDATE ON appraisals "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ---- appraisal_units ----------------------------------------------
    op.create_table(
        "appraisal_units",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("appraisal_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("appraisals.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("unit_label", sa.String(100), nullable=False),
        sa.Column("unit_type", unit_type_enum, nullable=False,
                  server_default="Detached"),
        sa.Column("tenure", tenure_enum, nullable=False,
                  server_default="Open_Market"),
        sa.Column("quantity", sa.Integer, nullable=False,
                  server_default="1"),
        sa.Column("beds", sa.Integer),
        sa.Column("gia_sqm", sa.Numeric(10, 2)),
        sa.Column("price_per_unit", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("build_cost_per_unit", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("quantity >= 0", name="ck_units_quantity_nonneg"),
        sa.CheckConstraint("price_per_unit >= 0", name="ck_units_price_nonneg"),
        sa.CheckConstraint("build_cost_per_unit >= 0",
                           name="ck_units_build_cost_nonneg"),
    )
    op.create_index("ix_appraisal_units_appraisal", "appraisal_units",
                    ["appraisal_id"])
    op.execute(
        "CREATE TRIGGER trg_appraisal_units_updated_at "
        "BEFORE UPDATE ON appraisal_units "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ---- appraisal_cost_lines -----------------------------------------
    op.create_table(
        "appraisal_cost_lines",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("appraisal_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("appraisals.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("cost_code_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="RESTRICT")),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("category", cat_enum, nullable=False,
                  server_default="Other"),
        sa.Column("auto_source", auto_src_enum, nullable=False,
                  server_default="Manual"),
        sa.Column("percentage", sa.Numeric(8, 4)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("is_locked", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("amount >= 0", name="ck_cost_lines_amount_nonneg"),
    )
    op.create_index("ix_appraisal_cost_lines_appraisal",
                    "appraisal_cost_lines", ["appraisal_id"])
    op.create_index("ix_appraisal_cost_lines_category",
                    "appraisal_cost_lines", ["category"])
    op.execute(
        "CREATE TRIGGER trg_appraisal_cost_lines_updated_at "
        "BEFORE UPDATE ON appraisal_cost_lines "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ---- appraisal_finance_model --------------------------------------
    op.create_table(
        "appraisal_finance_model",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("appraisal_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("appraisals.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("facility_type", fin_type_enum, nullable=False,
                  server_default="Debt"),
        sa.Column("principal_amount", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("interest_rate_pct", sa.Numeric(6, 3), nullable=False,
                  server_default="0.000"),
        sa.Column("arrangement_fee_pct", sa.Numeric(6, 3), nullable=False,
                  server_default="0.000"),
        sa.Column("exit_fee_pct", sa.Numeric(6, 3), nullable=False,
                  server_default="0.000"),
        sa.Column("interest_mode", int_mode_enum, nullable=False,
                  server_default="Simple_Monthly"),
        sa.Column("drawn_from_month", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("drawn_to_month", sa.Integer, nullable=False,
                  server_default="18"),
        # Cached outputs
        sa.Column("total_interest", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_fees", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_finance_cost", sa.Numeric(14, 2), nullable=False,
                  server_default="0"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("principal_amount >= 0",
                           name="ck_finance_principal_nonneg"),
        sa.CheckConstraint("interest_rate_pct >= 0",
                           name="ck_finance_rate_nonneg"),
        sa.CheckConstraint("drawn_to_month >= drawn_from_month",
                           name="ck_finance_draw_window"),
    )
    op.create_index("ix_appraisal_finance_model_appraisal",
                    "appraisal_finance_model", ["appraisal_id"])
    op.execute(
        "CREATE TRIGGER trg_appraisal_finance_model_updated_at "
        "BEFORE UPDATE ON appraisal_finance_model "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ---- RBAC permissions (idempotent) --------------------------------
    # Two new permission codes: appraisals.submit, appraisals.view_financials.
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES
            (gen_random_uuid(), 'appraisals.submit', 'appraisals', 'approve',
             'Submit an appraisal for approval', false),
            (gen_random_uuid(), 'appraisals.view_financials', 'appraisals',
             'view_sensitive', 'View gated financial fields on an appraisal', true)
        ON CONFLICT (code) DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_appraisal_finance_model_updated_at "
               "ON appraisal_finance_model;")
    op.drop_index("ix_appraisal_finance_model_appraisal",
                  table_name="appraisal_finance_model")
    op.drop_table("appraisal_finance_model")

    op.execute("DROP TRIGGER IF EXISTS trg_appraisal_cost_lines_updated_at "
               "ON appraisal_cost_lines;")
    op.drop_index("ix_appraisal_cost_lines_category",
                  table_name="appraisal_cost_lines")
    op.drop_index("ix_appraisal_cost_lines_appraisal",
                  table_name="appraisal_cost_lines")
    op.drop_table("appraisal_cost_lines")

    op.execute("DROP TRIGGER IF EXISTS trg_appraisal_units_updated_at "
               "ON appraisal_units;")
    op.drop_index("ix_appraisal_units_appraisal",
                  table_name="appraisal_units")
    op.drop_table("appraisal_units")

    op.execute("DROP TRIGGER IF EXISTS trg_appraisals_updated_at ON appraisals;")
    op.drop_index("ix_appraisals_project_state", table_name="appraisals")
    op.drop_index("ix_appraisals_state", table_name="appraisals")
    op.drop_index("ix_appraisals_project", table_name="appraisals")
    op.drop_table("appraisals")

    for enum_name in (
        "appraisal_interest_mode",
        "appraisal_finance_type",
        "appraisal_cost_category",
        "appraisal_cost_auto_source",
        "appraisal_unit_tenure",
        "appraisal_unit_type",
        "appraisal_state",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")

    op.execute(
        "DELETE FROM permissions "
        "WHERE code IN ('appraisals.submit','appraisals.view_financials')"
    )
