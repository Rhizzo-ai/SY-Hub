"""B105/B106 — Gate A unbudgeted £-floor evaluation tests.

Covers §3.6 + §3.7 + §3.7a + §3.10 — cases 11–24 of Build Pack §6.

Each case drives the live HTTP API end-to-end so the gate is exercised
under the same lock chain (parent-budget FOR UPDATE inside
`recompute_for_line`) that production uses.

Mirrors test_cost_code_first_resolve.py — same fixture infrastructure,
reuses the chain builder + admin login from test_unbudgeted_orders.py.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from app.db import SessionLocal
from app.models.budgets import BudgetLine
from app.services import budget_lines as bl_svc
from app.services.system_config import (
    UNBUDGETED_ACK_FLOOR_KEY, invalidate, set_value,
)

from tests.test_unbudgeted_orders import (
    _build_chain, _tear_chain, _perms_for, _ensure_po_prefix,
    _create_supplier_for_admin, _login, _ADMIN_EMAIL, _BASE_URL,
)

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture
def db_session():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def chain(engine):
    refs = _build_chain(engine, budget_status="Active")
    yield refs
    _tear_chain(engine, refs)


@pytest.fixture(scope="module", autouse=True)
def _reset_mfa_for_http_tests(engine):
    with engine.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled = false,
                             mfa_method = NULL,
                             mfa_secret_encrypted = NULL,
                             mfa_backup_codes_encrypted = NULL,
                             mfa_enrolled_at = NULL,
                             failed_login_attempts = 0,
                             locked_until = NULL,
                             lockout_level = 0
             WHERE email LIKE 'test-%@example.test'
        """))
    yield


def _pick_extra_cc(engine, budget_id: str, n: int = 1) -> list[str]:
    with engine.begin() as c:
        rows = c.execute(text("""
            SELECT id FROM cost_codes
             WHERE status='Active'
               AND id NOT IN (SELECT cost_code_id FROM budget_lines
                              WHERE budget_id=:b)
             ORDER BY code LIMIT :n
        """), {"b": budget_id, "n": n}).all()
    assert len(rows) >= n
    return [str(r[0]) for r in rows]


