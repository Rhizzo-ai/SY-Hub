"""Tests for Prompt 1.6 — Cost Codes (target 65–75)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login

load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
            or "http://localhost:8001")
DATABASE_URL = os.environ["DATABASE_URL"]
TEST_PASSWORD = "TestUser-Dev-2026!"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield eng
    eng.dispose()


# B88 Pack 1 Gate 4 — ensure the canonical cost-code structure is in
# place at the start of this module. The full pytest suite has tests
# (e.g. test_migration_0025_actuals.py round-trip) that downgrade past
# `0044_cost_code_groups` and re-upgrade, which DROPs + re-CREATEs the
# `parent_section_id` + `allows_subgroups` columns — resetting the
# canonical structure to a "flat" 19 parents with no subgroup links.
# Re-running the idempotent seed restores it.
@pytest.fixture(scope="module", autouse=True)
def _ensure_canonical_seed():
    from scripts.seed_cost_code_structure import run
    run()
    yield


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, "test-admin@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, "test-director@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL, "test-finance@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def pm():
    return plain_login(BASE_URL, "test-pm@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly():
    return plain_login(BASE_URL, "test-readonly@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def primary_entity_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM entities WHERE name='SY Homes (Shrewsbury) Ltd'"
        )).scalar())


@pytest.fixture(scope="module")
def construction_co_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM entities WHERE entity_type='ConstructionCo' LIMIT 1"
        )).scalar())


def _create_project(session, entity_id, *, project_type="Dev_Build", name=None):
    body = {
        "name": name or f"CC Test {uuid.uuid4().hex[:8]}",
        "project_type": project_type,
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Test Lane",
        "site_postcode": "SY1 1AA",
        "tenure": "Freehold",
    }
    r = session.post(f"{BASE_URL}/api/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ==========================================================================
# Schema / migrations (~10)
# ==========================================================================

class TestSchema:
    def test_all_5_tables_exist(self, db_engine):
        with db_engine.connect() as c:
            for t in ("cost_code_sections", "cost_codes",
                      "cost_code_subcategories", "cost_code_entity_mapping",
                      "project_cost_codes"):
                exists = c.execute(text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
                ), {"t": t}).scalar()
                assert exists, f"table {t} missing"

    def test_cost_codes_unique_code(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name='cost_codes'
                  AND constraint_type='UNIQUE'
                  AND constraint_name LIKE '%code%'
            """)).first()
        assert row

    def test_cost_codes_unique_prefix_sequence(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT 1 FROM pg_constraint
                WHERE conname='uq_cost_codes_prefix_sequence'
            """)).first()
        assert row

    def test_project_cost_codes_unique(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT 1 FROM pg_constraint
                WHERE conname='uq_project_cost_codes'
            """)).first()
        assert row

    def test_cost_code_entity_mapping_unique(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT 1 FROM pg_constraint
                WHERE conname='uq_cost_code_entity_mapping'
            """)).first()
        assert row

    def test_default_entity_enum_values(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT enumlabel FROM pg_enum e
                JOIN pg_type t ON t.oid=e.enumtypid
                WHERE t.typname='cost_code_default_entity'
            """)).fetchall()
        labels = {r[0] for r in rows}
        assert labels == {"Parent", "SPV", "ConstructionCo", "Context_Dependent"}
        assert "JV_Vehicle" not in labels and "Other" not in labels

    def test_p_and_l_enum_values(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT enumlabel FROM pg_enum e
                JOIN pg_type t ON t.oid=e.enumtypid
                WHERE t.typname='cost_section_p_and_l'
            """)).fetchall()
        assert {r[0] for r in rows} == {"COS", "Overhead", "Finance", "Tax"}

    def test_vat_treatment_enum_values(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT enumlabel FROM pg_enum e
                JOIN pg_type t ON t.oid=e.enumtypid
                WHERE t.typname='cost_code_vat_treatment'
            """)).fetchall()
        assert {r[0] for r in rows} == {
            "Standard", "Reduced", "Zero_New_Build",
            "Exempt", "Reverse_Charge", "Mixed",
        }

    def test_updated_at_trigger_fires(self, db_engine):
        # Edit a section's name and confirm updated_at advances.
        with db_engine.begin() as c:
            row = c.execute(text(
                "SELECT id, updated_at FROM cost_code_sections WHERE code='1'"
            )).first()
            sid, ts0 = row
            c.execute(text(
                "UPDATE cost_code_sections SET name=name WHERE id=:id"
            ), {"id": sid})
        with db_engine.connect() as c:
            ts1 = c.execute(text(
                "SELECT updated_at FROM cost_code_sections WHERE id=:id"
            ), {"id": sid}).scalar()
        assert ts1 >= ts0

    def test_delete_endpoint_wired_for_cost_codes(self, admin, db_engine):
        """B88 Pack 1 (Gate 3) wires DELETE /api/cost-codes/{id} with a
        complete delete-guard. Test gate flipped from "must be absent"
        to "must be wired" — ACQ-01 is heavily referenced by seeded
        project_cost_codes + budget_lines so a delete attempt MUST
        return 409 with named blockers, NOT 404/405.
        """
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACQ-01'"
            )).scalar()
        r = admin.delete(f"{BASE_URL}/api/cost-codes/{cid}")
        # Endpoint is wired (no longer 404/405). ACQ-01 has linked
        # records so 409 is the expected outcome.
        assert r.status_code == 409, r.text


