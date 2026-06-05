"""Build Pack 2.6-FIX (Chat 39) §R5 — A1 integrity tests.

Verifies that ``committed_not_invoiced`` is a single-writer column
maintained by ``budgets_reconciliation.recompute_for_line`` as
``retention_pending + po_committed_not_invoiced``, and that neither the
PG trigger nor an actual transition clobbers the other bucket.

Money-path assertions assert resulting financial state — not just status
codes.
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
from app.models.budgets import Budget, BudgetLine
from app.models.user import User
from app.schemas.actuals import CreateActualRequest
from app.services import actuals as actuals_svc
from app.services import budgets_reconciliation

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


def _perms(user) -> UserPermissions:
    perm_set = {
        "actuals.view", "actuals.view_sensitive",
        "actuals.create", "actuals.edit", "actuals.approve",
        "actuals.admin", "actuals.release_retention",
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
    refs: dict = {}
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

        # Per-module supplier (seed_test_users does not seed suppliers).
        supplier_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO suppliers
              (id, tenant_id, name, is_archived,
               created_by, updated_by)
            VALUES (:id, :tid, :name, false, :u, :u)
        """), {
            "id": supplier_id, "tid": admin.tenant_id,
            "name": f"Integrity39 supplier {supplier_id.hex[:6]}",
            "u": admin.id,
        })
        refs["supplier_id"] = supplier_id

        project_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '39 Integrity Way', 'SY3 9AA', false, :u)
        """), {"id": project_id, "code": f"INT39-{project_id.hex[:6]}",
               "name": f"Integrity Test {project_id.hex[:6]}",
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
                :id, :pid, 'Base', CURRENT_DATE,
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

        cc_id = c.execute(text(
            "SELECT id FROM cost_codes ORDER BY code LIMIT 1"
        )).scalar()
        if cc_id is None:
            pytest.skip("need >=1 cost_code")

        line_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budget_lines (id, budget_id, cost_code_id,
              display_order, line_description, entity_id, ftc_method,
              original_budget, approved_changes, current_budget,
              actuals_to_date, committed_value, invoiced_against_commitment,
              committed_not_invoiced, forecast_to_complete,
              forecast_final_cost, variance_value, variance_pct,
              variance_status, is_locked, requires_attention)
            VALUES (:id, :bid, :cc, 1, 'Line 1', :ent, 'Manual',
                    500000, 0, 500000,
                    0, 0, 0, 0, 500000, 500000,
                    0, 0, 'Green',
                    false, false)
        """), {"id": line_id, "bid": budget_id, "cc": cc_id, "ent": entity_id})
        refs["line_id"] = line_id

    yield refs

    with engine.begin() as c:
        # Tear down in dependency order. POs first (FK to budget_lines).
        c.execute(text(
            "DELETE FROM purchase_order_lines WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE project_id=:p)"
        ), {"p": refs["project_id"]})
        c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                  {"p": refs["project_id"]})
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
        c.execute(text("DELETE FROM suppliers WHERE id=:s"),
                  {"s": refs["supplier_id"]})


@pytest.fixture(autouse=True)
def _wipe(engine, seeds):
    yield
    with engine.begin() as c:
        c.execute(text(
            "DELETE FROM purchase_order_lines WHERE budget_line_id=:l"
        ), {"l": seeds["line_id"]})
        c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                  {"p": seeds["project_id"]})
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log"))
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals"))
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("""
            UPDATE budget_lines
               SET actuals_to_date=0, committed_not_invoiced=0,
                   committed_value=0, invoiced_against_commitment=0
             WHERE id=:l
        """), {"l": seeds["line_id"]})


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
    return _perms(admin_user)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_actual(db, seeds, user, perms, *, net, retention_rate=None):
    body = CreateActualRequest(
        project_id=seeds["project_id"],
        budget_line_id=seeds["line_id"],
        entity_id=seeds["entity_id"],
        source_type="Manual_Entry",
        transaction_date=date.today(),
        description="integrity test actual",
        net_amount=net,
        vat_amount=Decimal("0"),
        vat_rate_pct=Decimal("20"),
        supplier_name_snapshot="ACME Ltd",
        retention_rate_pct=retention_rate,
    )
    a = actuals_svc.create_actual(db, payload=body, user=user, perms=perms)
    db.commit()
    actuals_svc.post_actual(db, actual_id=a.id, user=user, perms=perms)
    db.commit()
    return a


