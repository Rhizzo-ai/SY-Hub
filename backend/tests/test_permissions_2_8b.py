"""Chat 35 §R5 — 2.8b permission catalogue + role-mapping gates.

Gates 27–28 + 36 of Build Pack 2.8b.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text


from tests._sc_valuations_common import DATABASE_URL


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


# ==========================================================================
# Gate 27 — Permission count = baseline + 7 = 129.
# Bumped by Chat 41 (Prompt 2.7-BE-rev-A): +2 (trades.view, trades.create)
# → 131. Bumped by Chat 41 operator eyeball (Prompt 2.7-FE-revision):
# +1 (suppliers.delete) → 132. Function names retained per the project
# convention.
# ==========================================================================

class TestPermissionCount:
    def test_total_permissions_in_db(self, db_engine):
        with db_engine.connect() as c:
            n = c.execute(text(
                "SELECT count(*) FROM permissions"
            )).scalar()
        assert n == 136, f"expected 136 permissions, got {n}"

    def test_new_2_8b_codes_present(self, db_engine):
        expected = {
            "subcontract_valuations.view",
            "subcontract_valuations.view_sensitive",
            "subcontract_valuations.create",
            "subcontract_valuations.certify",
            "payment_notices.view",
            "payment_notices.create",
            "payment_notices.release",
        }
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT code FROM permissions WHERE code = ANY(:codes)"
            ), {"codes": list(expected)}).fetchall()
        codes = {r[0] for r in rows}
        assert codes == expected, f"missing: {expected - codes}"

    def test_total_permissions_matches_catalogue(self):
        from app.seed_rbac import PERMISSION_CATALOGUE
        # Chat 41 (Prompt 2.7-BE-rev-A): +2 catalogue rows
        # (trades.view, trades.create) → 131. Chat 41 operator
        # eyeball (Prompt 2.7-FE-revision): +1 (suppliers.delete) → 132.
        # Chat 45 (Build Pack 2.7-DOCS-BE): +1 (documents.move) → 133.
        # B88 Pack 1 (Gate 2): +3 (cost_codes.{create,edit,delete}) → 136.
        assert len(PERMISSION_CATALOGUE) == 136


# ==========================================================================
# Gate 28 — Role mapping.
# ==========================================================================

class TestRoleMapping:
    def _codes_for_role(self, db, role_code: str) -> set[str]:
        rows = db.execute(text("""
            SELECT p.code FROM permissions p
              JOIN role_permissions rp ON rp.permission_id = p.id
              JOIN roles r ON r.id = rp.role_id
             WHERE r.code = :rc
        """), {"rc": role_code}).fetchall()
        return {r[0] for r in rows}

    def test_finance_holds_certify_and_release(self, db_engine):
        """Gate 28 — `.certify` + `.release` mapped to finance."""
        with db_engine.connect() as c:
            codes = self._codes_for_role(c, "finance")
        assert "subcontract_valuations.certify" in codes
        assert "payment_notices.release" in codes
        assert "payment_notices.create" in codes
        assert "subcontract_valuations.view_sensitive" in codes

    def test_director_holds_full_set(self, db_engine):
        with db_engine.connect() as c:
            codes = self._codes_for_role(c, "director")
        for c2 in (
            "subcontract_valuations.view",
            "subcontract_valuations.view_sensitive",
            "subcontract_valuations.create",
            "subcontract_valuations.certify",
            "payment_notices.view",
            "payment_notices.create",
            "payment_notices.release",
        ):
            assert c2 in codes, f"director missing {c2}"

    def test_pm_holds_create_and_view_no_certify(self, db_engine):
        """Gate 28 — PM has create/view but NOT certify/release."""
        with db_engine.connect() as c:
            codes = self._codes_for_role(c, "project_manager")
        assert "subcontract_valuations.view" in codes
        assert "subcontract_valuations.view_sensitive" in codes
        assert "subcontract_valuations.create" in codes
        assert "payment_notices.view" in codes
        # NOT in PM:
        assert "subcontract_valuations.certify" not in codes
        assert "payment_notices.release" not in codes
        assert "payment_notices.create" not in codes

    def test_read_only_only_views(self, db_engine):
        with db_engine.connect() as c:
            codes = self._codes_for_role(c, "read_only")
        assert "subcontract_valuations.view" in codes
        assert "payment_notices.view" in codes
        assert "subcontract_valuations.certify" not in codes
        assert "subcontract_valuations.create" not in codes
        assert "payment_notices.release" not in codes


# ==========================================================================
# Gate 36 — Permission action enum carries certify + release.
# ==========================================================================

class TestPermissionActionEnum:
    def test_certify_value_in_enum(self, db_engine):
        with db_engine.connect() as c:
            vals = [
                r[0] for r in c.execute(text("""
                    SELECT unnest(enum_range(NULL::permission_action))
                """)).fetchall()
            ]
        assert "certify" in vals
        assert "release" in vals

    def test_new_resources_in_resource_enum(self, db_engine):
        with db_engine.connect() as c:
            vals = [
                r[0] for r in c.execute(text("""
                    SELECT unnest(enum_range(NULL::permission_resource))
                """)).fetchall()
            ]
        assert "subcontract_valuations" in vals
        assert "payment_notices" in vals