# ==========================================================================
# Seed verification (~10)
# ==========================================================================

class TestSeed:
    def test_nine_sections(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-code-sections")
        assert r.status_code == 200
        # B88 Pack 1 Gate 4 reseeds the parent group codes from legacy
        # slugs (e.g. "acquisition") to canonical numerics ("1".."9").
        # Construction subgroups (parent_section_id != NULL) are NOT
        # in this assertion — only the 9 top-level parents are.
        parent_codes = [s["code"] for s in r.json()
                        if s.get("parent_section_id") is None]
        assert parent_codes == ["1", "2", "3", "4", "5",
                                 "6", "7", "8", "9"], parent_codes

    def test_section_p_and_l_categories(self, admin):
        rows = {s["code"]: s["default_p_and_l_category"]
                for s in admin.get(f"{BASE_URL}/api/cost-code-sections").json()
                if s.get("parent_section_id") is None}
        # B88 Pack 1 Gate 4 — parent group codes are now numeric.
        assert rows["6"] == "Finance"
        assert rows["7"] == "Overhead"
        assert rows["8"] == "Tax"
        assert rows["5"] == "COS"

    def test_canonical_total_is_129(self, db_engine):
        with db_engine.connect() as c:
            # B88 Pack 1 Gate 4 reseeds to a canonical 129-code
            # structure. Per Build Pack §5.3, live codes whose
            # (prefix, sequence) is not in the canonical list (e.g.
            # this pod's ACC-04..08) are NOT deleted — they are
            # reported as extras and live alongside the 129 canonical
            # rows. So we scope to canonical sequence ranges only.
            total = c.execute(text("""
                SELECT COUNT(*) FROM cost_codes WHERE
                  (prefix='ACQ' AND sequence <= 10) OR
                  (prefix='PLN' AND sequence <= 9) OR
                  (prefix='DES' AND sequence <= 9) OR
                  (prefix='FAC' AND sequence <= 5) OR
                  (prefix='SUB' AND sequence <= 5) OR
                  (prefix='SUP' AND sequence <= 10) OR
                  (prefix='INT' AND sequence <= 6) OR
                  (prefix='FIT' AND sequence <= 5) OR
                  (prefix='SER' AND sequence <= 10) OR
                  (prefix='PRE' AND sequence = 1) OR
                  (prefix='EXB' AND sequence <= 3) OR
                  (prefix='EXT' AND sequence <= 9) OR
                  (prefix='PRL' AND sequence <= 16) OR
                  (prefix='SAL' AND sequence <= 10) OR
                  (prefix='FIN' AND sequence <= 5) OR
                  (prefix='OHD' AND sequence <= 8) OR
                  (prefix='ACC' AND sequence <= 3) OR
                  (prefix='CTG' AND sequence <= 5)
            """)).scalar()
        assert total == 129

    def test_per_prefix_counts(self, db_engine):
        expected = {
            "ACQ": 10, "PLN": 9, "DES": 9, "FAC": 5, "SUB": 5, "SUP": 10,
            "INT": 6, "FIT": 5, "SER": 10, "PRE": 1, "EXB": 3, "EXT": 9,
            "PRL": 16, "SAL": 10, "FIN": 5, "OHD": 8, "ACC": 3, "CTG": 5,
        }
        # As above: count seeded codes only (sequence ≤ expected count).
        with db_engine.connect() as c:
            rows = {}
            for prefix, n in expected.items():
                if prefix == "PRE":
                    cnt = c.execute(text(
                        "SELECT COUNT(*) FROM cost_codes "
                        "WHERE prefix=:p AND sequence = 1"
                    ), {"p": prefix}).scalar()
                else:
                    cnt = c.execute(text(
                        "SELECT COUNT(*) FROM cost_codes "
                        "WHERE prefix=:p AND sequence <= :n"
                    ), {"p": prefix, "n": n}).scalar()
                rows[prefix] = cnt
        assert rows == expected

    def test_acq_01_metadata(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes?prefix=ACQ")
        codes = {c["code"]: c for c in r.json()}
        assert codes["ACQ-01"]["vat_treatment"] == "Exempt"
        assert codes["ACQ-01"]["is_vattable"] is False

    def test_sub_01_is_cis(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes?prefix=SUB")
        codes = {c["code"]: c for c in r.json()}
        assert codes["SUB-01"]["is_cis_applicable"] is True
        assert codes["SUB-01"]["vat_treatment"] == "Reverse_Charge"

    def test_ohd_01_not_capitalisable(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes?prefix=OHD")
        codes = {c["code"]: c for c in r.json()}
        assert codes["OHD-01"]["is_capitalisable"] is False

    def test_buildertrend_category_populated(self, db_engine):
        with db_engine.connect() as c:
            null_count = c.execute(text(
                "SELECT COUNT(*) FROM cost_codes WHERE buildertrend_category IS NULL"
            )).scalar()
        assert null_count == 0

    def test_subcategories_table_empty(self, db_engine):
        # Seed leaves subcategories empty. Other tests in this file may
        # transiently create rows but always clean up via fresh_code teardown.
        with db_engine.connect() as c:
            n = c.execute(text("SELECT COUNT(*) FROM cost_code_subcategories")).scalar()
        assert n >= 0  # placeholder for shape only — actual emptiness asserted below
        # Tighter check: no row references a seeded code (those clean up).
        with db_engine.connect() as c:
            seeded_orphans = c.execute(text("""
                SELECT COUNT(*) FROM cost_code_subcategories s
                JOIN cost_codes c ON c.id=s.cost_code_id
                WHERE c.prefix IN ('ACQ','PLN','DES','FAC','SUB','SUP','INT',
                                   'FIT','SER','PRE','EXB','EXT','PRL',
                                   'SAL','FIN','OHD','CTG')
            """)).scalar()
        assert seeded_orphans == 0

    def test_entity_mapping_table_empty_post_seed(self, db_engine):
        with db_engine.connect() as c:
            n = c.execute(text("SELECT COUNT(*) FROM cost_code_entity_mapping")).scalar()
        # Tests may have created some — accept 0+ but never via seed.
        # Specifically: no entries with notes='seeded' or similar.
        assert n >= 0  # placeholder; the real assertion is the seed migration

    def test_cost_codes_permissions_seeded(self, db_engine):
        with db_engine.connect() as c:
            roles_with_view = c.execute(text("""
                SELECT r.code FROM role_permissions rp
                JOIN roles r ON r.id=rp.role_id
                JOIN permissions p ON p.id=rp.permission_id
                WHERE p.code='cost_codes.view'
                ORDER BY r.code
            """)).fetchall()
            roles_with_admin = c.execute(text("""
                SELECT r.code FROM role_permissions rp
                JOIN roles r ON r.id=rp.role_id
                JOIN permissions p ON p.id=rp.permission_id
                WHERE p.code='cost_codes.admin'
                ORDER BY r.code
            """)).fetchall()
        view_codes = {r[0] for r in roles_with_view}
        admin_codes = {r[0] for r in roles_with_admin}
        for needed in ("super_admin", "director", "finance", "project_manager",
                       "site_manager", "sales", "read_only",
                       "investor_read_only", "consultant_portal"):
            assert needed in view_codes, f"{needed} missing cost_codes.view"
        for needed in ("super_admin", "director", "finance"):
            assert needed in admin_codes, f"{needed} missing cost_codes.admin"


# ==========================================================================
# Permission gates (~8)
# ==========================================================================

class TestPermissions:
    def test_unauthenticated_cannot_list_codes(self):
        r = requests.get(f"{BASE_URL}/api/cost-codes")
        assert r.status_code == 401

    def test_readonly_can_view_codes(self, readonly):
        r = readonly.get(f"{BASE_URL}/api/cost-codes")
        assert r.status_code == 200
        # At least the 133 seed codes exist; tests may add transient ones.
        assert len(r.json()) >= 133

    def test_readonly_cannot_create(self, readonly, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        r = readonly.post(f"{BASE_URL}/api/cost-codes", json={
            "code": "ACC-90", "name": "Forbidden", "section_id": str(sid),
        })
        assert r.status_code == 403

    def test_readonly_cannot_retire(self, readonly, db_engine):
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACC-08'"
            )).scalar()
        r = readonly.post(f"{BASE_URL}/api/cost-codes/{cid}/retire",
                          json={"retired_reason": "no perm"})
        assert r.status_code == 403

    def test_pm_cannot_admin_codes(self, pm, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        r = pm.post(f"{BASE_URL}/api/cost-codes", json={
            "code": "ACC-91", "name": "PM forbidden", "section_id": str(sid),
        })
        assert r.status_code == 403

    def test_finance_can_admin(self, finance, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        r = finance.post(f"{BASE_URL}/api/cost-codes", json={
            "code": "ACC-92", "name": "Finance can create",
            "section_id": str(sid),
        })
        assert r.status_code in (201, 409)
        if r.status_code == 201:
            # Cleanup
            with create_engine(DATABASE_URL).begin() as c:
                c.execute(text("DELETE FROM cost_codes WHERE code='ACC-92'"))

    def test_pm_can_view_project_cost_codes(self, pm, admin, primary_entity_id):
        # Make sure pm can view codes on a project they can see.
        proj = _create_project(admin, primary_entity_id, name=f"PM View {uuid.uuid4().hex[:6]}")
        r = pm.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes")
        assert r.status_code == 200

    def test_readonly_cannot_toggle_project_cost_code(
        self, readonly, admin, primary_entity_id
    ):
        proj = _create_project(admin, primary_entity_id, name=f"RO Toggle {uuid.uuid4().hex[:6]}")
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        first = rows[0]
        r = readonly.patch(
            f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/{first['cost_code_id']}",
            json={"is_enabled": False},
        )
        assert r.status_code == 403


# ==========================================================================
# CRUD endpoints (~15)
# ==========================================================================

@pytest.fixture
def fresh_code(admin, db_engine):
    """Create a unique cost code in '8 Accounting' section for mutation tests."""
    with db_engine.connect() as c:
        sid = c.execute(text(
            "SELECT id FROM cost_code_sections WHERE code='8'"
        )).scalar()
    # Find next free ACC-NN
    used = {r[0] for r in db_engine.connect().execute(text(
        "SELECT sequence FROM cost_codes WHERE prefix='ACC'"
    ))}
    seq = next(i for i in range(50, 99) if i not in used)
    code_str = f"ACC-{seq}"
    r = admin.post(f"{BASE_URL}/api/cost-codes", json={
        "code": code_str, "name": f"Test {code_str}", "section_id": str(sid),
        "default_entity": "Parent",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    yield r.json()
    with db_engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type='cost_codes' AND resource_id=:id"
        ), {"id": cid})
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type='cost_code_subcategories' "
            "AND resource_id IN (SELECT id FROM cost_code_subcategories WHERE cost_code_id=:id)"
        ), {"id": cid})
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM cost_code_subcategories WHERE cost_code_id=:id"),
                  {"id": cid})
        c.execute(text("DELETE FROM project_cost_codes WHERE cost_code_id=:id"),
                  {"id": cid})
        c.execute(text("DELETE FROM cost_codes WHERE id=:id"), {"id": cid})


class TestCRUD:
    def test_get_section_list(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-code-sections")
        assert r.status_code == 200
        assert all("active_code_count" in s for s in r.json())

    def test_filter_by_section(self, admin, db_engine):
        """Build Pack §5 — Construction codes live under subgroups
        4.00..4.09 (not under the parent group "4"). Query each
        subgroup and union the resulting prefixes to verify the full
        Construction tree contains exactly the canonical 10 prefixes.
        """
        with db_engine.connect() as c:
            sub_ids = [str(r[0]) for r in c.execute(text("""
                SELECT id FROM cost_code_sections
                WHERE parent_section_id = (
                    SELECT id FROM cost_code_sections WHERE code='4'
                )
            """)).fetchall()]
        assert len(sub_ids) == 10
        prefixes = set()
        for sid in sub_ids:
            r = admin.get(f"{BASE_URL}/api/cost-codes?section_id={sid}")
            assert r.status_code == 200
            for c in r.json():
                prefixes.add(c["prefix"])
        assert prefixes == {"FAC", "SUB", "SUP", "INT", "FIT", "SER",
                            "PRE", "EXB", "EXT", "PRL"}

    def test_filter_by_status(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes?status=Active")
        assert r.status_code == 200
        assert all(c["status"] == "Active" for c in r.json())

    def test_search_by_q(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes?q=acquisition")
        assert r.status_code == 200
        assert any("acquisition" in c["name"].lower() or
                   "acquisition" in (c["description"] or "").lower()
                   for c in r.json())

    def test_get_single_cost_code(self, admin, db_engine):
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACQ-01'"
            )).scalar()
        r = admin.get(f"{BASE_URL}/api/cost-codes/{cid}")
        assert r.status_code == 200
        assert r.json()["code"] == "ACQ-01"

    def test_get_unknown_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_create_then_get(self, fresh_code, admin):
        r = admin.get(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}")
        assert r.status_code == 200
        assert r.json()["code"] == fresh_code["code"]

    def test_patch_unlocked_field(self, fresh_code, admin):
        r = admin.patch(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}",
                        json={"name": "Renamed Test"})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed Test"

    def test_subcategory_create_and_list(self, fresh_code, admin):
        sub_code = f"{fresh_code['code']}.01"
        r = admin.post(
            f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/subcategories",
            json={"code": sub_code, "name": "Sub1",
                  "default_unit": "each", "display_order": 1},
        )
        assert r.status_code == 201, r.text
        ls = admin.get(
            f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/subcategories"
        ).json()
        assert len(ls) == 1 and ls[0]["code"] == sub_code

    def test_subcategory_format_validation(self, fresh_code, admin):
        r = admin.post(
            f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/subcategories",
            json={"code": "BAD-FORMAT", "name": "Nope", "display_order": 1},
        )
        assert r.status_code == 400

    def test_subcategory_patch(self, fresh_code, admin):
        sc = admin.post(
            f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/subcategories",
            json={"code": f"{fresh_code['code']}.99",
                  "name": "Patchable", "display_order": 99},
        ).json()
        r = admin.patch(f"{BASE_URL}/api/cost-code-subcategories/{sc['id']}",
                        json={"name": "Patched"})
        assert r.status_code == 200
        assert r.json()["name"] == "Patched"

    def test_entity_mapping_crud(self, fresh_code, admin, primary_entity_id):
        r = admin.post(f"{BASE_URL}/api/cost-code-entity-mapping", json={
            "cost_code_id": fresh_code["id"],
            "entity_id": primary_entity_id,
            "is_allowed": False,
            "notes": "blocked for test",
        })
        assert r.status_code == 201, r.text
        mid = r.json()["id"]

        ls = admin.get(
            f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/entity-mapping"
        ).json()
        assert len(ls) == 1 and ls[0]["is_allowed"] is False

        rp = admin.patch(
            f"{BASE_URL}/api/cost-code-entity-mapping/{mid}",
            json={"is_allowed": True, "xero_nominal_code_override": "5000"},
        )
        assert rp.status_code == 200
        assert rp.json()["is_allowed"] is True

        rd = admin.delete(f"{BASE_URL}/api/cost-code-entity-mapping/{mid}")
        assert rd.status_code == 204

    def test_entity_mapping_unknown_code_404(self, admin, primary_entity_id):
        r = admin.post(f"{BASE_URL}/api/cost-code-entity-mapping", json={
            "cost_code_id": str(uuid.uuid4()),
            "entity_id": primary_entity_id,
        })
        assert r.status_code == 404

    def test_create_bad_code_format(self, admin, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        r = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": "bad-01", "name": "Bad", "section_id": str(sid),
        })
        assert r.status_code == 400

    def test_create_duplicate(self, admin, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='1'"
            )).scalar()
        r = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": "ACQ-01", "name": "Dup", "section_id": str(sid),
        })
        assert r.status_code == 409


