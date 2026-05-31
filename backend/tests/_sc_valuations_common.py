"""Shared helpers for the 2.8b Valuations / Payment Notices / Retention test suite.

NB. Module name starts with `_` so pytest does NOT collect it. Builds
on `_subcontracts_common` to provide a budget + budget-line stand-up
helper (needed because certify posts an actual that requires a real
budget line on the subcontract's project).
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text

from tests._subcontracts_common import (  # noqa: F401  — re-export
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, DIRECTOR_EMAIL, FINANCE_EMAIL,
    PM_EMAIL, PRIMARY_ENTITY_NAME, PWD, READONLY_EMAIL,
    create_subcontract, make_entity_and_project, make_plain_supplier,
    make_subcontractor, raise_variation, sign_and_activate, wipe,
)


def seed_budget_for_project(admin_session, project_id: str) -> str:
    """Spin up an Approved appraisal → Active budget → return the
    first budget_line.id.

    Mirrors the helper baked into 2.8a's test_subcontracts_service
    `_create_issued_po(...)` but stops short of creating a PO.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        existing_aid = db.execute(text("""
            SELECT id FROM appraisals
             WHERE project_id=:p AND status='Approved' LIMIT 1
        """), {"p": project_id}).scalar()
    finally:
        db.close()

    if existing_aid is None:
        ar = admin_session.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
            json={
                "name": f"VAL-helper-{uuid.uuid4().hex[:6]}",
                "land_purchase_price": "100000",
            },
        )
        assert ar.status_code == 201, ar.text
        aid = ar.json()["id"]
        db = SessionLocal()
        try:
            cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))
            db.execute(text(
                "DELETE FROM appraisal_cost_lines WHERE appraisal_id=:a"
            ), {"a": aid})
            db.execute(text("""
                INSERT INTO appraisal_cost_lines
                  (id, appraisal_id, display_order, cost_code_id, label,
                   category, auto_source, amount, is_locked)
                VALUES (gen_random_uuid(), :a, 10, :cc, 'Build cost',
                        'Construction', 'Manual', 100000.00, false)
            """), {"a": aid, "cc": cc_id})
            db.commit()
        finally:
            db.close()
        admin_session.post(
            f"{BASE_URL}/api/v1/appraisals/{aid}/units",
            json={
                "unit_label": "U", "unit_type": "Detached",
                "tenure": "Open_Market", "quantity": 1,
                "price_per_unit": "200000",
                "build_cost_per_unit": "100000",
            },
        )
        admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
        admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
    else:
        aid = str(existing_aid)

    db = SessionLocal()
    try:
        existing = db.execute(text("""
            SELECT id, status FROM budgets
             WHERE project_id=:p AND is_current=true
             LIMIT 1
        """), {"p": project_id}).fetchone()
    finally:
        db.close()

    if existing is not None:
        budget_id, budget_status = str(existing[0]), existing[1]
    else:
        r = admin_session.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        budget_id = r.json()["id"]
        budget_status = "Draft"

    if budget_status == "Draft":
        ra = admin_session.post(
            f"{BASE_URL}/api/v1/budgets/{budget_id}/activate"
        )
        assert ra.status_code == 200, ra.text

    db = SessionLocal()
    try:
        bl_id = db.scalar(text("""
            SELECT id FROM budget_lines WHERE budget_id=:b LIMIT 1
        """), {"b": budget_id})
    finally:
        db.close()
    assert bl_id is not None, "Budget seeded with no lines"
    return str(bl_id)


def set_cis_status_for_supplier(supplier_id: str, status: Optional[str]) -> None:
    """Force `suppliers.current_cis_status` to a given value (test-only
    bypass — the 2.7 service rejects setting Unverified via the API).
    """
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text(
            "UPDATE suppliers SET current_cis_status=:s WHERE id=:i"
        ), {"s": status, "i": supplier_id})
        db.commit()
    finally:
        db.close()


def make_active_subcontract(
    admin_session, *,
    project_id: str, subcontractor_id: str,
    title: str = "VAL test SC",
    original_contract_sum: str = "100000.00",
    retention_pct: str = "5.00",
    cis_applies: bool = True,
) -> dict:
    """Create + sign + activate a subcontract — ready for valuations."""
    r = create_subcontract(
        admin_session,
        project_id=project_id,
        subcontractor_id=subcontractor_id,
        title=title,
        original_contract_sum=original_contract_sum,
        extra={
            "retention_pct": retention_pct,
            "cis_applies": cis_applies,
        },
    )
    assert r.status_code == 201, r.text
    sc_id = r.json()["id"]
    return sign_and_activate(admin_session, sc_id)


def create_valuation(
    session, *,
    subcontract_id: str,
    gross_applied_to_date: str,
    labour_portion: str = "0",
    materials_portion: str = "0",
):
    return session.post(
        f"{BASE_URL}/api/v1/subcontract-valuations",
        json={
            "subcontract_id": subcontract_id,
            "gross_applied_to_date": gross_applied_to_date,
            "labour_portion": labour_portion,
            "materials_portion": materials_portion,
        },
    )


def submit_valuation(session, val_id: str):
    return session.post(
        f"{BASE_URL}/api/v1/subcontract-valuations/{val_id}/submit"
    )


def certify_valuation(session, val_id: str, *, body: Optional[dict] = None):
    return session.post(
        f"{BASE_URL}/api/v1/subcontract-valuations/{val_id}/certify",
        json=body or {},
    )


def reject_valuation(session, val_id: str, *, reason: str):
    return session.post(
        f"{BASE_URL}/api/v1/subcontract-valuations/{val_id}/reject",
        json={"reason": reason},
    )


def wipe_2_8b(engine) -> None:
    """Extend the 2.8a wipe with valuations/notices/releases."""
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('subcontract_valuations','payment_notices',"
            " 'retention_releases','actual')"
        ))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM payment_notices"))
        c.execute(text("DELETE FROM retention_releases"))
        c.execute(text("DELETE FROM subcontract_valuations"))
        c.execute(text(
            "DELETE FROM actuals_change_log WHERE actual_id IN ("
            " SELECT id FROM actuals WHERE source_type='SC_Valuation')"
        ))
        c.execute(text(
            "DELETE FROM actuals WHERE source_type='SC_Valuation'"
        ))
    # Run the 2.8a wipe afterwards (cascades subcontracts + budgets etc).
    wipe(engine)
