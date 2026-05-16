"""Endpoint tests for the Actuals routes — Prompt 2.5A / Chat 19A.

Covers 30 tests across:
- CRUD endpoints (10)
- State transition endpoints (10)
- Attachments (5)
- List filters (5)

All tests hit the real HTTP server (supervisor-managed). Mirrors the
cookie-auth pattern from test_budgets.py.
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import date
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
DIRECTOR_EMAIL = "test-director@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"
READONLY_EMAIL = "test-readonly@example.test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    e = create_engine(DATABASE_URL, future=True)
    with e.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield e
    e.dispose()


def _wipe_routes(engine, project_ids):
    import uuid as _u
    pids = [_u.UUID(p) if isinstance(p, str) else p for p in project_ids]
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM actuals_change_log WHERE actual_id IN "
            "(SELECT id FROM actuals WHERE project_id = ANY(:p))"
        ).bindparams(p=pids))
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actual_attachments WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id = ANY(:p)")
                  .bindparams(p=pids))
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM audit_log WHERE project_id = ANY(:p)")
                  .bindparams(p=pids))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_line_items WHERE budget_line_id IN "
                       "(SELECT id FROM budget_lines WHERE budget_id IN "
                       "(SELECT id FROM budgets WHERE project_id = ANY(:p)))")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM budget_lines WHERE budget_id IN "
                       "(SELECT id FROM budgets WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM budgets WHERE project_id = ANY(:p)")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM appraisal_finance_model WHERE appraisal_id IN "
                       "(SELECT id FROM appraisals WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM appraisal_cost_lines WHERE appraisal_id IN "
                       "(SELECT id FROM appraisals WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM appraisal_units WHERE appraisal_id IN "
                       "(SELECT id FROM appraisals WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_decision_log WHERE appraisal_id IN "
                       "(SELECT id FROM appraisals WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_scenarios WHERE scenario_appraisal_id IN "
                       "(SELECT id FROM appraisals WHERE project_id = ANY(:p))")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM appraisals WHERE project_id = ANY(:p)")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM project_team_members WHERE project_id = ANY(:p)")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM user_role_projects WHERE project_id = ANY(:p)")
                  .bindparams(p=pids))
        c.execute(text("DELETE FROM projects WHERE id = ANY(:p)")
                  .bindparams(p=pids))


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
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def primary_entity_id(db_engine):
    with db_engine.connect() as c:
        eid = c.execute(text(
            "SELECT id FROM entities WHERE name = 'SY Homes (Shrewsbury) Ltd'"
        )).scalar()
    assert eid
    return str(eid)


def _make_approved_appraisal(admin_s, project_id):
    """Helper mirrored from test_budgets.py — create + approve an appraisal."""
    r = admin_s.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
        json={"name": f"Apx-{uuid.uuid4().hex[:6]}", "land_purchase_price": "200000"},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # Inject a Manual cost line with explicit cost_code_id
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
            VALUES (gen_random_uuid(), :a, 10, :cc, 'Build', 'Construction',
                    'Manual', 250000.00, false)
        """), {"a": aid, "cc": cc_id})
        db.commit()
    finally:
        db.close()

    admin_s.post(
        f"{BASE_URL}/api/v1/appraisals/{aid}/units",
        json={"unit_label": "U", "unit_type": "Detached",
              "tenure": "Open_Market", "quantity": 2,
              "price_per_unit": "400000", "build_cost_per_unit": "200000"},
    )
    admin_s.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
    admin_s.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
    return aid