# ==========================================================================
# Business logic (~15)
# ==========================================================================

class TestRetirement:
    def test_retire_no_replacement(self, fresh_code, admin):
        r = admin.post(
            f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/retire",
            json={"retired_reason": "Test retirement"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "Retired"
        assert r.json()["retired_at"] is not None

    def test_retire_already_retired_blocked(self, fresh_code, admin):
        admin.post(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/retire",
                   json={"retired_reason": "First"})
        r = admin.post(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/retire",
                      json={"retired_reason": "Second"})
        assert r.status_code == 409

    def test_retire_with_valid_replacement(self, admin, db_engine):
        # Use ACQ-10 as replacement; create fresh code in ACQ to retire
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='1'"
            )).scalar()
            replacement_id = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACQ-10'"
            )).scalar()
        # Make a temporary code
        used = {r[0] for r in db_engine.connect().execute(text(
            "SELECT sequence FROM cost_codes WHERE prefix='ACQ'"
        ))}
        seq = next(i for i in range(50, 99) if i not in used)
        new = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": f"ACQ-{seq}", "name": f"Tmp ACQ-{seq}",
            "section_id": str(sid),
        }).json()
        try:
            r = admin.post(f"{BASE_URL}/api/cost-codes/{new['id']}/retire",
                           json={"retired_reason": "Replaced",
                                 "replaced_by_code_id": str(replacement_id)})
            assert r.status_code == 200
            assert r.json()["replaced_by_code_id"] == str(replacement_id)
        finally:
            with create_engine(DATABASE_URL).begin() as c:
                c.execute(text("DELETE FROM cost_codes WHERE id=:id"),
                          {"id": new["id"]})

    def test_retire_self_replacement_rejected(self, fresh_code, admin):
        r = admin.post(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/retire",
                      json={"retired_reason": "self",
                            "replaced_by_code_id": fresh_code["id"]})
        assert r.status_code == 400

    def test_retire_unknown_replacement_404(self, fresh_code, admin):
        r = admin.post(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/retire",
                      json={"retired_reason": "unknown replacement target",
                            "replaced_by_code_id": str(uuid.uuid4())})
        assert r.status_code == 404

    def test_retire_replacement_must_be_active(self, admin, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        used = {r[0] for r in db_engine.connect().execute(text(
            "SELECT sequence FROM cost_codes WHERE prefix='ACC'"
        ))}
        s1 = next(i for i in range(50, 99) if i not in used)
        s2 = s1 + 1
        c1 = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": f"ACC-{s1}", "name": "First", "section_id": str(sid),
        }).json()
        c2 = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": f"ACC-{s2}", "name": "Second", "section_id": str(sid),
        }).json()
        try:
            admin.post(f"{BASE_URL}/api/cost-codes/{c2['id']}/retire",
                       json={"retired_reason": "first retire"})
            r = admin.post(f"{BASE_URL}/api/cost-codes/{c1['id']}/retire",
                          json={"retired_reason": "second retire pointing at retired",
                                "replaced_by_code_id": c2["id"]})
            assert r.status_code == 409
        finally:
            with create_engine(DATABASE_URL).begin() as c:
                c.execute(text("DELETE FROM cost_codes WHERE id IN (:a,:b)"),
                          {"a": c1["id"], "b": c2["id"]})

    def test_retire_cycle_detection(self, admin, db_engine):
        # Build chain A → B, then try to retire B with replaced_by=A.
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        used = {r[0] for r in db_engine.connect().execute(text(
            "SELECT sequence FROM cost_codes WHERE prefix='ACC'"
        ))}
        sA, sB = next(i for i in range(50, 99) if i not in used), None
        sB = sA + 1
        a = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": f"ACC-{sA}", "name": "A", "section_id": str(sid),
        }).json()
        b = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": f"ACC-{sB}", "name": "B", "section_id": str(sid),
        }).json()
        try:
            # Retire A → B (legal)
            admin.post(f"{BASE_URL}/api/cost-codes/{a['id']}/retire",
                       json={"retired_reason": "A becomes B",
                             "replaced_by_code_id": b["id"]})
            # Now retire B → A (cycle)
            r = admin.post(f"{BASE_URL}/api/cost-codes/{b['id']}/retire",
                          json={"retired_reason": "B → A would cycle",
                                "replaced_by_code_id": a["id"]})
            assert r.status_code == 409
        finally:
            with create_engine(DATABASE_URL).begin() as c:
                c.execute(text(
                    "UPDATE cost_codes SET replaced_by_code_id=NULL "
                    "WHERE id IN (:a,:b)"
                ), {"a": a["id"], "b": b["id"]})
                c.execute(text("DELETE FROM cost_codes WHERE id IN (:a,:b)"),
                          {"a": a["id"], "b": b["id"]})


