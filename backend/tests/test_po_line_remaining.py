"""C1-front (Chat 64) §R6 — derived ``remaining_amount`` on PO lines.

Covers the additive, read-only backend change shipped with the force-the-choice
bill-entry UI:

  * ``services.purchase_orders.remaining_by_line`` — the derivation helper
    (``net_amount − Σ counted-status linked bills``, clamped at zero).
  * ``services.purchase_orders._ser_line`` / ``serialise`` — sensitivity gating
    and map threading.
  * ``GET /v1/budget-lines/{line_id}/purchase-orders`` — each line carries
    ``remaining_amount`` (api-level, mirrors test_purchase_orders_api.py).

Cases 1–8 + 10 run in-process against a direct SQLAlchemy session (the
test_budgets_reconciliation.py / test_actuals_service.py house pattern). Case 9
is the api-level proof and reuses the existing api test's setup helpers.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.permissions import UserPermissions
from app.models.actuals import Actual
from app.models.purchase_orders import PurchaseOrder, PurchaseOrderLine
from app.models.user import User
from app.schemas.actuals import CreateActualRequest
from app.services import actuals as actuals_svc
from app.services import budgets_reconciliation
from app.services import purchase_orders as po_svc

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


def _all_perms(user) -> UserPermissions:
    perm_set = {
        "actuals.view", "actuals.view_sensitive",
        "actuals.create", "actuals.edit",
        "actuals.approve", "actuals.admin",
        "pos.view", "pos.view_sensitive",
    }
    return UserPermissions(
        user_id=user.id,
        tenant_id=user.tenant_id,
        all_permissions=set(perm_set),
        all_entity_perms=set(perm_set),
        all_project_perms=set(perm_set),
        is_super_admin=True,
    )


# ─────────────────────────────────────────────────────────────────────────
# Fixtures (mirror test_budgets_reconciliation.py)
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(scope="module")
def seeds(engine):
    refs = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        admin = c.execute(text(
            "SELECT id, tenant_id FROM users WHERE email='test-admin@example.test'"
        )).first()
        if not (entity_id and admin):
            pytest.skip("required seed rows missing")
        refs["entity_id"] = entity_id
        refs["user_id"] = admin.id
        refs["tenant_id"] = admin.tenant_id

        project_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 Remaining Way', 'SY3 2AA', false, :u)
        """), {"id": project_id, "code": f"REM-{project_id.hex[:6]}",
               "name": f"Remaining Test {project_id.hex[:6]}",
               "ent": entity_id, "u": admin.id})
        refs["project_id"] = project_id

        ag_id = uuid.uuid4()
        ap_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'Remaining Base', CURRENT_DATE,
                :uid, :gid, 'Base', true, 'Approved', 1
            )
        """), {"id": ap_id, "pid": project_id, "uid": admin.id, "gid": ag_id})
        refs["appraisal_id"] = ap_id

        budget_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budgets (id, project_id, source_appraisal_id,
              version_number, version_label, is_current, status,
              created_from_appraisal_at,
              total_budget, total_actuals, total_committed_not_invoiced,
              total_forecast_to_complete, forecast_final_cost,
              variance_vs_budget, variance_pct, summary_refreshed_at,
              created_by_user_id)
            VALUES (:id, :pid, :ap, 1, 'v1', true, 'Active', NOW(),
                    1000000, 0, 0, 1000000, 1000000, 0, 0, NOW(), :u)
        """), {"id": budget_id, "pid": project_id, "ap": ap_id, "u": admin.id})
        refs["budget_id"] = budget_id

        cc_rows = c.execute(text(
            "SELECT id, code FROM cost_codes ORDER BY code LIMIT 3"
        )).all()
        if len(cc_rows) < 2:
            pytest.skip("need >= 2 cost_codes")
        refs["cost_code"] = cc_rows[0].code

        line1_id = uuid.uuid4()
        line2_id = uuid.uuid4()
        for lid, order, cc in [(line1_id, 1, cc_rows[0].id), (line2_id, 2, cc_rows[1].id)]:
            c.execute(text("""
                INSERT INTO budget_lines (id, budget_id, cost_code_id,
                  display_order, line_description, entity_id, ftc_method,
                  original_budget, approved_changes, current_budget,
                  actuals_to_date, committed_value, invoiced_against_commitment,
                  committed_not_invoiced, forecast_to_complete,
                  forecast_final_cost, variance_value, variance_pct,
                  variance_status, is_locked, requires_attention)
                VALUES (:id, :bid, :cc, :ord, :ld, :ent, 'Manual',
                        500000, 0, 500000,
                        0, 0, 0, 0, 500000, 500000,
                        0, 0, 'Green',
                        false, false)
            """), {"id": lid, "bid": budget_id, "cc": cc,
                   "ord": order, "ld": f"Line {order}", "ent": entity_id})
        refs["line1_id"] = line1_id
        refs["line2_id"] = line2_id

        supplier_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO suppliers (id, tenant_id, name, created_by, updated_by)
            VALUES (:id, :t, 'Remaining Test Supplier', :u, :u)
        """), {"id": supplier_id, "t": admin.tenant_id, "u": admin.id})
        refs["supplier_id"] = supplier_id

    yield refs

    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": refs["project_id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                  {"p": refs["project_id"]})
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                  {"p": refs["project_id"]})
        c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM budgets WHERE id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": refs["appraisal_id"]})
        c.execute(text("DELETE FROM projects WHERE id=:p"),
                  {"p": refs["project_id"]})
        c.execute(text("DELETE FROM suppliers WHERE id=:s"),
                  {"s": refs["supplier_id"]})


@pytest.fixture(autouse=True)
def _wipe(engine, seeds):
    """Reset bills + POs for the seeds project between tests so each case
    starts clean. Scoped to the seeds project — does not touch unrelated rows.
    """
    yield
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": seeds["project_id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                  {"p": seeds["project_id"]})
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                  {"p": seeds["project_id"]})


@pytest.fixture
def db(Session):
    s = Session()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def admin_user(db, seeds):
    return db.get(User, seeds["user_id"])


@pytest.fixture
def perms(admin_user):
    return _all_perms(admin_user)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _make_po_line(db, seeds, *, budget_line_id, net, status="draft"):
    """Create a PurchaseOrder + one PurchaseOrderLine via the ORM and return
    the line. PO status is irrelevant to the remaining maths (it sums bills,
    not commitments) — 'draft' avoids the commitment-recompute trigger."""
    net_d = Decimal(net)
    po = PurchaseOrder(
        tenant_id=seeds["tenant_id"],
        project_id=seeds["project_id"],
        po_number=f"PO-{uuid.uuid4().hex[:8]}",
        supplier_id=seeds["supplier_id"],
        budget_id=seeds["budget_id"],
        status=status,
        subtotal_amount=net_d,
        vat_amount=Decimal("0"),
        total_amount=net_d,
        created_by=seeds["user_id"],
        updated_by=seeds["user_id"],
    )
    line = PurchaseOrderLine(
        purchase_order=po,
        budget_line_id=budget_line_id,
        cost_code=seeds["cost_code"],
        line_number=1,
        description="test po line",
        quantity=Decimal("1"),
        unit_rate=net_d,
        net_amount=net_d,
        vat_rate=Decimal("20.00"),
        vat_amount=Decimal("0"),
        gross_amount=net_d,
        created_by=seeds["user_id"],
        updated_by=seeds["user_id"],
    )
    db.add(po)
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


def _make_bill(db, seeds, user, perms, *, net, budget_line_id,
               linked_commitment_id=None, status="Posted"):
    """Create a bill (actual) optionally linked to a PO line, then advance it
    to ``status`` via the real service transitions."""
    body = CreateActualRequest(
        project_id=seeds["project_id"],
        budget_line_id=budget_line_id,
        entity_id=seeds["entity_id"],
        source_type="Manual_Entry",
        transaction_date=date.today(),
        description="remaining test bill",
        net_amount=Decimal(net),
        vat_amount=Decimal("0"),
        vat_rate_pct=Decimal("20"),
        supplier_name_snapshot="ACME Ltd",
        linked_commitment_id=linked_commitment_id,
    )
    a = actuals_svc.create_actual(db, payload=body, user=user, perms=perms)
    db.commit()
    if status == "Draft":
        return a
    if status == "Void":
        actuals_svc.void_actual(
            db, actual_id=a.id, void_reason="x", user=user, perms=perms,
        )
    else:
        actuals_svc.post_actual(db, actual_id=a.id, user=user, perms=perms)
        if status == "Paid":
            actuals_svc.mark_paid(
                db, actual_id=a.id, paid_date=date.today(),
                payment_reference="P", user=user, perms=perms,
            )
        elif status == "Disputed":
            actuals_svc.dispute_actual(
                db, actual_id=a.id, dispute_reason="x", user=user, perms=perms,
            )
    db.commit()
    return a


# ─────────────────────────────────────────────────────────────────────────
# Cases 1–6 — remaining_by_line derivation
# ─────────────────────────────────────────────────────────────────────────

class TestRemainingByLine:
    def test_01_no_bills_full_remaining(self, db, seeds):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        out = po_svc.remaining_by_line(db, [line])
        assert out[str(line.id)] == "10000.00"

    def test_02_one_posted_bill_reduces(self, db, seeds, admin_user, perms):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        _make_bill(db, seeds, admin_user, perms, net="4000",
                   budget_line_id=seeds["line1_id"], linked_commitment_id=line.id,
                   status="Posted")
        out = po_svc.remaining_by_line(db, [line])
        assert out[str(line.id)] == "6000.00"

    def test_03_over_invoiced_clamps_to_zero(self, db, seeds, admin_user, perms):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        _make_bill(db, seeds, admin_user, perms, net="4000",
                   budget_line_id=seeds["line1_id"], linked_commitment_id=line.id,
                   status="Posted")
        _make_bill(db, seeds, admin_user, perms, net="7000",
                   budget_line_id=seeds["line1_id"], linked_commitment_id=line.id,
                   status="Paid")
        out = po_svc.remaining_by_line(db, [line])
        assert out[str(line.id)] == "0.00"

    def test_04_draft_bill_does_not_reduce(self, db, seeds, admin_user, perms):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        _make_bill(db, seeds, admin_user, perms, net="4000",
                   budget_line_id=seeds["line1_id"], linked_commitment_id=line.id,
                   status="Draft")
        out = po_svc.remaining_by_line(db, [line])
        assert out[str(line.id)] == "10000.00"

    def test_05_void_bill_does_not_reduce(self, db, seeds, admin_user, perms):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        _make_bill(db, seeds, admin_user, perms, net="4000",
                   budget_line_id=seeds["line1_id"], linked_commitment_id=line.id,
                   status="Void")
        out = po_svc.remaining_by_line(db, [line])
        assert out[str(line.id)] == "10000.00"

    def test_06_bill_on_different_line_does_not_reduce(self, db, seeds, admin_user, perms):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        other = _make_po_line(db, seeds, budget_line_id=seeds["line2_id"], net="8000")
        # A posted bill linked to the OTHER PO line (on line2) must not touch line1.
        _make_bill(db, seeds, admin_user, perms, net="5000",
                   budget_line_id=seeds["line2_id"], linked_commitment_id=other.id,
                   status="Posted")
        out = po_svc.remaining_by_line(db, [line])
        assert out[str(line.id)] == "10000.00"


# ─────────────────────────────────────────────────────────────────────────
# Cases 7–8 — serialiser sensitivity + map threading
# ─────────────────────────────────────────────────────────────────────────

class TestSerialiserRemaining:
    def test_07_without_sensitive_is_null(self, db, seeds):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        rmap = po_svc.remaining_by_line(db, [line])
        out = po_svc._ser_line(line, include_sensitive=False, remaining_by_line_id=rmap)
        assert out["remaining_amount"] is None

    def test_08_with_sensitive_is_string_figure(self, db, seeds, admin_user, perms):
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        _make_bill(db, seeds, admin_user, perms, net="4000",
                   budget_line_id=seeds["line1_id"], linked_commitment_id=line.id,
                   status="Posted")
        rmap = po_svc.remaining_by_line(db, [line])
        out = po_svc._ser_line(line, include_sensitive=True, remaining_by_line_id=rmap)
        assert out["remaining_amount"] == "6000.00"

    def test_08b_no_map_emits_null_backward_compat(self, db, seeds):
        # Legacy callers pass no map → remaining_amount is null, never absent.
        line = _make_po_line(db, seeds, budget_line_id=seeds["line1_id"], net="10000")
        out = po_svc._ser_line(line, include_sensitive=True)
        assert out["remaining_amount"] is None


# ─────────────────────────────────────────────────────────────────────────
# Case 10 — counted-status lock-step (drift guard)
# ─────────────────────────────────────────────────────────────────────────

class TestCountedStatusLockstep:
    def test_10_counted_statuses_are_imported_not_redeclared(self):
        # The remaining helper imports COUNTED_STATUSES from the budget engine —
        # same object, so the two can never drift.
        assert po_svc.COUNTED_STATUSES is budgets_reconciliation.COUNTED_STATUSES
        assert po_svc.COUNTED_STATUSES == ("Posted", "Paid", "Disputed")


# ─────────────────────────────────────────────────────────────────────────
# Case 9 — api-level: endpoint carries remaining_amount
# (mirrors test_purchase_orders_api.py setup; requires the live uvicorn)
# ─────────────────────────────────────────────────────────────────────────

from tests.conftest import login_with_auto_enroll  # noqa: E402
from tests.test_purchase_orders_api import (  # noqa: E402
    ADMIN_EMAIL, BASE_URL, PWD, RO_EMAIL,
    _create_project, _create_supplier, _po_create_body, _seed_budget_and_lines,
)


@pytest.fixture(scope="module")
def http_engine():
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


@pytest.fixture(scope="module")
def http_admin(http_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def http_readonly(http_engine):
    return login_with_auto_enroll(None, BASE_URL, RO_EMAIL, PWD)


class TestRemainingApi:
    """GET /v1/budget-lines/{line_id}/purchase-orders carries remaining_amount."""

    def test_09_endpoint_includes_remaining_amount(
        self, http_admin, http_readonly, http_engine, Session,
    ):
        # --- setup: project + budget + line + supplier + PO (line net 200) ---
        from tests.test_purchase_orders_api import _entity_id
        eid = _entity_id(http_engine, ADMIN_EMAIL)
        project_id = _create_project(http_admin, eid)
        try:
            budget_id, budget_line_id = _seed_budget_and_lines(
                http_engine, http_admin, project_id,
            )
            supplier_id = _create_supplier(http_admin, uuid.uuid4().hex[:6].upper())
            setup = {
                "project_id": project_id, "budget_id": budget_id,
                "budget_line_id": budget_line_id, "supplier_id": supplier_id,
            }
            r = http_admin.post(
                f"{BASE_URL}/api/v1/projects/{project_id}/purchase-orders",
                json=_po_create_body(setup),  # qty 2 × unit_rate 100 → net 200
            )
            assert r.status_code == 201, r.text
            po = r.json()
            po_line = next(
                ln for ln in po["lines"]
                if str(ln["budget_line_id"]) == budget_line_id
            )
            assert po_line["net_amount"] == "200.00", po_line

            # --- a Posted bill of 50 linked to that PO line (via service) ---
            sess = Session()
            try:
                admin_user = sess.execute(
                    text("SELECT id FROM users WHERE email=:e"),
                    {"e": ADMIN_EMAIL},
                ).scalar()
                user = sess.get(User, admin_user)
                _make_bill(
                    sess,
                    {"project_id": uuid.UUID(project_id),
                     "budget_line_id": uuid.UUID(budget_line_id),
                     "entity_id": uuid.UUID(eid)},
                    user, _all_perms(user),
                    net="50",
                    budget_line_id=uuid.UUID(budget_line_id),
                    linked_commitment_id=uuid.UUID(po_line["id"]),
                    status="Posted",
                )
            finally:
                sess.close()

            # --- admin (has pos.view_sensitive): remaining present, = 150.00 ---
            r2 = http_admin.get(
                f"{BASE_URL}/api/v1/budget-lines/{budget_line_id}/purchase-orders"
            )
            assert r2.status_code == 200, r2.text
            items = r2.json()["items"]
            assert items, "PO row should be returned"
            line = next(
                ln for ln in items[0]["lines"]
                if str(ln["budget_line_id"]) == budget_line_id
            )
            assert "remaining_amount" in line
            assert line["remaining_amount"] == "150.00", line

            # --- read-only (no pos.view_sensitive): remaining_amount is null ---
            r3 = http_readonly.get(
                f"{BASE_URL}/api/v1/budget-lines/{budget_line_id}/purchase-orders"
            )
            assert r3.status_code == 200, r3.text
            ro_items = r3.json()["items"]
            assert ro_items, "RO should see the PO row exists"
            ro_line = ro_items[0]["lines"][0]
            assert ro_line.get("remaining_amount") is None, ro_line
        finally:
            with http_engine.begin() as c:
                c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
                c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                               "(SELECT id FROM actuals WHERE project_id=:p)"),
                          {"p": project_id})
                c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
                c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
                c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                          {"p": project_id})
                c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
                c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                          {"p": project_id})
                c.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                          {"p": project_id})
                c.execute(text("DELETE FROM appraisals WHERE project_id=:p"),
                          {"p": project_id})
                c.execute(text("DELETE FROM projects WHERE id=:p"),
                          {"p": project_id})