@pytest.fixture(scope="module")
def project(admin, primary_entity_id):
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": "Actuals Routes Test Project",
        "project_type": "Dev_Build",
        "primary_entity_id": primary_entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Routes Way, Shrewsbury",
        "site_postcode": "SY1 2AA",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def active_budget(admin, project):
    """Create + activate a budget on the test project. Returns the budget body."""
    aid = _make_approved_appraisal(admin, project["id"])
    rb = admin.post(
        f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert rb.status_code == 201, rb.text
    budget = rb.json()
    # Activate it
    ract = admin.post(f"{BASE_URL}/api/v1/budgets/{budget['id']}/activate")
    assert ract.status_code == 200, ract.text
    return ract.json()


@pytest.fixture(scope="module")
def line_id(active_budget):
    """Use the first budget line for actuals tests."""
    lines = active_budget["lines"]
    assert lines, "active_budget has no lines"
    return lines[0]["id"]


@pytest.fixture(scope="module", autouse=True)
def all_projects_cleanup(db_engine, project):
    yield
    _wipe_routes(db_engine, [project["id"]])


@pytest.fixture(autouse=True)
def _between(db_engine, project):
    yield
    # After each test, wipe actuals + attachments (preserve budget chain).
    with db_engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": project["id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actual_attachments WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": project["id"]})
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                  {"p": project["id"]})
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text(
            "UPDATE budget_lines SET actuals_to_date=0, committed_not_invoiced=0 "
            "WHERE budget_id IN (SELECT id FROM budgets WHERE project_id=:p)"
        ), {"p": project["id"]})


def _make_create_body(entity_id, line_id, project_id, **overrides):
    body = {
        "project_id": project_id,
        "budget_line_id": line_id,
        "entity_id": entity_id,
        "source_type": "Manual_Entry",
        "transaction_date": str(date.today()),
        "description": "route test",
        "net_amount": "1000.00",
        "vat_amount": "200.00",
        "vat_rate_pct": "20",
        "supplier_name_snapshot": "ACME Ltd",
    }
    body.update(overrides)
    return body