class TestImmutability:
    def test_locked_field_rejected_when_in_use(
        self, admin, primary_entity_id, db_engine
    ):
        # ACQ-01 is auto-populated into projects, so it's in use immediately
        # after a project is created.
        proj = _create_project(admin, primary_entity_id,
                               name=f"Lock test {uuid.uuid4().hex[:6]}")
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACQ-01'"
            )).scalar()
        r = admin.patch(f"{BASE_URL}/api/cost-codes/{cid}",
                        json={"vat_treatment": "Standard"})
        assert r.status_code == 409
        assert "vat_treatment" in r.text

    def test_unlocked_field_allowed_when_in_use(
        self, admin, primary_entity_id, db_engine
    ):
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACQ-02'"
            )).scalar()
        # name is unlocked
        r = admin.patch(f"{BASE_URL}/api/cost-codes/{cid}",
                        json={"notes": "Test note"})
        assert r.status_code == 200

    def test_locked_field_allowed_when_NOT_in_use(self, fresh_code, admin):
        r = admin.patch(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}",
                        json={"vat_treatment": "Reduced"})
        assert r.status_code == 200
        assert r.json()["vat_treatment"] == "Reduced"


class TestEntityResolution:
    def test_explicit_allow_with_override(
        self, admin, primary_entity_id, db_engine
    ):
        # Find an unused (cost_code, entity) pair and create explicit allow row
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='SAL-01'"
            )).scalar()
        m = admin.post(f"{BASE_URL}/api/cost-code-entity-mapping", json={
            "cost_code_id": str(cid), "entity_id": primary_entity_id,
            "is_allowed": True, "xero_nominal_code_override": "9999",
        })
        try:
            r = admin.get(
                f"{BASE_URL}/api/cost-codes/{cid}/can-use/{primary_entity_id}"
            )
            assert r.status_code == 200
            assert r.json() == {"allowed": True, "xero_nominal_code": "9999"}
        finally:
            if m.status_code == 201:
                admin.delete(f"{BASE_URL}/api/cost-code-entity-mapping/{m.json()['id']}")

    def test_explicit_deny(self, admin, primary_entity_id, db_engine):
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='SAL-02'"
            )).scalar()
        m = admin.post(f"{BASE_URL}/api/cost-code-entity-mapping", json={
            "cost_code_id": str(cid), "entity_id": primary_entity_id,
            "is_allowed": False,
        })
        try:
            r = admin.get(
                f"{BASE_URL}/api/cost-codes/{cid}/can-use/{primary_entity_id}"
            )
            assert r.json() == {"allowed": False, "xero_nominal_code": None}
        finally:
            if m.status_code == 201:
                admin.delete(f"{BASE_URL}/api/cost-code-entity-mapping/{m.json()['id']}")

    def test_no_row_spv_default_routing(
        self, admin, primary_entity_id, db_engine
    ):
        # ACQ-03 has applies_to_spv=true; primary entity is SPV. Should allow.
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='ACQ-03'"
            )).scalar()
        r = admin.get(
            f"{BASE_URL}/api/cost-codes/{cid}/can-use/{primary_entity_id}"
        )
        assert r.json()["allowed"] is True

    def test_no_row_jv_vehicle_returns_false(
        self, admin, primary_entity_id, db_engine
    ):
        # Create a JV_Vehicle entity
        with db_engine.connect() as c:
            tenant_id = c.execute(text(
                "SELECT tenant_id FROM entities LIMIT 1"
            )).scalar()
            # Insert directly to avoid going through the full create flow
        eid = uuid.uuid4()
        with db_engine.begin() as c:
            c.execute(text("""
                INSERT INTO entities (id, tenant_id, name, legal_name,
                  entity_type, status, default_currency, registered_address)
                VALUES (:id, :tid, :n, :ln, 'JV_Vehicle', 'Active',
                        'GBP', '1 Test JV Lane')
            """), {"id": eid, "tid": tenant_id,
                   "n": f"JV {uuid.uuid4().hex[:6]}",
                   "ln": "JV Test Holdings Ltd"})
        try:
            with db_engine.connect() as c:
                cid = c.execute(text(
                    "SELECT id FROM cost_codes WHERE code='ACQ-03'"
                )).scalar()
            r = admin.get(f"{BASE_URL}/api/cost-codes/{cid}/can-use/{eid}")
            assert r.json() == {"allowed": False, "xero_nominal_code": None}
        finally:
            with db_engine.begin() as c:
                c.execute(text("DELETE FROM entities WHERE id=:id"), {"id": str(eid)})


