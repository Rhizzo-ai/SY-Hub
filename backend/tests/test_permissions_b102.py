"""B102 — Gate 3 RBAC seed tests.

Pins:
  * `budgets.clear_unbudgeted` is in the live catalogue (T20)
  * total catalogue length == 143 (T21)
  * director role receives the new perm (T22)
  * finance role does NOT receive it (T23)
  * super_admin receives it via the set(ALL_PERMISSION_CODES) helper (T24)

Catalogue length is asserted in two places intentionally:
  - in-process (PERMISSION_CATALOGUE) — proves the source-of-truth list
    builds to 143 regardless of DB state.
  - on-DB (SELECT count(*) FROM permissions) — proves the live seed has
    been re-run. T21 covers the in-process side; the live-DB count is
    pinned by test_packages_service.py::test_TRB_1 (already bumped
    142→143 in the same commit as this file).
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


# ----------------------------------------------------------------------
# T20 — `budgets.clear_unbudgeted` is in PERMISSION_CATALOGUE; not sensitive.
# ----------------------------------------------------------------------
class TestBudgetsClearUnbudgetedInCatalogue:
    def test_budgets_clear_unbudgeted_in_catalogue(self):
        from app.seed_rbac import PERMISSION_CATALOGUE

        rows = [r for r in PERMISSION_CATALOGUE
                if r[0] == "budgets.clear_unbudgeted"]
        assert len(rows) == 1, (
            "expected exactly one budgets.clear_unbudgeted entry, "
            f"got {len(rows)}"
        )
        code, resource, action, _desc, is_sensitive = rows[0]
        assert resource == "budgets"
        assert action == "clear_unbudgeted"
        # B102 contract: the act of acknowledging an unbudgeted line
        # is NOT money-disclosing — it doesn't show figures, it
        # simply marks the flag as sighted. Keep the sensitive set
        # at {"admin"} so this perm can be granted to non-financial
        # operators (e.g. PMs) via the future B83 admin screen
        # without exposing budgets.view_sensitive.
        assert is_sensitive is False


# ----------------------------------------------------------------------
# T21 — total catalogue length is 143.
# ----------------------------------------------------------------------
class TestPermissionCountIs143:
    def test_permission_count_is_143(self):
        from app.seed_rbac import PERMISSION_CATALOGUE

        assert len(PERMISSION_CATALOGUE) == 143, (
            f"expected 143 entries, got {len(PERMISSION_CATALOGUE)}; "
            "if you intended to add/remove a permission, update this "
            "and test_packages_service.py::test_TRB_1 in lockstep."
        )


# ----------------------------------------------------------------------
# T22 — director role's seeded perms include budgets.clear_unbudgeted.
# ----------------------------------------------------------------------
class TestDirectorHasClearUnbudgeted:
    def test_director_has_clear_unbudgeted_inprocess(self):
        # Source-of-truth: ROLE_PERMISSIONS dict in seed_rbac.
        from app.seed_rbac import ROLE_PERMISSIONS

        assert "budgets.clear_unbudgeted" in ROLE_PERMISSIONS["director"], (
            "director must hold budgets.clear_unbudgeted via the "
            "all-minus-exclusions mechanism; if you intentionally "
            "removed director's grant, update this test."
        )

    def test_director_has_clear_unbudgeted_in_live_db(self, engine):
        # Live-DB pin: confirm the seeder actually wrote the role link.
        with engine.connect() as c:
            row = c.execute(text(
                """
                SELECT 1
                FROM permissions p
                JOIN role_permissions rp ON rp.permission_id = p.id
                JOIN roles r ON r.id = rp.role_id
                WHERE r.code = 'director'
                  AND p.code = 'budgets.clear_unbudgeted'
                """
            )).first()
        assert row is not None, (
            "director role missing budgets.clear_unbudgeted in live DB "
            "— reseed_rbac may not have run after the catalogue bump."
        )


# ----------------------------------------------------------------------
# T23 — finance role does NOT hold budgets.clear_unbudgeted by default.
# ----------------------------------------------------------------------
class TestFinanceLacksClearUnbudgeted:
    def test_finance_lacks_clear_unbudgeted_inprocess(self):
        from app.seed_rbac import ROLE_PERMISSIONS

        assert (
            "budgets.clear_unbudgeted" not in ROLE_PERMISSIONS["finance"]
        ), (
            "finance must NOT hold budgets.clear_unbudgeted by default "
            "(B102 spec — director-only acknowledgement). If you "
            "intentionally widened finance, update this test."
        )

    def test_finance_lacks_clear_unbudgeted_in_live_db(self, engine):
        with engine.connect() as c:
            row = c.execute(text(
                """
                SELECT 1
                FROM permissions p
                JOIN role_permissions rp ON rp.permission_id = p.id
                JOIN roles r ON r.id = rp.role_id
                WHERE r.code = 'finance'
                  AND p.code = 'budgets.clear_unbudgeted'
                """
            )).first()
        assert row is None, (
            "finance role has budgets.clear_unbudgeted in live DB — "
            "spec says default-off; check seed_rbac.ROLE_PERMISSIONS"
            "['finance'] for an accidental grant."
        )


# ----------------------------------------------------------------------
# T24 — super_admin receives the perm via set(ALL_PERMISSION_CODES).
#       Worth an explicit pin because the rest of the role-grant chain
#       (director, finance) is bespoke; super_admin is the catch-all
#       and we want a regression test if anyone "optimises" the
#       all-perms helper into an explicit list and forgets to add
#       new perms.
# ----------------------------------------------------------------------
class TestSuperAdminHasClearUnbudgeted:
    def test_super_admin_has_clear_unbudgeted_inprocess(self):
        from app.seed_rbac import ROLE_PERMISSIONS

        assert "budgets.clear_unbudgeted" in ROLE_PERMISSIONS["super_admin"]

    def test_super_admin_has_clear_unbudgeted_in_live_db(self, engine):
        with engine.connect() as c:
            row = c.execute(text(
                """
                SELECT 1
                FROM permissions p
                JOIN role_permissions rp ON rp.permission_id = p.id
                JOIN roles r ON r.id = rp.role_id
                WHERE r.code = 'super_admin'
                  AND p.code = 'budgets.clear_unbudgeted'
                """
            )).first()
        assert row is not None
