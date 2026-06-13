"""Shared helpers for the B88 Pack 3 packages test suite.

Module name starts with `_` so pytest does NOT collect it as a test file.
Mirrors the `_subcontracts_common.py` / `_bcr_common.py` shape.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import text


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
SITE_EMAIL = "test-site@example.test"

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


def wipe(engine) -> None:
    """Module-scoped wipe: packages + downstream + budgets + appraisals.

    Order matters because of FKs. budget_lines is referenced by
    package_lines (ON DELETE RESTRICT — by design, to prevent a
    referenced line from being deleted out from under a package). So we
    wipe pack 3 tables FIRST regardless of project filter.
    """
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('packages','subcontracts','subcontract_variations',"
            " 'budgets','budget_lines','budget_line_items',"
            " 'budget_changes',"
            " 'appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members',"
            " 'purchase_orders','purchase_order_lines')"
        ))
        c.execute(text("UPDATE audit_log SET project_id = NULL "
                       "WHERE project_id IS NOT NULL"))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        # Pack 3 tables — wipe FIRST so budget_lines can be deleted.
        c.execute(text("DELETE FROM package_award_lines"))
        c.execute(text("DELETE FROM package_awards"))
        c.execute(text("DELETE FROM package_bid_lines"))
        c.execute(text("DELETE FROM package_bids"))
        c.execute(text("DELETE FROM package_lines"))
        c.execute(text("DELETE FROM packages"))
        # Downstream subcontract + variations
        c.execute(text("DELETE FROM subcontract_variations"))
        c.execute(text("DELETE FROM subcontracts"))
        # BCR
        c.execute(text("DELETE FROM budget_change_lines"))
        c.execute(text("DELETE FROM budget_changes"))
        # PO chain
        c.execute(text("DELETE FROM purchase_order_receipt_photos"))
        c.execute(text("DELETE FROM purchase_order_receipt_lines"))
        c.execute(text("DELETE FROM purchase_order_receipts"))
        c.execute(text("DELETE FROM purchase_order_approvals"))
        c.execute(text("DELETE FROM purchase_order_lines"))
        c.execute(text("DELETE FROM purchase_orders"))
        # Budgets + appraisals
        c.execute(text("DELETE FROM budget_line_items"))
        c.execute(text("DELETE FROM budget_lines"))
        c.execute(text("DELETE FROM budgets"))
        c.execute(text("DELETE FROM appraisal_finance_model"))
        c.execute(text("DELETE FROM appraisal_cost_lines"))
        c.execute(text("DELETE FROM appraisal_units"))
        c.execute(text(
            "ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER"
        ))
        c.execute(text("DELETE FROM appraisal_decision_log"))
        c.execute(text(
            "ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER"
        ))
        c.execute(text("DELETE FROM appraisal_revisions"))
        c.execute(text("DELETE FROM appraisal_scenarios"))
        c.execute(text("DELETE FROM appraisals"))
        c.execute(text("DELETE FROM project_team_members"))
        c.execute(text("DELETE FROM user_role_projects"))
        c.execute(text(
            "DELETE FROM projects WHERE name LIKE 'PKG Test%'"
        ))
        c.execute(text(
            "DELETE FROM suppliers WHERE name LIKE 'PKG-Test-%'"
        ))


def make_entity_and_project(
    admin_session, *, name_prefix: str = "PKG Test",
) -> tuple[str, str]:
    from sqlalchemy import create_engine
    eng = create_engine(DATABASE_URL, future=True)
    with eng.connect() as c:
        entity_id = c.execute(text(
            "SELECT id FROM entities WHERE name = :n"
        ), {"n": PRIMARY_ENTITY_NAME}).scalar()
    eng.dispose()
    assert entity_id is not None
    project_name = f"{name_prefix} {uuid.uuid4().hex[:6]}"
    r = admin_session.post(f"{BASE_URL}/api/projects", json={
        "name": project_name,
        "project_type": "Dev_Build",
        "primary_entity_id": str(entity_id),
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 PKG Test Way",
        "site_postcode": "SY1 2AA",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return str(entity_id), r.json()["id"]


def make_supplier(
    admin_session, *, supplier_type: str = "Supplier",
    name: Optional[str] = None,
) -> str:
    if name is None:
        name = f"PKG-Test-{supplier_type}-{uuid.uuid4().hex[:8]}"
    r = admin_session.post(f"{BASE_URL}/api/v1/suppliers", json={
        "name": name,
        "supplier_type": supplier_type,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_contractor(admin_session, **kw) -> str:
    return make_supplier(admin_session, supplier_type="Contractor", **kw)


def make_active_budget(
    admin_session, db_engine, project_id, *,
    line_count: int = 2,
    line_amount: Decimal = Decimal("100000.00"),
):
    """Create an Active budget on `project_id` with `line_count` lines.

    Each line has the same `line_amount` for `original_budget` and
    `current_budget`. Each line also gets a single BudgetLineItem so
    package lines can inherit qty/unit/rate (LD-P4) deterministically.
    Returns the activated budget dict.
    """
    # Re-use the BCR helper for the appraisal+budget bootstrap shape —
    # it produces an Active budget with `line_count` budget_lines.
    from tests._bcr_common import make_approved_appraisal
    # NB: we don't call _bcr_common.wipe_budgets_only here because that
    # helper has UNSCOPED `DELETE FROM budget_lines` statements which would
    # also wipe the FIRST project's budget_lines (and thereby trip the
    # package_lines FK). For Pack 3 we only ever call make_active_budget
    # against freshly-created projects so no wipe is needed.
    aid = make_approved_appraisal(admin_session, project_id)
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert r.status_code == 201, r.text
    budget = r.json()
    bid = budget["id"]

    from app.db import SessionLocal
    db = SessionLocal()
    try:
        cc_ids = [
            r[0] for r in db.execute(text(
                "SELECT id FROM cost_codes ORDER BY id LIMIT :n"
            ), {"n": line_count})
        ]
        if len(cc_ids) < line_count:
            raise RuntimeError(
                f"Need {line_count} cost_codes; found {len(cc_ids)}"
            )
        ent_id = db.scalar(text("SELECT id FROM entities LIMIT 1"))
        db.execute(text(
            "DELETE FROM budget_line_items WHERE budget_line_id IN "
            "(SELECT id FROM budget_lines WHERE budget_id=:b)"
        ), {"b": bid})
        db.execute(text(
            "DELETE FROM budget_lines WHERE budget_id=:b"
        ), {"b": bid})
        for i in range(line_count):
            new_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO budget_lines
                  (id, budget_id, cost_code_id, entity_id, line_description,
                   original_budget, approved_changes, current_budget,
                   actuals_to_date, committed_value,
                   invoiced_against_commitment, committed_not_invoiced,
                   forecast_to_complete, ftc_method, forecast_final_cost,
                   variance_value, variance_pct, variance_status,
                   is_locked, requires_attention, is_contingency,
                   display_order, created_at, updated_at)
                VALUES
                  (:id, :b, :cc, :ent, :desc,
                   :amt, 0, :amt,
                   0, 0, 0, 0, :amt, 'Budget_Remaining', :amt,
                   0, 0, 'Green',
                   false, false, false,
                   :ord, now(), now())
            """), {
                "id": str(new_id), "b": bid,
                "cc": str(cc_ids[i]), "ent": ent_id,
                "desc": f"PKG Line {i+1}",
                "amt": str(line_amount),
                "ord": i,
            })
            # Single BudgetLineItem with deterministic qty/rate so package
            # lines inherit cleanly (LD-P4).
            db.execute(text("""
                INSERT INTO budget_line_items
                  (id, budget_line_id, description, quantity, unit, rate,
                   amount, notes, display_order, created_at, updated_at)
                VALUES
                  (:id, :bl, :desc, :qty, :unit, :rate, :amt, NULL, 1,
                   now(), now())
            """), {
                "id": str(uuid.uuid4()),
                "bl": str(new_id),
                "desc": f"Item {i+1}",
                "qty": "100",
                "unit": "m2",
                # rate = amount / qty so net = qty * rate = line_amount
                "rate": str(line_amount / Decimal("100")),
                "amt": str(line_amount),
            })
        db.commit()
    finally:
        db.close()
    ra = admin_session.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
    assert ra.status_code == 200, ra.text
    out = ra.json()
    out["lines"] = sorted(
        out["lines"], key=lambda x: x.get("display_order", 0),
    )
    return out


