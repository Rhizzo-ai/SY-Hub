"""B88 Pack 1 — Cost-Code Group Hierarchy (two-tier).

Adds the self-referential parent link + `allows_subgroups` flag to
`cost_code_sections`. Pure schema migration — no data step. Canonical
content (9 parents + 10 Construction subgroups + 129 codes) is seeded
by `app.scripts.seed_cost_code_structure` (Build Pack §5), not by this
migration, so the rows stay editable from the operator UI.

Up:
  - ADD COLUMN cost_code_sections.parent_section_id UUID NULL
    FK cost_code_sections.id ON DELETE RESTRICT
  - ADD INDEX ix_cost_code_sections_parent
  - ADD COLUMN cost_code_sections.allows_subgroups BOOLEAN NOT NULL
    DEFAULT false (server_default for new rows; existing 9 rows backfill
    to false automatically).

Down:
  - DROP INDEX ix_cost_code_sections_parent
  - DROP COLUMN parent_section_id, allows_subgroups
  Downgrade is destructive — does NOT preserve tier-2 data.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0044_cost_code_groups"
down_revision = "0043_document_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cost_code_sections",
        sa.Column(
            "parent_section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cost_code_sections.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_cost_code_sections_parent",
        "cost_code_sections",
        ["parent_section_id"],
    )
    op.add_column(
        "cost_code_sections",
        sa.Column(
            "allows_subgroups",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_cost_code_sections_parent", table_name="cost_code_sections")
    op.drop_column("cost_code_sections", "allows_subgroups")
    op.drop_column("cost_code_sections", "parent_section_id")
