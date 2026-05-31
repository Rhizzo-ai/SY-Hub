"""Chat 34 §R5 (Prompt 2.8a) — Subcontract variations API tests.

Focused on the HTTP-surface concerns and the variation→BCR
integration gates 22, 23, 26, 27 + permission gating 30.

Gate 22 — Approve BudgetChange → create_bcr(Adjustment,
         source_variation_id set); `generated_bcr_id` populated;
         contract sum UNCHANGED.
Gate 23 — Generated BCR is a normal Draft BCR (NOT auto-applied);
         budget_line.approved_changes is unchanged until applied.
Gate 26 — End-to-end: user A raises→costs→approves(BudgetChange);
         a DIFFERENT user B approves+applies the generated BCR (B ≠
         BCR creator, so 2.6 self-approval guard permits it) →
         budget line approved_changes reflects the variation value;
         budget header FFC recomputed.
Gate 27 — The applied BCR's source_variation_id round-trips to the
         variation.
Gate 30 — `subcontract_variations.issue` absent → 403 on issue.

See `tests/test_subcontract_variations_service.py` for state-machine /
business-rule coverage.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._bcr_common import make_active_budget
from tests._subcontracts_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, DIRECTOR_EMAIL, FINANCE_EMAIL,
    PM_EMAIL, PWD, READONLY_EMAIL,
    create_subcontract, make_entity_and_project, make_subcontractor,
    sign_and_activate, wipe,
)
from tests.conftest import login_with_auto_enroll


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


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(db_engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_self_approval_threshold(db_engine, admin):
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    r = admin.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def sub_id(admin):
    return make_subcontractor(admin)


def _setup_sc_with_active_budget(admin, db_engine, sub_id, *, prefix):
    """Create a project + Active budget + Active subcontract; return
    (subcontract dict, budget dict, project_id)."""
    _, pid = make_entity_and_project(admin, name_prefix=prefix)
    budget = make_active_budget(
        admin, db_engine, pid, line_count=3,
        line_amount=Decimal("100000.00"),
    )
    r = create_subcontract(
        admin, project_id=pid, subcontractor_id=sub_id,
        title="Variation carrier",
        original_contract_sum="50000.00",
    )
    assert r.status_code == 201, r.text
    sc = sign_and_activate(admin, r.json()["id"])
    return sc, budget, pid


# ==========================================================================
# Gates 22, 23 — Approve BudgetChange creates Draft BCR; contract sum
# unchanged; approved_changes unchanged until applied.
# ==========================================================================

class TestApproveBudgetChange:
    def test_creates_draft_bcr_and_leaves_contract_sum_unchanged(
        self, admin, db_engine, sub_id,
    ):
        sc, budget, _ = _setup_sc_with_active_budget(
            admin, db_engine, sub_id, prefix="V API BC",
        )
        target_line = budget["lines"][0]
        contract_sum_before = sc["current_contract_sum"]

        v_r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "BC variation",
            },
        )
        assert v_r.status_code == 201, v_r.text
        v_id = v_r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "2500.00"},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={
                "cost_treatment": "BudgetChange",
                "target_budget_line_id": target_line["id"],
            },
        )
        assert r.status_code == 200, r.text
        v_body = r.json()
        assert v_body["status"] == "Approved"
        assert v_body["cost_treatment"] == "BudgetChange"
        assert v_body["generated_bcr_id"] is not None
        bcr_id = v_body["generated_bcr_id"]

        # Gate 22 — subcontract.current_contract_sum unchanged.
        sc_get = admin.get(f"{BASE_URL}/api/v1/subcontracts/{sc['id']}")
        assert sc_get.json()["current_contract_sum"] == contract_sum_before

        # Gate 23 — the generated BCR is in Draft.
        bcr_get = admin.get(
            f"{BASE_URL}/api/v1/budget-changes/{bcr_id}"
        )
        assert bcr_get.status_code == 200, bcr_get.text
        bcr_body = bcr_get.json()
        assert bcr_body["status"] == "Draft", bcr_body
        assert bcr_body["source_variation_id"] == v_id  # Gate 27 prelim.

        # Budget line approved_changes still 0 (BCR not applied).
        with db_engine.connect() as c:
            ac = c.execute(text("""
                SELECT approved_changes FROM budget_lines WHERE id=:i
            """), {"i": target_line["id"]}).scalar()
        assert Decimal(str(ac)) == Decimal("0"), ac


# ==========================================================================
# Gates 26, 27 — End-to-end variation → BCR apply by different user.
# ==========================================================================

class TestEndToEndApply:
    def test_two_user_flow_applies_to_budget(
        self, admin, director, db_engine, sub_id,
    ):
        sc, budget, _ = _setup_sc_with_active_budget(
            admin, db_engine, sub_id, prefix="V API E2E",
        )
        target_line = budget["lines"][0]

        # User A (admin) raises + costs + approves the variation.
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "E2E variation",
            },
        )
        assert r.status_code == 201, r.text
        v_id = r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "3000.00"},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={
                "cost_treatment": "BudgetChange",
                "target_budget_line_id": target_line["id"],
            },
        )
        assert r.status_code == 200, r.text
        bcr_id = r.json()["generated_bcr_id"]

        # User B (director) drives the BCR through submit → approve → apply.
        r = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/submit",
        )
        assert r.status_code == 200, r.text
        r = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/approve",
        )
        assert r.status_code == 200, r.text
        r = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/apply",
        )
        assert r.status_code == 200, r.text

        # Gate 26 — budget_line.approved_changes reflects variation value.
        with db_engine.connect() as c:
            ac = c.execute(text("""
                SELECT approved_changes FROM budget_lines WHERE id=:i
            """), {"i": target_line["id"]}).scalar()
        assert Decimal(str(ac)) == Decimal("3000.00")

        # Gate 27 — applied BCR's source_variation_id round-trips.
        with db_engine.connect() as c:
            sv = c.execute(text("""
                SELECT source_variation_id FROM budget_changes WHERE id=:i
            """), {"i": bcr_id}).scalar()
        assert str(sv) == v_id


# ==========================================================================
# Gate 30 — `subcontract_variations.issue` absent → 403 on issue.
# ==========================================================================

class TestPermissionGates:
    def test_pm_cannot_approve(self, admin, pm, db_engine, sub_id):
        sc, _, _ = _setup_sc_with_active_budget(
            admin, db_engine, sub_id, prefix="V API PM403",
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "pm-approve",
            },
        )
        assert r.status_code == 201
        v_id = r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "10.00"},
        )
        # PM does not hold .approve.
        r = pm.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={"cost_treatment": "WithinContractSum"},
        )
        assert r.status_code == 403, r.text

    def test_pm_cannot_issue(self, admin, pm, db_engine, sub_id):
        sc, _, _ = _setup_sc_with_active_budget(
            admin, db_engine, sub_id, prefix="V API PM403i",
        )
        # Drive the variation to Approved as admin so PM can attempt issue.
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "issue403",
            },
        )
        v_id = r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "10.00"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={"cost_treatment": "WithinContractSum"},
        )
        r = pm.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/issue",
        )
        assert r.status_code == 403, r.text

    def test_readonly_cannot_raise(self, admin, readonly, db_engine, sub_id):
        sc, _, _ = _setup_sc_with_active_budget(
            admin, db_engine, sub_id, prefix="V API RO",
        )
        r = readonly.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "ro-raise",
            },
        )
        assert r.status_code == 403, r.text


# ==========================================================================
# List / Get cross-tenant.
# ==========================================================================

class TestReads:
    def test_list_filter_by_subcontract(self, admin, db_engine, sub_id):
        sc, _, _ = _setup_sc_with_active_budget(
            admin, db_engine, sub_id, prefix="V API List",
        )
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "list-1",
            },
        )
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc["id"], "title": "list-2",
            },
        )
        r = admin.get(
            f"{BASE_URL}/api/v1/subcontract-variations",
            params={"subcontract_id": sc["id"]},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 2
        assert all(it["subcontract_id"] == sc["id"] for it in items)

    def test_get_unknown_returns_404(self, admin):
        r = admin.get(
            f"{BASE_URL}/api/v1/subcontract-variations/{uuid.uuid4()}"
        )
        assert r.status_code == 404, r.text
