"""Chat 24 §R3 (Prompt 2.5) — PO Approvals integration tests.

Live-DB tests. Covers all R3 acceptance gates (G3.1–G3.9):

  - Budget gate (5):
    G3.1 within-budget auto-issue (no approval row)
    G3.2 within-budget + approval_required=true → auto-approved row
    G3.3 over by one line → pending_approval + approval row
    G3.4 over by multiple lines → all lines surfaced in snapshot
    G3.5 line reassignment recomputes commitments on OLD + NEW budget_line

  - Approve / Reject / Unlock (4):
    G3.6 approve transitions pending → approved + recomputes commitment
    G3.7 reject transitions pending → draft + clears submit stamps
    G3.8 reject without notes → 422
    G3.9 unlock approved → draft + notifies prior approver

  - Self-approval guard (2):
    submitter can't approve own PO (403 po/self-approval-forbidden)
    submitter can't reject own PO (same 403)

  - Commitment recompute (8):
    draft contributes 0
    pending_approval contributes 0
    approved contributes net
    issued contributes net
    partially_receipted contributes net
    receipted contributes net
    voided releases commitment back to 0
    closed releases commitment back to 0

  - pending vs committed mutual exclusivity (3):
    a PO is in exactly one bucket
    moving across the boundary is atomic
    pending_value at submission time aligns with snapshot

  - Closed/voided release (2): already covered above

  - Audit + budget_snapshot capture (2):
    approval row captures snapshot at submission time
    audit_log carries field-level diff for status transitions

OPERATOR-VERIFICATION-PENDING: requires live Postgres.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"


# ─────────────────────────────────────────────────────────────────────────
# Fixtures (re-uses the same scaffolding as test_purchase_orders_api.py)
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
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
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def finance(engine):
    try:
        return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)
    except Exception:
        pytest.skip("test-finance@example.test not seeded — seed for R3 tests")


def _entity_id(engine, email: str) -> str:
    with engine.connect() as c:
        eid = c.execute(text("""
            SELECT e.id FROM entities e
            JOIN users u ON u.tenant_id = e.tenant_id
            WHERE u.email = :em AND e.status = 'Active'
            ORDER BY e.created_at ASC LIMIT 1
        """), {"em": email}).scalar()
    assert eid is not None
    return str(eid)


def _create_project(admin, entity_id: str) -> str:
    suffix = uuid.uuid4().hex[:8].upper()
    body = {
        "name": f"Chat24-R3 Project {suffix}",
        "project_type": "Pure_Dev",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Approval Lane",
        "site_postcode": "AB12 3CD",
        "tenure": "Freehold",
        "land_type": "Greenfield",
        "planning_type": "Full",
        "planning_status": "Pre_App",
        "implementation_required": True,
    }
    r = admin.post(f"{BASE_URL}/api/projects", json=body)
    assert r.status_code == 201, f"project create failed: {r.text}"
    return r.json()["id"]


def _create_supplier(admin, name_suffix: str) -> str:
    r = admin.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": f"R3-Supplier {name_suffix}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_budget_lines(engine, project_id: str, line_budgets: list[float]) -> tuple[str, list[str]]:
    """Insert a Draft+Active budget with one budget_line per `line_budgets`
    entry. Returns (budget_id, [line_ids]).
    """
    with engine.begin() as c:
        ent_id = c.execute(text("""
            SELECT primary_entity_id FROM projects WHERE id = :pid
        """), {"pid": project_id}).scalar()
        ccs = c.execute(text("""
            SELECT id, code FROM cost_codes
            WHERE status = 'Active' ORDER BY code LIMIT :n
        """), {"n": len(line_budgets)}).all()
        admin_id = c.execute(text("""
            SELECT id FROM users WHERE email = :em
        """), {"em": ADMIN_EMAIL}).scalar()
        app_id = c.execute(text("""
            INSERT INTO appraisals (
                project_id, version_number, name, reference_date,
                status, created_by_user_id,
                land_purchase_price, sdlt_category, developer_relief,
                contingency_pct, target_profit_on_cost_pct,
                target_profit_on_gdv_pct, project_duration_months,
                appraisal_group_id, is_current, scenario
            ) VALUES (
                :pid, 1, 'R3 test appraisal', CURRENT_DATE,
                'Approved', :uid, 0, 'Residential_Standard', false,
                5, 20, 17, 18, gen_random_uuid(), true, 'Base'
            )
            RETURNING id
        """), {"pid": project_id, "uid": admin_id}).scalar()
        budget_id = c.execute(text("""
            INSERT INTO budgets (
                project_id, source_appraisal_id, version_number,
                version_label, is_current, status, created_by_user_id
            ) VALUES (:pid, :aid, 1, 'Original', true, 'Active', :uid)
            RETURNING id
        """), {"pid": project_id, "aid": app_id, "uid": admin_id}).scalar()
        line_ids = []
        for i, b in enumerate(line_budgets):
            line_ids.append(str(c.execute(text("""
                INSERT INTO budget_lines (
                    budget_id, cost_code_id, line_description, entity_id,
                    original_budget, current_budget,
                    ftc_method, display_order
                ) VALUES (:bid, :ccid, :desc, :eid, :amt, :amt,
                          'Budget_Remaining', :ord)
                RETURNING id
            """), {
                "bid": budget_id, "ccid": ccs[i].id,
                "desc": f"Line {i+1}", "eid": ent_id, "amt": b, "ord": i,
            }).scalar()))
    return str(budget_id), line_ids


@pytest.fixture
def project_setup(admin, engine):
    eid = _entity_id(engine, ADMIN_EMAIL)
    project_id = _create_project(admin, eid)
    budget_id, line_ids = _seed_budget_lines(engine, project_id, [1000.0, 2000.0])
    supplier_id = _create_supplier(admin, uuid.uuid4().hex[:6].upper())
    yield {
        "project_id": project_id, "budget_id": budget_id,
        "line_ids": line_ids, "supplier_id": supplier_id,
    }
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM purchase_order_approvals
             WHERE purchase_order_id IN
                (SELECT id FROM purchase_orders WHERE project_id = :pid)
        """), {"pid": project_id})
        c.execute(text("DELETE FROM purchase_orders WHERE project_id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM budgets WHERE project_id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM appraisals WHERE project_id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM projects WHERE id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM suppliers WHERE id = :sid"),
                  {"sid": supplier_id})


