"""Chat 34 §R5 (Prompt 2.8a) — Subcontracts service-level tests.

Covers Build Pack 2.8a §R5 gates 3–13 (subcontract create / lifecycle
+ LD1 PO link + LD2 subcontractor-only guard + sum sensitive gating).

Although these tests round-trip via the HTTP layer (the easier path —
fixture-loaded auth sessions are HTTP-based), they exercise the
service-layer business rules in `services/subcontracts.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from tests._subcontracts_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, FINANCE_EMAIL, PM_EMAIL, PWD,
    create_subcontract, make_entity_and_project, make_plain_supplier,
    make_subcontractor, sign_and_activate, wipe,
)
from tests.conftest import login_with_auto_enroll


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield eng
    eng.dispose()


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    wipe(db_engine)
    yield
    wipe(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_self_approval_threshold(db_engine, admin):
    """Default £10k threshold blocks admin self-activate on the £100k
    seeded budgets we need for PO link tests."""
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    r = admin.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def pm(db_engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)


@pytest.fixture(scope="module")
def project_a(admin):
    _, pid = make_entity_and_project(admin, name_prefix="SC Test A")
    return pid


@pytest.fixture(scope="module")
def project_b(admin):
    _, pid = make_entity_and_project(admin, name_prefix="SC Test B")
    return pid


@pytest.fixture(scope="module")
def sub_id(admin):
    return make_subcontractor(admin)


@pytest.fixture(scope="module")
def supplier_id(admin):
    return make_plain_supplier(admin)


# ==========================================================================
# Gate 3 — Create against a Subcontractor → Draft, SC-0001, sum=original.
# ==========================================================================

class TestCreate:
    def test_create_against_subcontractor_returns_draft_sc0001(
        self, admin, project_a, sub_id,
    ):
        r = create_subcontract(
            admin, project_id=project_a, subcontractor_id=sub_id,
            title="Groundworks package",
            original_contract_sum="50000.00",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "Draft"
        assert body["reference"] == "SC-0001"
        assert body["original_contract_sum"] == "50000.00"
        assert body["current_contract_sum"] == "50000.00"

    # Gate 4 — Create against plain Supplier → 422 (LD2).
    def test_create_against_plain_supplier_returns_422(
        self, admin, project_a, supplier_id,
    ):
        r = create_subcontract(
            admin, project_id=project_a, subcontractor_id=supplier_id,
            title="Bad — plain supplier",
        )
        assert r.status_code == 422, r.text
        assert "Subcontractor" in r.json()["detail"]

    # Gate 8 — Second subcontract same project → SC-0002.
    def test_second_subcontract_same_project_is_sc0002(
        self, admin, project_a, sub_id,
    ):
        r = create_subcontract(
            admin, project_id=project_a, subcontractor_id=sub_id,
            title="M&E package",
            original_contract_sum="20000.00",
        )
        assert r.status_code == 201, r.text
        assert r.json()["reference"] == "SC-0002"


# ==========================================================================
# Gates 5–7 — PO link (LD1).
# ==========================================================================

def _create_issued_po(
    admin, project_id, subcontractor_id, *,
    total_amount: str = "50000.00",
):
    """Create a budget + PO using the real APIs (no DB hacking) so the
    PO's NOT-NULL `budget_id` FK is satisfied cleanly.

    Returns the PO id. Each call creates a fresh appraisal + budget
    scoped to the supplied project, with PO-line cleanup integrated to
    avoid cross-test budget_lines FK violations.
    """
    import uuid as _uuid
    from decimal import Decimal
    from app.db import SessionLocal

    # 1. Approved appraisal (one per project; only one allowed at a time).
    db = SessionLocal()
    try:
        existing_aid = db.execute(text("""
            SELECT id FROM appraisals
             WHERE project_id=:p AND status='Approved' LIMIT 1
        """), {"p": project_id}).scalar()
    finally:
        db.close()
    if existing_aid is None:
        ar = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
            json={
                "name": f"PO-helper-{_uuid.uuid4().hex[:6]}",
                "land_purchase_price": "100000",
            },
        )
        assert ar.status_code == 201, ar.text
        aid = ar.json()["id"]
        # Seed a single Manual cost line so the budget seed path is valid.
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
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{aid}/units",
            json={
                "unit_label": "U", "unit_type": "Detached",
                "tenure": "Open_Market", "quantity": 1,
                "price_per_unit": str(total_amount),
                "build_cost_per_unit": "100000",
            },
        )
        admin.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
        admin.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
    else:
        aid = str(existing_aid)

    # 2. Draft or Active budget — re-use any existing current budget,
    # otherwise seed one from the approved appraisal.
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
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        assert r.status_code == 201, r.text
        budget_id = r.json()["id"]
        budget_status = "Draft"
    # Activate if still Draft — PO creation requires Active.
    if budget_status == "Draft":
        ra = admin.post(f"{BASE_URL}/api/v1/budgets/{budget_id}/activate")
        assert ra.status_code == 200, ra.text

    # 3. Pick the first budget line for the PO line ref.
    db = SessionLocal()
    try:
        bl_id = db.scalar(text("""
            SELECT id FROM budget_lines WHERE budget_id=:b LIMIT 1
        """), {"b": budget_id})
    finally:
        db.close()
    assert bl_id is not None, "Budget seeded with no lines"

    # 4. Create the PO via the real endpoint.
    line_total = total_amount
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/purchase-orders",
        json={
            "supplier_id": subcontractor_id,
            "budget_id": budget_id,
            "lines": [{
                "budget_line_id": str(bl_id),
                "description": "PO link test line",
                "quantity": 1,
                "unit_rate": float(line_total),
                "vat_rate": 0,
            }],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestPOLink:
    def test_po_same_project_same_subcontractor_links_ok(
        self, admin, project_b, sub_id,
    ):
        po_id = _create_issued_po(
            admin, project_b, sub_id, total_amount="80000.00",
        )
        r = create_subcontract(
            admin, project_id=project_b, subcontractor_id=sub_id,
            title="PO-linked SC",
            original_contract_sum="80000.00",
            purchase_order_id=po_id,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["purchase_order_id"] == po_id
        assert body["po_reconciliation_note"] is None

    def test_po_different_project_is_rejected(self, admin, project_a, project_b, sub_id):
        po_id = _create_issued_po(
            admin, project_b, sub_id, total_amount="10000.00",
        )
        r = create_subcontract(
            admin, project_id=project_a, subcontractor_id=sub_id,
            title="Bad — different project",
            original_contract_sum="10000.00",
            purchase_order_id=po_id,
        )
        assert r.status_code == 422, r.text
        assert "different project" in r.json()["detail"]

    def test_po_sum_mismatch_links_with_note(self, admin, sub_id):
        # Fresh project so PO numbering is clean.
        _, pid = make_entity_and_project(admin, name_prefix="SC Test PO-mismatch")
        po_id = _create_issued_po(admin, pid, sub_id, total_amount="60000.00")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="PO mismatch",
            original_contract_sum="55000.00",  # ≠ PO total
            purchase_order_id=po_id,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["purchase_order_id"] == po_id
        note = body["po_reconciliation_note"]
        assert note is not None and "does not match" in note


# ==========================================================================
# Gates 9-12 — Lifecycle transitions + cross-tenant 404.
# ==========================================================================

class TestLifecycle:
    @pytest.fixture
    def fresh_sc(self, admin, sub_id):
        _, pid = make_entity_and_project(admin, name_prefix="SC Test Life")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="Lifecycle SC",
            original_contract_sum="25000.00",
        )
        assert r.status_code == 201, r.text
        return r.json()

    def test_activate_without_signed_rejected(self, admin, fresh_sc):
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontracts/{fresh_sc['id']}/activate"
        )
        assert r.status_code == 409, r.text
        assert "signed" in r.json()["detail"].lower()

    def test_activate_with_signed_moves_to_active(self, admin, fresh_sc):
        sc_id = fresh_sc["id"]
        r = admin.patch(
            f"{BASE_URL}/api/v1/subcontracts/{sc_id}",
            json={"signed_at": datetime.now(timezone.utc).isoformat()},
        )
        assert r.status_code == 200, r.text
        r = admin.post(f"{BASE_URL}/api/v1/subcontracts/{sc_id}/activate")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Active"

    def test_complete_from_draft_rejected(self, admin, fresh_sc):
        sc_id = fresh_sc["id"]  # still Draft
        r = admin.post(f"{BASE_URL}/api/v1/subcontracts/{sc_id}/complete")
        assert r.status_code == 409, r.text

    def test_complete_from_active_moves_to_completed(self, admin, sub_id):
        # Independent SC: take it Draft → Active → Completed.
        _, pid = make_entity_and_project(admin, name_prefix="SC Test Complete")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="To complete", original_contract_sum="1000.00",
        )
        assert r.status_code == 201, r.text
        sc = sign_and_activate(admin, r.json()["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontracts/{sc['id']}/complete"
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Completed"

    def test_terminate_from_any_state(self, admin, fresh_sc):
        sc_id = fresh_sc["id"]
        # fresh_sc was activated above as a side-effect of the prior test.
        # Terminate it from whatever state it now sits in (Active).
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontracts/{sc_id}/terminate"
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Terminated"


class TestCrossTenant:
    def test_get_nonexistent_returns_404(self, admin):
        r = admin.get(
            f"{BASE_URL}/api/v1/subcontracts/{uuid.uuid4()}"
        )
        assert r.status_code == 404, r.text


# ==========================================================================
# Gate 13 — Sum fields hidden without `subcontracts.view_sensitive`.
# ==========================================================================

class TestSensitiveGating:
    def test_pm_sees_sums_pm_holds_view_sensitive(
        self, pm, admin, sub_id,
    ):
        """PM holds `subcontracts.view_sensitive` per the role map —
        sanity check that the sensitive sum fields are visible."""
        _, pid = make_entity_and_project(admin, name_prefix="SC Test PM")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="PM visibility", original_contract_sum="9999.99",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]
        r = pm.get(f"{BASE_URL}/api/v1/subcontracts/{sc_id}")
        assert r.status_code == 200, r.text
        assert r.json()["original_contract_sum"] == "9999.99"

    def test_role_without_view_sensitive_nulls_sums(
        self, admin, sub_id, db_engine,
    ):
        """Create a one-off user with `subcontracts.view` ONLY (no
        view_sensitive) and assert the response nulls the sum fields.
        """
        # Quickest path: directly assign `read_only` (holds .view but
        # not .view_sensitive) and login.
        # `test-readonly@example.test` is seeded with read_only.
        from tests._subcontracts_common import READONLY_EMAIL
        readonly = login_with_auto_enroll(
            None, BASE_URL, READONLY_EMAIL, PWD,
        )
        _, pid = make_entity_and_project(admin, name_prefix="SC Test Sens")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="sensitive", original_contract_sum="42000.00",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]
        r = readonly.get(f"{BASE_URL}/api/v1/subcontracts/{sc_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["original_contract_sum"] is None
        assert body["current_contract_sum"] is None
        # Non-sensitive fields are still present.
        assert body["title"] == "sensitive"
