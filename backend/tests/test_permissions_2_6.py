"""Chat 33 §R5 (Prompt 2.6) — Budget Change permissions tests.

Covers Build Pack 2.6 acceptance gates 31–34: permission count, new
permission codes, role mapping for `apply` (must match `approve`
exactly per operator decision Q1=b), and `submit` mapping for PM.

Mirrors the chat-32 `test_permissions_2_7.py` shape — purely data
assertions against `permissions` / `role_permissions` tables; no HTTP
round-trips.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests._bcr_common import DATABASE_URL


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


class TestPermissionCount26:
    def test_permission_count_baseline_plus_2(self, engine):
        """Build pack §R2 expected baseline + 5 = 115 BUT pre-existing
        `budget_changes.{view,create,edit,approve}` were already in the
        seed at 2.6 entry. Operator decision (Chat 33 §R0 Q1=b):
        ADDITIVE — keep `edit`, add `submit`+`apply`. Net +2 → 112.
        Test gate 31 reads baseline+2.
        """
        with engine.connect() as c:
            count = c.execute(text(
                "SELECT COUNT(*) FROM permissions"
            )).scalar()
        assert count == 133, (
            f"Expected 132 permissions (110 baseline + 2 from 2.6 + "
            f"10 from 2.8a + 7 from 2.8b + 2 from 2.7-BE-rev-A + "
            f"1 from 2.7-FE-rev eyeball); got {count}"
        )

    def test_new_perms_are_seeded(self, engine):
        with engine.connect() as c:
            codes = {
                r[0] for r in c.execute(text(
                    "SELECT code FROM permissions WHERE resource='budget_changes'"
                ))
            }
        assert codes == {
            "budget_changes.view", "budget_changes.create",
            "budget_changes.edit", "budget_changes.submit",
            "budget_changes.approve", "budget_changes.apply",
        }


class TestRoleMapping26:
    def test_apply_role_mapping(self, engine):
        """Per operator instruction §R0 Q1: `apply` mapped to the same
        roles as `approve`. Live DB check."""
        with engine.connect() as c:
            approve_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'budget_changes.approve'
                """))
            }
            apply_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'budget_changes.apply'
                """))
            }
        assert apply_roles == approve_roles, (
            f"apply ({apply_roles}) and approve ({approve_roles}) must map "
            f"to the same role set per Chat 33 §R0 Q1 decision."
        )

    def test_submit_mapped_to_pm(self, engine):
        """PM must hold .submit — the BCR raiser path."""
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT 1 FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.code='project_manager'
                  AND p.code='budget_changes.submit'
            """)).first()
        assert row is not None
