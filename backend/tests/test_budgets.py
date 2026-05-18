"""Prompt 2.4A — Budgets Core: backend tests.

Covers:
- Service-layer create_from_appraisal (success + every guard)
- State machine (activate/lock/unlock/close/new-version + illegal transitions)
- Tenant isolation via Pattern α (cross-tenant 404s)
- Line + item CRUD (incl. lock/terminal state guards)
- FTC / FFC / variance recompute math
- Audit log coverage on every CUD
- Role-based access (PM creates, director/super_admin force-unlock, readonly view)
- Concurrency invariant (one is_current per project, partial-unique index)
- API integration over HTTP (cookies-only contract)
- Sensitive-field gating on responses
- Detail endpoint query budget (≤ 5)
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, select, text

from tests.conftest import login_with_auto_enroll, plain_login


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
DIRECTOR_EMAIL = "test-director@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"
READONLY_EMAIL = "test-readonly@example.test"
SITE_MANAGER_EMAIL = "test-site@example.test"  # Chat 16.5 #81 — site_manager fixture

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


# --------------------------------------------------------------------------
# Fixtures (mirror tests/test_appraisals.py)
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


def _wipe_budgets(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('budgets','budget_lines','budget_line_items',"
            " 'appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members')"
        ))
        c.execute(text("UPDATE audit_log SET project_id = NULL "
                       "WHERE project_id IS NOT NULL"))
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
        c.execute(text("DELETE FROM projects WHERE name LIKE 'Budget Test%'"))


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    _wipe_budgets(db_engine)
    yield
    _wipe_budgets(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(db_engine):
    return plain_login(BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def site_manager(db_engine):
    """Chat 16.5 #81 — site_manager session for negative-perm coverage on
    POST /budgets/from-appraisal. test-site@example.test is seeded by
    scripts/seed_test_users.py with role_code='site_manager' (entity_scope=
    All, project_scope=All), which has documents/programmes view+edit but
    NO budgets.create — yielding the 403 the test asserts."""
    return plain_login(BASE_URL, SITE_MANAGER_EMAIL, PWD)


@pytest.fixture(scope="module")
def entity_id(db_engine):
    with db_engine.connect() as c:
        pid = c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": PRIMARY_ENTITY_NAME},
        ).scalar()
    assert pid
    return str(pid)


@pytest.fixture(scope="module")
def project(admin, entity_id):
    """One shared project for the whole module."""
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": "Budget Test Project",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Budget Way, Shrewsbury",
        "site_postcode": "SY1 2AA",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _make_approved_appraisal(admin_session, project_id: str,
                             *, land_price: str = "200000",
                             with_units: bool = True) -> str:
    """Create + approve an appraisal so it can seed a budget. Returns id.

    The default skeleton lines (Percentage_Of_*, SDLT_Engine, Finance_Engine)
    are seeded without cost_code_ids — this would trip the B5 guard. We
    wipe them and inject a single Manual line with an explicit cost_code_id
    so the budget seed path is exercisable.
    """
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
        json={"name": f"Appraisal-{uuid.uuid4().hex[:6]}",
              "land_purchase_price": land_price},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # Wipe skeleton lines and inject one Manual line with cost_code_id.
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

    if with_units:
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
def approved_appraisal_id(admin, project):
    """Module-scoped approved appraisal (won't be reused for create as
    is_current on first call)."""
    return _make_approved_appraisal(admin, project["id"])


# --------------------------------------------------------------------------
# Permissions catalogue / RBAC sanity
# --------------------------------------------------------------------------

class TestBudgetPermissions:
    def test_budgets_admin_permission_exists(self):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            row = db.execute(text(
                "SELECT code, action, is_sensitive FROM permissions "
                "WHERE code='budgets.admin'"
            )).first()
            assert row is not None, "budgets.admin must be seeded"
            assert row[1] == "admin"
            assert row[2] is True
        finally:
            db.close()

    def test_pm_role_has_budgets_create(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "budgets.create" in ROLE_PERMISSIONS["project_manager"]

    def test_director_has_budgets_admin(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "budgets.admin" in ROLE_PERMISSIONS["director"]

    def test_super_admin_has_budgets_admin(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "budgets.admin" in ROLE_PERMISSIONS["super_admin"]

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_existing_budgets_approve_perm_still_present(self):
        """Build Pack #72 — B23 risk register regression guard. The legacy
        `budgets.approve` permission MUST survive the 2.4A migration.
        Asserted directly against the live permissions table (the seed runs
        on bootstrap, so any migration that drops the row would surface as
        a missing seed regression here)."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            rows = db.execute(text(
                "SELECT code FROM permissions WHERE code='budgets.approve'"
            )).all()
        finally:
            db.close()
        assert len(rows) == 1, (
            f"Expected exactly one 'budgets.approve' permission row, "
            f"found {len(rows)}. B23 regression — the 2.4A scope's perm "
            f"catalogue must continue to expose the legacy approve perm."
        )

    def test_pm_role_does_not_have_budgets_admin(self):
        """Build Pack #74 — negative permission guard. project_manager
        must not have budgets.admin (only super_admin and director do).
        Asserted at both the seed-source layer and the persisted role
        table to catch drift in either direction."""
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "budgets.admin" not in ROLE_PERMISSIONS["project_manager"]
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            row = db.execute(text("""
                SELECT 1
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.code = 'project_manager'
                  AND p.code = 'budgets.admin'
            """)).first()
        finally:
            db.close()
        assert row is None, (
            "project_manager has been granted budgets.admin in "
            "role_permissions — negative permission guard violated."
        )


# --------------------------------------------------------------------------
# Service-layer: create_from_appraisal (B5 guards + happy path)
# --------------------------------------------------------------------------

