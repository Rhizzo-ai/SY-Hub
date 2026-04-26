"""0011 cost codes — schema only

Revision ID: 0011_cost_codes
Revises: 0010_audit_trigger_comment

Creates the cost-code classification system: 5 tables (sections, codes,
subcategories, entity_mapping, project_cost_codes), enums, indexes,
updated_at triggers. Seeds and permissions land in subsequent revisions
(0012 sections, 0013 codes, 0014 permission grants).

No tenant_id — cost codes are a global catalogue per Prompt 1.6 brief.
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_cost_codes"
down_revision = "0010_audit_trigger_comment"
branch_labels = None
depends_on = None


# --- enums --------------------------------------------------------------

P_AND_L_CATEGORIES = ("COS", "Overhead", "Finance", "Tax")
DEFAULT_ENTITY_VALUES = ("Parent", "SPV", "ConstructionCo", "Context_Dependent")
VAT_TREATMENTS = (
    "Standard", "Reduced", "Zero_New_Build",
    "Exempt", "Reverse_Charge", "Mixed",
)
COST_CODE_STATUSES = ("Active", "Retired")
SUBCAT_UNITS = (
    "each", "m", "m_squared", "m_cubed",
    "tonnes", "sum", "hours", "day", "week",
)


def _attach_updated_at_trigger(table: str) -> None:
    op.execute(f"""
        CREATE TRIGGER trg_{table}_updated_at
        BEFORE UPDATE ON {table}
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)


def upgrade() -> None:
    # Enums — SQLAlchemy creates these automatically when the first table
    # using them is created via op.create_table. We just declare them here.
    p_and_l_enum = sa.Enum(*P_AND_L_CATEGORIES, name="cost_section_p_and_l")
    default_entity_enum = sa.Enum(*DEFAULT_ENTITY_VALUES, name="cost_code_default_entity")
    vat_treatment_enum = sa.Enum(*VAT_TREATMENTS, name="cost_code_vat_treatment")
    cost_code_status_enum = sa.Enum(*COST_CODE_STATUSES, name="cost_code_status")
    subcat_unit_enum = sa.Enum(*SUBCAT_UNITS, name="cost_code_subcat_unit")

    # cost_code_sections
    op.create_table(
        "cost_code_sections",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("is_direct_cost", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("default_p_and_l_category", p_and_l_enum,
                  nullable=False, server_default="COS"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cost_code_sections_display_order",
                    "cost_code_sections", ["display_order"])

    # cost_codes
    op.create_table(
        "cost_codes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("prefix", sa.String(3), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("section_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_code_sections.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("nrm_reference", sa.String(20)),
        sa.Column("buildertrend_category", sa.String(100)),
        sa.Column("applies_to_parent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("applies_to_spv", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("applies_to_construction_co", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("default_entity", default_entity_enum, nullable=False, server_default="SPV"),
        sa.Column("entity_rule_notes", sa.Text),
        sa.Column("xero_nominal_code", sa.String(10)),
        sa.Column("xero_nominal_name", sa.String(255)),
        sa.Column("is_vattable", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("vat_treatment", vat_treatment_enum, nullable=False, server_default="Standard"),
        sa.Column("is_cis_applicable", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_retention_applicable", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_capitalisable", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("status", cost_code_status_enum, nullable=False, server_default="Active"),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("retired_reason", sa.Text),
        sa.Column("replaced_by_code_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="SET NULL")),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("prefix", "sequence", name="uq_cost_codes_prefix_sequence"),
    )
    op.create_index("ix_cost_codes_section_id", "cost_codes", ["section_id"])
    op.create_index("ix_cost_codes_status", "cost_codes", ["status"])
    op.create_index(
        "ix_cost_codes_replaced_by",
        "cost_codes", ["replaced_by_code_id"],
        postgresql_where=sa.text("replaced_by_code_id IS NOT NULL"),
    )

    # cost_code_subcategories
    op.create_table(
        "cost_code_subcategories",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cost_code_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("code", sa.String(15), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("default_unit", subcat_unit_enum),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("status", cost_code_status_enum, nullable=False, server_default="Active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cost_code_subcategories_cost_code_id",
                    "cost_code_subcategories", ["cost_code_id"])

    # cost_code_entity_mapping
    op.create_table(
        "cost_code_entity_mapping",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cost_code_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("entity_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("is_allowed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("xero_nominal_code_override", sa.String(10)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cost_code_id", "entity_id",
                            name="uq_cost_code_entity_mapping"),
    )

    # project_cost_codes
    op.create_table(
        "project_cost_codes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("cost_code_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("project_override_name", sa.String(255)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "cost_code_id",
                            name="uq_project_cost_codes"),
    )
    op.create_index("ix_project_cost_codes_project_id",
                    "project_cost_codes", ["project_id"])
    op.create_index("ix_project_cost_codes_cost_code_id",
                    "project_cost_codes", ["cost_code_id"])

    # updated_at triggers
    for t in (
        "cost_code_sections", "cost_codes", "cost_code_subcategories",
        "cost_code_entity_mapping", "project_cost_codes",
    ):
        _attach_updated_at_trigger(t)


def downgrade() -> None:
    for t in (
        "project_cost_codes", "cost_code_entity_mapping",
        "cost_code_subcategories", "cost_codes", "cost_code_sections",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_updated_at ON {t};")
        op.drop_table(t)
    for enum_name in (
        "cost_code_subcat_unit", "cost_code_status",
        "cost_code_vat_treatment", "cost_code_default_entity",
        "cost_section_p_and_l",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