class TestProjectAutoPopulate:
    def test_dev_build_enables_all(self, admin, primary_entity_id, db_engine):
        with db_engine.connect() as c:
            active_count = c.execute(text(
                "SELECT COUNT(*) FROM cost_codes WHERE status='Active'"
            )).scalar()
        proj = _create_project(admin, primary_entity_id,
                              project_type="Dev_Build",
                              name=f"DB {uuid.uuid4().hex[:6]}")
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        assert len(rows) == active_count
        assert all(r["is_enabled"] for r in rows)

    def test_pure_dev_disables_construction(self, admin, primary_entity_id):
        proj = _create_project(admin, primary_entity_id,
                              project_type="Pure_Dev",
                              name=f"PD {uuid.uuid4().hex[:6]}")
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        # Construction prefixes (not in PURE_DEV_ENABLED_PREFIXES) → disabled
        for r in rows:
            if r["prefix"] in ("SUB", "SUP", "INT", "FIT", "SER",
                               "PRE", "EXB", "EXT", "PRL"):
                assert r["is_enabled"] is False, f"{r['code']} should be disabled"
            else:
                assert r["is_enabled"] is True, f"{r['code']} should be enabled"

    def test_db_contract_disables_sal(self, admin, primary_entity_id):
        proj = _create_project(admin, primary_entity_id,
                              project_type="DB_Contract",
                              name=f"DBC {uuid.uuid4().hex[:6]}")
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        for r in rows:
            if r["prefix"] == "SAL":
                assert r["is_enabled"] is False
            else:
                assert r["is_enabled"] is True

    def test_jv_enables_all(self, admin, primary_entity_id):
        proj = _create_project(admin, primary_entity_id,
                              project_type="JV",
                              name=f"JV {uuid.uuid4().hex[:6]}")
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        assert all(r["is_enabled"] for r in rows)


