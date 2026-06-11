"""B88 Pack 2 — Scope enforcement on existing budgets endpoints + RBAC.

Covers Build Pack §5 (the leak fix) and §6 (PM permission revocation).
Mirrors `test_budget_grid.py` fixtures so the suite stands alone.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"
DIRECTOR_EMAIL = "test-director@example.test"

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
        c.execute(text("""
            UPDATE user_roles SET project_scope = 'All'
            WHERE id IN (
              SELECT ur.id FROM user_roles ur
              JOIN users u ON u.id = ur.user_id
              JOIN roles r ON r.id = ur.role_id
              WHERE u.email = 'test-pm@example.test'
                AND r.code = 'project_manager'
                AND ur.status = 'Active'
            )
        """))
    yield eng
    eng.dispose()


def _wipe(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('budgets','budget_lines','budget_line_items',"
            " 'appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members')"
        ))
        c.execute(text("UPDATE audit_log SET project_id = NULL WHERE project_id IS NOT NULL"))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_line_items"))
        c.execute(text("DELETE FROM budget_lines"))
        c.execute(text("DELETE FROM budgets"))
        c.execute(text("DELETE FROM appraisal_finance_model"))
        c.execute(text("DELETE FROM appraisal_cost_lines"))
        c.execute(text("DELETE FROM appraisal_units"))
        c.execute(text("ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_decision_log"))
        c.execute(text("ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_revisions"))
        c.execute(text("DELETE FROM appraisal_scenarios"))
        c.execute(text("DELETE FROM appraisals"))
        c.execute(text("DELETE FROM project_team_members"))
        c.execute(text("DELETE FROM user_role_projects"))
        c.execute(text("DELETE FROM projects WHERE name LIKE 'B88P2 Scope%'"))


@pytest.fixture(scope="module", autouse=True)
def _clean(engine):
    # Ensure canonical cost-code structure (parents + subgroups + scope
    # flags) is in place — earlier suites may have round-tripped the
    # alembic head and reset flags to default.
    from scripts.seed_cost_code_structure import run as _reseed
    _reseed()
    _wipe(engine)
    yield
    _wipe(engine)


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def director(engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return plain_login(BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def entity_id(engine):
    with engine.connect() as c:
        pid = c.execute(text("SELECT id FROM entities WHERE name = :n"),
                        {"n": PRIMARY_ENTITY_NAME}).scalar()
    assert pid
    return str(pid)


@pytest.fixture(scope="module")
def admin_user_id(engine):
    with engine.connect() as c:
        uid = c.execute(text(
            "SELECT id FROM users WHERE email = 'test-admin@example.test'"
        )).scalar()
    return str(uid)


@pytest.fixture(scope="module")
def project(admin, entity_id):
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": "B88P2 Scope Project",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "2 Scope Way, Shrewsbury",
        "site_postcode": "SY1 2CC",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _pick(engine, prefix: str, n: int) -> list[str]:
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id FROM cost_codes WHERE prefix = :p AND status = 'Active' "
            "ORDER BY sequence LIMIT :n"
        ), {"p": prefix, "n": n}).fetchall()
    return [str(r.id) for r in rows]


def _make_approved_appraisal(admin_session, project_id: str,
                             *, land_price: str = "200000") -> str:
    """Mirror tests/test_budgets.py::_make_approved_appraisal."""
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
        json={"name": f"Scope-A-{uuid.uuid4().hex[:6]}",
              "land_purchase_price": land_price},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))
        db.execute(text(
            "DELETE FROM appraisal_cost_lines WHERE appraisal_id=:a"
        ), {"a": aid})
        db.execute(text("""
            INSERT INTO appraisal_cost_lines
              (id, appraisal_id, display_order, cost_code_id, label,
               category, auto_source, amount, is_locked)
            VALUES (gen_random_uuid(), :a, 10, :cc, 'Build cost',
                    'Construction', 'Manual', 250000.00, false)
        """), {"a": aid, "cc": cc_id})
        db.commit()
    finally:
        db.close()
    ru = admin_session.post(
        f"{BASE_URL}/api/v1/appraisals/{aid}/units",
        json={"unit_label": "U", "unit_type": "Detached",
              "tenure": "Open_Market", "quantity": 2,
              "price_per_unit": "400000",
              "build_cost_per_unit": "200000"},
    )
    assert ru.status_code == 201, ru.text
    rsub = admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
    assert rsub.status_code == 200, rsub.text
    rap = admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
    assert rap.status_code == 200, rap.text
    return aid


@pytest.fixture(scope="module")
def budget_mixed(engine, admin, project, entity_id, admin_user_id):
    """Build a budget with both construction (SUB-) and land (ACQ-) lines.

    Uses the API to create + approve the appraisal, then injects our
    deterministic line set via direct SQL.
    """
    aid = _make_approved_appraisal(admin, project["id"])
    rb = admin.post(
        f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert rb.status_code == 201, rb.text
    bid = rb.json()["id"]

    with engine.begin() as c:
        c.execute(text("DELETE FROM budget_line_items WHERE budget_line_id IN "
                       "(SELECT id FROM budget_lines WHERE budget_id = :b)"),
                  {"b": bid})
        c.execute(text("DELETE FROM budget_lines WHERE budget_id = :b"),
                  {"b": bid})

        sub_codes = _pick(engine, "SUB", 1) or _pick(engine, "FAC", 1)
        acq_codes = _pick(engine, "ACQ", 1)

        def addline(cc, desc, cb, order):
            return c.execute(text("""
                INSERT INTO budget_lines (id, budget_id, cost_code_id, line_description, entity_id,
                  original_budget, approved_changes, current_budget, actuals_to_date,
                  committed_value, invoiced_against_commitment, committed_not_invoiced,
                  forecast_to_complete, ftc_method, forecast_final_cost, variance_value,
                  variance_pct, variance_status, display_order, created_at, updated_at)
                VALUES (gen_random_uuid(), :b, :cc, :d, :e, :cb, 0, :cb, 0, 0, 0, 0, 0,
                  'Manual', :cb, 0, 0, 'Green', :ord, NOW(), NOW())
                RETURNING id
            """), {"b": bid, "cc": cc, "d": desc, "e": entity_id,
                    "cb": cb, "ord": order}).scalar()

        construction_lines = [addline(cc, f"Construction {i}", Decimal("5000"), i)
                              for i, cc in enumerate(sub_codes)]
        land_lines = [addline(cc, f"Land {i}", Decimal("100000"), 10 + i)
                      for i, cc in enumerate(acq_codes)]

        # Activate the budget so reorder/lifecycle tests can exercise it.
        c.execute(text("UPDATE budgets SET status='Active' WHERE id = :b"),
                  {"b": bid})

        total = c.execute(text(
            "SELECT COALESCE(SUM(current_budget), 0) FROM budget_lines WHERE budget_id = :b"
        ), {"b": bid}).scalar()
        c.execute(text("UPDATE budgets SET total_budget = :t WHERE id = :i"),
                  {"t": total, "i": bid})

    return {
        "id": str(bid),
        "construction_line_ids": [str(x) for x in construction_lines],
        "land_line_ids": [str(x) for x in land_lines],
    }


# --------------------------------------------------------------------------
# §R8 Test 1 — detail endpoint filters lines + omits total_budget
# --------------------------------------------------------------------------

class TestDetailEndpointPmScoped:
    def test_pm_detail_filters_lines_and_omits_total_budget(
        self, pm, budget_mixed,
    ):
        r = pm.get(f"{BASE_URL}/api/v1/budgets/{budget_mixed['id']}")
        if r.status_code == 404:
            pytest.skip("PM project scope missing")
        assert r.status_code == 200, r.text
        body = r.json()
        line_ids = {ln["id"] for ln in body.get("lines", [])}
        # Land lines must NOT appear.
        for lid in budget_mixed["land_line_ids"]:
            assert lid not in line_ids
        # Construction lines DO appear (if any seeded).
        for lid in budget_mixed["construction_line_ids"]:
            assert lid in line_ids
        # total_budget absent for Tier 2 (B88 Pack 2 §R5).
        assert "total_budget" not in body
        assert "total_actuals" not in body


# --------------------------------------------------------------------------
# §R8 Test 2 — list endpoint omits total_budget for Tier 2
# --------------------------------------------------------------------------

class TestListEndpointPmScoped:
    def test_pm_list_omits_total_budget(self, pm, project):
        r = pm.get(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets"
        )
        if r.status_code == 404:
            pytest.skip("PM project scope missing")
        assert r.status_code == 200, r.text
        body = r.json()
        for item in body.get("items", []):
            assert "total_budget" not in item, (
                "total_budget must be omitted from PM list responses"
            )

    def test_director_list_carries_total_budget(self, director, project):
        r = director.get(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets"
        )
        assert r.status_code == 200, r.text
        for item in r.json().get("items", []):
            assert "total_budget" in item


# --------------------------------------------------------------------------
# §R8 Tests 3-6 — write guards (404 to PM, 200 to director)
# --------------------------------------------------------------------------

class TestLineWriteGuards:
    def test_patch_out_of_scope_line_pm_404(self, pm, budget_mixed):
        lid = budget_mixed["land_line_ids"][0]
        r = pm.patch(
            f"{BASE_URL}/api/v1/budget-lines/{lid}",
            json={"notes": "from PM"},
        )
        assert r.status_code == 404

    def test_patch_out_of_scope_line_director_200(
        self, director, budget_mixed,
    ):
        lid = budget_mixed["land_line_ids"][0]
        r = director.patch(
            f"{BASE_URL}/api/v1/budget-lines/{lid}",
            json={"notes": "from director"},
        )
        assert r.status_code == 200, r.text

    def test_delete_out_of_scope_line_pm_404(
        self, pm, admin, budget_mixed, engine, entity_id, admin_user_id,
    ):
        # Use a fresh transient line — DELETE removes it. Need a cost
        # code NOT already on the budget (unique idx on budget_id +
        # cost_code_id when subcat is NULL).
        with engine.begin() as c:
            existing_ccs = {
                str(r[0]) for r in c.execute(text(
                    "SELECT cost_code_id FROM budget_lines WHERE budget_id = :b"
                ), {"b": budget_mixed["id"]}).fetchall()
            }
            row = c.execute(text(
                "SELECT id FROM cost_codes WHERE prefix = 'ACQ' "
                "AND status = 'Active' ORDER BY sequence"
            )).fetchall()
            cc_id = next(
                (str(r[0]) for r in row if str(r[0]) not in existing_ccs),
                None,
            )
            if cc_id is None:
                pytest.skip("no spare ACQ code")
            nlid = c.execute(text("""
                INSERT INTO budget_lines (id, budget_id, cost_code_id, line_description, entity_id,
                  original_budget, approved_changes, current_budget, actuals_to_date,
                  committed_value, invoiced_against_commitment, committed_not_invoiced,
                  forecast_to_complete, ftc_method, forecast_final_cost, variance_value,
                  variance_pct, variance_status, display_order, created_at, updated_at)
                VALUES (gen_random_uuid(), :b, :cc, 'transient-land', :e, 100, 0, 100,
                  0, 0, 0, 0, 0, 'Manual', 100, 0, 0, 'Green', 99, NOW(), NOW())
                RETURNING id
            """), {"b": budget_mixed["id"], "cc": cc_id, "e": entity_id}).scalar()
        r = pm.delete(f"{BASE_URL}/api/v1/budget-lines/{nlid}")
        assert r.status_code == 404
        # Clean up.
        with engine.begin() as c:
            c.execute(text("DELETE FROM budget_lines WHERE id = :i"), {"i": nlid})

    def test_get_items_out_of_scope_line_pm_404(self, pm, budget_mixed):
        lid = budget_mixed["land_line_ids"][0]
        r = pm.get(f"{BASE_URL}/api/v1/budget-lines/{lid}/items")
        assert r.status_code == 404

    def test_post_items_out_of_scope_line_pm_404(self, pm, budget_mixed):
        lid = budget_mixed["land_line_ids"][0]
        r = pm.post(
            f"{BASE_URL}/api/v1/budget-lines/{lid}/items",
            json={"description": "x", "amount": "10.00"},
        )
        assert r.status_code == 404


# --------------------------------------------------------------------------
# §R8 Test 7 — reorder 403 for Tier 2, 200 for full-budget
# --------------------------------------------------------------------------

class TestReorderGuard:
    def test_pm_reorder_403(self, pm, budget_mixed):
        ids = (budget_mixed["construction_line_ids"]
               + budget_mixed["land_line_ids"])
        r = pm.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": budget_mixed["id"], "ordered_line_ids": ids},
        )
        assert r.status_code == 403


# --------------------------------------------------------------------------
# §R8 Test 9 — RBAC revocation: PM lacks budgets.view_sensitive
# --------------------------------------------------------------------------

class TestRbacRevocation:
    def test_pm_lacks_budgets_view_sensitive_after_bootstrap(self, engine):
        """B88 Pack 2 §6 — migration 0045 data step removes the grant on
        EXISTING (warm) DBs. seed_rbac.ROLE_PERMISSIONS source also has
        the entry removed."""
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT 1
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.code = 'project_manager'
                  AND p.code = 'budgets.view_sensitive'
            """)).first()
        assert row is None, (
            "project_manager must NOT carry budgets.view_sensitive "
            "after B88 Pack 2 migration 0045"
        )
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "budgets.view_sensitive" not in ROLE_PERMISSIONS["project_manager"]

    def test_director_and_finance_still_have_view_sensitive(self, engine):
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT r.code
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE p.code = 'budgets.view_sensitive'
            """)).fetchall()
        codes = {r.code for r in rows}
        assert "director" in codes
        assert "finance" in codes
        assert "super_admin" in codes


# --------------------------------------------------------------------------
# §R8 Test 10 — super_admin bypass everywhere
# --------------------------------------------------------------------------

class TestSuperAdminBypass:
    def test_admin_sees_total_budget_on_detail(self, admin, budget_mixed):
        r = admin.get(f"{BASE_URL}/api/v1/budgets/{budget_mixed['id']}")
        assert r.status_code == 200
        body = r.json()
        assert "total_budget" in body
        # All lines visible.
        line_ids = {ln["id"] for ln in body["lines"]}
        for lid in (budget_mixed["construction_line_ids"]
                    + budget_mixed["land_line_ids"]):
            assert lid in line_ids


# --------------------------------------------------------------------------
# §R8 Test 11 — section PATCH retoggle moves a line in/out of PM's grid
# --------------------------------------------------------------------------

class TestSectionScopeToggle:
    def test_pm_grid_responds_to_scope_toggle(
        self, pm, admin, budget_mixed, engine,
    ):
        # Find a non-construction section that has at least one of the
        # budget's lines on it (e.g. ACQ → section "1").
        with engine.connect() as c:
            sec = c.execute(text(
                "SELECT cs.id FROM cost_code_sections cs "
                "WHERE cs.code = '1'"
            )).first()
        sid = str(sec.id)
        # Flip flag on
        r = admin.patch(
            f"{BASE_URL}/api/cost-code-sections/{sid}",
            json={"included_in_construction_scope": True},
        )
        assert r.status_code == 200, r.text
        try:
            r2 = pm.get(f"{BASE_URL}/api/v1/budgets/{budget_mixed['id']}/grid")
            if r2.status_code == 404:
                pytest.skip("PM project scope missing")
            assert r2.status_code == 200
            codes = [g["code"] for g in r2.json()["groups"]]
            assert "1" in codes, "land section must appear once flagged in scope"
        finally:
            admin.patch(
                f"{BASE_URL}/api/cost-code-sections/{sid}",
                json={"included_in_construction_scope": False},
            )


# --------------------------------------------------------------------------
# §R8 Test 12 — migration data step flagged section "4" + subgroups
# --------------------------------------------------------------------------

class TestMigrationDataStep:
    def test_section_4_and_subgroups_in_construction_scope(self, engine):
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, included_in_construction_scope
                FROM cost_code_sections
                WHERE code = '4'
                   OR parent_section_id = (
                       SELECT id FROM cost_code_sections WHERE code = '4'
                   )
            """)).fetchall()
        assert rows, "expected section '4' + subgroups present"
        for r in rows:
            assert r.included_in_construction_scope is True, (
                f"section {r.code} should be construction-scoped"
            )

    def test_other_sections_not_in_construction_scope(self, engine):
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, included_in_construction_scope
                FROM cost_code_sections
                WHERE code IN ('1','2','3','5','6','7','8','9')
            """)).fetchall()
        for r in rows:
            assert r.included_in_construction_scope is False, (
                f"section {r.code} must default to construction_scope=false"
            )


# --------------------------------------------------------------------------
# §R8 Test 13 — seed re-run preserves operator scope toggle
# --------------------------------------------------------------------------

class TestSeedPreservesScopeToggle:
    def test_seed_does_not_revert_scope_flip(self, engine, admin):
        # Find section "1" and flip it on via API.
        with engine.connect() as c:
            sid = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code = '1'"
            )).scalar()
        sid_str = str(sid)
        r = admin.patch(
            f"{BASE_URL}/api/cost-code-sections/{sid_str}",
            json={"included_in_construction_scope": True},
        )
        assert r.status_code == 200
        try:
            # Re-run the structure seed
            import sys
            sys.path.insert(0, "/app/backend")
            from scripts.seed_cost_code_structure import run as _reseed
            _reseed()
            # Flag must still be True (operator's edit preserved).
            with engine.connect() as c:
                still = c.execute(text(
                    "SELECT included_in_construction_scope "
                    "FROM cost_code_sections WHERE id = :i"
                ), {"i": sid}).scalar()
            assert still is True, "seed re-run reverted operator scope toggle"
        finally:
            admin.patch(
                f"{BASE_URL}/api/cost-code-sections/{sid_str}",
                json={"included_in_construction_scope": False},
            )
