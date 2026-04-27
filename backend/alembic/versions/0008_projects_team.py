"""0008 projects + project_team_members (Prompt 1.5)

Revision ID: 0008_projects_team
Revises: 0007_audit_trigger_cascade
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_projects_team"
down_revision = "0007_audit_trigger_cascade"
branch_labels = None
depends_on = None


PROJECT_TYPES = ("Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract")
LAND_OWNERSHIP = ("Direct_Purchase", "Option", "Conditional_Contract", "JV_Contribution", "Existing_Holding")
TENURES = ("Freehold", "Leasehold", "Long_Leasehold", "Option", "Conditional", "Other")
LAND_TYPES = ("Greenfield", "Brownfield", "Mixed", "Urban_Infill", "Garden_Land")
PLANNING_TYPES = ("Full", "Outline", "Reserved_Matters", "Hybrid", "Permitted_Dev", "Prior_Approval")
PLANNING_STATUSES = ("Pre_App", "Submitted", "Approved", "Refused", "Appeal", "Not_Required")
PROJECT_STAGES = (
    "Lead", "Appraisal", "Deal_Pipeline", "Planning", "Pre_Con",
    "Construction", "Sales", "Post_Completion", "Closed", "Dead",
)
PROJECT_STATUSES = ("Active", "On_Hold", "Dead", "Complete")
TEAM_ROLES = (
    "Project_Lead", "Contracts_Manager", "Site_Manager", "Quantity_Surveyor",
    "Designer", "Consultant", "Finance", "Sales", "Support",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in [
        ("project_type_enum", PROJECT_TYPES),
        ("land_ownership_enum", LAND_OWNERSHIP),
        ("project_tenure_enum", TENURES),
        ("land_type_enum", LAND_TYPES),
        ("planning_type_enum", PLANNING_TYPES),
        ("planning_status_enum", PLANNING_STATUSES),
        ("project_stage_enum", PROJECT_STAGES),
        ("project_status_enum", PROJECT_STATUSES),
        ("team_role_enum", TEAM_ROLES),
    ]:
        postgresql.ENUM(*values, name=name, create_type=True).create(bind, checkfirst=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("project_code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("project_type", postgresql.ENUM(name="project_type_enum", create_type=False), nullable=False),
        sa.Column("parent_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("primary_entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("construction_entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="RESTRICT")),
        sa.Column("land_ownership_method", postgresql.ENUM(name="land_ownership_enum", create_type=False), nullable=False),
        sa.Column("site_address", sa.Text, nullable=False),
        sa.Column("site_postcode", sa.String(10), nullable=False),
        sa.Column("local_authority", sa.String(100)),
        sa.Column("site_area_ha", sa.Numeric(10, 4)),
        sa.Column("site_area_acres", sa.Numeric(10, 4)),
        sa.Column("tenure", postgresql.ENUM(name="project_tenure_enum", create_type=False),
                  nullable=False, server_default="Freehold"),
        sa.Column("lease_years_remaining", sa.Integer),
        sa.Column("land_type", postgresql.ENUM(name="land_type_enum", create_type=False)),
        sa.Column("planning_ref", sa.String(50)),
        sa.Column("planning_type", postgresql.ENUM(name="planning_type_enum", create_type=False)),
        sa.Column("planning_status", postgresql.ENUM(name="planning_status_enum", create_type=False)),
        sa.Column("planning_approval_date", sa.Date),
        sa.Column("planning_expiry_date", sa.Date),
        sa.Column("implementation_required", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("s106_required", sa.Boolean, server_default=sa.false()),
        sa.Column("cil_required", sa.Boolean, server_default=sa.false()),
        sa.Column("vat_opt_to_tax", sa.Boolean, server_default=sa.false()),
        sa.Column("vat_opt_to_tax_date", sa.Date),
        sa.Column("units_target", sa.Integer),
        sa.Column("units_actual", sa.Integer),
        sa.Column("affordable_housing_pct", sa.Numeric(5, 2), server_default="0"),
        sa.Column("target_start_date", sa.Date),
        sa.Column("target_pc_date", sa.Date),
        sa.Column("actual_start_date", sa.Date),
        sa.Column("actual_pc_date", sa.Date),
        sa.Column("current_stage", postgresql.ENUM(name="project_stage_enum", create_type=False),
                  nullable=False, server_default="Lead"),
        sa.Column("stage_entered_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("status", postgresql.ENUM(name="project_status_enum", create_type=False),
                  nullable=False, server_default="Active"),
        sa.Column("dead_reason", sa.Text),
        sa.Column("gdv_actual", sa.Numeric(14, 2), server_default="0"),
        sa.Column("build_cost_actual", sa.Numeric(14, 2), server_default="0"),
        sa.Column("all_in_cost_actual", sa.Numeric(14, 2), server_default="0"),
        sa.Column("profit_actual", sa.Numeric(14, 2), server_default="0"),
        sa.Column("margin_actual_pct", sa.Numeric(6, 3), server_default="0"),
        sa.Column("financials_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("project_lead_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_projects_entity_status", "projects", ["primary_entity_id", "status"])
    op.create_index("ix_projects_stage", "projects", ["current_stage"])
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_lead", "projects", ["project_lead_user_id"])
    # Partial index for planning expiry sweep candidates.
    op.execute("""
        CREATE INDEX ix_projects_planning_expiry_candidates
        ON projects (planning_expiry_date)
        WHERE implementation_required = true AND actual_start_date IS NULL
    """)
    # updated_at trigger
    op.execute("""
        CREATE TRIGGER projects_set_updated_at
          BEFORE UPDATE ON projects
          FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.create_table(
        "project_team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role_on_project",
                  postgresql.ENUM(name="team_role_enum", create_type=False), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_team_project_role_removed",
                    "project_team_members", ["project_id", "role_on_project", "removed_at"])
    op.create_index("ix_team_user_removed", "project_team_members", ["user_id", "removed_at"])
    # Partial unique — one active primary per (project, role).
    op.execute("""
        CREATE UNIQUE INDEX ux_team_one_active_primary_per_role
        ON project_team_members (project_id, role_on_project)
        WHERE is_primary = true AND removed_at IS NULL
    """)
    op.execute("""
        CREATE TRIGGER team_set_updated_at
          BEFORE UPDATE ON project_team_members
          FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS team_set_updated_at ON project_team_members")
    op.execute("DROP INDEX IF EXISTS ux_team_one_active_primary_per_role")
    op.drop_index("ix_team_user_removed", table_name="project_team_members")
    op.drop_index("ix_team_project_role_removed", table_name="project_team_members")
    op.drop_table("project_team_members")
    op.execute("DROP TRIGGER IF EXISTS projects_set_updated_at ON projects")
    op.execute("DROP INDEX IF EXISTS ix_projects_planning_expiry_candidates")
    op.drop_index("ix_projects_lead", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_stage", table_name="projects")
    op.drop_index("ix_projects_entity_status", table_name="projects")
    op.drop_table("projects")
    bind = op.get_bind()
    for name in [
        "team_role_enum", "project_status_enum", "project_stage_enum",
        "planning_status_enum", "planning_type_enum", "land_type_enum",
        "project_tenure_enum", "land_ownership_enum", "project_type_enum",
    ]:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