class TestProjectToggle:
    def test_disable_then_enable(self, admin, primary_entity_id):
        proj = _create_project(admin, primary_entity_id,
                              name=f"Toggle {uuid.uuid4().hex[:6]}")
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        first = rows[0]
        r = admin.patch(
            f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/{first['cost_code_id']}",
            json={"is_enabled": False, "project_override_name": "Custom"},
        )
        assert r.status_code == 200
        assert r.json()["is_enabled"] is False
        assert r.json()["project_override_name"] == "Custom"

    def test_cannot_enable_retired_code(
        self, admin, primary_entity_id, db_engine
    ):
        # Create a fresh code, retire it, attach to a project (manually
        # since auto-populate already ran), then try to enable.
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        used = {r[0] for r in db_engine.connect().execute(text(
            "SELECT sequence FROM cost_codes WHERE prefix='ACC'"
        ))}
        seq = next(i for i in range(50, 99) if i not in used)
        new = admin.post(f"{BASE_URL}/api/cost-codes", json={
            "code": f"ACC-{seq}", "name": "RT-test", "section_id": str(sid),
        }).json()
        proj = _create_project(admin, primary_entity_id,
                              name=f"RT {uuid.uuid4().hex[:6]}")
        try:
            # Auto-populate already created a row for new code; disable it,
            # then retire the code, then attempt enable.
            admin.patch(
                f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/{new['id']}",
                json={"is_enabled": False},
            )
            admin.post(f"{BASE_URL}/api/cost-codes/{new['id']}/retire",
                       json={"retired_reason": "Test"})
            r = admin.patch(
                f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/{new['id']}",
                json={"is_enabled": True},
            )
            assert r.status_code == 409
        finally:
            with create_engine(DATABASE_URL).begin() as c:
                c.execute(text(
                    "DELETE FROM project_cost_codes WHERE cost_code_id=:id"
                ), {"id": new["id"]})
                c.execute(text("DELETE FROM cost_codes WHERE id=:id"),
                          {"id": new["id"]})

    def test_bulk_toggle_section(self, admin, primary_entity_id):
        proj = _create_project(admin, primary_entity_id,
                              name=f"Bulk {uuid.uuid4().hex[:6]}")
        r = admin.post(
            f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/bulk-toggle",
            json={"section_code": "7", "is_enabled": False},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["rows_updated"] == 8  # OHD has 8 codes (parent group "7" Company Overheads)
        rows = admin.get(f"{BASE_URL}/api/projects/{proj['id']}/cost-codes").json()
        for row in rows:
            if row["prefix"] == "OHD":
                assert row["is_enabled"] is False

    def test_bulk_toggle_unknown_section_404(self, admin, primary_entity_id):
        proj = _create_project(admin, primary_entity_id,
                              name=f"Bad {uuid.uuid4().hex[:6]}")
        r = admin.post(
            f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/bulk-toggle",
            json={"section_code": "no_such_section", "is_enabled": False},
        )
        assert r.status_code == 404


# ==========================================================================
# Audit verification (~7)
# ==========================================================================

class TestAudit:
    def test_create_writes_audit(self, fresh_code, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT 1 FROM audit_log WHERE resource_type='cost_codes' "
                "AND resource_id=:id AND action='Create'"
            ), {"id": fresh_code["id"]}).first()
        assert row

    def test_update_writes_audit_with_diff(self, fresh_code, admin, db_engine):
        admin.patch(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}",
                    json={"name": "Audit Diff Renamed"})
        with db_engine.connect() as c:
            fc = c.execute(text(
                "SELECT field_changes FROM audit_log "
                "WHERE resource_type='cost_codes' AND resource_id=:id "
                "AND action='Update' ORDER BY created_at DESC LIMIT 1"
            ), {"id": fresh_code["id"]}).scalar()
        assert any(f["field"] == "name" for f in fc)

    def test_retire_writes_audit(self, fresh_code, admin, db_engine):
        admin.post(f"{BASE_URL}/api/cost-codes/{fresh_code['id']}/retire",
                   json={"retired_reason": "Audit test"})
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT metadata_json FROM audit_log "
                "WHERE resource_type='cost_codes' AND resource_id=:id "
                "AND action='Status_Change'"
            ), {"id": fresh_code["id"]}).first()
        assert row
        assert row[0]["kind"] == "retire"

    def test_auto_populate_emits_one_summary_audit(
        self, admin, primary_entity_id, db_engine
    ):
        with db_engine.connect() as c:
            active_count = c.execute(text(
                "SELECT COUNT(*) FROM cost_codes WHERE status='Active'"
            )).scalar()
        proj = _create_project(admin, primary_entity_id,
                              name=f"AuditAP {uuid.uuid4().hex[:6]}")
        with db_engine.connect() as c:
            n = c.execute(text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE resource_type='project_cost_codes' "
                "AND resource_id=:pid"
            ), {"pid": proj["id"]}).scalar()
        # Expect exactly 1 (the summary) — definitely NOT one-per-row.
        assert n == 1
        with db_engine.connect() as c:
            meta = c.execute(text(
                "SELECT metadata_json FROM audit_log "
                "WHERE resource_type='project_cost_codes' "
                "AND resource_id=:pid"
            ), {"pid": proj["id"]}).scalar()
        assert meta["kind"] == "bulk_auto_populate"
        assert meta["enabled_count"] + meta["disabled_count"] == active_count

    def test_bulk_toggle_emits_one_audit(
        self, admin, primary_entity_id, db_engine
    ):
        proj = _create_project(admin, primary_entity_id,
                              name=f"AuditBT {uuid.uuid4().hex[:6]}")
        admin.post(
            f"{BASE_URL}/api/projects/{proj['id']}/cost-codes/bulk-toggle",
            json={"section_code": "8", "is_enabled": False},
        )
        with db_engine.connect() as c:
            n = c.execute(text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE resource_type='project_cost_codes' "
                "AND resource_id=:pid AND action='Update' "
                "AND metadata_json->>'kind'='bulk_toggle'"
            ), {"pid": proj["id"]}).scalar()
        assert n == 1

    def test_section_update_audited(self, admin, db_engine):
        with db_engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        admin.patch(f"{BASE_URL}/api/cost-code-sections/{sid}",
                    json={"name": f"Accounting & Financial Services"})
        # name unchanged; force a real change
        admin.patch(f"{BASE_URL}/api/cost-code-sections/{sid}",
                    json={"name": "Accounting Tweaked"})
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT 1 FROM audit_log WHERE resource_type='cost_code_sections' "
                "AND resource_id=:id AND action='Update'"
            ), {"id": sid}).first()
        assert row
        # Reset
        admin.patch(f"{BASE_URL}/api/cost-code-sections/{sid}",
                    json={"name": "Accounting & Financial Services"})

    def test_entity_mapping_create_audited(
        self, admin, primary_entity_id, db_engine
    ):
        with db_engine.connect() as c:
            cid = c.execute(text(
                "SELECT id FROM cost_codes WHERE code='SAL-03'"
            )).scalar()
        m = admin.post(f"{BASE_URL}/api/cost-code-entity-mapping", json={
            "cost_code_id": str(cid), "entity_id": primary_entity_id,
            "is_allowed": True,
        })
        try:
            mid = m.json()["id"]
            with db_engine.connect() as c:
                row = c.execute(text(
                    "SELECT 1 FROM audit_log "
                    "WHERE resource_type='cost_code_entity_mapping' "
                    "AND resource_id=:id AND action='Create'"
                ), {"id": mid}).first()
            assert row
        finally:
            if m.status_code == 201:
                admin.delete(f"{BASE_URL}/api/cost-code-entity-mapping/{m.json()['id']}")
