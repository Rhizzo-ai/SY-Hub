"""Budgets reconciliation service tests — Prompt 2.5A / Chat 19A.

Direct against `app.services.budgets_reconciliation` via SQLAlchemy sessions.
Mirrors the fixture pattern from test_actuals_service.py.
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
from app.models.budgets import Budget, BudgetLine
from app.models.user import User
from app.schemas.actuals import CreateActualRequest
from app.services import actuals as actuals_svc
from app.services import budgets_reconciliation

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


def _all_perms(user) -> UserPermissions:
    perm_set = {
        "actuals.view", "actuals.view_sensitive",
        "actuals.create", "actuals.edit",
        "actuals.approve", "actuals.admin",
    }
    return UserPermissions(
        user_id=user.id,
        tenant_id=user.tenant_id,
        all_permissions=set(perm_set),
        all_entity_perms=set(perm_set),
        all_project_perms=set(perm_set),
        is_super_admin=True,
    )


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
                    '1 Reco Way', 'SY3 2AA', false, :u)
        """), {"id": project_id, "code": f"RECO-{project_id.hex[:6]}",
               "name": f"Reco Test {project_id.hex[:6]}",
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
                :id, :pid, 'Reco Base', CURRENT_DATE,
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

        cc_rows = c.execute(text("SELECT id FROM cost_codes ORDER BY code LIMIT 3")).all()
        cc_ids = [r[0] for r in cc_rows]
        if len(cc_ids) < 2:
            pytest.skip("need >= 2 cost_codes")

        line1_id = uuid.uuid4()
        line2_id = uuid.uuid4()
        for lid, order, cc in [(line1_id, 1, cc_ids[0]), (line2_id, 2, cc_ids[1])]:
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
        c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM budgets WHERE id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": refs["appraisal_id"]})
        c.execute(text("DELETE FROM projects WHERE id=:p"),
                  {"p": refs["project_id"]})


@pytest.fixture(autouse=True)
def _wipe(engine):
    yield
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log"))
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals"))
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text(
            "UPDATE budget_lines SET actuals_to_date=0, committed_not_invoiced=0"
        ))


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


def _make_actual(db, seeds, user, perms, *, status="Posted",
                 net=Decimal("1000.00"),
                 budget_line_id=None,
                 retention_rate=None, retention_released=False):
    body = CreateActualRequest(
        project_id=seeds["project_id"],
        budget_line_id=budget_line_id or seeds["line1_id"],
        entity_id=seeds["entity_id"],
        source_type="Manual_Entry",
        transaction_date=date.today(),
        description="reco test",
        net_amount=net,
        vat_amount=Decimal("0"),
        vat_rate_pct=Decimal("20"),
        supplier_name_snapshot="ACME Ltd",
        retention_rate_pct=retention_rate,
    )
    a = actuals_svc.create_actual(db, payload=body, user=user, perms=perms)
    db.commit()
    if status != "Draft":
        if status == "Void":
            actuals_svc.void_actual(
                db, actual_id=a.id, void_reason="x",
                user=user, perms=perms,
            )
        else:
            actuals_svc.post_actual(
                db, actual_id=a.id, user=user, perms=perms,
            )
            if status == "Paid":
                actuals_svc.mark_paid(
                    db, actual_id=a.id, paid_date=date.today(),
                    payment_reference="P", user=user, perms=perms,
                )
            elif status == "Disputed":
                actuals_svc.dispute_actual(
                    db, actual_id=a.id, dispute_reason="x",
                    user=user, perms=perms,
                )
            if retention_released and retention_rate:
                actuals_svc.release_retention(
                    db, actual_id=a.id, retention_release_date=date.today(),
                    user=user, perms=perms,
                )
        db.commit()
    return a


class TestReconciliation:
    def test_recompute_sums_posted_only_excludes_void(
        self, db, seeds, admin_user, perms,
    ):
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("100.00"))
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("200.00"))
        _make_actual(db, seeds, admin_user, perms, status="Void",
                     net=Decimal("999.00"))
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("300.00")

    def test_recompute_updates_parent_budget_header(
        self, db, seeds, admin_user, perms,
    ):
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("400.00"))
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        budget = db.get(Budget, seeds["budget_id"])
        db.refresh(budget)
        # total_actuals on budget header reflects the sum across lines.
        assert budget.total_actuals >= Decimal("400.00")

    def test_recompute_recomputes_line_variance(
        self, db, seeds, admin_user, perms,
    ):
        """current_budget=500000, post 600000 in actuals → variance Red."""
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("600000.00"))
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("600000.00")

    def test_voiding_posted_reduces_actuals_to_date(
        self, db, seeds, admin_user, perms,
    ):
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("300.00"))
        a2 = _make_actual(db, seeds, admin_user, perms, status="Posted",
                          net=Decimal("500.00"))
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("800.00")

        actuals_svc.void_actual(
            db, actual_id=a2.id, void_reason="dup",
            user=admin_user, perms=perms,
        )
        db.commit()
        db.refresh(line)
        assert line.actuals_to_date == Decimal("300.00")

    def test_recompute_idempotent(self, db, seeds, admin_user, perms):
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("750.00"))
        for _ in range(3):
            budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("750.00")

    def test_multiple_lines_independent(self, db, seeds, admin_user, perms):
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("100.00"), budget_line_id=seeds["line1_id"])
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("250.00"), budget_line_id=seeds["line2_id"])
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        budgets_reconciliation.recompute_for_line(db, seeds["line2_id"])
        db.commit()
        l1 = db.get(BudgetLine, seeds["line1_id"])
        l2 = db.get(BudgetLine, seeds["line2_id"])
        db.refresh(l1)
        db.refresh(l2)
        assert l1.actuals_to_date == Decimal("100.00")
        assert l2.actuals_to_date == Decimal("250.00")

    def test_disputed_still_counted(self, db, seeds, admin_user, perms):
        """Per service: COUNTED_STATUSES = (Posted, Paid, Disputed). Disputed
        still represents real cost on the books."""
        _make_actual(db, seeds, admin_user, perms, status="Disputed",
                     net=Decimal("123.00"))
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("123.00")

    def test_retention_pending_subtracted(self, db, seeds, admin_user, perms):
        """Posted w/ retention 10% on 1000 → 100 retention pending.
        actuals_to_date should be 1000 - 100 = 900, committed_not_invoiced=100.
        """
        _make_actual(db, seeds, admin_user, perms, status="Posted",
                     net=Decimal("1000.00"),
                     retention_rate=Decimal("10"))
        budgets_reconciliation.recompute_for_line(db, seeds["line1_id"])
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("900.00")
        assert line.committed_not_invoiced == Decimal("100.00")