class TestCreateFromAppraisal:
    def test_create_via_api(self, admin, project):
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "Draft"
        assert body["is_current"] is True
        assert body["version_number"] >= 1
        assert isinstance(body["lines"], list)
        # source_appraisal_id round-trips
        assert body["source_appraisal_id"] == aid

    def test_create_blocks_when_appraisal_not_approved(self, admin, project):
        # Create a Draft (not approved) appraisal.
        r0 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/appraisals",
            json={"name": "NotApproved", "land_purchase_price": "100000"},
        )
        assert r0.status_code == 201
        aid = r0.json()["id"]
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 400, r.text
        assert "Approved" in r.json().get("detail", "")

    def test_create_404_for_unknown_appraisal(self, admin, project):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": str(uuid.uuid4())},
        )
        assert r.status_code == 400, r.text

    def test_create_blocks_when_existing_current_non_terminal(
        self, admin, project,
    ):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid_a = _make_approved_appraisal(admin, project["id"])
        r1 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid_a},
        )
        assert r1.status_code == 201
        aid_b = _make_approved_appraisal(admin, project["id"])
        r2 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid_b},
        )
        # Existing Draft is_current must block re-seed.
        assert r2.status_code == 409, r2.text

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_original_budget_total_matches_appraisal_total_cost(
        self, admin, project,
    ):
        """Build Pack #6 — sum of seeded `original_budget` values across
        all budget lines must equal the appraisal's cost-line total
        (`SUM(amount) FROM appraisal_cost_lines`). This is the post-merge
        invariant: even when two appraisal_cost_lines collapse onto the
        same cost_code (and merge into one budget_line), the total is
        preserved."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        # Sum the appraisal cost-line amounts (the seed source).
        db = SessionLocal()
        try:
            appraisal_total = db.execute(text(
                "SELECT COALESCE(SUM(amount), 0) "
                "FROM appraisal_cost_lines WHERE appraisal_id=:a"
            ), {"a": aid}).scalar()
        finally:
            db.close()
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        line_total = sum(
            (Decimal(line["original_budget"]) for line in body["lines"]),
            Decimal("0"),
        )
        assert line_total.quantize(Decimal("0.01")) == \
            Decimal(appraisal_total).quantize(Decimal("0.01")), (
                f"sum(original_budget)={line_total} ≠ "
                f"appraisal_cost_lines.SUM(amount)={appraisal_total}"
            )

    def test_create_handles_zero_cost_lines_appraisal(self, project):
        """Build Pack #10 — `create_from_appraisal` against an Approved
        appraisal with ZERO cost lines must raise BudgetCreationError
        ('no cost lines; nothing to seed'). Verified at the service
        layer because the HTTP submit/approve pipeline itself rejects
        cost-line-less appraisals on /submit, which would mask the case
        under test. Mirrors the direct-Appraisal-insert pattern used by
        TestServiceGuards in this module."""
        from app.db import SessionLocal
        from app.services.budgets import create_from_appraisal
        from app.services.budget_errors import BudgetCreationError
        from app.models.appraisals import Appraisal
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
            uid = db.scalar(text(
                "SELECT id FROM users WHERE email='test-admin@example.test'"
            ))
            u = db.get(User, uid)
            perms = compute_effective_permissions(db, u.id, u.tenant_id)
            ap = Appraisal(
                project_id=uuid.UUID(project["id"]),
                version_number=88, name=f"empty-{uuid.uuid4().hex[:6]}",
                reference_date=date(2025, 1, 1),
                land_purchase_price=Decimal("100000"),
                sdlt_category="Residential_Standard",
                developer_relief=False,
                project_duration_months=12,
                status="Approved", is_current=False,
                created_by_user_id=u.id,
            )
            db.add(ap)
            db.flush()
            # Direct insert via SQLAlchemy ORM does NOT seed skeleton
            # cost lines (those come from the API layer). But belt-and-
            # braces: explicitly delete in case any trigger/observer
            # later seeds them.
            db.execute(text(
                "DELETE FROM appraisal_cost_lines WHERE appraisal_id=:a"
            ), {"a": ap.id})
            db.flush()
            with pytest.raises(BudgetCreationError) as ei:
                create_from_appraisal(
                    db, project_id=uuid.UUID(project["id"]),
                    source_appraisal_id=ap.id, user=u, perms=perms,
                )
            msg = str(ei.value).lower()
            assert "no cost lines" in msg or "nothing to seed" in msg, (
                f"unexpected error message for zero-cost-lines case: "
                f"{ei.value!r}"
            )
        finally:
            db.rollback()
            db.close()


# --------------------------------------------------------------------------
# Service-level: B5 guards, merging, isolation (work directly on the DB
# session to avoid HTTP overhead)
# --------------------------------------------------------------------------

@pytest.fixture
def db_session():
    from app.db import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _admin_user(db):
    from app.models.user import User
    return db.scalar(text("SELECT id FROM users WHERE email='rhys@syhomes.co.uk'"))


def _perms_for(db, user_id):
    from app.auth.permissions import compute_effective_permissions
    from app.models.user import User
    u = db.get(User, user_id)
    return u, compute_effective_permissions(db, u.id, u.tenant_id)


class TestServiceGuards:
    def test_b5_guard_null_cost_code_id(self, project):
        """B5: cost lines with null cost_code_id must raise BudgetCreationError."""
        from app.db import SessionLocal
        from app.services.budgets import create_from_appraisal
        from app.services.budget_errors import BudgetCreationError
        from app.models.appraisals import (
            Appraisal, AppraisalCostLine,
        )
        db = SessionLocal()
        try:
            uid = db.scalar(text(
                "SELECT id FROM users WHERE email='test-admin@example.test'"
            ))
            from app.models.user import User
            from app.auth.permissions import compute_effective_permissions
            u = db.get(User, uid)
            perms = compute_effective_permissions(db, u.id, u.tenant_id)

            ap = Appraisal(
                project_id=uuid.UUID(project["id"]),
                version_number=99, name="B5-test",
                reference_date=date(2025, 1, 1),
                land_purchase_price=Decimal("100000"),
                sdlt_category="Residential_Standard",
                developer_relief=False,
                project_duration_months=12,
                status="Approved", is_current=False,
                created_by_user_id=u.id,
            )
            db.add(ap)
            db.flush()
            # Cost line with NULL cost_code_id.
            db.add(AppraisalCostLine(
                appraisal_id=ap.id, display_order=1,
                cost_code_id=None,
                label="Bad", category="Other",
                auto_source="Manual", amount=Decimal("100"),
            ))
            db.flush()
            with pytest.raises(BudgetCreationError, match="cost_code_id"):
                create_from_appraisal(
                    db, project_id=uuid.UUID(project["id"]),
                    source_appraisal_id=ap.id, user=u, perms=perms,
                )
        finally:
            db.rollback()
            db.close()

    def test_b5_guard_null_amount(self, project):
        """The schema NOT NULL on amount enforces this at DB level —
        the service-side guard is belt-and-braces. Verify the schema
        constraint exists rather than executing an impossible insert.
        """
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            row = db.execute(text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='appraisal_cost_lines' AND column_name='amount'"
            )).first()
            assert row is not None and row[0] == "NO"
        finally:
            db.close()

    def test_merge_same_cost_code_to_one_line(self, project):
        """Two cost lines, same (cost_code, NULL subcat, primary_entity)
        must collapse into ONE budget_line whose original_budget is the sum.
        """
        from app.db import SessionLocal
        from app.services.budgets import create_from_appraisal
        from app.models.appraisals import Appraisal, AppraisalCostLine
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions
        db = SessionLocal()
        try:
            uid = db.scalar(text(
                "SELECT id FROM users WHERE email='test-admin@example.test'"
            ))
            u = db.get(User, uid)
            perms = compute_effective_permissions(db, u.id, u.tenant_id)
            cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))

            ap = Appraisal(
                project_id=uuid.UUID(project["id"]),
                version_number=97, name="merge-test",
                reference_date=date(2025, 1, 1),
                land_purchase_price=Decimal("100000"),
                sdlt_category="Residential_Standard",
                developer_relief=False,
                project_duration_months=12,
                status="Approved", is_current=False,
                created_by_user_id=u.id,
            )
            db.add(ap); db.flush()
            db.add(AppraisalCostLine(
                appraisal_id=ap.id, display_order=1, cost_code_id=cc_id,
                label="L1", category="Other",
                auto_source="Manual", amount=Decimal("1000"),
            ))
            db.add(AppraisalCostLine(
                appraisal_id=ap.id, display_order=2, cost_code_id=cc_id,
                label="L2", category="Other",
                auto_source="Manual", amount=Decimal("2500"),
            ))
            db.flush()

            # Wipe existing is_current so create can proceed.
            db.execute(text(
                "UPDATE budgets SET is_current=false WHERE project_id=:p"
            ), {"p": project["id"]})
            db.flush()
            b = create_from_appraisal(
                db, project_id=uuid.UUID(project["id"]),
                source_appraisal_id=ap.id, user=u, perms=perms,
            )
            assert len(b.lines) == 1
            assert b.lines[0].original_budget == Decimal("3500.00")
        finally:
            db.rollback()
            db.close()


# --------------------------------------------------------------------------
# Variance classification + recompute math
# --------------------------------------------------------------------------

class TestVarianceClassification:
    def test_under_budget_is_green(self):
        from app.services.budgets import _classify_variance
        assert _classify_variance(Decimal("-10")) == "Green"
        assert _classify_variance(Decimal("0")) == "Green"

    def test_below_amber_is_green(self):
        from app.services.budgets import _classify_variance
        assert _classify_variance(Decimal("4.5")) == "Green"

    def test_amber_band(self):
        from app.services.budgets import _classify_variance
        assert _classify_variance(Decimal("7")) == "Amber"
        assert _classify_variance(Decimal("14.999")) == "Amber"

    def test_red_band(self):
        from app.services.budgets import _classify_variance
        assert _classify_variance(Decimal("15.001")) == "Red"
        assert _classify_variance(Decimal("100")) == "Red"

    def test_variance_pct_zero_when_current_budget_zero(self):
        """Build Pack #49 — `_recompute_line` must store
        `variance_pct = Decimal('0.000')` (NOT None, NOT raise
        ZeroDivisionError) when `current_budget == 0`. Pure unit test
        against the recompute primitive — no DB session required."""
        from app.services.budgets import _recompute_line
        from app.models.budgets import BudgetLine
        l = BudgetLine(
            budget_id=uuid.uuid4(), cost_code_id=uuid.uuid4(),
            entity_id=uuid.uuid4(), line_description="zero-cb",
            original_budget=Decimal("0"),
            approved_changes=Decimal("0"),
            actuals_to_date=Decimal("0"),
            committed_value=Decimal("0"),
            committed_not_invoiced=Decimal("0"),
            ftc_method="Budget_Remaining",
            display_order=0,
        )
        _recompute_line(l)
        assert l.current_budget == Decimal("0")
        assert l.variance_pct == Decimal("0.000")
        # No variance with zero baseline → Green band per
        # _classify_variance (variance_pct == 0 → Green).
        assert l.variance_status == "Green"


class TestRecomputeMath:
    def test_recompute_line_budget_remaining(self, project):
        from app.services.budgets import _recompute_line
        from app.models.budgets import BudgetLine
        l = BudgetLine(
            budget_id=uuid.uuid4(), cost_code_id=uuid.uuid4(),
            entity_id=uuid.uuid4(), line_description="x",
            original_budget=Decimal("1000"),
            approved_changes=Decimal("100"),
            actuals_to_date=Decimal("200"),
            committed_value=Decimal("300"),
            committed_not_invoiced=Decimal("200"),
            ftc_method="Budget_Remaining",
            display_order=0,
        )
        _recompute_line(l)
        # current_budget = 1000+100 = 1100
        assert l.current_budget == Decimal("1100")
        # ftc = max(0, 1100 - 200 - 200) = 700  (committed_not_invoiced is committed-cost in this fn)
        assert l.forecast_to_complete == Decimal("700.00")
        # ffc = actuals + cni + ftc = 200 + 200 + 700 = 1100
        assert l.forecast_final_cost == Decimal("1100.00")
        assert l.variance_value == Decimal("0.00")
        assert l.variance_status == "Green"

    def test_recompute_line_committed_only(self):
        from app.services.budgets import _recompute_line
        from app.models.budgets import BudgetLine
        l = BudgetLine(
            budget_id=uuid.uuid4(), cost_code_id=uuid.uuid4(),
            entity_id=uuid.uuid4(), line_description="x",
            original_budget=Decimal("1000"),
            approved_changes=Decimal("0"),
            actuals_to_date=Decimal("100"),
            committed_value=Decimal("0"),
            committed_not_invoiced=Decimal("0"),
            ftc_method="Committed_Only",
            display_order=0,
        )
        _recompute_line(l)
        assert l.forecast_to_complete == Decimal("0.00")

    def test_recompute_line_red_variance(self):
        from app.services.budgets import _recompute_line
        from app.models.budgets import BudgetLine
        l = BudgetLine(
            budget_id=uuid.uuid4(), cost_code_id=uuid.uuid4(),
            entity_id=uuid.uuid4(), line_description="x",
            original_budget=Decimal("1000"),
            approved_changes=Decimal("0"),
            actuals_to_date=Decimal("0"),
            committed_value=Decimal("0"),
            committed_not_invoiced=Decimal("1500"),
            ftc_method="Budget_Remaining",
            display_order=0,
        )
        _recompute_line(l)
        # current_budget=1000, ftc=max(0,1000-0-1500)=0,
        # ffc=0+1500+0=1500, variance=500, pct=50% → Red.
        assert l.variance_status == "Red"
        assert l.variance_value == Decimal("500.00")

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_ftc_manual_uses_provided_value(
        self, admin, fresh_active_budget,
    ):
        """Build Pack #41 — when `ftc_method='Manual'`, the supplied
        `forecast_to_complete` is used verbatim by the recompute engine
        (no override). FFC = actuals + committed_not_invoiced + ftc."""
        line = fresh_active_budget["lines"][0]
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"ftc_method": "Manual",
                  "forecast_to_complete": "1234.56"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ftc_method"] == "Manual"
        assert Decimal(body["forecast_to_complete"]) == Decimal("1234.56")
        expected_ffc = (
            Decimal(body["actuals_to_date"])
            + Decimal(body["committed_not_invoiced"])
            + Decimal("1234.56")
        )
        assert Decimal(body["forecast_final_cost"]) == \
            expected_ffc.quantize(Decimal("0.01")), (
                f"FFC mismatch: got {body['forecast_final_cost']}, "
                f"expected {expected_ffc}"
            )

    def test_ftc_percentage_complete(self, admin, fresh_active_budget):
        """Build Pack #45 — when `ftc_method='Percentage_Complete'` and
        `percentage_complete=25`, the recompute engine sets
        `forecast_to_complete = max(0, current_budget * 0.75 - actuals
        - committed_not_invoiced)`. On a fresh budget where actuals=0
        and committed_not_invoiced=0, this collapses to
        `current_budget * 0.75`."""
        line = fresh_active_budget["lines"][0]
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"ftc_method": "Percentage_Complete",
                  "percentage_complete": "25"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        cb = Decimal(body["current_budget"])
        actuals = Decimal(body["actuals_to_date"])
        cni = Decimal(body["committed_not_invoiced"])
        # _recompute_line: remaining = current_budget * (100 - pct) / 100
        #                  ftc = max(0, remaining - actuals - cni)
        expected_ftc = max(
            Decimal("0"),
            (cb * Decimal("75") / Decimal("100") - actuals - cni),
        ).quantize(Decimal("0.01"))
        assert Decimal(body["forecast_to_complete"]) == expected_ftc, (
            f"ftc mismatch: got {body['forecast_to_complete']}, "
            f"expected {expected_ftc} from cb={cb}, actuals={actuals}, "
            f"cni={cni}"
        )

    def test_ftc_percentage_complete_falls_back_to_budget_remaining_when_zero(
        self, admin, fresh_active_budget,
    ):
        """Build Pack #46 — `ftc_method='Percentage_Complete'` with
        `percentage_complete=0` MUST yield the same value as
        Budget_Remaining, i.e. `max(0, current_budget - actuals -
        committed_not_invoiced)`. The recompute formula
        `cb * (100 - 0) / 100 - actuals - cni == cb - actuals - cni`
        gives this naturally; assertion is independent of the fresh-
        budget shortcut."""
        line = fresh_active_budget["lines"][0]
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"ftc_method": "Percentage_Complete",
                  "percentage_complete": "0"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        cb = Decimal(body["current_budget"])
        actuals = Decimal(body["actuals_to_date"])
        cni = Decimal(body["committed_not_invoiced"])
        budget_remaining = max(
            Decimal("0"), cb - actuals - cni,
        ).quantize(Decimal("0.01"))
        assert Decimal(body["forecast_to_complete"]) == budget_remaining, (
            f"pct=0 fallback failed: ftc={body['forecast_to_complete']} "
            f"≠ budget_remaining={budget_remaining}"
        )

    def test_variance_pct_overflow_handled_gracefully(self):
        """Build Pack #53 — `_recompute_line` must not raise on extreme
        values (e.g. ffc≫current_budget). Verified at the Python layer:
        the recompute primitive is pure-Decimal and never raises. The
        underlying `budget_lines.variance_pct` column is `NUMERIC(6,3)`
        — a flush of an extreme value would fail with NumericValueOut-
        OfRange, but the service contract is that the recompute itself
        is tolerant; clamp/flush-handling is the caller's contract.

        Inputs: original=1, cni=999_999_999, ftc=Manual(0).
        Expected: cb=1, ffc=999_999_999, variance_value=999_999_998,
        variance_pct=99_999_999_800.000, status=Red.
        """
        from app.services.budgets import _recompute_line
        from app.models.budgets import BudgetLine
        l = BudgetLine(
            budget_id=uuid.uuid4(), cost_code_id=uuid.uuid4(),
            entity_id=uuid.uuid4(), line_description="overflow",
            original_budget=Decimal("1"),
            approved_changes=Decimal("0"),
            actuals_to_date=Decimal("0"),
            committed_value=Decimal("0"),
            committed_not_invoiced=Decimal("999999999"),
            ftc_method="Manual",
            forecast_to_complete=Decimal("0"),
            display_order=0,
        )
        # No exception expected from the recompute call itself.
        _recompute_line(l)
        assert l.current_budget == Decimal("1")
        assert l.forecast_final_cost == Decimal("999999999.00")
        assert l.variance_value == Decimal("999999998.00")
        assert l.variance_pct is not None
        assert l.variance_pct == Decimal("99999999800.000")
        assert l.variance_status == "Red"


# --------------------------------------------------------------------------
# State machine — happy paths + illegals
# --------------------------------------------------------------------------

class TestStateMachine:
    def test_full_lifecycle(self, admin, project):
        aid = _make_approved_appraisal(admin, project["id"])
        # Need to ensure no existing current. Wipe.
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()

        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201
        bid = r.json()["id"]

        # Draft -> Active
        ra = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        assert ra.status_code == 200, ra.text
        assert ra.json()["status"] == "Active"
        # Activate from Active should 409
        rax = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        assert rax.status_code == 409

        # Active -> Locked
        rl = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        assert rl.status_code == 200, rl.text
        assert rl.json()["status"] == "Locked"

        # Locked -> Active (admin only)
        ru = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/unlock")
        assert ru.status_code == 200, ru.text
        assert ru.json()["status"] == "Active"

        # Active -> Closed (terminal)
        rc = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/close")
        assert rc.status_code == 200, rc.text
        assert rc.json()["status"] == "Closed"

        # Closed cannot transition.
        for ep in ("activate", "lock", "unlock"):
            r = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/{ep}")
            assert r.status_code == 409, f"{ep}: {r.text}"

    def test_lock_blocked_from_draft(self, admin, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        rl = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        assert rl.status_code == 409

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_lock_in_memory_line_state_consistent_with_db(
        self, db_session, project,
    ):
        """Build Pack #33 — service-layer `lock()` only mutates the
        budget header (status, locked_at, locked_by_user_id). It does
        NOT touch any per-line columns in 2.4A scope. Therefore the
        invariant under test is: after lock() returns, the in-memory
        Budget reflects post-lock header state without an explicit
        refresh, AND its `lines` collection remains consistent with
        the DB row count for that budget (no spurious add/remove)."""
        from app.services.budgets import (
            create_from_appraisal, activate, lock,
        )
        from app.models.appraisals import Appraisal, AppraisalCostLine
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions

        db = db_session
        db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                   {"p": project["id"]})
        db.commit()
        uid = db.scalar(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        ))
        u = db.get(User, uid)
        perms = compute_effective_permissions(db, u.id, u.tenant_id)
        cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))

        ap = Appraisal(
            project_id=uuid.UUID(project["id"]),
            version_number=86, name="lock-mem",
            reference_date=date(2025, 1, 1),
            land_purchase_price=Decimal("100000"),
            sdlt_category="Residential_Standard",
            developer_relief=False,
            project_duration_months=12,
            status="Approved", is_current=False,
            created_by_user_id=u.id,
        )
        db.add(ap)
        db.flush()
        db.add(AppraisalCostLine(
            appraisal_id=ap.id, display_order=1, cost_code_id=cc_id,
            label="x", category="Other", auto_source="Manual",
            amount=Decimal("1000"),
        ))
        db.flush()

        b = create_from_appraisal(
            db, project_id=uuid.UUID(project["id"]),
            source_appraisal_id=ap.id, user=u, perms=perms,
        )
        activate(db, budget_id=b.id, user=u, perms=perms)
        line_count_before = len(b.lines)
        locked = lock(db, budget_id=b.id, user=u, perms=perms)

        # Header state visible in-memory without explicit refresh.
        assert locked.status == "Locked"
        assert locked.locked_at is not None
        assert locked.locked_by_user_id == u.id

        # In-memory lines collection matches DB row count for the budget.
        db_count = db.execute(text(
            "SELECT COUNT(*) FROM budget_lines WHERE budget_id=:b"
        ), {"b": b.id}).scalar()
        assert len(locked.lines) == line_count_before == db_count

    def test_unlock_in_memory_line_state_consistent_with_db(
        self, db_session, project,
    ):
        """Build Pack #34 — mirror of #33 for `unlock()`. After unlock()
        returns, in-memory header reflects post-unlock state without an
        explicit refresh, and the lines collection still matches the
        DB row count."""
        from app.services.budgets import (
            create_from_appraisal, activate, lock, unlock,
        )
        from app.models.appraisals import Appraisal, AppraisalCostLine
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions

        db = db_session
        db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                   {"p": project["id"]})
        db.commit()
        uid = db.scalar(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        ))
        u = db.get(User, uid)
        perms = compute_effective_permissions(db, u.id, u.tenant_id)
        cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))

        ap = Appraisal(
            project_id=uuid.UUID(project["id"]),
            version_number=85, name="unlock-mem",
            reference_date=date(2025, 1, 1),
            land_purchase_price=Decimal("100000"),
            sdlt_category="Residential_Standard",
            developer_relief=False,
            project_duration_months=12,
            status="Approved", is_current=False,
            created_by_user_id=u.id,
        )
        db.add(ap)
        db.flush()
        db.add(AppraisalCostLine(
            appraisal_id=ap.id, display_order=1, cost_code_id=cc_id,
            label="y", category="Other", auto_source="Manual",
            amount=Decimal("2000"),
        ))
        db.flush()

        b = create_from_appraisal(
            db, project_id=uuid.UUID(project["id"]),
            source_appraisal_id=ap.id, user=u, perms=perms,
        )
        activate(db, budget_id=b.id, user=u, perms=perms)
        lock(db, budget_id=b.id, user=u, perms=perms)
        unlocked = unlock(db, budget_id=b.id, user=u, perms=perms)

        assert unlocked.status == "Active"
        assert unlocked.locked_at is None
        assert unlocked.locked_by_user_id is None

        db_count = db.execute(text(
            "SELECT COUNT(*) FROM budget_lines WHERE budget_id=:b"
        ), {"b": b.id}).scalar()
        assert len(unlocked.lines) == db_count

    def test_get_list_budgets_for_project_filters_by_is_current(
        self, admin, project,
    ):
        """Build Pack #89 — `GET /api/v1/projects/:id/budgets`:
        - default (no filter) returns ALL versions for the project,
        - `?is_current=true` returns only the current (non-superseded)
          version,
        - `?is_current=false` returns only non-current versions.

        Set up: v1 created, activated, then new-version → v2.
        v1 becomes Superseded/is_current=False; v2 is Draft/
        is_current=True."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        v1_id = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{v1_id}/activate")
        rv = admin.post(
            f"{BASE_URL}/api/v1/budgets/{v1_id}/new-version",
            json={"version_label": "v2-list-filter"},
        )
        assert rv.status_code == 201, rv.text
        v2_id = rv.json()["id"]

        # No filter → both versions.
        rl = admin.get(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets"
        )
        assert rl.status_code == 200, rl.text
        all_ids = {b["id"] for b in rl.json()["items"]}
        assert {v1_id, v2_id}.issubset(all_ids)
        assert rl.json()["count"] >= 2

        # ?is_current=true → only v2.
        rt = admin.get(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets"
            f"?is_current=true"
        )
        assert rt.status_code == 200, rt.text
        cur_items = rt.json()["items"]
        assert len(cur_items) == 1
        assert cur_items[0]["id"] == v2_id
        assert cur_items[0]["is_current"] is True

        # ?is_current=false → only v1 (now superseded).
        rf = admin.get(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets"
            f"?is_current=false"
        )
        assert rf.status_code == 200, rf.text
        old_items = rf.json()["items"]
        assert v1_id in {b["id"] for b in old_items}
        for b in old_items:
            assert b["is_current"] is False


