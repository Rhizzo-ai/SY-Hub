"""B83 — Role & Permissions Admin: operator revocation overrides (Chat 52).

Creates `role_permission_revocations` — the seed-precedence table
(operator decision D1). Every operator-removed grant is recorded here;
`app.seed_rbac._seed_role_permissions` stays additive for everything
EXCEPT pairs present in this table, which it must never re-add. This is
what makes operator matrix edits survive every bootstrap/recycle
re-seed.

Up:
  - CREATE TABLE role_permission_revocations (
      role_id            UUID NOT NULL  FK roles.id        ON DELETE CASCADE,
      permission_id      UUID NOT NULL  FK permissions.id  ON DELETE CASCADE,
      revoked_by_user_id UUID NULL      FK users.id        ON DELETE SET NULL,
      revoked_at         timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (role_id, permission_id)
    )
  - No data step. No enum changes. No other schema changes.
  - No additional indexes — the composite PK covers the seed's lookup
    pattern (full pair-set scan) and the endpoint's per-pair upserts.

Down:
  - DROP TABLE role_permission_revocations. DESTRUCTIVE for operator
    grant-removal overrides — the next seed re-adds every revoked pair.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0046_rbac_operator_overrides"
down_revision = "0045_construction_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_permission_revocations",
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revoked_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )


def downgrade() -> None:
    op.drop_table("role_permission_revocations")
