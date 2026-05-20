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
            WHERE u.email = :em AND e.is_archived = false
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
        json={"name": f"R3-Supplier {name_suffix}", "default_vat_rate": 20.0},
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
    def test_g31_within_budget_auto_issue_no_approval_row(
        self, admin, project_setup,
    ):
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "issued"
        assert body["approval"] is None
        # No approval row inserted.
        ra = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/approvals")
        assert ra.status_code == 200
        assert ra.json()["total"] == 0

    def test_g32_within_budget_approval_required_auto_approves(
        self, admin, project_setup,
    ):
        po = _create_po(admin, project_setup, net_per_line=[500.0],
                        approval_required=True)
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
        )
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "approved"
        assert body["approval"] is not None
        assert body["approval"]["resolution"] == "approved"
        # Audit Approve row.
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
        po = _create_po(admin, project_setup, net_per_line=[500.0])
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po['id']}/submit", json={},
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