class TestPermissionGating:
    def test_unlock_requires_admin(self, admin, pm, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        # PM can NOT unlock (no budgets.admin)
        ru = pm.post(f"{BASE_URL}/api/v1/budgets/{bid}/unlock")
        assert ru.status_code == 403

    def test_pm_can_create_from_appraisal(self, admin, pm, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = pm.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text

    def test_readonly_cannot_create(self, admin, readonly, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = readonly.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 403

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_post_from_appraisal_403_with_site_manager_session(
        self, admin, site_manager, project,
    ):
        """Build Pack #81 — `site_manager` role does NOT have
        `budgets.create`, so POST /budgets/from-appraisal must return
        403 (require_permission gate fires before any service code)."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = site_manager.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 403, r.text

    def test_post_lock_endpoint_with_pm_session(
        self, admin, pm, project,
    ):
        """Build Pack #85 — `project_manager` CAN lock an active budget
        (PM has `budgets.edit`, which the lock endpoint requires).
        Unlock requires `budgets.admin` and is covered separately by
        `test_unlock_requires_admin` — this test proves the asymmetry."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        bid = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        rl = pm.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        assert rl.status_code == 200, rl.text
        assert rl.json()["status"] == "Locked"


# --------------------------------------------------------------------------
# Lines + items via API
# --------------------------------------------------------------------------

@pytest.fixture
def fresh_active_budget(admin, project):
    """Create a fresh Active budget with at least one line. Module isolation."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                   {"p": project["id"]})
        db.commit()
    finally:
        db.close()
    aid = _make_approved_appraisal(admin, project["id"])
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    bid = body["id"]
    admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
    detail = admin.get(f"{BASE_URL}/api/v1/budgets/{bid}").json()
    return detail


class TestLineEdits:
    def test_patch_line_description(self, admin, fresh_active_budget):
        line = fresh_active_budget["lines"][0]
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"line_description": "edited"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["line_description"] == "edited"

    def test_patch_line_unknown_field_rejected(self, admin, fresh_active_budget):
        line = fresh_active_budget["lines"][0]
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"hacker_field": "xxx"},
        )
        assert r.status_code == 422  # pydantic extra=forbid

    def test_patch_line_404_for_unknown(self, admin):
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{uuid.uuid4()}",
            json={"notes": "x"},
        )
        assert r.status_code == 404

    def test_line_payload_emits_created_at_and_updated_at(
        self, admin, fresh_active_budget,
    ):
        """2.4A.2 precursor for §R7 LineDrawer conflict detection: line
        payload must carry timestamp fields so the frontend can detect
        out-of-band edits via updated_at delta."""
        line = fresh_active_budget["lines"][0]
        for key in ("created_at", "updated_at"):
            assert key in line, (
                f"Line payload missing {key} (needed for 2.4B-i §R7 "
                f"refetch-on-save banner). Keys present: {sorted(line.keys())}"
            )
            # ISO-8601 string
            assert isinstance(line[key], str) and "T" in line[key]
        # PATCH bumps updated_at
        before = line["updated_at"]
        import time as _time
        _time.sleep(0.01)
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"notes": "tick"},
        )
        assert r.status_code == 200
        after = r.json()["updated_at"]
        assert after > before, (
            f"PATCH should advance updated_at: before={before} after={after}"
        )


    def test_line_changes_recompute_header(self, admin, fresh_active_budget):
        bid = fresh_active_budget["id"]
        line = fresh_active_budget["lines"][0]
        before = fresh_active_budget["total_budget"]
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"original_budget": "99999.00"},
        )
        assert r.status_code == 200
        after = admin.get(f"{BASE_URL}/api/v1/budgets/{bid}").json()["total_budget"]
        assert Decimal(after) != Decimal(before)

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_header_summary_refreshed_at_advances_on_recompute(
        self, admin, fresh_active_budget,
    ):
        """Build Pack #70 — every successful line edit triggers
        `recompute_summary`, which stamps `budget.summary_refreshed_at`
        to `now()`. Verified via two GETs straddling a PATCH; sleep
        100ms to guarantee a wall-clock advance even on coarse-
        precision timestamp columns."""
        import time
        from datetime import datetime
        bid = fresh_active_budget["id"]
        line = fresh_active_budget["lines"][0]
        t0_str = admin.get(
            f"{BASE_URL}/api/v1/budgets/{bid}"
        ).json()["summary_refreshed_at"]
        assert t0_str is not None, (
            "summary_refreshed_at must be present in the detail "
            "response — column missing or never stamped (Build Pack "
            "B16 invariant violated)."
        )
        time.sleep(0.1)
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}",
            json={"notes": "summary-refreshed-at-tick"},
        )
        assert r.status_code == 200, r.text
        t1_str = admin.get(
            f"{BASE_URL}/api/v1/budgets/{bid}"
        ).json()["summary_refreshed_at"]
        t0 = datetime.fromisoformat(t0_str.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(t1_str.replace("Z", "+00:00"))
        assert t1 > t0, (
            f"summary_refreshed_at did not advance: t0={t0_str}, "
            f"t1={t1_str}"
        )


# ============================================================================
# Prompt 2.4A.1 — bulk reorder lines (precursor for 2.4B-i drag-reorder)
# ============================================================================

@pytest.fixture
def budget_with_three_lines(admin, project):
    """Active budget with 3 lines (display_order 0,1,2). Module isolation
    via the same wipe pattern as fresh_active_budget."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                   {"p": project["id"]})
        db.commit()
    finally:
        db.close()
    aid = _make_approved_appraisal(admin, project["id"])
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")

    # Inject two extra lines via direct SQL so we have ≥3 lines to reorder.
    db = SessionLocal()
    try:
        from app.models.budgets import Budget, BudgetLine
        b = db.get(Budget, uuid.UUID(bid))
        existing_max = max(
            (ln.display_order for ln in b.lines), default=-1,
        )
        entity_id = db.scalar(text(
            "SELECT id FROM entities WHERE name = 'SY Homes (Shrewsbury) Ltd'"
        ))
        # Each extra line needs a distinct (cost_code_id, subcategory) tuple
        # to satisfy the uq_budget_lines_budget_cost_subcat unique index.
        # Easiest: distinct cost_code_ids.
        cc_ids = db.execute(
            text("SELECT id FROM cost_codes ORDER BY code LIMIT 3")
        ).scalars().all()
        assert len(cc_ids) >= 3, "Need 3+ cost codes for reorder fixture"
        for i, cc in enumerate(cc_ids[1:], start=existing_max + 1):
            line = BudgetLine(
                budget_id=b.id, cost_code_id=cc, entity_id=entity_id,
                line_description=f"Reorder fixture line {i}",
                original_budget=Decimal(f"{(i + 1) * 10000}.00"),
                ftc_method="Budget_Remaining", display_order=i,
            )
            db.add(line)
        db.commit()
    finally:
        db.close()

    detail = admin.get(f"{BASE_URL}/api/v1/budgets/{bid}").json()
    assert len(detail["lines"]) >= 3, (
        f"Reorder fixture expected ≥3 lines, got {len(detail['lines'])}"
    )
    return detail


class TestBulkReorderLines:
    """POST /budget-lines/reorder (Prompt 2.4A.1)."""

    def test_reorder_success_reverses_order_and_bumps_updated_at(
        self, admin, budget_with_three_lines,
    ):
        """Happy path: reverse the line order. Verify (a) new display_order
        matches the submitted order, (b) updated_at advances on every
        affected line, (c) summary_refreshed_at bumped on the budget."""
        import time
        b = budget_with_three_lines
        bid = b["id"]
        # Lines come back sorted by display_order asc (see _serialise_budget_detail)
        ordered_ids = [ln["id"] for ln in b["lines"]]
        reversed_ids = list(reversed(ordered_ids))

        # Capture pre-reorder updated_at per line for the bump assertion.
        from app.db import SessionLocal
        from app.models.budgets import BudgetLine
        db = SessionLocal()
        try:
            pre = {
                str(ln.id): ln.updated_at
                for ln in db.scalars(
                    select(BudgetLine).where(
                        BudgetLine.budget_id == uuid.UUID(bid),
                    )
                )
            }
        finally:
            db.close()
        t0 = b["summary_refreshed_at"]
        time.sleep(0.1)

        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": reversed_ids},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == bid
        # Returned lines sorted asc by display_order — verify the order
        # matches the submitted ordered_line_ids.
        returned_ids = [ln["id"] for ln in body["lines"]]
        assert returned_ids == reversed_ids, (
            f"Returned order {returned_ids} ≠ submitted {reversed_ids}"
        )
        # display_order values are dense 0..N-1
        for pos, ln in enumerate(body["lines"]):
            assert ln["display_order"] == pos

        # summary_refreshed_at advanced
        t1 = body["summary_refreshed_at"]
        from datetime import datetime
        assert datetime.fromisoformat(t1.replace("Z", "+00:00")) > \
               datetime.fromisoformat(t0.replace("Z", "+00:00"))

        # updated_at bumped on every line whose position changed (all 3 here)
        db = SessionLocal()
        try:
            post = {
                str(ln.id): ln.updated_at
                for ln in db.scalars(
                    select(BudgetLine).where(
                        BudgetLine.budget_id == uuid.UUID(bid),
                    )
                )
            }
        finally:
            db.close()
        for lid in ordered_ids:
            assert post[lid] > pre[lid], (
                f"updated_at did not advance on reordered line {lid}: "
                f"pre={pre[lid]} post={post[lid]}"
            )

    def test_reorder_rejects_partial_ids_400(
        self, admin, budget_with_three_lines,
    ):
        """Submitting fewer ids than lines on the budget → 400."""
        b = budget_with_three_lines
        bid = b["id"]
        ordered_ids = [ln["id"] for ln in b["lines"]]
        partial = ordered_ids[:-1]  # drop the last one
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": partial},
        )
        assert r.status_code == 400, r.text
        assert "missing" in r.json()["detail"].lower() or \
               "every line" in r.json()["detail"].lower()

    def test_reorder_rejects_foreign_id_400(
        self, admin, budget_with_three_lines,
    ):
        """Submitting an unknown UUID alongside the real ones → 400."""
        b = budget_with_three_lines
        bid = b["id"]
        ordered_ids = [ln["id"] for ln in b["lines"]]
        # Replace one real id with a random uuid → same length, foreign id present.
        tainted = ordered_ids[:-1] + [str(uuid.uuid4())]
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": tainted},
        )
        assert r.status_code == 400, r.text
        assert "foreign" in r.json()["detail"].lower() or \
               "every line" in r.json()["detail"].lower()

    def test_reorder_rejects_duplicate_ids_400(
        self, admin, budget_with_three_lines,
    ):
        """Submitting an id twice (same length as line count) → 400."""
        b = budget_with_three_lines
        bid = b["id"]
        ordered_ids = [ln["id"] for ln in b["lines"]]
        # Duplicate the first id, drop the last to keep the length correct.
        dup = [ordered_ids[0]] + ordered_ids[:-1]
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": dup},
        )
        assert r.status_code == 400, r.text
        assert "duplicate" in r.json()["detail"].lower()

    def test_reorder_requires_budgets_edit_perm_403(
        self, readonly, budget_with_three_lines,
    ):
        """test-readonly@example.test has budgets.view but not budgets.edit."""
        b = budget_with_three_lines
        bid = b["id"]
        ordered_ids = [ln["id"] for ln in b["lines"]]
        r = readonly.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": ordered_ids},
        )
        assert r.status_code == 403, r.text

    def test_reorder_locked_budget_returns_409(
        self, admin, budget_with_three_lines,
    ):
        """Lock the budget, then a reorder attempt → 409."""
        b = budget_with_three_lines
        bid = b["id"]
        rl = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        assert rl.status_code == 200, rl.text

        ordered_ids = [ln["id"] for ln in b["lines"]]
        reversed_ids = list(reversed(ordered_ids))
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": reversed_ids},
        )
        assert r.status_code == 409, r.text
        assert "locked" in r.json()["detail"].lower()

    def test_reorder_unknown_budget_returns_404(self, admin):
        """Non-existent budget id → 404."""
        ghost = str(uuid.uuid4())
        # Need ordered_line_ids non-empty to pass schema validation.
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": ghost, "ordered_line_ids": [str(uuid.uuid4())]},
        )
        assert r.status_code == 404, r.text

    def test_reorder_writes_audit_row(
        self, admin, budget_with_three_lines,
    ):
        """Audit log row written for the reorder with field_changes per
        affected line + metadata.kind == 'lines_reorder'."""
        b = budget_with_three_lines
        bid = b["id"]
        ordered_ids = [ln["id"] for ln in b["lines"]]
        reversed_ids = list(reversed(ordered_ids))
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/reorder",
            json={"budget_id": bid, "ordered_line_ids": reversed_ids},
        )
        assert r.status_code == 200, r.text

        from app.db import SessionLocal
        db = SessionLocal()
        try:
            row = db.execute(text("""
                SELECT field_changes, metadata_json FROM audit_log
                WHERE resource_type='budget_lines'
                  AND resource_id=:bid
                  AND metadata_json->>'kind' = 'lines_reorder'
                ORDER BY created_at DESC LIMIT 1
            """), {"bid": bid}).first()
        finally:
            db.close()
        assert row is not None, (
            "No audit row found for reorder action on budget " + bid
        )
        field_changes, metadata = row[0], row[1]
        assert metadata["kind"] == "lines_reorder"
        assert metadata["total_lines"] == 3
        assert metadata["lines_affected"] >= 2  # reversed-3-list moves 2+
        assert isinstance(field_changes, list)
        # Every audit field_change entry references display_order
        for entry in field_changes:
            assert entry["field"] == "display_order"



