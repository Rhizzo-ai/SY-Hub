#!/usr/bin/env python3
"""
Chat 26 §R7 Batch 1 spot-check seed — purchase orders.

Pre-req: run `bash /app/scripts/seed_r7_spotcheck.sh` first to create the
spot-check project + Active budget + 10 budget_lines.

Seeds five purchase orders covering every state the operator needs to
eyeball Batch 1:

  PO #1  draft                          (submitted_by = test-pm) →
         operator clicks Submit; if within budget, auto-approves.
  PO #2  pending_approval (over-budget) (submitted_by = test-pm) →
         operator sees Approve + Reject + budget_snapshot table.
         (Not the operator's own PO → self-approval rule does NOT fire.)
  PO #3  pending_approval (user-flagged)(submitted_by = test-admin) →
         operator IS the submitter → Approve disabled with tooltip,
         Reject hidden. Self-approval rule.
  PO #4  approved                       (submitted_by = test-pm) →
         operator sees Issue / Send back / Void.
  PO #5  approved                       (submitted_by = test-admin) →
         operator IS the submitter → Send back still allowed (correction
         path; not subject to self-approval rule).

Login: `test-admin@example.test` / password from $TEST_USER_PASSWORD.

Idempotent — re-runs delete prior POs and approvals on the spot-check
project and re-seed.
"""
from __future__ import annotations

import os
import sys
import uuid

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

# Must match seed_r7_spotcheck.sh
PROJECT_ID = "b2a265ef-dc30-4779-96f6-e139d1881e07"

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"

sys.path.insert(0, "/app/backend")
from tests.conftest import login_with_auto_enroll  # noqa: E402


def _http_check(resp, msg):
    if resp.status_code >= 400:
        raise SystemExit(
            f"{msg}: HTTP {resp.status_code} — {resp.text[:400]}"
        )
    return resp


def _budget_and_lines(engine):
    with engine.connect() as c:
        bid = c.execute(text("""
            SELECT id FROM budgets WHERE project_id = :pid AND is_current = true
        """), {"pid": PROJECT_ID}).scalar()
        if bid is None:
            raise SystemExit(
                "No current budget for the spot-check project. "
                "Run /app/scripts/seed_r7_spotcheck.sh first."
            )
        rows = c.execute(text("""
            SELECT bl.id, cc.code, bl.current_budget, bl.actuals_to_date
            FROM budget_lines bl
            JOIN cost_codes cc ON cc.id = bl.cost_code_id
            WHERE bl.budget_id = :bid
            ORDER BY bl.display_order
        """), {"bid": bid}).all()
    by_code = {r.code: r for r in rows}
    return str(bid), by_code


def _disable_mfa_for_test_users(engine):
    """The login_with_auto_enroll helper enrolls super-admin roles in MFA
    on first call. The enrolment secret is in-process only, so a second
    invocation of this script fails with "no cached secret". Reset MFA
    on every test-* user at the start so the script is re-runnable.
    """
    with engine.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))


def _grant_spotcheck_perms_to_pm(engine):
    """test-pm@example.test is the operator's spot-check persona — the
    only test-* user with PO perms whose role doesn't force MFA. To
    exercise the full Batch-1 matrix (incl. Approve / Reject on a
    pending PO submitted by someone else, e.g. PO #3) the PM needs the
    `pos.approve` perm in addition to the PM role's defaults. We attach
    `pos.approve` via a direct role_permissions row on the
    'Project Manager' role for the spot-check sandbox only — production
    seeding never runs this script.
    """
    with engine.begin() as c:
        # Add pos.approve to Project Manager role if missing.
        c.execute(text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
              FROM roles r, permissions p
             WHERE r.name = 'Project Manager'
               AND p.code = 'pos.approve'
               AND NOT EXISTS (
                  SELECT 1 FROM role_permissions
                   WHERE role_id = r.id AND permission_id = p.id
               )
        """))


def _wipe_pos(engine):
    """Idempotency: wipe previous POs + approvals on the spot-check project."""
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM purchase_order_approvals
             WHERE purchase_order_id IN
                (SELECT id FROM purchase_orders WHERE project_id = :pid)
        """), {"pid": PROJECT_ID})
        c.execute(text("""
            DELETE FROM purchase_order_lines
             WHERE purchase_order_id IN
                (SELECT id FROM purchase_orders WHERE project_id = :pid)
        """), {"pid": PROJECT_ID})
        c.execute(text("""
            ALTER TABLE audit_log DISABLE TRIGGER USER;
        """))
        c.execute(text("""
            DELETE FROM audit_log
             WHERE resource_type = 'purchase_order'
               AND project_id = :pid
        """), {"pid": PROJECT_ID})
        c.execute(text("""
            ALTER TABLE audit_log ENABLE TRIGGER USER;
        """))
        c.execute(text("""
            DELETE FROM purchase_orders WHERE project_id = :pid
        """), {"pid": PROJECT_ID})


