"""B88 Pack 2 — Construction scope flag + PM permission revocation.

Adds the `included_in_construction_scope` boolean to `cost_code_sections`
so the Construction Budget (Tier 2) screen can be served by a
backend-enforced, data-driven scope filter (Build Pack §9 / D1 / D9).

Data step ALSO revokes the existing `project_manager` →
`budgets.view_sensitive` role grant — `app.seed_rbac._seed_role_permissions`
is additive-only so the seed alone cannot drop the row on existing DBs
(Build Pack §6, operator decision D3).

Up:
  - ADD COLUMN cost_code_sections.included_in_construction_scope BOOLEAN
    NOT NULL DEFAULT false  (server_default kept in place)
  - DATA: set the flag true for code '4' + every section whose
    `parent_section_id` points at the row with code '4'. Guarded for
    fresh empty DBs (UPDATE affects 0 rows, does not error).
  - DATA: DELETE the role_permissions row joining
    `project_manager` → `budgets.view_sensitive`. Guarded for absence.

Down:
  - DROP COLUMN cost_code_sections.included_in_construction_scope.
  - Re-grant `project_manager` → `budgets.view_sensitive` if both rows
    still exist (best-effort; idempotent).
  - DESTRUCTIVE for operator scope edits — the flag is dropped wholesale.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0045_construction_scope"
down_revision = "0044_cost_code_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cost_code_sections",
        sa.Column(
            "included_in_construction_scope",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Data step 1: flag Construction parent + its subgroups.
    op.execute(
        """
        UPDATE cost_code_sections
        SET included_in_construction_scope = true
        WHERE code = '4'
           OR parent_section_id = (
               SELECT id FROM cost_code_sections WHERE code = '4'
           )
        """
    )

    # Data step 2: revoke project_manager → budgets.view_sensitive.
    # `seed_rbac._seed_role_permissions` is additive-only so the seed
    # alone cannot drop the row on already-bootstrapped DBs. Build Pack
    # §6 / operator decision D3.
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'project_manager')
          AND permission_id = (
              SELECT id FROM permissions WHERE code = 'budgets.view_sensitive'
          )
        """
    )


def downgrade() -> None:
    # Re-grant PM → budgets.view_sensitive (idempotent best-effort).
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE r.code = 'project_manager'
          AND p.code = 'budgets.view_sensitive'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )

    op.drop_column("cost_code_sections", "included_in_construction_scope")