class TestLineItems:
    def test_create_list_update_delete_item(self, admin, fresh_active_budget):
        line = fresh_active_budget["lines"][0]
        # Create
        rc = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}/items",
            json={"description": "Item 1", "amount": "500.00"},
        )
        assert rc.status_code == 201, rc.text
        item_id = rc.json()["id"]
        # List
        rl = admin.get(f"{BASE_URL}/api/v1/budget-lines/{line['id']}/items")
        assert rl.status_code == 200
        ids = [i["id"] for i in rl.json()["items"]]
        assert item_id in ids
        # Update
        ru = admin.patch(
            f"{BASE_URL}/api/v1/budget-line-items/{item_id}",
            json={"description": "Item 1 v2"},
        )
        assert ru.status_code == 200
        assert ru.json()["description"] == "Item 1 v2"
        # Delete
        rd = admin.delete(f"{BASE_URL}/api/v1/budget-line-items/{item_id}")
        assert rd.status_code == 204

    def test_create_item_rejects_extra_fields(self, admin, fresh_active_budget):
        line = fresh_active_budget["lines"][0]
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}/items",
            json={"description": "x", "amount": "1", "evil": "yes"},
        )
        assert r.status_code == 422

    def test_item_crud_blocked_on_locked_budget(self, admin, project):
        # Build a fresh Locked budget.
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        detail = admin.get(f"{BASE_URL}/api/v1/budgets/{bid}").json()
        line_id = detail["lines"][0]["id"]
        rc = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/{line_id}/items",
            json={"description": "x", "amount": "1"},
        )
        assert rc.status_code == 409


    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_create_item_via_relationship_collection_populated(
        self, db_session, project,
    ):
        """Build Pack #64 — after `create_item`, the parent
        `BudgetLine.items` relationship populates when reloaded in the
        same session. Validates SQLAlchemy `back_populates` wiring at
        the ORM layer (independent of the API serialiser)."""
        from app.services.budgets import create_from_appraisal, activate
        from app.services.budget_lines import create_item
        from app.models.budgets import BudgetLine
        from app.models.appraisals import Appraisal, AppraisalCostLine
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions

        db = db_session
        db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                   {"p": project["id"]})
        db.commit()
        uid = db.scalar(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        ))
        u = db.get(User, uid)
        perms = compute_effective_permissions(db, u.id, u.tenant_id)
        cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))

        ap = Appraisal(
            project_id=uuid.UUID(project["id"]),
            version_number=84, name="rel-coll",
            reference_date=date(2025, 1, 1),
            land_purchase_price=Decimal("100000"),
            sdlt_category="Residential_Standard",
            developer_relief=False,
            project_duration_months=12,
            status="Approved", is_current=False,
            created_by_user_id=u.id,
        )
        db.add(ap)
        db.flush()
        db.add(AppraisalCostLine(
            appraisal_id=ap.id, display_order=1, cost_code_id=cc_id,
            label="z", category="Other", auto_source="Manual",
            amount=Decimal("500"),
        ))
        db.flush()

        b = create_from_appraisal(
            db, project_id=uuid.UUID(project["id"]),
            source_appraisal_id=ap.id, user=u, perms=perms,
        )
        activate(db, budget_id=b.id, user=u, perms=perms)
        line_id = b.lines[0].id
        item = create_item(
            db, line_id=line_id, user=u, perms=perms,
            description="rel-test", amount=Decimal("100.00"),
        )
        # Force a reload of the line so the relationship collection
        # repopulates from the DB (back_populates round-trip).
        db.expire(b.lines[0])
        reloaded = db.get(BudgetLine, line_id)
        assert reloaded is not None
        assert len(reloaded.items) == 1
        assert reloaded.items[0].id == item.id
        assert reloaded.items[0].description == "rel-test"

    def test_item_amount_validation_warns_but_does_not_block(
        self, admin, fresh_active_budget,
    ):
        """Build Pack #65 — per spec, when an item's `amount` differs
        from `quantity * rate`, the service warns but does NOT reject
        the create. The user-supplied `amount` is canonical and
        round-trips verbatim."""
        line = fresh_active_budget["lines"][0]
        r = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}/items",
            json={
                "description": "mismatch-on-purpose",
                "quantity": "10",
                "rate": "5.00",
                "amount": "999.99",  # Deliberate ≠ 10 * 5 = 50.00
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert Decimal(body["amount"]) == Decimal("999.99")
        assert Decimal(body["quantity"]) == Decimal("10")
        assert Decimal(body["rate"]) == Decimal("5.00")
        assert body["description"] == "mismatch-on-purpose"

    def test_delete_line_cascades_items(
        self, admin, fresh_active_budget, db_engine,
    ):
        """Build Pack #66 — DB-level `ON DELETE CASCADE` on
        `budget_line_items.budget_line_id` fires on a raw-SQL DELETE of
        the parent line. Validates the FK definition independently of
        the ORM-level cascade configured on the relationship."""
        line = fresh_active_budget["lines"][0]
        line_id = line["id"]
        # Create 2 items.
        for desc in ("c1", "c2"):
            rc = admin.post(
                f"{BASE_URL}/api/v1/budget-lines/{line_id}/items",
                json={"description": desc, "amount": "10.00"},
            )
            assert rc.status_code == 201, rc.text
        # Sanity check: 2 items present.
        with db_engine.connect() as c:
            before = c.execute(text(
                "SELECT COUNT(*) FROM budget_line_items "
                "WHERE budget_line_id=:l"
            ), {"l": line_id}).scalar()
        assert before == 2

        # Raw-SQL DELETE the parent line. FK cascade should fire.
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM budget_lines WHERE id=:l"),
                      {"l": line_id})
        with db_engine.connect() as c:
            after = c.execute(text(
                "SELECT COUNT(*) FROM budget_line_items "
                "WHERE budget_line_id=:l"
            ), {"l": line_id}).scalar()
        assert after == 0, (
            f"FK cascade did not fire — {after} orphan items remain "
            f"after parent line delete."
        )