def _ensure_supplier(engine, admin_session) -> str:
    """Idempotent supplier — re-use the spot-check supplier if it already exists."""
    name = "R7 Spot-check Supplier"
    with engine.connect() as c:
        sid = c.execute(text("""
            SELECT id FROM suppliers WHERE name = :n LIMIT 1
        """), {"n": name}).scalar()
    if sid:
        return str(sid)
    r = admin_session.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": name, "default_vat_rate": 20.0},
    )
    _http_check(r, "create supplier")
    return r.json()["id"]


def _ensure_default_po_prefix(engine):
    """Idempotent default 'po' number-prefix on the spot-check project."""
    with engine.begin() as c:
        existing = c.execute(text("""
            SELECT id FROM project_number_prefixes
             WHERE project_id = :pid AND entity_type = 'po' AND is_default = true
             LIMIT 1
        """), {"pid": PROJECT_ID}).scalar()
        if existing:
            return str(existing)
        admin_id = c.execute(text("""
            SELECT id FROM users WHERE email = :em
        """), {"em": ADMIN_EMAIL}).scalar()
        pid = c.execute(text("""
            INSERT INTO project_number_prefixes (
                project_id, entity_type, middle_prefix, description,
                is_default, is_archived, next_sequence,
                created_by, updated_by
            ) VALUES (
                :pid, 'po', NULL, 'Default PO numbering (R7 spot-check)',
                true, false, 1, :uid, :uid
            )
            RETURNING id
        """), {"pid": PROJECT_ID, "uid": admin_id}).scalar()
    return str(pid)


def _create_po(session, *, budget_id: str, supplier_id: str,
               lines: list, approval_required: bool = False) -> dict:
    r = session.post(
        f"{BASE_URL}/api/v1/projects/{PROJECT_ID}/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "budget_id": budget_id,
            "approval_required": approval_required,
            "lines": lines,
        },
    )
    _http_check(r, "create PO")
    return r.json()


def _submit_po(session, po_id: str) -> dict:
    r = session.post(
        f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit", json={},
    )
    _http_check(r, f"submit PO {po_id}")
    return r.json()


