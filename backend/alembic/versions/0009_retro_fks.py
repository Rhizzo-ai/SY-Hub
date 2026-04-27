"""0009 retroactive FK wiring to projects

Revision ID: 0009_retro_fks_to_proj
Revises: 0008_projects_team

Adds FK constraints deferred from Prompts 1.2 (user_role_projects) and
1.4 (audit_log) now that the projects table exists.
"""
from alembic import op


revision = "0009_retro_fks_to_proj"
down_revision = "0008_projects_team"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_user_role_projects_project_id",
        "user_role_projects", "projects",
        ["project_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_audit_log_project_id",
        "audit_log", "projects",
        ["project_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_log_project_id", "audit_log", type_="foreignkey")
    op.drop_constraint("fk_user_role_projects_project_id",
                       "user_role_projects", type_="foreignkey")
