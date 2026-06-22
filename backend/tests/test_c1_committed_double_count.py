"""C1-back — Budget Double-Counts Committed Cost (Chat 63).

Proves the committed-cost double-count is gone and stays gone.

Root cause fixed: ``budget_lines.invoiced_against_commitment`` was never written
(defaulted 0 forever), so ``committed_not_invoiced`` never decreased as bills
arrived — a £10k PO + its £10k bill read as £20k. The fix derives
``invoiced_against_commitment`` fresh inside ``recompute_for_line`` from the
linked bills, clamps the PO term at zero, and validates the bill→PO-line link on
create/update. A one-off backfill migration recomputes existing lines.

Direct against the services via real SQLAlchemy sessions on the live Postgres —
mirrors the fixture pattern in ``test_budgets_reconciliation.py``. Every test
asserts DB-level figures / HTTP codes, not merely no-error.
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
from app.models.purchase_orders import PurchaseOrder, PurchaseOrderLine
from app.models.user import User
from app.schemas.actuals import CreateActualRequest, UpdateDraftActualRequest
from app.services import actuals as actuals_svc
from app.services import budgets_reconciliation
from app.services.actual_errors import CommitmentLinkError

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

        # Supplier (POs require one).
        supplier_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO suppliers (id, tenant_id, name, created_by, updated_by)
            VALUES (:id, :t, :n, :u, :u)
        """), {"id": supplier_id, "t": admin.tenant_id,
               "n": f"C1 Supplier {supplier_id.hex[:6]}", "u": admin.id})
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
                    '1 C1 Way', 'SY3 2AA', false, :u)
        """), {"id": project_id, "code": f"C1-{project_id.hex[:6]}",
               "name": f"C1 Test {project_id.hex[:6]}",
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
                :id, :pid, 'C1 Base', CURRENT_DATE,
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
        c.execute(text(
            "UPDATE budget_lines SET actuals_to_date=0, committed_not_invoiced=0, "
            "invoiced_against_commitment=0, committed_value=0 WHERE budget_id=:b"
        ), {"b": seeds["budget_id"]})


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


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _make_po_line(db, seeds, *, net, budget_line_id=None, status="approved"):
    """Create an approved PO with one line on the given budget line. Returns
    the PurchaseOrderLine id. PO status defaults to 'approved' (in
    PO_COMMITTED_STATUSES) so the committed term counts it."""
    bl = budget_line_id or seeds["line1_id"]
    po = PurchaseOrder(
        tenant_id=seeds["tenant_id"],
        project_id=seeds["project_id"],
        po_number=f"PO-{uuid.uuid4().hex[:10]}",
        supplier_id=seeds["supplier_id"],
        budget_id=seeds["budget_id"],
        status=status,
        created_by=seeds["user_id"],
        updated_by=seeds["user_id"],
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        budget_line_id=bl,
        cost_code="C1",
        line_number=1,
        description="po line",
        quantity=Decimal("1"),
        unit_rate=Decimal(str(net)),
        net_amount=Decimal(str(net)),
        vat_amount=Decimal("0"),
        gross_amount=Decimal(str(net)),
        created_by=seeds["user_id"],
        updated_by=seeds["user_id"],
    )
    db.add(line)
    db.flush()
    db.commit()
    return line.id


def _create_actual(db, seeds, user, perms, *, net,
                   budget_line_id=None, linked_commitment_id=None,
                   retention_rate=None):
    body = CreateActualRequest(
        project_id=seeds["project_id"],
        budget_line_id=budget_line_id or seeds["line1_id"],
        entity_id=seeds["entity_id"],
        source_type="Manual_Entry",
        transaction_date=date.today(),
        description="c1 test",
        net_amount=Decimal(str(net)),
        vat_amount=Decimal("0"),
        vat_rate_pct=Decimal("20"),
        supplier_name_snapshot="ACME Ltd",
        retention_rate_pct=retention_rate,
        linked_commitment_id=linked_commitment_id,
    )
    a = actuals_svc.create_actual(db, payload=body, user=user, perms=perms)
    db.commit()
    return a


def _make_actual(db, seeds, user, perms, *, net, status="Posted",
                 budget_line_id=None, linked_commitment_id=None,
                 retention_rate=None):
    a = _create_actual(
        db, seeds, user, perms, net=net, budget_line_id=budget_line_id,
        linked_commitment_id=linked_commitment_id, retention_rate=retention_rate,
    )
    if status == "Draft":
        return a
    if status == "Void":
        actuals_svc.void_actual(db, actual_id=a.id, void_reason="x",
                                user=user, perms=perms)
    else:
        actuals_svc.post_actual(db, actual_id=a.id, user=user, perms=perms)
        if status == "Paid":
            actuals_svc.mark_paid(db, actual_id=a.id, paid_date=date.today(),
                                  payment_reference="P", user=user, perms=perms)
        elif status == "Disputed":
            actuals_svc.dispute_actual(db, actual_id=a.id, dispute_reason="x",
                                       user=user, perms=perms)
    db.commit()
    return a


def _recompute(db, line_id):
    budgets_reconciliation.recompute_for_line(db, line_id)
    db.commit()


def _line(db, line_id):
    line = db.get(BudgetLine, line_id)
    db.refresh(line)
    return line


# ==========================================================================
# Core double-count maths
# ==========================================================================
def test_po_only_committed_full(db, seeds, admin_user, perms):
    """One £10k PO, no bills → committed_not_invoiced = 10000, actuals = 0."""
    _make_po_line(db, seeds, net=10000)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("10000.00")
    assert line.actuals_to_date == Decimal("0.00")
    assert line.invoiced_against_commitment == Decimal("0.00")


def test_linked_bill_reduces_committed(db, seeds, admin_user, perms):
    """£10k PO + £10k bill linked to that PO line, posted → committed_not_
    invoiced = 0, actuals_to_date = 10000. THE headline anti-double-count."""
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=10000,
                 status="Posted", linked_commitment_id=pol)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("0.00")
    assert line.actuals_to_date == Decimal("10000.00")
    assert line.invoiced_against_commitment == Decimal("10000.00")


def test_partial_invoice(db, seeds, admin_user, perms):
    """£10k PO + £4k linked bill posted → committed_not_invoiced = 6000,
    actuals = 4000."""
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=4000,
                 status="Posted", linked_commitment_id=pol)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("6000.00")
    assert line.actuals_to_date == Decimal("4000.00")
    assert line.invoiced_against_commitment == Decimal("4000.00")


def test_overinvoice_clamps_po_term_to_zero(db, seeds, admin_user, perms):
    """£10k PO + £12k linked bill posted → PO term clamps to 0 (not −2000), so
    committed_not_invoiced = 0 exactly; actuals_to_date = 12000."""
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=12000,
                 status="Posted", linked_commitment_id=pol)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("0.00")  # clamped, not -2000
    assert line.actuals_to_date == Decimal("12000.00")
    assert line.invoiced_against_commitment == Decimal("12000.00")


def test_standalone_bill_does_not_reduce_committed(db, seeds, admin_user, perms):
    """£10k PO + £3k bill with linked_commitment_id = NULL → committed_not_
    invoiced unchanged at 10000, actuals = 3000. Standalone costs don't eat
    commitment."""
    _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=3000,
                 status="Posted", linked_commitment_id=None)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("10000.00")
    assert line.actuals_to_date == Decimal("3000.00")
    assert line.invoiced_against_commitment == Decimal("0.00")


def test_multiple_pos_multiple_bills_on_one_line(db, seeds, admin_user, perms):
    """Two PO lines (£6k + £4k) on one budget line, two linked bills (£6k +
    £1k) → committed = 10000, invoiced = 7000, committed_not_invoiced = 3000,
    actuals = 7000."""
    pol_a = _make_po_line(db, seeds, net=6000)
    pol_b = _make_po_line(db, seeds, net=4000)
    _make_actual(db, seeds, admin_user, perms, net=6000,
                 status="Posted", linked_commitment_id=pol_a)
    _make_actual(db, seeds, admin_user, perms, net=1000,
                 status="Posted", linked_commitment_id=pol_b)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.invoiced_against_commitment == Decimal("7000.00")
    assert line.committed_not_invoiced == Decimal("3000.00")
    assert line.actuals_to_date == Decimal("7000.00")


# ==========================================================================
# Lifecycle — derived figure self-corrects
# ==========================================================================
def test_void_restores_committed(db, seeds, admin_user, perms):
    """Linked £10k bill posted (committed_not_invoiced = 0) then voided →
    committed_not_invoiced back to 10000, actuals 0."""
    pol = _make_po_line(db, seeds, net=10000)
    a = _make_actual(db, seeds, admin_user, perms, net=10000,
                     status="Posted", linked_commitment_id=pol)
    _recompute(db, seeds["line1_id"])
    assert _line(db, seeds["line1_id"]).committed_not_invoiced == Decimal("0.00")

    actuals_svc.void_actual(db, actual_id=a.id, void_reason="dup",
                            user=admin_user, perms=perms)
    db.commit()
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("10000.00")
    assert line.actuals_to_date == Decimal("0.00")
    assert line.invoiced_against_commitment == Decimal("0.00")


def test_dispute_still_counts(db, seeds, admin_user, perms):
    """Disputed is in COUNTED_STATUSES → a disputed linked bill still reduces
    committed."""
    assert "Disputed" in budgets_reconciliation.COUNTED_STATUSES
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=10000,
                 status="Disputed", linked_commitment_id=pol)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.committed_not_invoiced == Decimal("0.00")
    assert line.invoiced_against_commitment == Decimal("10000.00")
    assert line.actuals_to_date == Decimal("10000.00")


def test_retention_plus_po_combined(db, seeds, admin_user, perms):
    """Retention pending AND a linked bill compose: committed_not_invoiced =
    retention_pending + (po − invoiced).

    £10k PO; £4k linked bill (no retention) → po term = 6000; £2k standalone
    bill @ 10% retention → 200 pending. committed_not_invoiced = 200 + 6000 =
    6200; actuals = (4000 + 2000) − 200 = 5800."""
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=4000,
                 status="Posted", linked_commitment_id=pol)
    _make_actual(db, seeds, admin_user, perms, net=2000,
                 status="Posted", linked_commitment_id=None,
                 retention_rate=Decimal("10"))
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])
    assert line.invoiced_against_commitment == Decimal("4000.00")
    assert line.committed_not_invoiced == Decimal("6200.00")
    assert line.actuals_to_date == Decimal("5800.00")


# ==========================================================================
# Link validation
# ==========================================================================
def test_link_to_nonexistent_po_line_rejected(db, seeds, admin_user, perms):
    """Create bill with a random linked_commitment_id → CommitmentLinkError
    (HTTP 422)."""
    with pytest.raises(CommitmentLinkError) as ei:
        _create_actual(db, seeds, admin_user, perms, net=1000,
                       linked_commitment_id=uuid.uuid4())
    db.rollback()
    assert ei.value.http_status == 422


def test_link_to_po_line_on_other_budget_line_rejected(db, seeds, admin_user, perms):
    """PO line on line2, bill on line1 linked to it → rejected (422)."""
    pol_other = _make_po_line(db, seeds, net=5000, budget_line_id=seeds["line2_id"])
    with pytest.raises(CommitmentLinkError) as ei:
        _create_actual(db, seeds, admin_user, perms, net=1000,
                       budget_line_id=seeds["line1_id"],
                       linked_commitment_id=pol_other)
    db.rollback()
    assert ei.value.http_status == 422


def test_link_null_allowed(db, seeds, admin_user, perms):
    """NULL link → created fine (standalone)."""
    a = _create_actual(db, seeds, admin_user, perms, net=1000,
                       linked_commitment_id=None)
    assert a.id is not None
    assert a.linked_commitment_id is None


def test_update_relink_validated(db, seeds, admin_user, perms):
    """update_draft_actual CAN change both fields.

    (a) re-linking a draft to a foreign PO line is rejected (422).
    (b) the MOVE-LINE trap — a draft validly linked on line A moved to line B
        (budget_line_id change only, link untouched) → rejected (422), because
        the existing link now points at a PO line on the old line."""
    pol_a = _make_po_line(db, seeds, net=10000, budget_line_id=seeds["line1_id"])
    pol_b = _make_po_line(db, seeds, net=10000, budget_line_id=seeds["line2_id"])

    # Draft validly linked on line A.
    a = _make_actual(db, seeds, admin_user, perms, net=5000, status="Draft",
                     budget_line_id=seeds["line1_id"], linked_commitment_id=pol_a)

    # (a) re-link to a foreign PO line (on line B) → rejected.
    with pytest.raises(CommitmentLinkError) as ei_a:
        actuals_svc.update_draft_actual(
            db, actual_id=a.id,
            payload=UpdateDraftActualRequest(linked_commitment_id=pol_b),
            user=admin_user, perms=perms,
        )
    db.rollback()
    assert ei_a.value.http_status == 422

    # (b) move-line trap: change budget_line_id to line B, link untouched.
    with pytest.raises(CommitmentLinkError) as ei_b:
        actuals_svc.update_draft_actual(
            db, actual_id=a.id,
            payload=UpdateDraftActualRequest(budget_line_id=seeds["line2_id"]),
            user=admin_user, perms=perms,
        )
    db.rollback()
    assert ei_b.value.http_status == 422


# ==========================================================================
# Backfill
# ==========================================================================
def _seed_broken_line(db, seeds, admin_user, perms):
    """Build a line with a £10k PO + a £10k posted linked bill, then FORCE the
    pre-fix broken cached state (committed_not_invoiced = full PO,
    invoiced_against_commitment = 0) directly in the DB."""
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=10000,
                 status="Posted", linked_commitment_id=pol)
    # Force the broken pre-fix cache (what the old code left behind).
    db.execute(
        text("UPDATE budget_lines SET committed_not_invoiced=10000, "
             "invoiced_against_commitment=0 WHERE id=:l"),
        {"l": seeds["line1_id"]},
    )
    db.commit()


def test_backfill_fixes_preexisting_double_count(db, seeds, admin_user, perms):
    """Seed a line in the BROKEN state, run the backfill logic (the migration's
    recompute_for_line) → committed_not_invoiced corrected, invoiced populated.
    Assert before/after."""
    _seed_broken_line(db, seeds, admin_user, perms)
    before = _line(db, seeds["line1_id"])
    assert before.committed_not_invoiced == Decimal("10000.00")  # broken double-count
    assert before.invoiced_against_commitment == Decimal("0.00")

    # The backfill migration's logic == recompute_for_line.
    _recompute(db, seeds["line1_id"])

    after = _line(db, seeds["line1_id"])
    assert after.committed_not_invoiced == Decimal("0.00")        # corrected
    assert after.invoiced_against_commitment == Decimal("10000.00")
    assert after.actuals_to_date == Decimal("10000.00")


def test_backfill_idempotent(db, seeds, admin_user, perms):
    """Running the backfill twice yields identical figures (no drift)."""
    _seed_broken_line(db, seeds, admin_user, perms)
    _recompute(db, seeds["line1_id"])
    first = _line(db, seeds["line1_id"])
    snap = (first.committed_not_invoiced,
            first.invoiced_against_commitment,
            first.actuals_to_date)

    _recompute(db, seeds["line1_id"])
    second = _line(db, seeds["line1_id"])
    assert (second.committed_not_invoiced,
            second.invoiced_against_commitment,
            second.actuals_to_date) == snap


def test_backfill_matches_live_recompute(db, seeds, admin_user, perms):
    """The backfill result equals an independent derivation via the service
    helpers — proves no maths drift between the backfill and the live path
    (the migration reuses recompute_for_line verbatim)."""
    pol = _make_po_line(db, seeds, net=10000)
    _make_actual(db, seeds, admin_user, perms, net=4000,
                 status="Posted", linked_commitment_id=pol)
    _recompute(db, seeds["line1_id"])
    line = _line(db, seeds["line1_id"])

    # Independent derivation using the same helpers the service uses.
    expected_invoiced = budgets_reconciliation._invoiced_against_commitment_for_line(
        db, line
    )
    expected_po_term = budgets_reconciliation._po_committed_not_invoiced_for_line(
        db, line
    )
    assert line.invoiced_against_commitment == expected_invoiced.quantize(
        Decimal("0.01")
    )
    # No retention here → committed_not_invoiced == PO term.
    assert line.committed_not_invoiced == expected_po_term.quantize(Decimal("0.01"))
    assert line.committed_not_invoiced == Decimal("6000.00")
    assert expected_invoiced == Decimal("4000.00")