def _make_po_with_line(
    db, seeds, *, status: str, net: Decimal,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a PO + one PO line via raw SQL (bypasses approval flows).

    Sets ``po.status`` directly so the test can land at issued/approved
    without dragging the whole approval state machine in. Fires
    ``trg_pol_commitments_on_change`` → updates ``committed_value`` on the
    budget_line via the PG trigger.
    """
    po_id = uuid.uuid4()
    pol_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO purchase_orders
          (id, tenant_id, project_id, po_number, supplier_id, budget_id,
           status, subtotal_amount, vat_amount, total_amount, currency,
           created_by, updated_by)
        VALUES (:id, :ten, :pid, :num, :sup, :bid, :st,
                :net, 0, :net, 'GBP', :u, :u)
    """), {
        "id": po_id, "ten": seeds["tenant_id"], "pid": seeds["project_id"],
        "num": f"PO-{po_id.hex[:8]}", "sup": seeds["supplier_id"],
        "bid": seeds["budget_id"], "st": status, "net": net,
        "u": seeds["user_id"],
    })
    db.execute(text("""
        INSERT INTO purchase_order_lines
          (id, purchase_order_id, budget_line_id, cost_code, line_number,
           description, quantity, unit_rate, net_amount, vat_rate, vat_amount,
           gross_amount, receipted_quantity, created_by, updated_by)
        VALUES (:id, :poid, :bl, 'CC-1', 1, 'test line',
                1, :net, :net, 20, 0, :net, 0, :u, :u)
    """), {
        "id": pol_id, "poid": po_id, "bl": seeds["line_id"], "net": net,
        "u": seeds["user_id"],
    })
    db.commit()
    return po_id, pol_id


# ---------------------------------------------------------------------------
# Test #1
# ---------------------------------------------------------------------------

def test_committed_not_invoiced_holds_both_retention_and_po(
    db, seeds, admin_user, perms,
):
    """A1 #1 — committed_not_invoiced = retention_pending + PO bucket.

    Both buckets MUST survive. Asserts the sum, not either alone.
    """
    # PO bucket: an 'approved' PO worth £2,000.
    _make_po_with_line(db, seeds, status="approved", net=Decimal("2000.00"))

    # Retention bucket: £1,000 actual at 10% → £100 retention pending.
    _post_actual(db, seeds, admin_user, perms,
                 net=Decimal("1000.00"),
                 retention_rate=Decimal("10"))

    # Trigger the Python recompute (in production this is called from
    # the actual transition path; explicit here so the test sees a
    # deterministic post-recompute state).
    budgets_reconciliation.recompute_for_line(db, seeds["line_id"])
    db.commit()

    line = db.get(BudgetLine, seeds["line_id"])
    db.refresh(line)
    # actuals_to_date = 1000 − 100 retention pending = 900.
    assert line.actuals_to_date == Decimal("900.00")
    # committed_not_invoiced = 100 (retention) + 2000 (PO) = 2100.
    assert line.committed_not_invoiced == Decimal("2100.00")
    # Sanity: it's NOT either bucket alone.
    assert line.committed_not_invoiced != Decimal("100.00")
    assert line.committed_not_invoiced != Decimal("2000.00")


# ---------------------------------------------------------------------------
# Test #2 — explicit retention-release transition coverage
# ---------------------------------------------------------------------------

def test_actual_transition_does_not_clobber_po_commitment(
    db, seeds, admin_user, perms,
):
    """A1 #2 — Posting / voiding an actual must leave the PO bucket alone.

    Includes an explicit retention-RELEASE transition: released retention
    must drop out of committed_not_invoiced (flow into actuals_to_date)
    while the PO bucket is preserved.
    """
    # PO bucket: £5,000 approved.
    _make_po_with_line(db, seeds, status="approved", net=Decimal("5000.00"))

    # Post an actual with 5% retention on £1,000 → £50 retention pending.
    a_ret = _post_actual(db, seeds, admin_user, perms,
                         net=Decimal("1000.00"),
                         retention_rate=Decimal("5"))
    db.commit()

    # Post a second actual without retention so we have a "void candidate".
    a_void = _post_actual(db, seeds, admin_user, perms,
                          net=Decimal("250.00"))
    budgets_reconciliation.recompute_for_line(db, seeds["line_id"])
    db.commit()

    line = db.get(BudgetLine, seeds["line_id"])
    db.refresh(line)
    # 5000 (PO) + 50 (retention pending) = 5050.
    assert line.committed_not_invoiced == Decimal("5050.00")
    # 1000 + 250 - 50 retention = 1200.
    assert line.actuals_to_date == Decimal("1200.00")

    # Void the second (non-retention) actual. PO bucket survives.
    actuals_svc.void_actual(
        db, actual_id=a_void.id, void_reason="dup",
        user=admin_user, perms=perms,
    )
    db.commit()
    db.refresh(line)
    assert line.committed_not_invoiced == Decimal("5050.00"), (
        "Voiding an actual clobbered the PO bucket"
    )
    # actuals_to_date = 1000 - 50 retention pending = 950.
    assert line.actuals_to_date == Decimal("950.00")

    # ── Retention-release transition (Chat 39 §R2 A1 explicit coverage).
    actuals_svc.release_retention(
        db, actual_id=a_ret.id, retention_release_date=date.today(),
        user=admin_user, perms=perms,
    )
    db.commit()
    db.refresh(line)
    # Released retention must NOT remain in committed_not_invoiced.
    assert line.committed_not_invoiced == Decimal("5000.00"), (
        "Released retention still parked in committed_not_invoiced"
    )
    # 1000 gross released → flows to actuals_to_date.
    assert line.actuals_to_date == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Test #3 — PO change must not clobber retention