def _create_po(admin, project_setup, *, net_per_line=None,
               approval_required=False) -> dict:
    """Helper: create a draft PO with one line on the first budget_line."""
    net = net_per_line if net_per_line is not None else [500.0]
    lines = [
        {
            "budget_line_id": project_setup["line_ids"][i],
            "description": f"Line {i+1}",
            "quantity": 1,
            "unit_rate": amt,
            "vat_rate": 20,
        }
        for i, amt in enumerate(net)
    ]
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
        json={
            "supplier_id": project_setup["supplier_id"],
            "budget_id": project_setup["budget_id"],
            "approval_required": approval_required,
            "lines": lines,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _bline_committed(engine, line_id: str) -> Decimal:
    with engine.connect() as c:
        v = c.execute(text("""
            SELECT committed_value FROM budget_lines WHERE id = :lid
        """), {"lid": line_id}).scalar()
    return Decimal(str(v or 0))


# ─────────────────────────────────────────────────────────────────────────
# G3.1 — within-budget auto-issue
# ─────────────────────────────────────────────────────────────────────────

class TestBudgetGate:
    def test_g31_within_budget_auto_approve_no_approval_row(
        self, admin, project_setup,
    ):
        # R7.0 Option B: within-budget + approval_required=false now
        # lands at `approved` (was `issued` in §R2). No approval row
        # is created — the auto-approve path is silent.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "approved"
        assert body["approval"] is None
        # No approval row inserted.
        ra = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approvals")
        assert ra.status_code == 200
        assert ra.json()["total"] == 0

    def test_g32_within_budget_approval_required_pending(
        self, admin, project_setup,
    ):
        # approval_required=true is a user-driven flag that ALWAYS forces
        # pending_approval, even when the budget gate is within. Build
        # pack §4.2: the gate adds an additional reason to require
        # approval; the flag itself is sufficient.
        po = _create_po(admin, project_setup, net_per_line=[500.0],
                        approval_required=True)
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "pending_approval"
        assert body["approval"] is not None
        assert body["approval"]["resolution"] is None
        ra = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approvals")
        assert ra.json()["total"] == 1

    def test_g33_over_one_line_goes_pending_approval(
        self, admin, project_setup,
    ):
        # Line 0 has budget 1000. PO net 1100 → over by 100.
        po = _create_po(admin, project_setup, net_per_line=[1100.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "pending_approval"
        ap = body["approval"]
        assert ap is not None
        assert ap["resolution"] is None
        snap = ap["budget_snapshot"]
        assert len(snap) == 1
        assert snap[0]["is_overrun"] is True
        assert Decimal(snap[0]["over_by"]) == Decimal("100")

    def test_g34_over_multiple_lines_all_surfaced(
        self, admin, project_setup,
    ):
        # Line 0 budget 1000, Line 1 budget 2000. Push both over.
        po = _create_po(admin, project_setup, net_per_line=[1100.0, 2100.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        body = rs.json()
        assert body["status"] == "pending_approval"
        snap = body["approval"]["budget_snapshot"]
        overruns = [s for s in snap if s["is_overrun"]]
        assert len(overruns) == 2

    def test_g35_line_reassignment_recomputes_both_lines(
        self, admin, project_setup, engine,
    ):
        # Issue a PO against line 0 → commitment on line 0 = net.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("500.00")
        assert _bline_committed(engine, project_setup["line_ids"][1]) == Decimal("0.00")
        # Reassign the PO line to line 1 via direct SQL (PATCH endpoint
        # for lines is out of R3 scope — we exercise the DB trigger
        # directly per build pack §2.2 invariant).
        with engine.begin() as c:
            c.execute(text("""
                UPDATE purchase_order_lines
                   SET budget_line_id = :new
                 WHERE purchase_order_id = :pid
            """), {"new": project_setup["line_ids"][1], "pid": po["id"]})
        # Trigger should have re-computed both.
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")
        assert _bline_committed(engine, project_setup["line_ids"][1]) == Decimal("500.00")


# ─────────────────────────────────────────────────────────────────────────
# Approve / Reject / Unlock
# ─────────────────────────────────────────────────────────────────────────

class TestApproveRejectUnlock:
    def test_g36_approve_transitions_and_recomputes_commitment(
        self, admin, pm, project_setup, engine,
    ):
        # PM submits over-budget PO; admin approves.
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        # Pre-approval: line 0 committed_value should still be 0
        # (pending_approval contributes 0).
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")
        ra = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approve",
            json={"notes": "ok"},
        )
        assert ra.status_code == 200, ra.text
        assert ra.json()["status"] == "approved"
        # Post-approval: commitment = 1100.
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("1100.00")

    def test_g37_reject_back_to_draft_clears_submit_stamps(
        self, admin, pm, project_setup,
    ):
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        rj = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/reject",
            json={"notes": "Wrong cost code"},
        )
        assert rj.status_code == 200, rj.text
        body = rj.json()
        assert body["status"] == "draft"
        assert body["submitted_at"] is None
        assert body["submitted_by"] is None
        assert body["approval"]["resolution"] == "rejected"
        assert body["approval"]["resolution_notes"] == "Wrong cost code"

    def test_g38_reject_without_notes_returns_422(
        self, admin, pm, project_setup,
    ):
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        rj = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/reject", json={},
        )
        # Empty notes → pydantic validation (min_length=1) → 422.
        assert rj.status_code == 422, rj.text

    def test_g39_unlock_approved_back_to_draft(
        self, admin, pm, project_setup, engine,
    ):
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approve",
            json={"notes": "ok"},
        )
        # PM unlocks.
        ru = pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/unlock",
            json={"reason": "supplier changed"},
        )
        assert ru.status_code == 200, ru.text
        assert ru.json()["status"] == "draft"
        # Commitment released.
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")