# --------------------------------------------------------------------------
# New version (clones lines, supersedes old)
# --------------------------------------------------------------------------

class TestNewVersion:
    def test_new_version_supersedes_old(self, admin, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        old_bid = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{old_bid}/activate")
        line_count = len(r.json()["lines"])

        rv = admin.post(
            f"{BASE_URL}/api/v1/budgets/{old_bid}/new-version",
            json={"version_label": "v2-test"},
        )
        assert rv.status_code == 201, rv.text
        new = rv.json()
        assert new["status"] == "Draft"
        assert new["is_current"] is True
        assert new["version_label"] == "v2-test"
        assert len(new["lines"]) == line_count

        old_after = admin.get(f"{BASE_URL}/api/v1/budgets/{old_bid}").json()
        assert old_after["status"] == "Superseded"
        assert old_after["is_current"] is False

    def test_new_version_blocked_from_draft(self, admin, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        # Don't activate — try new_version on Draft.
        rv = admin.post(
            f"{BASE_URL}/api/v1/budgets/{bid}/new-version",
            json={"version_label": "v2"},
        )
        assert rv.status_code == 409

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_create_new_version_carries_programme_task_link(
        self, admin, project, db_engine,
    ):
        """Build Pack #30 — `linked_programme_task_id` (B9 / locked
        decision 13) is carried from old-version lines onto new-version
        cloned lines. The column has no FK constraint until Track 4 /
        Prompt 3.2, so the test seeds a synthetic uuid via raw SQL
        (the `UpdateBudgetLineRequest` schema deliberately omits this
        field — only the new_version cloning path propagates it)."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        old_bid = r.json()["id"]
        line = r.json()["lines"][0]
        line_id = line["id"]
        cost_code_id = line["cost_code_id"]

        fake_task_id = uuid.uuid4()
        with db_engine.begin() as c:
            c.execute(text(
                "UPDATE budget_lines SET linked_programme_task_id=:t "
                "WHERE id=:l"
            ), {"t": str(fake_task_id), "l": line_id})

        admin.post(f"{BASE_URL}/api/v1/budgets/{old_bid}/activate")
        rv = admin.post(
            f"{BASE_URL}/api/v1/budgets/{old_bid}/new-version",
            json={"version_label": "v2-link-carry"},
        )
        assert rv.status_code == 201, rv.text

        new_lines = rv.json()["lines"]
        matching = [
            l for l in new_lines if l["cost_code_id"] == cost_code_id
        ]
        assert len(matching) == 1, (
            f"expected exactly one cloned line with cost_code_id="
            f"{cost_code_id}, found {len(matching)}"
        )
        new_line_id = matching[0]["id"]
        # The serialised payload exposes linked_programme_task_id; cross-
        # check against raw SQL too (paranoia).
        assert matching[0]["linked_programme_task_id"] == \
            str(fake_task_id)
        with db_engine.connect() as c:
            carried = c.execute(text(
                "SELECT linked_programme_task_id FROM budget_lines "
                "WHERE id=:l"
            ), {"l": new_line_id}).scalar()
        assert str(carried) == str(fake_task_id)

    def test_create_new_version_clones_items_with_lines(
        self, admin, project,
    ):
        """Build Pack #31 — items on the OLD version's lines ARE cloned
        onto the corresponding NEW version's lines per service B11
        ('copies lines (and items per B11)').

        Resolution of Chat 16.5 STOP #31: B11 is canonical. The
        chat-16-closing #31 spec ('items are version-specific work
        breakdown; not cloned') was wrong and has been corrected.
        Items survive the new_version cloning path; lines are matched
        across versions by `cost_code_id` (subcategory ignored — every
        cloned line preserves its parent's items 1:1).

        Asserts: for each new-version line, the count of items equals
        the count of items on the v1 line with the matching
        cost_code_id."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        v1_id = r.json()["id"]
        v1_lines = r.json()["lines"]
        v1_line = v1_lines[0]
        admin.post(f"{BASE_URL}/api/v1/budgets/{v1_id}/activate")

        # Add 2 items to v1's first line so the count is unambiguous
        # (1 item per cloned line could be a coincidence; 2 proves it).
        for desc in ("clone-test-item-a", "clone-test-item-b"):
            rc = admin.post(
                f"{BASE_URL}/api/v1/budget-lines/{v1_line['id']}/items",
                json={"description": desc, "amount": "111.00"},
            )
            assert rc.status_code == 201, rc.text

        # Build a {cost_code_id: item_count} map for v1.
        rv1 = admin.get(f"{BASE_URL}/api/v1/budgets/{v1_id}").json()
        v1_counts = {
            l["cost_code_id"]: len(l.get("items", []))
            for l in rv1["lines"]
        }
        assert v1_counts[v1_line["cost_code_id"]] == 2, (
            f"setup invariant violated: expected 2 items on v1 line, "
            f"got {v1_counts[v1_line['cost_code_id']]}"
        )

        rv = admin.post(
            f"{BASE_URL}/api/v1/budgets/{v1_id}/new-version",
            json={"version_label": "v2-clone-items"},
        )
        assert rv.status_code == 201, rv.text
        new_lines = rv.json()["lines"]

        # Every new-version line's item count matches its v1 counterpart
        # (matched by cost_code_id).
        assert len(new_lines) == len(v1_lines), (
            f"new-version line count {len(new_lines)} ≠ v1 line count "
            f"{len(v1_lines)}"
        )
        for nl in new_lines:
            cc = nl["cost_code_id"]
            assert cc in v1_counts, (
                f"new-version line cost_code_id={cc} has no v1 "
                f"counterpart"
            )
            assert len(nl.get("items", [])) == v1_counts[cc], (
                f"new-version line cc={cc} carried "
                f"{len(nl.get('items', []))} item(s); expected "
                f"{v1_counts[cc]} per B11 cloning."
            )


# --------------------------------------------------------------------------
# Tenant isolation (Pattern α): cross-tenant access returns 404
# --------------------------------------------------------------------------

class TestTenantIsolation:
    """Pattern α tenant scoping: cross-tenant access returns 404 via the
    service layer's `_scope_check_project` (db.get(Project) → hasattr →
    `_visible_project_ids`). Phase 1 HTTP auth is single-tenant by design,
    so we exercise the path at the service layer with a synthetic second
    tenant + user.
    """

    @pytest.fixture(scope="class")
    def t2(self, db_engine):
        from app.auth.passwords import hash_password
        with db_engine.begin() as c:
            tid = c.execute(text(
                "INSERT INTO tenants (id, name) VALUES "
                "(gen_random_uuid(), 'Test Tenant 2 (budgets)') RETURNING id"
            )).scalar()
            # Use a non-super_admin role so _visible_project_ids actually
            # gates the user. Tenant 2 has zero projects, so this user's
            # visible set will be empty regardless of project_scope='All'.
            ro_role_id = c.execute(text(
                "SELECT id FROM roles WHERE code='read_only'"
            )).scalar()
            uid = c.execute(text("""
                INSERT INTO users (id, tenant_id, email, email_verified,
                  password_hash, password_algorithm, password_changed_at,
                  password_history, first_name, last_name, display_name,
                  user_type, status, mfa_enabled)
                VALUES (gen_random_uuid(), :t,
                  't2-svc-readonly@example.test', true,
                  :h, 'argon2id', now(), '[]', 'T2', 'RO', 'T2 RO',
                  'Internal', 'Active', false)
                RETURNING id
            """), {"t": tid, "h": hash_password(PWD)}).scalar()
            c.execute(text("""
                INSERT INTO user_roles (id, user_id, role_id, entity_scope,
                  project_scope, view_overrides, assigned_by_user_id, status)
                VALUES (gen_random_uuid(), :u, :r, 'All', 'Specific', '[]',
                        :u, 'Active')
            """), {"u": uid, "r": ro_role_id})
        yield {"tenant_id": tid, "user_id": uid}
        with db_engine.begin() as c:
            c.execute(text(
                "DELETE FROM user_roles WHERE user_id IN "
                "(SELECT id FROM users WHERE tenant_id=:t)"
            ), {"t": tid})
            c.execute(text("DELETE FROM users WHERE tenant_id=:t"), {"t": tid})
            c.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": tid})

    def test_cross_tenant_load_returns_404(self, admin, project, t2):
        """A super_admin in tenant 2 cannot resolve a budget owned by a
        project in tenant 1 — the project itself is not in their
        _visible_project_ids set (tenant 2 has zero projects)."""
        from app.db import SessionLocal
        from app.services.budgets import _load_budget_for_read
        from app.services.budget_errors import BudgetNotFoundError
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions

        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        bid = uuid.UUID(r.json()["id"])

        db = SessionLocal()
        try:
            t2_user = db.get(User, t2["user_id"])
            t2_perms = compute_effective_permissions(
                db, t2_user.id, t2_user.tenant_id,
            )
            # Even though super_admin globally, scope is via
            # _visible_project_ids tied to tenant. Tenant 2 has no project
            # entries → set() → access denied → 404 via raised
            # BudgetNotFoundError.
            with pytest.raises(BudgetNotFoundError):
                _load_budget_for_read(db, bid, t2_user, t2_perms)
        finally:
            db.close()

    def test_cross_tenant_list_excludes(self, admin, project, t2):
        from app.db import SessionLocal
        from app.services.budgets import list_budgets
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions

        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )

        db = SessionLocal()
        try:
            t2_user = db.get(User, t2["user_id"])
            t2_perms = compute_effective_permissions(
                db, t2_user.id, t2_user.tenant_id,
            )
            # Listing for a specific cross-tenant project_id returns [].
            rows = list_budgets(
                db, user=t2_user, perms=t2_perms,
                project_id=uuid.UUID(project["id"]),
            )
            assert rows == []
        finally:
            db.close()


# --------------------------------------------------------------------------
# Audit log coverage
# --------------------------------------------------------------------------

class TestAuditLogCoverage:
    def _last_action(self, db, resource_type, resource_id, action):
        return db.execute(text(
            "SELECT metadata_json FROM audit_log "
            "WHERE resource_type=:rt AND resource_id=:rid AND action=:a "
            "ORDER BY created_at DESC LIMIT 1"
        ), {"rt": resource_type, "rid": resource_id, "a": action}).first()

    def test_create_lock_unlock_close_all_audited(self, admin, project):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/unlock")
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/close")

        db = SessionLocal()
        try:
            create_row = self._last_action(db, "budgets", bid, "Create")
            assert create_row is not None
            assert create_row[0]["kind"] == "create_from_appraisal"

            for transition in ("activate", "lock", "unlock", "close"):
                row = db.execute(text(
                    "SELECT metadata_json FROM audit_log "
                    "WHERE resource_type='budgets' AND resource_id=:rid "
                    "  AND action='Status_Change' "
                    "  AND metadata_json->>'kind' = :k "
                    "ORDER BY created_at DESC LIMIT 1"
                ), {"rid": bid, "k": transition}).first()
                assert row is not None, f"missing audit for {transition}"
                assert row[0]["new_status"] in (
                    "Active", "Locked", "Closed",
                )
        finally:
            db.close()

    def test_line_patch_audited(self, admin, fresh_active_budget):
        line_id = fresh_active_budget["lines"][0]["id"]
        admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line_id}",
            json={"notes": "audited-note"},
        )
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            row = db.execute(text(
                "SELECT field_changes FROM audit_log "
                "WHERE resource_type='budget_lines' AND resource_id=:rid "
                "  AND action='Update' "
                "ORDER BY created_at DESC LIMIT 1"
            ), {"rid": line_id}).first()
            assert row is not None
            fc = row[0] or []
            assert any(c["field"] == "notes" for c in fc)
        finally:
            db.close()

    def test_item_crud_audited(self, admin, fresh_active_budget):
        line_id = fresh_active_budget["lines"][0]["id"]
        rc = admin.post(
            f"{BASE_URL}/api/v1/budget-lines/{line_id}/items",
            json={"description": "audit test", "amount": "10.00"},
        )
        item_id = rc.json()["id"]
        admin.patch(
            f"{BASE_URL}/api/v1/budget-line-items/{item_id}",
            json={"description": "audit v2"},
        )
        admin.delete(f"{BASE_URL}/api/v1/budget-line-items/{item_id}")
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            for action in ("Create", "Update", "Delete"):
                row = db.execute(text(
                    "SELECT 1 FROM audit_log "
                    "WHERE resource_type='budget_line_items' "
                    "  AND resource_id=:rid AND action=:a"
                ), {"rid": item_id, "a": action}).first()
                assert row is not None, f"missing {action} audit for item"
        finally:
            db.close()

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_create_version_writes_audit_log_with_superseded_id(
        self, admin, project,
    ):
        """Build Pack #39 — `new_version` creation writes a `Create`
        audit_log row whose `metadata_json` includes
        `kind='new_version'` and `superseded_id` pointing at the old
        version's id."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        v1_id = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{v1_id}/activate")
        rv = admin.post(
            f"{BASE_URL}/api/v1/budgets/{v1_id}/new-version",
            json={"version_label": "v2-audit"},
        )
        assert rv.status_code == 201, rv.text
        v2_id = rv.json()["id"]

        db = SessionLocal()
        try:
            row = db.execute(text(
                "SELECT metadata_json FROM audit_log "
                "WHERE resource_type='budgets' AND resource_id=:r "
                "  AND action='Create' "
                "  AND metadata_json->>'kind' = 'new_version' "
                "ORDER BY created_at DESC LIMIT 1"
            ), {"r": v2_id}).first()
            assert row is not None, (
                "expected an audit_log row for the new-version create "
                f"with kind='new_version', resource_id={v2_id}"
            )
            meta = row[0]
            assert meta["kind"] == "new_version"
            assert meta["superseded_id"] == v1_id
        finally:
            db.close()


# --------------------------------------------------------------------------
# Sensitive-field gating: readonly sees non-sensitive only
# --------------------------------------------------------------------------

class TestSensitiveGating:
    def test_readonly_misses_sensitive_keys(
        self, admin, readonly, project,
    ):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        # readonly should see basic fields but NOT sensitive monetary caches.
        rg = readonly.get(f"{BASE_URL}/api/v1/budgets/{bid}")
        if rg.status_code == 404:
            pytest.skip("readonly user has no project scope")
        assert rg.status_code == 200, rg.text
        body = rg.json()
        # Non-sensitive present
        assert "total_budget" in body
        assert "status" in body
        # Sensitive omitted (not nullified)
        for k in (
            "total_actuals", "total_committed_not_invoiced",
            "forecast_final_cost", "variance_vs_budget", "variance_pct",
        ):
            assert k not in body, f"expected {k!r} to be omitted for readonly"

    def test_admin_sees_sensitive(self, admin, fresh_active_budget):
        bid = fresh_active_budget["id"]
        body = admin.get(f"{BASE_URL}/api/v1/budgets/{bid}").json()
        assert "total_actuals" in body
        assert "variance_pct" in body


# --------------------------------------------------------------------------
# Concurrency invariant — partial unique index B3
# --------------------------------------------------------------------------

class TestConcurrencyInvariant:
    def test_one_current_per_project_partial_index_exists(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname='uq_budgets_one_current_per_project'"
            )).first()
            assert row is not None

    def test_partial_index_blocks_duplicate_current(
        self, db_engine, admin, project,
    ):
        # Create one is_current via service. Attempt to insert a second
        # is_current=true row directly via SQL — must violate the partial
        # unique index.
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201
        # Direct SQL inject second is_current=true row.
        from sqlalchemy.exc import IntegrityError
        admin_uid = None
        with db_engine.connect() as c:
            admin_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "rhys@syhomes.co.uk")
            admin_uid = c.execute(text(
                "SELECT id FROM users WHERE email=:e"
            ), {"e": admin_email}).scalar()
        with pytest.raises(IntegrityError):
            with db_engine.begin() as c:
                c.execute(text("""
                    INSERT INTO budgets
                      (id, project_id, source_appraisal_id, version_number,
                       version_label, is_current, status,
                       created_by_user_id)
                    VALUES (gen_random_uuid(), :p, :a, 99, 'rogue',
                            true, 'Draft', :u)
                """), {"p": project["id"], "a": aid, "u": admin_uid})

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_concurrent_lock_serialised_via_select_for_update(
        self, admin, project,
    ):
        """Build Pack #14 — concurrent writers on a single budget are
        serialised via `SELECT … FOR UPDATE` on the `budgets` row.
        Asserted deterministically with two raw psycopg-3 connections
        and `FOR UPDATE NOWAIT` (raises SQLSTATE 55P03 /
        psycopg.errors.LockNotAvailable when the row is already
        locked). Avoids `time.sleep` entirely.

        Sequence:
          1. Connection A: BEGIN; SELECT ... FOR UPDATE  (holds lock)
          2. Connection B: SELECT ... FOR UPDATE NOWAIT  → 55P03
          3. Connection A: COMMIT                        (releases)
          4. Connection B (after rollback): retry NOWAIT → succeeds
        """
        import psycopg
        from app.db import SessionLocal, DATABASE_URL

        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        bid = r.json()["id"]

        # Strip the SQLAlchemy driver prefix for direct psycopg-3 use.
        raw_dsn = DATABASE_URL.replace("postgresql+psycopg://",
                                       "postgresql://")
        conn_a = psycopg.connect(raw_dsn, autocommit=False)
        conn_b = psycopg.connect(raw_dsn, autocommit=False)
        try:
            # 1. Connection A acquires the row lock (implicit BEGIN
            #    when autocommit=False).
            cur_a = conn_a.cursor()
            cur_a.execute(
                "SELECT id FROM budgets WHERE id = %s FOR UPDATE",
                (bid,),
            )
            assert cur_a.fetchone() is not None

            # 2. Connection B's NOWAIT must immediately fail.
            cur_b = conn_b.cursor()
            with pytest.raises(psycopg.errors.LockNotAvailable):
                cur_b.execute(
                    "SELECT id FROM budgets WHERE id = %s "
                    "FOR UPDATE NOWAIT",
                    (bid,),
                )
            # Roll back B's failed transaction before reuse.
            conn_b.rollback()

            # 3. A releases by committing.
            conn_a.commit()

            # 4. B can now acquire the lock without waiting.
            cur_b2 = conn_b.cursor()
            cur_b2.execute(
                "SELECT id FROM budgets WHERE id = %s FOR UPDATE NOWAIT",
                (bid,),
            )
            assert cur_b2.fetchone() is not None
            conn_b.commit()
        finally:
            for c in (conn_a, conn_b):
                try:
                    c.rollback()
                except Exception:
                    pass
                c.close()


# --------------------------------------------------------------------------
# refresh-attention scan endpoint
# --------------------------------------------------------------------------

class TestRefreshAttention:
    def test_admin_scan_runs(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/v1/internal/budgets/refresh-attention",
            json={},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("flagged", "cleared", "scanned"):
            assert k in body

    def test_pm_cannot_scan(self, pm):
        r = pm.post(
            f"{BASE_URL}/api/v1/internal/budgets/refresh-attention",
            json={},
        )
        assert r.status_code == 403

    # ----------------------------------------------------------------
    # Chat 16.5 — Build Pack coverage debt (R2)
    # ----------------------------------------------------------------

    def test_requires_attention_clears_when_no_longer_matching(
        self, admin, project,
    ):
        """Build Pack #78 — `requires_attention=True` rows are cleared
        on the next refresh-attention scan once they no longer match
        the criteria (variance_status flips Red→Amber/Green, OR an
        approval action moves status off Pending_Approval).

        Setup: drive a line into Red via Manual ftc inflation, run
        scan to flag it, then patch the line back to Green and re-run
        scan. The line's `requires_attention` must be False after
        the second scan (and the `cleared` count includes it)."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        bid = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
        line = r.json()["lines"][0]
        line_id = line["id"]
        cb = Decimal(line["current_budget"])

        # Drive the line into Red: ftc 10× current_budget guarantees
        # variance_pct ≫ 15%.
        r1 = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line_id}",
            json={"ftc_method": "Manual",
                  "forecast_to_complete": str(cb * 10)},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["variance_status"] == "Red"

        # First scan: flags the Red line.
        r2 = admin.post(
            f"{BASE_URL}/api/v1/internal/budgets/refresh-attention",
            json={},
        )
        assert r2.status_code == 200, r2.text
        # Verify the line is now flagged.
        with admin.get(f"{BASE_URL}/api/v1/budgets/{bid}") as _:
            pass
        db = SessionLocal()
        try:
            flagged = db.execute(text(
                "SELECT requires_attention FROM budget_lines WHERE id=:l"
            ), {"l": line_id}).scalar()
        finally:
            db.close()
        assert flagged is True, (
            "expected requires_attention=True after Red scan"
        )

        # Restore Green: ftc=0 → ffc = actuals + cni = 0 → variance=
        # -current_budget (under-budget) → Green.
        r3 = admin.patch(
            f"{BASE_URL}/api/v1/budget-lines/{line_id}",
            json={"ftc_method": "Manual",
                  "forecast_to_complete": "0"},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["variance_status"] == "Green"

        # Second scan: cleared count must include this line.
        r4 = admin.post(
            f"{BASE_URL}/api/v1/internal/budgets/refresh-attention",
            json={},
        )
        assert r4.status_code == 200, r4.text
        assert r4.json()["cleared"] >= 1, (
            f"expected cleared>=1 after Green re-scan, got {r4.json()}"
        )

        # Final state: line is no longer flagged.
        db = SessionLocal()
        try:
            cleared = db.execute(text(
                "SELECT requires_attention FROM budget_lines WHERE id=:l"
            ), {"l": line_id}).scalar()
        finally:
            db.close()
        assert cleared is False, (
            "expected requires_attention=False after the line returned "
            "to Green and was rescanned"
        )


# --------------------------------------------------------------------------
# Detail endpoint query budget — B16 / Test #91 (≤5 queries)
# --------------------------------------------------------------------------

class TestDetailQueryBudget:
    def test_detail_endpoint_query_count(self, db_engine, admin, project):
        # Build a budget with several lines so selectinload is exercised.
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                       {"p": project["id"]})
            db.commit()
        finally:
            db.close()
        aid = _make_approved_appraisal(admin, project["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r.json()["id"]
        # Hit the endpoint counting SELECT queries on the live engine.
        # Note: we count app-server queries, not the test session — so we
        # piggy-back on the existing engine via a counter of the live PG
        # via pg_stat_statements is not portable. Instead, we attach a
        # before_cursor_execute listener to the SessionLocal engine and
        # invoke the service-layer load directly (deterministic mirror of
        # the route's body).
        from app.services.budgets import _load_budget_for_read
        from app.models.user import User
        from app.auth.permissions import compute_effective_permissions
        db = SessionLocal()
        try:
            admin_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "rhys@syhomes.co.uk")
            uid = db.execute(
                text("SELECT id FROM users WHERE email=:e"), {"e": admin_email}
            ).scalar()
            u = db.get(User, uid)
            perms = compute_effective_permissions(db, u.id, u.tenant_id)
            queries: list[str] = []

            def _on_before(conn, cursor, statement, *args, **kw):
                queries.append(statement)

            engine = db.get_bind()
            event.listen(engine, "before_cursor_execute", _on_before)
            try:
                b = _load_budget_for_read(db, uuid.UUID(bid), u, perms)
                _ = [(l.id, [i.id for i in l.items]) for l in b.lines]
            finally:
                event.remove(engine, "before_cursor_execute", _on_before)

            # _load_budget_for_read fires:
            #   1 Budget + selectinload(lines) + selectinload(items) = 3
            #   1 Project lookup
            #   1 _visible_project_ids (UserRole load)
            # Some setups add user_role_projects (only for Specific scope) —
            # super_admin has 'All' so that's skipped.
            assert len(queries) <= 5, (
                f"detail load issued {len(queries)} queries: "
                + "\n".join(queries)
            )
        finally:
            db.close()