def create_package(
    session, *, project_id: str, budget_id: str,
    title: str = "Test Package",
    kind: str = "materials",
    description: Optional[str] = None,
):
    body = {
        "budget_id": budget_id,
        "title": title,
        "kind": kind,
    }
    if description is not None:
        body["description"] = description
    return session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/packages", json=body,
    )


def add_line(session, package_id: str, *, budget_line_id: str, **extra):
    body = {"budget_line_id": budget_line_id, **extra}
    return session.post(
        f"{BASE_URL}/api/v1/packages/{package_id}/lines", json=body,
    )


def send_to_tender(session, package_id: str):
    return session.post(
        f"{BASE_URL}/api/v1/packages/{package_id}/send-to-tender",
    )


def invite_bidder(session, package_id: str, *, supplier_id: str):
    return session.post(
        f"{BASE_URL}/api/v1/packages/{package_id}/bids",
        json={"supplier_id": supplier_id},
    )


def enter_bid(session, bid_id: str, *, lines):
    return session.post(
        f"{BASE_URL}/api/v1/bids/{bid_id}/enter",
        json={"lines": lines},
    )


def award(session, package_id: str, *, awards):
    return session.post(
        f"{BASE_URL}/api/v1/packages/{package_id}/award",
        json={"awards": awards},
    )


def cancel_award(session, award_id: str, *, reason: str):
    return session.post(
        f"{BASE_URL}/api/v1/awards/{award_id}/cancel",
        json={"reason": reason},
    )


def bump_self_approval_threshold(admin_session):
    """Raise BUDGET_SELF_APPROVAL_THRESHOLD so admin can activate big budgets."""
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    r = admin_session.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )
    assert r.status_code == 200, r.text