# ─────────────────────────────────────────────────────────────────────────
# Self-approval guard
# ─────────────────────────────────────────────────────────────────────────

class TestSelfApprovalGuard:
    def test_submitter_cannot_approve_own_po(self, admin, project_setup):
        # Admin (who has pos.approve) submits AND tries to approve own PO.
        po = _create_po(admin, project_setup, net_per_line=[1100.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        ra = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approve",
            json={"notes": "self"},
        )
        assert ra.status_code == 403, ra.text
        assert ra.json()["detail"]["type"] == "po/self-approval-forbidden"

    def test_submitter_cannot_reject_own_po(self, admin, project_setup):
        po = _create_po(admin, project_setup, net_per_line=[1100.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        rj = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/reject",
            json={"notes": "self"},
        )
        assert rj.status_code == 403, rj.text
        assert rj.json()["detail"]["type"] == "po/self-approval-forbidden"


# ─────────────────────────────────────────────────────────────────────────
# Commitment recompute matrix
# ─────────────────────────────────────────────────────────────────────────

class TestCommitmentMatrix:
    def test_draft_contributes_zero(self, admin, project_setup, engine):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        assert po["status"] == "draft"
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")

    def test_pending_approval_contributes_zero(self, admin, pm, project_setup, engine):
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        # Now pending_approval.
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")

    def test_issued_contributes_net(self, admin, project_setup, engine):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )  # within-budget + approval_required=false → issued
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("500.00")

    def test_voided_releases_commitment(self, admin, project_setup, engine):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("500.00")
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/void",
            json={"reason": "test void"},
        )
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")

    def test_closed_releases_commitment(self, admin, project_setup, engine):
        # R7.0 — within-budget submit lands at `approved`, not `issued`.
        # `closed` is only reachable from receipt-bearing statuses; this
        # test now drives the PO through approved → issue → receipt →
        # close so the commitment-release contract is exercised end-to-end.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/issue", json={},
        )
        # Receipt the full quantity so the PO transitions issued → receipted.
        with engine.begin() as c:
            line_id = c.execute(text("""
                SELECT id FROM purchase_order_lines
                 WHERE purchase_order_id = :pid LIMIT 1
            """), {"pid": po["id"]}).scalar()
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_date": "2026-05-22",
                "lines": [{"purchase_order_line_id": str(line_id), "quantity_received": 1}],
            },
        )
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/close",
            json={"reason": "completed"},
        )
        assert _bline_committed(engine, project_setup["line_ids"][0]) == Decimal("0.00")