def main():
    engine = create_engine(DATABASE_URL, future=True)

    # Self-healing: any pod-restart re-enables MFA on super-admins, and
    # our cached enrolment secrets are lost. Reset MFA so login works.
    _disable_mfa_for_test_users(engine)

    # Spot-check-only: PM gets pos.approve so the operator can walk the
    # full matrix from a single non-MFA login.
    _grant_spotcheck_perms_to_pm(engine)

    # Sanity — wipe prior POs on this project so re-runs are clean.
    _wipe_pos(engine)

    # Resolve budget + lines for sizing.
    budget_id, by_code = _budget_and_lines(engine)
    print(f"Budget: {budget_id}")
    print(f"  ACQ-03 headroom: £{by_code['ACQ-03'].current_budget - by_code['ACQ-03'].actuals_to_date}")
    print(f"  EXT-04 headroom: £{by_code['EXT-04'].current_budget - by_code['EXT-04'].actuals_to_date}")
    print(f"  FIN-02 headroom: £{by_code['FIN-02'].current_budget - by_code['FIN-02'].actuals_to_date}")

    admin = login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)
    pm = login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)

    supplier_id = _ensure_supplier(engine, admin)
    print(f"Supplier: {supplier_id}")
    prefix_id = _ensure_default_po_prefix(engine)
    print(f"Default PO prefix: {prefix_id}")

    # ── PO #1 — draft (submitted_by = test-pm later) ──────────────────
    po1 = _create_po(
        pm, budget_id=budget_id, supplier_id=supplier_id,
        lines=[{
            "budget_line_id": str(by_code["EXT-04"].id),
            "description": "Paving — phase 1 (draft)",
            "quantity": 1, "unit_rate": 5000.0, "vat_rate": 20,
            "cost_code": "EXT-04",
        }],
    )
    print(f"PO #1 [draft]                                   {po1['po_number']} → {po1['id']}")

    # ── PO #2 — pending_approval (over-budget; submitted_by = test-pm) ─
    # ACQ-03 has £3k headroom (15k budget - 12k actuals). £5k net trips the gate.
    po2 = _create_po(
        pm, budget_id=budget_id, supplier_id=supplier_id,
        lines=[{
            "budget_line_id": str(by_code["ACQ-03"].id),
            "description": "Extra conveyancing — overrun",
            "quantity": 1, "unit_rate": 5000.0, "vat_rate": 20,
            "cost_code": "ACQ-03",
        }],
    )
    _submit_po(pm, po2["id"])
    po2 = pm.get(f"{BASE_URL}/api/v1/purchase-orders/{po2['id']}").json()
    print(f"PO #2 [pending_approval, submitted by test-pm]  {po2['po_number']} → {po2['id']} "
          f"(status={po2['status']})")

    # ── PO #3 — pending_approval (user-flagged; submitted_by = test-admin) ─
    po3 = _create_po(
        admin, budget_id=budget_id, supplier_id=supplier_id,
        approval_required=True,
        lines=[{
            "budget_line_id": str(by_code["EXT-04"].id),
            "description": "Paving — phase 2 (self-approval test)",
            "quantity": 1, "unit_rate": 7500.0, "vat_rate": 20,
            "cost_code": "EXT-04",
        }],
    )
    _submit_po(admin, po3["id"])
    po3 = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po3['id']}").json()
    print(f"PO #3 [pending_approval, submitted by test-admin]{po3['po_number']} → {po3['id']} "
          f"(status={po3['status']}, self-approval target)")

    # ── PO #4 — approved (within budget, submitted_by = test-pm) ──────
    po4 = _create_po(
        pm, budget_id=budget_id, supplier_id=supplier_id,
        lines=[{
            "budget_line_id": str(by_code["FIN-02"].id),
            "description": "Mezz fees — tranche 1",
            "quantity": 1, "unit_rate": 8000.0, "vat_rate": 20,
            "cost_code": "FIN-02",
        }],
    )
    _submit_po(pm, po4["id"])
    po4 = pm.get(f"{BASE_URL}/api/v1/purchase-orders/{po4['id']}").json()
    print(f"PO #4 [approved, submitted by test-pm]          {po4['po_number']} → {po4['id']} "
          f"(status={po4['status']})")

    # ── PO #5 — approved (within budget, submitted_by = test-admin) ───
    po5 = _create_po(
        admin, budget_id=budget_id, supplier_id=supplier_id,
        lines=[{
            "budget_line_id": str(by_code["FIN-02"].id),
            "description": "Mezz fees — tranche 2 (send-back self-test)",
            "quantity": 1, "unit_rate": 6000.0, "vat_rate": 20,
            "cost_code": "FIN-02",
        }],
    )
    _submit_po(admin, po5["id"])
    po5 = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po5['id']}").json()
    print(f"PO #5 [approved, submitted by test-admin]       {po5['po_number']} → {po5['id']} "
          f"(status={po5['status']}, send-back-not-self-guarded target)")

    # ── Summary ───────────────────────────────────────────────────────
    app_url = (
        os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
        or "https://sy-spot-check-r70.preview.emergentagent.com"
    )
    print("")
    print("─── R7 Batch 1 PO spot-check seeded ─────────────────────────────────")
    print(f"  Login as: {ADMIN_EMAIL}   pwd: {PWD}")
    print("")
    print("  Project (Budgets tab is here — R7.1):")
    print(f"    {app_url}/projects/{PROJECT_ID}")
    print("")
    print("  Per-PO detail pages (status × persona × edit_tier × self-approval):")
    for po, label in (
        (po1, "draft, by test-pm           — operator clicks Submit"),
        (po2, "pending_approval, by test-pm — operator can Approve/Reject"),
        (po3, "pending_approval, by test-admin — SELF-APPROVAL: Approve disabled, Reject hidden"),
        (po4, "approved, by test-pm        — operator: Issue / Send back  (Void → Batch 2)"),
        (po5, "approved, by test-admin     — SELF-APPROVAL DOES NOT block Send back"),
    ):
        print(f"    {po['po_number']:>12}  {label}")
        print(f"      {app_url}/projects/{PROJECT_ID}/purchase-orders/{po['id']}")
    print("─────────────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
