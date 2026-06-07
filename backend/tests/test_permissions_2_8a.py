"""Chat 34 §R5 (Prompt 2.8a) — Subcontract permissions tests.

Covers Build Pack 2.8a §R5 gates 28–30:
  28. Permission count = baseline + 10 (122 if baseline 112).
  29. `subcontracts.approve` + `subcontract_variations.approve/issue`
      mapped to the approval roles; create/cost to the contracts set.
  30. Role grants enforce 403 at the router layer (covered in the API
      tests under TestPermissionGates).

Mirrors the chat-33 `test_permissions_2_6.py` shape — purely data
assertions against `permissions` / `role_permissions` tables; no HTTP
round-trips.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests._subcontracts_common import DATABASE_URL


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


NEW_PERMS = {
    "subcontracts.view",
    "subcontracts.view_sensitive",
    "subcontracts.create",
    "subcontracts.edit",
    "subcontracts.approve",
    "subcontract_variations.view",
    "subcontract_variations.create",
    "subcontract_variations.cost",
    "subcontract_variations.approve",
    "subcontract_variations.issue",
}


class TestPermissionCount28a:
    def test_permission_count_baseline_plus_10(self, engine):
        """Baseline (post-2.6) = 112. 2.8a adds 10 (5 subcontracts + 5
        subcontract_variations) → 122. Chat 35 (2.8b) adds 7 (4
        subcontract_valuations + 3 payment_notices) → 129. Chat 41
        (2.7-BE-rev-A) adds 2 (trades.view + trades.create) → 131.
        Chat 41 operator eyeball (2.7-FE-revision) adds 1
        (suppliers.delete) → 132. Function name retains
        'baseline_plus_10' per chat-15 §3 literal-drift convention."""
        with engine.connect() as c:
            count = c.execute(text(
                "SELECT COUNT(*) FROM permissions"
            )).scalar()
        assert count == 133, (
            f"Expected 132 permissions (112 baseline + 10 from 2.8a "
            f"+ 7 from 2.8b + 2 from 2.7-BE-rev-A + 1 from 2.7-FE-rev "
            f"eyeball); got {count}"
        )

    def test_new_perms_are_seeded(self, engine):
        with engine.connect() as c:
            codes = {
                r[0] for r in c.execute(text(
                    "SELECT code FROM permissions "
                    "WHERE resource IN "
                    "('subcontracts','subcontract_variations')"
                ))
            }
        assert codes == NEW_PERMS, (
            f"Expected {NEW_PERMS}; got {codes}"
        )


class TestRoleMapping28a:
    def _roles_with(self, engine, code: str) -> set[str]:
        with engine.connect() as c:
            return {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM role_permissions rp
                      JOIN roles r ON r.id = rp.role_id
                      JOIN permissions p ON p.id = rp.permission_id
                     WHERE p.code = :c
                """), {"c": code})
            }

    def test_super_admin_has_all_new_perms(self, engine):
        for code in NEW_PERMS:
            roles = self._roles_with(engine, code)
            assert "super_admin" in roles, (code, roles)

    def test_director_has_all_new_perms(self, engine):
        for code in NEW_PERMS:
            roles = self._roles_with(engine, code)
            assert "director" in roles, (code, roles)

    def test_pm_create_and_cost(self, engine):
        """PM raises and edits subcontracts + raises/costs variations."""
        for code in (
            "subcontracts.create", "subcontracts.edit",
            "subcontract_variations.create",
            "subcontract_variations.cost",
        ):
            roles = self._roles_with(engine, code)
            assert "project_manager" in roles, (code, roles)

    def test_pm_cannot_approve_subcontracts(self, engine):
        """PM does NOT hold the approve/issue authority on either
        resource — separation of duties."""
        for code in (
            "subcontracts.approve",
            "subcontract_variations.approve",
            "subcontract_variations.issue",
        ):
            roles = self._roles_with(engine, code)
            assert "project_manager" not in roles, (code, roles)

    def test_finance_holds_approve_and_issue(self, engine):
        """Finance is the approval/issue authority for variations and
        subcontracts (mirrors finance's `budget_changes.approve/apply`
        + `pos.approve` mapping)."""
        for code in (
            "subcontracts.approve",
            "subcontract_variations.approve",
            "subcontract_variations.issue",
        ):
            roles = self._roles_with(engine, code)
            assert "finance" in roles, (code, roles)

    def test_finance_does_not_hold_create_edit(self, engine):
        """Finance approves, but does NOT create/edit subcontracts or
        raise/cost variations — that authority sits with PM."""
        for code in (
            "subcontracts.create", "subcontracts.edit",
            "subcontract_variations.create",
            "subcontract_variations.cost",
        ):
            roles = self._roles_with(engine, code)
            assert "finance" not in roles, (code, roles)

    def test_read_only_holds_view_only(self, engine):
        for code in (
            "subcontracts.view",
            "subcontract_variations.view",
        ):
            roles = self._roles_with(engine, code)
            assert "read_only" in roles, (code, roles)
        for code in (
            "subcontracts.create",
            "subcontracts.approve",
            "subcontract_variations.create",
            "subcontract_variations.approve",
            "subcontract_variations.issue",
        ):
            roles = self._roles_with(engine, code)
            assert "read_only" not in roles, (code, roles)

    def test_site_manager_view_only(self, engine):
        for code in (
            "subcontracts.view",
            "subcontract_variations.view",
        ):
            roles = self._roles_with(engine, code)
            assert "site_manager" in roles, (code, roles)
        for code in (
            "subcontracts.create",
            "subcontract_variations.create",
        ):
            roles = self._roles_with(engine, code)
            assert "site_manager" not in roles, (code, roles)


class TestPermissionEnums28a:
    def test_cost_is_new_action_value(self, engine):
        with engine.connect() as c:
            vals = {r[0] for r in c.execute(text("""
                SELECT enumlabel FROM pg_enum
                 WHERE enumtypid = (
                    SELECT oid FROM pg_type
                     WHERE typname='permission_action'
                 )
            """))}
        assert "cost" in vals
        assert "issue" in vals  # pre-existing — not new in 2.8a