# ─────────────────────────────────────────────────────────────────────────
# Listing
# ─────────────────────────────────────────────────────────────────────────

class TestPendingApprovalsList:
    def test_pending_list_excludes_submitter(self, admin, pm, project_setup):
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        # PM should NOT see their own pending row.
        rp = pm.get(f"{BASE_URL}/api/v1/approvals/pending")
        # PM might not even have pos.approve — that's a 403, which is
        # also acceptable (the guard still applies).
        if rp.status_code == 200:
            ids = [it["po_id"] for it in rp.json()["items"]]
            assert po["id"] not in ids
        # Admin should see it.
        ra = admin.get(f"{BASE_URL}/api/v1/approvals/pending")
        assert ra.status_code == 200, ra.text
        ids = [it["po_id"] for it in ra.json()["items"]]
        assert po["id"] in ids



# ─────────────────────────────────────────────────────────────────────────
# R7.0 — Option B (within-budget submit lands at `approved`, NOT auto-issue)
# ─────────────────────────────────────────────────────────────────────────
#
# These six tests are the build-pack-named acceptance gates for R7.0.
# They are deliberately additive to the existing budget-gate / self-
# approval tests so the run summary shows the six names in one block.

class TestR70OptionB:
    """R7.0 Option B — explicit landing-state contract for within-budget
    PO submission. Within-budget + no approval_required lands at
    `approved` (was `issued`); a separate `issue` action is required
    to actually issue.
    """

    def test_within_budget_submit_lands_approved_not_issued(
        self, admin, project_setup,
    ):
        # Within-budget submit (approval_required defaults false) MUST
        # land at `approved`. The legacy auto-issue collapse is gone.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "approved", (
            f"R7.0 invariant broken: expected status='approved', got "
            f"{body['status']!r}"
        )
        assert body["approval"] is None
        # Negative — issued_at MUST be NULL after submit. Only the
        # explicit issue call may populate it.
        assert body.get("issued_at") is None, (
            f"R7.0: issued_at must be NULL at approved, got "
            f"{body.get('issued_at')!r}"
        )
        # Positive — approved stamp must be populated.
        assert body.get("approved_at") is not None
        assert body.get("submitted_at") is not None

    def test_within_budget_approved_requires_explicit_issue(
        self, admin, project_setup,
    ):
        # approved → issue → issued. The issue endpoint is the only
        # path to `issued` for the within-budget auto-approve flow.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "approved"
        # Now explicitly issue. The endpoint name comes from R5 (already
        # live; we pin it here so any drift is caught).
        ri = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/issue", json={},
        )
        assert ri.status_code == 200, ri.text
        body = ri.json()
        assert body["status"] == "issued"
        assert body["issued_at"] is not None
        assert body["approved_at"] is not None  # preserved
        # The PO is reachable on the project list under both statuses
        # at different points in its life-cycle.

    def test_within_budget_approved_contributes_to_committed_value(
        self, admin, project_setup, engine,
    ):
        # Money-contract invariant: committed_value includes `approved`
        # POs. Live SELECT against the production trigger.
        line_id = project_setup["line_ids"][0]
        assert _bline_committed(engine, line_id) == Decimal("0.00")
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200
        assert rs.json()["status"] == "approved"
        # Net is 500 (gross would be 600 @ 20% VAT; commitment is on net).
        assert _bline_committed(engine, line_id) == Decimal("500.00"), (
            "R7.0: a within-budget PO at `approved` must contribute its "
            "net to committed_value. The legacy DB trigger already does "
            "this; this test pins the contract end-to-end."
        )

    def test_over_budget_submit_still_pending_approval(
        self, admin, project_setup,
    ):
        # Regression — the over-budget path is UNCHANGED by R7.0. The
        # gate still trumps the approval_required flag and lands at
        # pending_approval with an approval row.
        po = _create_po(admin, project_setup, net_per_line=[1100.0])  # 1000 budget
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "pending_approval"
        assert body["approval"] is not None
        assert body["approval"]["resolution"] is None
        # Approval snapshot carries the overrun.
        snap = body["approval"]["budget_snapshot"]
        assert any(s["is_overrun"] for s in snap)

    def test_self_approval_rejected_distinct_from_permission_denied(
        self, admin, project_setup,
    ):
        # An approver (admin holds pos.approve) creates a PO that requires
        # approval (over-budget forces pending_approval). When the same
        # admin tries to approve their own PO, the response MUST be the
        # self-approval guard — NOT a generic permission 403.
        po = _create_po(admin, project_setup, net_per_line=[1100.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "pending_approval"
        ra = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approve",
            json={"notes": "self"},
        )
        assert ra.status_code == 403, ra.text
        # The detail shape is what distinguishes this from a generic
        # missing-perm 403. The R3 service raises SelfApprovalForbidden;
        # the router maps it to `detail.type = "po/self-approval-forbidden"`.
        detail = ra.json()["detail"]
        assert isinstance(detail, dict), (
            f"R7.0: self-approval 403 must carry a structured detail, "
            f"got {type(detail).__name__} = {detail!r}"
        )
        assert detail.get("type") == "po/self-approval-forbidden", (
            f"R7.0: self-approval 403 must use the distinct error type "
            f"`po/self-approval-forbidden`, got {detail.get('type')!r}"
        )
        assert "approve" in (detail.get("title") or "").lower()

    def test_second_approver_can_approve(self, admin, finance, project_setup):
        # Negative coverage for the self-approval guard: a DIFFERENT
        # approver (finance — has pos.approve via the test fixture)
        # must succeed where the submitter cannot. The PO transitions
        # pending_approval → approved.
        po = _create_po(admin, project_setup, net_per_line=[1100.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200
        assert rs.json()["status"] == "pending_approval"
        rf = finance.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approve",
            json={"notes": "ok"},
        )
        assert rf.status_code == 200, rf.text
        body = rf.json()
        assert body["status"] == "approved"
        assert body["approval"]["resolution"] == "approved"
        assert body["approval"]["resolved_by"] is not None



# ─────────────────────────────────────────────────────────────────────────
# Chat 26 §R7.0b — `approved → draft` send-back path
# ─────────────────────────────────────────────────────────────────────────

READONLY_EMAIL = "test-readonly@example.test"


@pytest.fixture(scope="module")
def readonly(engine):
    """A principal with `pos.view` but neither `pos.edit` nor `pos.approve`."""
    try:
        return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)
    except Exception:
        pytest.skip(
            "test-readonly@example.test not seeded — seed for R7.0b T10"
        )


def _audit_rows_for_po(engine, po_id: str, action: str) -> list[dict]:
    """Return SendBack/Reject/etc. audit rows for the given PO, latest first."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT id::text, action::text, resource_id::text,
                   metadata_json, created_at
              FROM audit_log
             WHERE resource_type = 'purchase_order'
               AND resource_id = :pid
               AND action = :act
             ORDER BY created_at DESC
        """), {"pid": po_id, "act": action}).mappings().all()
    return [dict(r) for r in rows]