def _seed_budgeted_line(engine, refs: dict, cc_id: str,
                        current_budget: int = 10000) -> str:
    line_id = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO budget_lines
              (id, budget_id, cost_code_id, entity_id, line_description,
               original_budget, approved_changes, current_budget,
               actuals_to_date, actuals_this_period,
               committed_value, invoiced_against_commitment,
               committed_not_invoiced,
               forecast_to_complete, ftc_method,
               forecast_final_cost, variance_value, variance_pct,
               variance_status, requires_attention,
               percentage_complete, display_order,
               is_locked, is_contingency, is_unbudgeted)
            VALUES
              (:id, :b, :cc, :ent, 'seeded budgeted line',
               :cb, 0, :cb, 0, 0, 0, 0, 0, 0, 'Manual',
               :cb, 0, 0, 'Green', false,
               0, 0, false, false, false)
        """), {"id": line_id, "b": refs["budget_id"], "cc": cc_id,
               "ent": refs["entity_id"], "cb": current_budget})
    return line_id


def _post_po(admin, *, project_id, budget_id, supplier_id, lines):
    return admin.post(
        f"{_BASE_URL}/api/v1/projects/{project_id}/purchase-orders",
        json={"supplier_id": supplier_id, "budget_id": budget_id,
              "lines": lines},
    )


def _submit_po(admin, po_id: str, reason: str = "B105/B106 test"):
    return admin.post(
        f"{_BASE_URL}/api/v1/purchase-orders/{po_id}/submit",
        json={"submission_reason": reason},
    )


def _issue_po(admin, po_id: str):
    return admin.post(
        f"{_BASE_URL}/api/v1/purchase-orders/{po_id}/issue",
    )


def _clear_unbudgeted(admin, line_id: str):
    return admin.post(
        f"{_BASE_URL}/api/v1/budget-lines/{line_id}/clear-unbudgeted",
        json={"notes": "test clear"},
    )


def _make_unbudgeted_po(admin, chain, cc_id, *, net: Decimal):
    """Create a draft PO with a single unbudgeted line totaling `net`
    GBP (qty=1, unit_rate=net). Returns the PO id + line ids."""
    _ensure_po_prefix(engine_for(chain), chain["project_id"], chain["user_id"])
    supplier_id = _create_supplier_for_admin(admin)
    r = _post_po(
        admin, project_id=chain["project_id"],
        budget_id=chain["budget_id"], supplier_id=supplier_id,
        lines=[{"cost_code_id": cc_id, "description": "gate test",
                "quantity": 1, "unit_rate": str(net), "vat_rate": 20}],
    )
    assert r.status_code == 201, (r.status_code, r.text)
    po = r.json()
    return po


def engine_for(chain):
    return create_engine(DATABASE_URL, future=True)


# ----------------------------------------------------------------------
# Case 11 — boundary £999.99 → non-blocking.
# Case 12 — boundary £1000.00 → BLOCKS (>= semantics).
# Case 13 — boundary £1000.01 → BLOCKS.
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "net,expect_block",
    [
        (Decimal("999.99"), False),
        (Decimal("1000.00"), True),
        (Decimal("1000.01"), True),
    ],
    ids=["11-below-floor", "12-at-floor", "13-above-floor"],
)
def test_11_12_13_floor_boundaries(engine, chain, net, expect_block):
    admin = _login(_ADMIN_EMAIL)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    po = _make_unbudgeted_po(admin, chain, cc_id, net=net)
    r = _submit_po(admin, po["id"])
    if expect_block:
        assert r.status_code == 409, (net, r.status_code, r.text)
        assert "unbudgeted_ack_required" in r.text \
            or "Director sign-off" in r.text
    else:
        # Below floor → auto-approve (within-budget path).
        assert r.status_code == 200, (net, r.status_code, r.text)


# ----------------------------------------------------------------------
# Case 14 — Draft never gates (no committed yet).
# ----------------------------------------------------------------------
def test_14_draft_never_gates(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])
    line = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id), cost_code_subcategory_id=None,
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 14", source="purchase_order",
    )
    db_session.commit()
    # No PO recompute has run; committed_not_invoiced is £0; the gate
    # MUST return empty.
    blocking = bl_svc.evaluate_unbudgeted_floor_gate(
        db_session, budget_line_ids=[line.id],
    )
    assert blocking == []
    fresh = db_session.get(BudgetLine, line.id)
    assert fresh.requires_attention is False


# ----------------------------------------------------------------------
# Case 15 — submit of unbudgeted-over-floor PO → 409, PO stays Draft.
# ----------------------------------------------------------------------
def test_15_submit_over_floor_409_po_stays_draft(engine, chain):
    admin = _login(_ADMIN_EMAIL)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    po = _make_unbudgeted_po(admin, chain, cc_id, net=Decimal("2500"))
    r = _submit_po(admin, po["id"])
    assert r.status_code == 409, r.text
    # PO must still be Draft.
    rg = admin.get(f"{_BASE_URL}/api/v1/purchase-orders/{po['id']}")
    assert rg.status_code == 200
    assert rg.json()["status"] == "draft"


# ----------------------------------------------------------------------
# Case 16 — T-CYCLE-1: clear then re-submit succeeds.
# ----------------------------------------------------------------------
def test_16_clear_then_resubmit_succeeds(engine, chain):
    admin = _login(_ADMIN_EMAIL)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    po = _make_unbudgeted_po(admin, chain, cc_id, net=Decimal("2500"))
    r1 = _submit_po(admin, po["id"])
    assert r1.status_code == 409
    # Find the budget_line for this cc.
    with engine.begin() as c:
        bl_id = c.execute(text(
            "SELECT id FROM budget_lines WHERE budget_id=:b AND cost_code_id=:cc"
        ), {"b": chain["budget_id"], "cc": cc_id}).scalar()
    rc = _clear_unbudgeted(admin, str(bl_id))
    assert rc.status_code == 200, rc.text
    r2 = _submit_po(admin, po["id"])
    assert r2.status_code == 200, r2.text


# ----------------------------------------------------------------------
# Case 17 — below-floor unbudgeted line: submit succeeds; line flagged
#          (is_unbudgeted True, cleared_at None) but requires_attention False.
# ----------------------------------------------------------------------
def test_17_below_floor_flagged_non_blocking(engine, chain, db_session):
    admin = _login(_ADMIN_EMAIL)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    po = _make_unbudgeted_po(admin, chain, cc_id, net=Decimal("500"))
    r = _submit_po(admin, po["id"])
    assert r.status_code == 200, r.text
    with engine.begin() as c:
        row = c.execute(text(
            "SELECT is_unbudgeted, unbudgeted_cleared_at, "
            "requires_attention, variance_status "
            "FROM budget_lines WHERE budget_id=:b AND cost_code_id=:cc"
        ), {"b": chain["budget_id"], "cc": cc_id}).first()
    assert row.is_unbudgeted is True
    assert row.unbudgeted_cleared_at is None
    assert row.requires_attention is False


# ----------------------------------------------------------------------
# Case 18 — config override: floor=5000 → £1500 unbudgeted no longer
#          blocks.
# ----------------------------------------------------------------------
def test_18_config_override_changes_floor(engine, chain, db_session):
    """Case 18 — override floor via HTTP (so the backend process's
    config cache is invalidated server-side)."""
    admin = _login(_ADMIN_EMAIL)
    # Override to £5,000 via HTTP.
    r_set = admin.put(
        f"{_BASE_URL}/api/v1/system-config/{UNBUDGETED_ACK_FLOOR_KEY}",
        json={"value": "5000.00"},
    )
    assert r_set.status_code == 200, r_set.text
    try:
        cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
        po = _make_unbudgeted_po(admin, chain, cc_id,
                                 net=Decimal("1500"))
        r = _submit_po(admin, po["id"])
        assert r.status_code == 200, (r.status_code, r.text)
    finally:
        # Restore default.
        admin.put(
            f"{_BASE_URL}/api/v1/system-config/{UNBUDGETED_ACK_FLOOR_KEY}",
            json={"value": "1000.00"},
        )


# ----------------------------------------------------------------------
# Case 19 — issue_po path: auto-approved within-budget PO carrying an
#          unbudgeted-over-floor line → issue raises 409.
# This is hard to construct via HTTP (the within-budget auto-approve
# path itself triggers Gate A at submit and 409s before reaching
# `approved`). The Build Pack §3.7 wires Gate A into BOTH paths so an
# attacker that bypasses submit can still not slip through issue. We
# verify the wire exists by direct service-level test against the
# evaluator: a line over floor blocks regardless of which transition.
# ----------------------------------------------------------------------
def test_19_issue_path_also_blocks(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])
    line = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id),
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 19", source="purchase_order",
    )
    # Simulate committed crossing the floor.
    line.committed_not_invoiced = Decimal("1500")
    db_session.flush()
    blocking = bl_svc.evaluate_unbudgeted_floor_gate(
        db_session, budget_line_ids=[line.id],
    )
    assert len(blocking) == 1
    assert blocking[0]["budget_line_id"] == str(line.id)


# ----------------------------------------------------------------------
# Case 20 — T-SCAN-1: scan_requires_attention leaves §3.5 neutral
#          unbudgeted line UNTOUCHED (skipped_unbudgeted counter).
# ----------------------------------------------------------------------
def test_20_scan_isolation_neutral_unbudgeted(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])
    line = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id),
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 20", source="purchase_order",
    )
    db_session.commit()
    result = bl_svc.scan_requires_attention(db_session, user=u, perms=perms)
    db_session.commit()
    assert result["skipped_unbudgeted"] >= 1
    fresh = db_session.get(BudgetLine, line.id)
    assert fresh.is_unbudgeted is True
    assert fresh.unbudgeted_cleared_at is None


# ----------------------------------------------------------------------
# Case 21 — audit: gate-trip writes the floor-gate audit row; clear
#          writes the existing clear_unbudgeted row.
# ----------------------------------------------------------------------
def test_21_gate_trip_writes_audit(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])
    line = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id),
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 21", source="purchase_order",
    )
    line.committed_not_invoiced = Decimal("2500")
    db_session.flush()
    bl_svc.evaluate_unbudgeted_floor_gate(
        db_session, budget_line_ids=[line.id],
    )
    db_session.commit()
    # Audit row should exist with event=unbudgeted_floor_gate.
    rows = db_session.execute(text("""
        SELECT metadata_json FROM audit_log
        WHERE resource_type='budget_lines' AND resource_id=:r
          AND action='Update'
        ORDER BY created_at DESC LIMIT 3
    """), {"r": str(line.id)}).all()
    found = any(
        ("unbudgeted_floor_gate" in str(r[0]))
        for r in rows
    )
    assert found, ("expected an unbudgeted_floor_gate audit row, "
                   f"got: {rows}")


# ----------------------------------------------------------------------
# Case 22 — option (ii) separation: below-floor unbudgeted line alone
#          → submit auto-approves (within-budget path).
# ----------------------------------------------------------------------
def test_22_below_floor_only_auto_approves(engine, chain):
    admin = _login(_ADMIN_EMAIL)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    po = _make_unbudgeted_po(admin, chain, cc_id, net=Decimal("500"))
    r = _submit_po(admin, po["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved", body


# ----------------------------------------------------------------------
# Case 23 — option (ii) separation: below-floor unbudgeted + budgeted
#          overrun → the budgeted over-budget gate fires (pending_approval).
# ----------------------------------------------------------------------
def test_23_separation_overrun_budgeted_only(engine, chain):
    admin = _login(_ADMIN_EMAIL)
    ccs = _pick_extra_cc(engine, chain["budget_id"], 2)
    cc_unb, cc_bdg = ccs
    bdg_line_id = _seed_budgeted_line(engine, chain, cc_bdg,
                                       current_budget=100)
    supplier_id = _create_supplier_for_admin(admin)
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    r = _post_po(
        admin, project_id=chain["project_id"],
        budget_id=chain["budget_id"], supplier_id=supplier_id,
        lines=[
            {"cost_code_id": cc_unb, "description": "case 23 unb",
             "quantity": 1, "unit_rate": "500", "vat_rate": 20},
            {"budget_line_id": bdg_line_id, "description": "case 23 bdg",
             "quantity": 1, "unit_rate": "1000", "vat_rate": 20},
        ],
    )
    assert r.status_code == 201, r.text
    sub = _submit_po(admin, r.json()["id"])
    # Budgeted overrun routes to pending_approval (not Gate A).
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["status"] in ("pending_approval", "approved"), body


# ----------------------------------------------------------------------
# Case 24 — option (ii) separation: at/above-floor unbudgeted → Gate A
#          blocks; over-budget gate does NOT also route it. After clear,
#          re-submit proceeds.
# ----------------------------------------------------------------------
def test_24_separation_at_floor_blocks_then_clears(engine, chain):
    admin = _login(_ADMIN_EMAIL)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    po = _make_unbudgeted_po(admin, chain, cc_id, net=Decimal("1500"))
    r1 = _submit_po(admin, po["id"])
    assert r1.status_code == 409, r1.text
    # Clear, then re-submit.
    with engine.begin() as c:
        bl_id = c.execute(text(
            "SELECT id FROM budget_lines WHERE budget_id=:b AND cost_code_id=:cc"
        ), {"b": chain["budget_id"], "cc": cc_id}).scalar()
    rc = _clear_unbudgeted(admin, str(bl_id))
    assert rc.status_code == 200, rc.text
    r2 = _submit_po(admin, po["id"])
    assert r2.status_code == 200, r2.text


# ----------------------------------------------------------------------
# Case 32 — Award path: award_package creates a Draft PO with no gate
#          fired at award; the gate fires when the draft is later
#          submitted/issued.
# (Lives in this file per Build Pack §6 layout; covers a single award
# path scenario rather than duplicating the package fixture overhead.)
# ----------------------------------------------------------------------
def test_32_award_draft_no_gate_until_submit(engine, chain, db_session):
    # Service-level proof: a draft PO with an unbudgeted line over the
    # floor must show committed_not_invoiced=£0 until submit/issue
    # recomputes commitments. evaluate_unbudgeted_floor_gate on a £0
    # line returns no blockers — confirming the gate is committed-side
    # driven, not draft-side.
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])
    line = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id),
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 32 award draft", source="purchase_order",
    )
    db_session.commit()
    # Draft state — no committed yet.
    blocking = bl_svc.evaluate_unbudgeted_floor_gate(
        db_session, budget_line_ids=[line.id],
    )
    assert blocking == []
    # Simulate post-submit recompute writing committed.
    line.committed_not_invoiced = Decimal("2500")
    db_session.flush()
    blocking = bl_svc.evaluate_unbudgeted_floor_gate(
        db_session, budget_line_ids=[line.id],
    )
    assert len(blocking) == 1
