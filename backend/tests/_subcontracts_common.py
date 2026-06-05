"""Shared helpers for the 2.8a Subcontracts & Variations test suite.

NB. Module name starts with `_` so pytest does NOT collect it as a
test file. Pure Python — fixtures live in the individual test files.

Mirrors `tests/_bcr_common.py` shape so callers can compose the two
helper modules in tests that span both 2.6 (BCRs) and 2.8a
(Subcontracts/Variations) — e.g. the variation→BCR end-to-end gate.
"""
from __future__ import annotations

import os
import uuid
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

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


def wipe(engine) -> None:
    """Module-scoped wipe of subcontract + BCR + budget + appraisal state.

    Mirrors `_bcr_common.wipe` and extends with `subcontract_variations`
    + `subcontracts`. `purchase_orders` is ALSO wiped because LD1 tests
    create PO rows for the PO-linked subcontract paths.
    """
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('subcontracts','subcontract_variations',"
            " 'budgets','budget_lines','budget_line_items',"
            " 'budget_changes',"
            " 'appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members',"
            " 'purchase_orders','purchase_order_lines')"
        ))
        c.execute(text("UPDATE audit_log SET project_id = NULL "
                       "WHERE project_id IS NOT NULL"))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM subcontract_variations"))
        c.execute(text("DELETE FROM subcontracts"))
        c.execute(text("DELETE FROM budget_change_lines"))
        c.execute(text("DELETE FROM budget_changes"))
        # PO chain — wipe before budget_lines (FK references).
        c.execute(text("DELETE FROM purchase_order_receipt_photos"))
        c.execute(text("DELETE FROM purchase_order_receipt_lines"))
        c.execute(text("DELETE FROM purchase_order_receipts"))
        c.execute(text("DELETE FROM purchase_order_approvals"))
        c.execute(text("DELETE FROM purchase_order_lines"))
        c.execute(text("DELETE FROM purchase_orders"))
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
            "DELETE FROM projects WHERE name LIKE 'SC Test%'"
        ))
        c.execute(text(
            "DELETE FROM suppliers WHERE name LIKE 'SC-Test-%'"
        ))


def make_entity_and_project(
    admin_session, *, name_prefix: str = "SC Test",
) -> tuple[str, str]:
    """Resolve the primary tenant entity then create a new project."""
    from sqlalchemy import create_engine
    eng = create_engine(DATABASE_URL, future=True)
    with eng.connect() as c:
        entity_id = c.execute(text(
            "SELECT id FROM entities WHERE name = :n"
        ), {"n": PRIMARY_ENTITY_NAME}).scalar()
    eng.dispose()
    assert entity_id is not None, (
        f"Primary entity {PRIMARY_ENTITY_NAME!r} not seeded; check bootstrap"
    )

    project_name = f"{name_prefix} {uuid.uuid4().hex[:6]}"
    r = admin_session.post(f"{BASE_URL}/api/projects", json={
        "name": project_name,
        "project_type": "Dev_Build",
        "primary_entity_id": str(entity_id),
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 SC Test Way, Shrewsbury",
        "site_postcode": "SY1 2AA",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return str(entity_id), r.json()["id"]


def make_subcontractor(
    admin_session, *, name: Optional[str] = None,
) -> str:
    """Create a CIS subcontractor (`supplier_type='Contractor'` per
    Chat 41 §R3.2 — the 4-value contact-type label relabel).
    Returns its id."""
    if name is None:
        name = f"SC-Test-Sub-{uuid.uuid4().hex[:8]}"
    r = admin_session.post(f"{BASE_URL}/api/v1/suppliers", json={
        "name": name,
        "supplier_type": "Contractor",
        "cis_registered": False,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_plain_supplier(
    admin_session, *, name: Optional[str] = None,
) -> str:
    """Create a plain `supplier_type='Supplier'` supplier; return its id."""
    if name is None:
        name = f"SC-Test-Plain-{uuid.uuid4().hex[:8]}"
    r = admin_session.post(f"{BASE_URL}/api/v1/suppliers", json={
        "name": name,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def create_subcontract(
    session, *, project_id: str, subcontractor_id: str,
    title: str = "Test SC",
    original_contract_sum: str = "10000.00",
    purchase_order_id: Optional[str] = None,
    extra: Optional[dict] = None,
):
    body = {
        "project_id": project_id,
        "subcontractor_id": subcontractor_id,
        "title": title,
        "original_contract_sum": original_contract_sum,
    }
    if purchase_order_id is not None:
        body["purchase_order_id"] = purchase_order_id
    if extra:
        body.update(extra)
    r = session.post(f"{BASE_URL}/api/v1/subcontracts", json=body)
    return r


def sign_and_activate(session, sc_id: str) -> dict:
    """Sign + activate a Draft subcontract; return the active body."""
    from datetime import datetime, timezone
    r = session.patch(
        f"{BASE_URL}/api/v1/subcontracts/{sc_id}",
        json={"signed_at": datetime.now(timezone.utc).isoformat()},
    )
    assert r.status_code == 200, r.text
    r = session.post(f"{BASE_URL}/api/v1/subcontracts/{sc_id}/activate")
    assert r.status_code == 200, r.text
    return r.json()


def raise_variation(
    session, *, subcontract_id: str, title: str = "Test V",
    estimated_value: Optional[str] = None,
):
    body = {"subcontract_id": subcontract_id, "title": title}
    if estimated_value is not None:
        body["estimated_value"] = estimated_value
    return session.post(
        f"{BASE_URL}/api/v1/subcontract-variations", json=body,
    )