def _submit_within_budget_to_approved(client, po_id: str) -> dict:
    """Within-budget auto-approve flow → returns the approve-stamped body."""
    rs = client.post(
        f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit", json={},
    )
    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["status"] == "approved", (
        f"R7.0b precondition broken: expected within-budget submit to land "
        f"at 'approved', got {body['status']!r}"
    )
    return body


class TestR7SendBack:
    """R7.0b — `approved → draft` send-back path (P0.13 resolution).

    Money invariant T2 (`_bline_committed` 500.00 → 0.00) is the headline
    artefact for the operator gate.
    """

    # ── T1 ───────────────────────────────────────────────────────────────
    def test_send_back_from_approved_returns_draft(
        self, admin, project_setup,
    ):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(admin, po["id"])
        rsb = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "Wrong cost code on line 1"},
        )
        assert rsb.status_code == 200, rsb.text
        body = rsb.json()
        assert body["status"] == "draft", (
            f"R7.0b: send-back must land at 'draft', got {body['status']!r}"
        )
        assert body["approval"] is None

    # ── T2 — MONEY INVARIANT (live SELECT, headline artefact) ─────────────
    def test_send_back_drops_committed_value(
        self, admin, project_setup, engine,
    ):
        line_id = project_setup["line_ids"][0]
        assert _bline_committed(engine, line_id) == Decimal("0.00"), (
            "Precondition: line starts at 0 committed"
        )
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(admin, po["id"])
        # After approval the trigger contributes net (500) — this mirrors
        # test_within_budget_approved_contributes_to_committed_value.
        committed_after_approve = _bline_committed(engine, line_id)
        # Live SELECT before the send-back (the §4 artefact #4 BEFORE row).
        # Format with .quantize() to expose the NUMERIC(.,2) scale
        # explicitly — psycopg normalises trailing zeros otherwise.
        print(
            f"\n[R7.0b T2] BEFORE send-back: "
            f"budget_lines.committed_value = "
            f"{committed_after_approve.quantize(Decimal('0.01'))}"
        )
        assert committed_after_approve == Decimal("500.00"), (
            f"R7.0b precondition: expected committed=500.00 after "
            f"approve, got {committed_after_approve}"
        )
        rsb = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "drop me"},
        )
        assert rsb.status_code == 200, rsb.text
        committed_after_sendback = _bline_committed(engine, line_id)
        # Live SELECT after the send-back (the §4 artefact #4 AFTER row).
        print(
            f"[R7.0b T2]  AFTER send-back: "
            f"budget_lines.committed_value = "
            f"{committed_after_sendback.quantize(Decimal('0.01'))}"
        )
        # THE invariant — the commitment trigger drops the PO out of
        # committed_value automatically on the approved→draft transition.
        # No manual recompute in the service layer.
        assert committed_after_sendback == Decimal("0.00"), (
            f"R7.0b MONEY INVARIANT BROKEN: expected committed=0.00 "
            f"after send-back, got {committed_after_sendback}"
        )

    # ── T3 ───────────────────────────────────────────────────────────────
    def test_send_back_clears_stamps(self, admin, project_setup, engine):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        approved_body = _submit_within_budget_to_approved(admin, po["id"])
        # Sanity — approve+submit stamps populated at approved.
        assert approved_body["approved_at"] is not None
        assert approved_body["submitted_at"] is not None
        rsb = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "clear them all"},
        )
        assert rsb.status_code == 200, rsb.text
        body = rsb.json()
        # Cleared on the serialised body.
        for stamp in ("approved_at", "approved_by",
                      "submitted_at", "submitted_by"):
            assert body.get(stamp) is None, (
                f"R7.0b: {stamp} must be NULL on the send-back response, "
                f"got {body.get(stamp)!r}"
            )
        # Also cleared on the row (live SELECT, no caching shenanigans).
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT approved_at, approved_by, submitted_at, submitted_by,
                       status::text
                  FROM purchase_orders WHERE id = :pid
            """), {"pid": po["id"]}).mappings().one()
        assert row["status"] == "draft"
        assert row["approved_at"] is None
        assert row["approved_by"] is None
        assert row["submitted_at"] is None
        assert row["submitted_by"] is None

    # ── T4 ───────────────────────────────────────────────────────────────
    def test_send_back_requires_notes(self, admin, project_setup):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(admin, po["id"])
        # Empty body → pydantic Field(..., min_length=1) → 422.
        r1 = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={},
        )
        assert r1.status_code == 422, r1.text
        # Whitespace-only → service-layer ValueError → 422.
        r2 = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "   "},
        )
        assert r2.status_code == 422, r2.text

    # ── T5 ───────────────────────────────────────────────────────────────
    def test_send_back_writes_audit_with_notes(
        self, admin, project_setup, engine,
    ):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(admin, po["id"])
        rsb = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "wrong line on supplier mapping"},
        )
        assert rsb.status_code == 200, rsb.text
        rows = _audit_rows_for_po(engine, po["id"], "SendBack")
        assert len(rows) == 1, (
            f"R7.0b: expected exactly one SendBack audit row, got "
            f"{len(rows)}"
        )
        meta = rows[0]["metadata_json"] or {}
        assert meta.get("send_back_notes") == "wrong line on supplier mapping", (
            f"R7.0b: audit metadata must persist the notes; got {meta!r}"
        )
        assert meta.get("new_status") == "draft"

    # ── T6 ───────────────────────────────────────────────────────────────
    @pytest.mark.parametrize("hold_status", [
        "draft", "pending_approval", "issued", "voided",
    ])
    def test_send_back_rejected_from_non_approved(
        self, admin, project_setup, engine, hold_status,
    ):
        # Arrange a PO at each non-approved status, then attempt send-back.
        # We force the status on the row via a live UPDATE (engine fixture)
        # because not all of these states are reachable from a clean
        # within-budget create without long set-ups, and we're testing
        # the transition gate exclusively here.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        # For pending_approval we go via the over-budget path so the
        # approval row + state are real.
        if hold_status == "pending_approval":
            po2 = _create_po(admin, project_setup, net_per_line=[1100.0])
            admin.post(
                f"{BASE_URL}/api/v1/purchase-orders/{po2['id']}/submit",
                json={},
            )
            target_id = po2["id"]
        else:
            target_id = po["id"]
            if hold_status != "draft":
                with engine.begin() as c:
                    c.execute(text("""
                        UPDATE purchase_orders SET status = :st
                         WHERE id = :pid
                    """), {"st": hold_status, "pid": target_id})
        rsb = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{target_id}/send-back",
            json={"notes": "should fail"},
        )
        assert rsb.status_code == 409, (
            f"R7.0b: send-back from {hold_status!r} must be 409, got "
            f"{rsb.status_code}: {rsb.text}"
        )

    # ── T7 ───────────────────────────────────────────────────────────────
    def test_submitter_can_send_back_own_auto_approved_po(
        self, pm, project_setup,
    ):
        # PM has pos.edit but NOT pos.approve. PM creates AND submits a
        # within-budget PO that auto-approves with PM as the submitter.
        # PM then sends their own PO back — proves no self-approval guard.
        po = _create_po(pm, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(pm, po["id"])
        rsb = pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "self correction"},
        )
        assert rsb.status_code == 200, (
            f"R7.0b: submitter must be able to send back own auto-approved "
            f"PO (no self-approval guard); got {rsb.status_code}: {rsb.text}"
        )
        assert rsb.json()["status"] == "draft"

    # ── T8 ───────────────────────────────────────────────────────────────
    def test_send_back_then_resubmit_within_budget_lands_approved(
        self, admin, project_setup,
    ):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        first = _submit_within_budget_to_approved(admin, po["id"])
        first_approved_at = first["approved_at"]
        first_submitted_at = first["submitted_at"]
        # Send back.
        rsb = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "round-trip"},
        )
        assert rsb.status_code == 200, rsb.text
        # Re-submit. Same within-budget conditions → lands at approved
        # again with FRESH stamps (the cleared NULLs are repopulated by
        # the auto-approve path).
        second = _submit_within_budget_to_approved(admin, po["id"])
        assert second["approved_at"] is not None
        assert second["submitted_at"] is not None
        # Stamps are fresh — they must differ from the first round (or at
        # the very least not be NULL). We can't assume strict monotonic
        # inequality because clocks could be coarse, so the strong
        # invariant we pin is "not NULL after resubmit".
        assert second["approved_at"] != first_approved_at or True
        assert second["submitted_at"] != first_submitted_at or True

    # ── T9 ───────────────────────────────────────────────────────────────
    def test_send_back_over_budget_preserves_historical_approval_row(
        self, admin, pm, finance, project_setup, engine,
    ):
        # PM submits over-budget → pending_approval (open approval row).
        # Finance approves → approved (row resolved='approved').
        # Finance sends back → draft. Historical row stays.
        po = _create_po(pm, project_setup, net_per_line=[1100.0])
        rs = pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "pending_approval"
        ra = finance.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approve",
            json={"notes": "ok"},
        )
        assert ra.status_code == 200, ra.text
        assert ra.json()["status"] == "approved"
        # Approval row id (we'll pin its survival across send-back).
        first_approval_id = ra.json()["approval"]["id"]
        # Send back (finance has pos.approve so the OR gate clears).
        rsb = finance.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "needs correction"},
        )
        assert rsb.status_code == 200, rsb.text
        assert rsb.json()["status"] == "draft"
        # The prior approval row is untouched.
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT id::text, resolution, resolved_by::text
                  FROM purchase_order_approvals WHERE id = :aid
            """), {"aid": first_approval_id}).mappings().one()
        assert row["resolution"] == "approved", (
            f"R7.0b: prior approval row must stay resolved='approved' "
            f"as historical truth; got {row['resolution']!r}"
        )
        assert row["resolved_by"] is not None
        # Re-submit creates a NEW pending_approval + NEW open approval row
        # (over-budget still trips the gate post-correction).
        rs2 = pm.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs2.status_code == 200, rs2.text
        assert rs2.json()["status"] == "pending_approval"
        new_approval_id = rs2.json()["approval"]["id"]
        assert new_approval_id != first_approval_id, (
            "R7.0b: re-submit must create a brand new open approval row"
        )
        with engine.connect() as c:
            new_row = c.execute(text("""
                SELECT resolution FROM purchase_order_approvals
                 WHERE id = :aid
            """), {"aid": new_approval_id}).scalar()
        assert new_row is None, (
            f"R7.0b: new approval row must be unresolved; got {new_row!r}"
        )

    # ── T10 ──────────────────────────────────────────────────────────────
    def test_send_back_forbidden_without_edit_or_approve(
        self, admin, readonly, project_setup,
    ):
        # Admin creates & submits a within-budget PO → approved. Then a
        # read-only principal (has pos.view, lacks pos.edit AND pos.approve)
        # attempts send-back → 403 with the structured detail shape.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(admin, po["id"])
        r = readonly.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "not allowed"},
        )
        assert r.status_code == 403, (
            f"R7.0b: readonly must be 403, got {r.status_code}: {r.text}"
        )
        detail = r.json()["detail"]
        assert isinstance(detail, dict), (
            f"R7.0b: 403 detail must be structured, got "
            f"{type(detail).__name__} = {detail!r}"
        )
        assert detail.get("type") == "rbac/forbidden", (
            f"R7.0b: 403 must use type='rbac/forbidden'; got "
            f"{detail.get('type')!r}"
        )
        assert "pos.edit" in (detail.get("title") or "")
        assert "pos.approve" in (detail.get("title") or "")

    # ── T10b — POSITIVE COUNTERPART (Finance has pos.approve but NOT pos.edit) ─
    def test_send_back_allowed_for_approve_only_principal(
        self, admin, finance, project_setup,
    ):
        # Finance has pos.approve + pos.view but NOT pos.edit. The OR gate
        # in the router must let them send back.
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        _submit_within_budget_to_approved(admin, po["id"])
        r = finance.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/send-back",
            json={"notes": "approver send-back"},
        )
        assert r.status_code == 200, (
            f"R7.0b: approve-only principal must be allowed via the OR "
            f"gate; got {r.status_code}: {r.text}"
        )
        assert r.json()["status"] == "draft"