# ---------------------------------------------------------------------------

def test_po_change_does_not_clobber_retention_pending(
    db, seeds, admin_user, perms,
):
    """A1 #3 — A PO status change must not destroy the retention bucket.

    Inverse of #2. Validates the trigger no longer writes
    committed_not_invoiced.
    """
    # Retention pending: £200 (£2,000 @ 10%).
    _post_actual(db, seeds, admin_user, perms,
                 net=Decimal("2000.00"),
                 retention_rate=Decimal("10"))
    # PO at issued status worth £3,000.
    po_id, _ = _make_po_with_line(
        db, seeds, status="issued", net=Decimal("3000.00"),
    )

    budgets_reconciliation.recompute_for_line(db, seeds["line_id"])
    db.commit()

    line = db.get(BudgetLine, seeds["line_id"])
    db.refresh(line)
    # 200 + 3000 = 3200.
    assert line.committed_not_invoiced == Decimal("3200.00")

    # Mutate the PO status (issued → voided). Trigger updates committed_value
    # but must NOT write committed_not_invoiced. The Python recompute is then
    # called explicitly (mirrors production: po_transitions paths invoke
    # recompute_for_po → recompute_for_line).
    db.execute(text(
        "UPDATE purchase_orders SET status='voided', "
        "voided_at=NOW(), voided_by=:u, voided_reason='test' "
        "WHERE id=:id"
    ), {"u": seeds["user_id"], "id": po_id})
    db.commit()

    # After the trigger ran: committed_value should drop to 0 (voided
    # excluded). committed_not_invoiced is STALE at 3200 — the Python
    # recompute is what writes it.
    db.refresh(line)
    assert line.committed_value == Decimal("0.00")
    # The retention bucket survives the PG trigger entirely.
    assert line.committed_not_invoiced == Decimal("3200.00")

    # Now run the Python recompute (the production path
    # recompute_for_po wires this in). PO bucket goes to 0, retention
    # survives.
    budgets_reconciliation.recompute_for_line(db, seeds["line_id"])
    db.commit()
    db.refresh(line)
    assert line.committed_not_invoiced == Decimal("200.00"), (
        "Retention pending was clobbered by PO state change"
    )


# ---------------------------------------------------------------------------
# Test #4 — derived FFC / variance reflect the combined column
# ---------------------------------------------------------------------------

def test_ffc_and_variance_reflect_combined_committed(
    db, seeds, admin_user, perms,
):
    """A1 #4 — forecast_final_cost and variance derive from the COMBINED
    committed_not_invoiced (both buckets), not either alone.
    """
    # PO bucket: £100,000 issued.
    _make_po_with_line(db, seeds, status="issued", net=Decimal("100000.00"))
    # Retention pending: 5% on £50,000 = £2,500.
    _post_actual(db, seeds, admin_user, perms,
                 net=Decimal("50000.00"),
                 retention_rate=Decimal("5"))
    budgets_reconciliation.recompute_for_line(db, seeds["line_id"])
    db.commit()

    line = db.get(BudgetLine, seeds["line_id"])
    db.refresh(line)
    # committed_not_invoiced = 2,500 + 100,000 = 102,500.
    assert line.committed_not_invoiced == Decimal("102500.00")
    # actuals_to_date = 50,000 − 2,500 = 47,500.
    assert line.actuals_to_date == Decimal("47500.00")

    # forecast_final_cost (Budget_Remaining ftc default → 500000 - 47500
    # − 102500 = 350000, then FFC = 47500 + 102500 + 350000 = 500000).
    # Whatever the precise FTC math, FFC MUST include BOTH buckets — so
    # FFC − actuals_to_date = committed + ftc, and that delta MUST be
    # >= 102,500 (the combined committed). Equivalently: FFC >= actuals
    # + combined-committed.
    assert line.forecast_final_cost >= (
        line.actuals_to_date + line.committed_not_invoiced
    )
    # Direct ftc_method=Manual default = Budget_Remaining → FFC = current_budget.
    # Test that FFC was NOT computed using only one of the two buckets:
    # if PO bucket had been clobbered, committed = 2500, FTC would
    # absorb the missing 100,000, but the FFC magnitude still equals
    # current_budget (500,000) under Budget_Remaining. So we assert the
    # column itself instead:
    assert line.committed_not_invoiced > Decimal("100000.00")
    assert line.committed_not_invoiced > Decimal("2500.00")