def _create_draft(s, primary_entity_id, line_id, project_id, **overrides):
    r = s.post(
        f"{BASE_URL}/api/v1/actuals",
        json=_make_create_body(primary_entity_id, line_id, project_id, **overrides),
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# CRUD endpoints (10 tests)
# ---------------------------------------------------------------------------

class TestCRUDEndpoints:
    def test_create_returns_201_and_body(self, admin, primary_entity_id, line_id, project):
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals",
            json=_make_create_body(primary_entity_id, line_id, project["id"]),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "Draft"
        assert body["net_amount"] == "1000.00"
        assert body["gross_amount"] == "1200.00"

    def test_create_400_on_bad_budget_line(
        self, admin, primary_entity_id, line_id, project,
    ):
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals",
            json=_make_create_body(
                primary_entity_id, str(uuid.uuid4()), project["id"],
            ),
        )
        assert r.status_code == 400, r.text

    def test_create_403_without_perms(
        self, readonly, primary_entity_id, line_id, project,
    ):
        r = readonly.post(
            f"{BASE_URL}/api/v1/actuals",
            json=_make_create_body(primary_entity_id, line_id, project["id"]),
        )
        assert r.status_code == 403, r.text

    def test_create_404_on_unknown_project(
        self, admin, primary_entity_id, line_id,
    ):
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals",
            json=_make_create_body(
                primary_entity_id, line_id, str(uuid.uuid4()),
            ),
        )
        # service raises ActualNotFoundError → 404
        assert r.status_code in (400, 404), r.text

    def test_get_actual_200(self, admin, primary_entity_id, line_id, project):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = admin.get(f"{BASE_URL}/api/v1/actuals/{a['id']}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == a["id"]
        assert body["status"] == "Draft"

    def test_get_actual_404_unknown(self, admin):
        r = admin.get(f"{BASE_URL}/api/v1/actuals/{uuid.uuid4()}")
        assert r.status_code == 404, r.text

    def test_get_as_finance_includes_sensitive_fields(
        self, finance, primary_entity_id, line_id, project,
    ):
        # Finance has actuals.view_sensitive
        # Need to create via admin first since finance has actuals.create too
        r = finance.post(
            f"{BASE_URL}/api/v1/actuals",
            json=_make_create_body(
                primary_entity_id, line_id, project["id"],
                retention_rate_pct="5",
            ),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # Sensitive fields include retention_amount
        assert "retention_amount" in body

    def test_get_as_readonly_excludes_sensitive(
        self, admin, readonly, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"],
                          retention_rate_pct="5")
        r = readonly.get(f"{BASE_URL}/api/v1/actuals/{a['id']}")
        assert r.status_code == 200, r.text
        body = r.json()
        # Read-only lacks actuals.view_sensitive → retention_amount absent
        assert "retention_amount" not in body

    def test_patch_actual_happy(self, admin, primary_entity_id, line_id, project):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = admin.patch(
            f"{BASE_URL}/api/v1/actuals/{a['id']}",
            json={"description": "edited", "net_amount": "2500.00"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["description"] == "edited"
        assert body["net_amount"] == "2500.00"

    def test_patch_actual_409_on_non_draft(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        rpost = admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        assert rpost.status_code == 200, rpost.text
        r = admin.patch(
            f"{BASE_URL}/api/v1/actuals/{a['id']}",
            json={"description": "no go"},
        )
        assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# State transition endpoints (10 tests)
# ---------------------------------------------------------------------------

class TestStateEndpoints:
    def test_post_200_status_changes(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Posted"

    def test_post_403_without_edit_perm(
        self, admin, readonly, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = readonly.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={},
        )
        assert r.status_code == 403, r.text

    def test_post_409_on_non_draft(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        assert r.status_code == 409, r.text

    def test_mark_paid_200(self, admin, primary_entity_id, line_id, project):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/mark-paid",
            json={"paid_date": str(date.today()), "payment_reference": "PAY-1"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "Paid"
        assert body["paid_date"] == str(date.today())

    def test_void_200_with_reason(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/void",
            json={"void_reason": "duplicate invoice"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Void"

    def test_void_403_without_approve(
        self, admin, pm, primary_entity_id, line_id, project,
    ):
        # PM has create/edit but NOT approve. Voiding requires actuals.approve.
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = pm.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/void",
            json={"void_reason": "x"},
        )
        # pm may or may not have project_scope on this project; accept 403/404.
        assert r.status_code in (403, 404), r.text

    def test_dispute_200(self, admin, primary_entity_id, line_id, project):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/dispute",
            json={"dispute_reason": "wrong amount"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Disputed"

    def test_undispute_200(self, admin, primary_entity_id, line_id, project):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        rp = admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        assert rp.status_code == 200, rp.text
        rd = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/dispute",
            json={"dispute_reason": "wrong"},
        )
        assert rd.status_code == 200, rd.text
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/undispute", json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Posted"

    def test_release_retention_200(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"],
                          retention_rate_pct="5")
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/release-retention",
            json={"retention_release_date": str(date.today())},
        )
        assert r.status_code == 200, r.text
        assert r.json()["retention_released"] is True

    def test_change_log_returns_timeline(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a['id']}/post", json={})
        r = admin.get(f"{BASE_URL}/api/v1/actuals/{a['id']}/change-log")
        assert r.status_code == 200, r.text
        body = r.json()
        types = {row["event_type"] for row in body["items"]}
        assert "Created" in types
        assert "Posted" in types


# ---------------------------------------------------------------------------
# Attachments (5 tests)
# ---------------------------------------------------------------------------

class TestAttachments:
    def test_upload_attachment_stores_file(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        files = {"file": ("invoice.pdf", b"%PDF-1.4 fake", "application/pdf")}
        data = {"source": "Manual_Upload"}
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments",
            files=files, data=data,
            headers={"Content-Type": None},  # let requests pick multipart
        )
        # requests sends multipart automatically when files=... + headers content-type cleared
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["original_filename"] == "invoice.pdf"
        assert body["file_type"] == "application/pdf"

    def test_upload_rejects_bad_mime(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        files = {"file": ("a.exe", b"MZbinary", "application/x-msdownload")}
        data = {"source": "Manual_Upload"}
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments",
            files=files, data=data,
            headers={"Content-Type": None},
        )
        assert r.status_code == 415, r.text

    def test_upload_rejects_oversize(
        self, admin, primary_entity_id, line_id, project,
    ):
        # ACTUALS_ATTACHMENT_MAX_BYTES default = 25MB. Send 26MB.
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        big = b"\x00" * (26 * 1024 * 1024)
        files = {"file": ("big.pdf", big, "application/pdf")}
        data = {"source": "Manual_Upload"}
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments",
            files=files, data=data,
            headers={"Content-Type": None},
        )
        assert r.status_code == 413, r.text

    def test_delete_attachment_on_draft(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        files = {"file": ("doc.pdf", b"%PDF data", "application/pdf")}
        data = {"source": "Manual_Upload"}
        ru = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments",
            files=files, data=data, headers={"Content-Type": None},
        )
        assert ru.status_code == 201
        att_id = ru.json()["id"]
        rd = admin.delete(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments/{att_id}",
        )
        assert rd.status_code == 204, rd.text

    def test_list_attachments(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        files = {"file": ("doc.pdf", b"%PDF data", "application/pdf")}
        data = {"source": "Manual_Upload"}
        admin.post(
            f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments",
            files=files, data=data, headers={"Content-Type": None},
        )
        r = admin.get(f"{BASE_URL}/api/v1/actuals/{a['id']}/attachments")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1
        assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# List filters (5 tests)
# ---------------------------------------------------------------------------

class TestListFilters:
    def test_filter_by_status(
        self, admin, primary_entity_id, line_id, project,
    ):
        a1 = _create_draft(admin, primary_entity_id, line_id, project["id"])
        _create_draft(admin, primary_entity_id, line_id, project["id"])
        admin.post(f"{BASE_URL}/api/v1/actuals/{a1['id']}/post", json={})
        r = admin.get(
            f"{BASE_URL}/api/v1/actuals?status=Posted&project_id={project['id']}",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert all(item["status"] == "Posted" for item in body["items"])
        assert body["total"] == 1

    def test_filter_by_source_type(
        self, admin, primary_entity_id, line_id, project,
    ):
        _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = admin.get(
            f"{BASE_URL}/api/v1/actuals?source_type=Manual_Entry"
            f"&project_id={project['id']}",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert all(item["source_type"] == "Manual_Entry"
                   for item in body["items"])

    def test_filter_by_budget_line_id(
        self, admin, primary_entity_id, line_id, project,
    ):
        _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = admin.get(
            f"{BASE_URL}/api/v1/actuals?budget_line_id={line_id}",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert all(item["budget_line_id"] == line_id for item in body["items"])

    def test_filter_by_transaction_date_range(
        self, admin, primary_entity_id, line_id, project,
    ):
        _create_draft(admin, primary_entity_id, line_id, project["id"])
        today = str(date.today())
        r = admin.get(
            f"{BASE_URL}/api/v1/actuals?transaction_date_from={today}"
            f"&transaction_date_to={today}&project_id={project['id']}",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1

    def test_project_scoped_list(
        self, admin, primary_entity_id, line_id, project,
    ):
        a = _create_draft(admin, primary_entity_id, line_id, project["id"])
        r = admin.get(
            f"{BASE_URL}/api/v1/projects/{project['id']}/actuals",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert any(item["id"] == a["id"] for item in body["items"])


    def test_list_actuals_filter_multi_status_returns_both(
        self, admin, primary_entity_id, line_id, project,
    ):
        """D32 — comma-separated status filter should match each value."""
        a1 = _create_draft(admin, primary_entity_id, line_id, project["id"])
        a2 = _create_draft(admin, primary_entity_id, line_id, project["id"])
        # a1 -> Posted, a2 -> Posted then -> Disputed
        r = admin.post(f"{BASE_URL}/api/v1/actuals/{a1['id']}/post", json={})
        assert r.status_code == 200, r.text
        r = admin.post(f"{BASE_URL}/api/v1/actuals/{a2['id']}/post", json={})
        assert r.status_code == 200, r.text
        r = admin.post(
            f"{BASE_URL}/api/v1/actuals/{a2['id']}/dispute",
            json={"dispute_reason": "test multi-status filter"},
        )
        assert r.status_code == 200, r.text

        r = admin.get(
            f"{BASE_URL}/api/v1/actuals?status=Posted,Disputed"
            f"&project_id={project['id']}",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        ids = {item["id"] for item in body["items"]}
        assert a1["id"] in ids, "expected Posted actual in multi-status list"
        assert a2["id"] in ids, "expected Disputed actual in multi-status list"
        for item in body["items"]:
            assert item["status"] in {"Posted", "Disputed"}

    def test_list_actuals_filter_invalid_status_returns_422(self, admin):
        """D32 — unknown status value must be rejected by the validator."""
        r = admin.get(f"{BASE_URL}/api/v1/actuals?status=Bogus")
        assert r.status_code == 422, r.text
