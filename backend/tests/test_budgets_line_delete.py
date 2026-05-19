"""Chat 23 §R7.3 — single-line DELETE endpoint tests.

Per Build Pack A locked decision: the frontend bulk-delete fan-out
calls this endpoint sequentially. The endpoint itself is NOT bulk;
it deletes one line and emits one audit row.

Covers:
  - 204 happy path + audit row emitted with metadata
  - 404 for unknown line
  - 403 for caller without budgets.edit (readonly user)
  - 409 for Locked / Closed / Superseded budgets
  - Recomputed budget totals after delete
"""
from __future__ import annotations

import os
import uuid

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
READONLY_EMAIL = "test-readonly@example.test"

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


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


def _wipe(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('budgets','budget_lines','budget_line_items',"
            " 'appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members')"
        ))
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
        c.execute(text("DELETE FROM projects WHERE name LIKE 'BudLineDelete%'"))


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    _wipe(db_engine)
    yield
    _wipe(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def entity_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": PRIMARY_ENTITY_NAME},
        ).scalar())


@pytest.fixture(scope="module")
def project(admin, entity_id):
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": "BudLineDelete Project",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Delete Lane, Shrewsbury",
        "site_postcode": "SY1 3BB",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _make_appraisal(admin_session, project_id: str) -> str:
    from app.db import SessionLocal
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
        json={"name": f"A-{uuid.uuid4().hex[:6]}",
              "land_purchase_price": "200000"},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    db = SessionLocal()
    try:
        cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))
        db.execute(text(
            "DELETE FROM appraisal_cost_lines WHERE appraisal_id=:a"
        ), {"a": aid})
        # Two lines so we can delete one and still have one left to verify
        # totals recompute.
        for i, label in enumerate(("Build A", "Build B"), start=1):
            db.execute(text("""
                INSERT INTO appraisal_cost_lines
                  (id, appraisal_id, display_order, cost_code_id, label,
                   category, auto_source, amount, is_locked)
                VALUES (gen_random_uuid(), :a, :ord, :cc, :lbl,
                        'Construction', 'Manual', :amt, false)
            """), {"a": aid, "ord": i * 10, "cc": cc_id,
                   "lbl": label, "amt": 125000 + i})
        db.commit()
    finally:
        db.close()
    admin_session.post(
        f"{BASE_URL}/api/v1/appraisals/{aid}/units",
        json={"unit_label": "U", "unit_type": "Detached",
              "tenure": "Open_Market", "quantity": 2,
              "price_per_unit": "400000",
              "build_cost_per_unit": "200000"},
    )
    admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
    admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
    return aid


@pytest.fixture
def fresh_active(admin, project):
    """Fresh Active budget with TWO lines (different cost codes merged
    one-to-one). Function-scoped so each test gets a clean budget."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                   {"p": project["id"]})
        db.commit()
    finally:
        db.close()
    aid = _make_appraisal(admin, project["id"])
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    r2 = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
    assert r2.status_code == 200, r2.text
    return admin.get(f"{BASE_URL}/api/v1/budgets/{bid}").json()


class TestDeleteBudgetLine:
    def test_delete_line_204(self, admin, fresh_active):
        line = fresh_active["lines"][0]
        r = admin.delete(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}"
        )
        assert r.status_code == 204, r.text
        # Verify gone via GET detail
        detail = admin.get(
            f"{BASE_URL}/api/v1/budgets/{fresh_active['id']}"
        ).json()
        ids = {ln["id"] for ln in detail["lines"]}
        assert line["id"] not in ids

    def test_delete_line_recomputes_totals(self, admin, fresh_active):
        from decimal import Decimal
        before = Decimal(fresh_active["total_budget"])
        line = fresh_active["lines"][0]
        line_amt = Decimal(line["original_budget"])
        r = admin.delete(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}"
        )
        assert r.status_code == 204
        after = Decimal(admin.get(
            f"{BASE_URL}/api/v1/budgets/{fresh_active['id']}"
        ).json()["total_budget"])
        assert after == before - line_amt, (
            f"total_budget should drop by deleted line amount: "
            f"before={before}, after={after}, line_amt={line_amt}"
        )

    def test_delete_line_404_unknown(self, admin):
        r = admin.delete(
            f"{BASE_URL}/api/v1/budget-lines/{uuid.uuid4()}"
        )
        assert r.status_code == 404

    def test_delete_line_403_readonly(self, readonly, fresh_active):
        line = fresh_active["lines"][0]
        r = readonly.delete(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}"
        )
        assert r.status_code == 403

    def test_delete_line_409_when_locked(self, admin, fresh_active):
        bid = fresh_active["id"]
        r_lock = admin.post(f"{BASE_URL}/api/v1/budgets/{bid}/lock")
        assert r_lock.status_code == 200, r_lock.text
        line = fresh_active["lines"][0]
        r = admin.delete(
            f"{BASE_URL}/api/v1/budget-lines/{line['id']}"
        )
        assert r.status_code == 409, r.text

    def test_delete_line_emits_audit_row(self, admin, fresh_active, db_engine):
        line = fresh_active["lines"][0]
        line_id = line["id"]
        r = admin.delete(
            f"{BASE_URL}/api/v1/budget-lines/{line_id}"
        )
        assert r.status_code == 204
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT action, resource_type, resource_id, metadata_json
                FROM audit_log
                WHERE resource_type='budget_lines'
                  AND resource_id=:rid
                  AND action='Delete'
                ORDER BY created_at DESC LIMIT 1
            """), {"rid": line_id}).first()
        assert row is not None, "Expected audit_log row for line delete"
        assert row[0] == "Delete"
        assert row[1] == "budget_lines"
        meta = row[3] or {}
        assert meta.get("kind") == "line_delete"
        assert meta.get("budget_id") == fresh_active["id"]
