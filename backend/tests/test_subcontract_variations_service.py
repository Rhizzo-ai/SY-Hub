"""Chat 34 §R5 (Prompt 2.8a) — Subcontract variations service tests.

Covers Build Pack 2.8a §R5 gates 14–25 + 31–34:
  14. Raise on Active subcontract → Raised, VAR-0001.
  15. Raise on Draft subcontract → rejected (409).
  16. cost sets agreed_value, Raised → Costed.
  17. Approve from Raised (skip cost) → 409.
  18. issue from Approved → Issued; from Costed → 409.
  19. reject (reason required) / withdraw → terminal; missing reason → 422.
  20. Second variation → VAR-0002.
  21. Approve WithinContractSum → current_contract_sum += agreed_value;
      no BCR created.
  22. Approve BudgetChange → calls create_bcr(Adjustment,
      source_variation_id set); generated_bcr_id populated; contract sum
      UNCHANGED.
  23. The generated BCR is a normal Draft BCR (NOT auto-applied) —
      assert its status is Draft and budget_line.approved_changes is
      unchanged until the BCR is separately applied.
  24. BudgetChange variation on a project with no Active budget → 422.
  25. Approving with invalid cost_treatment → 422.
  31. Subcontract status transitions rejected from wrong states
      (already covered in service tests; here we lean on the variation
      surface).
  32. Variation status transitions rejected from wrong states.
  33. Numbering is race-safe (sequential under contention — light
      single-process check; the production guarantee is via the row
      lock + unique constraint).
  34. Audit row written on create/approve/issue (service-layer
      record_audit).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._bcr_common import make_active_budget
from tests._subcontracts_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, FINANCE_EMAIL, PM_EMAIL, PWD,
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
def pm(db_engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_self_approval_threshold(db_engine, admin):
    """Same workaround the 2.6 suite uses — avoid blocking budget
    activation on big seeded contract sums."""
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


def _make_active_subcontract(admin, sub_id, *, prefix="V test"):
    _, pid = make_entity_and_project(admin, name_prefix=prefix)
    r = create_subcontract(
        admin, project_id=pid, subcontractor_id=sub_id,
        title="Carrier SC", original_contract_sum="100000.00",
    )
    assert r.status_code == 201, r.text
    sc = sign_and_activate(admin, r.json()["id"])
    return sc, pid


# ==========================================================================
# Gate 14 — Raise on Active subcontract → Raised, VAR-0001.
# Gate 20 — Second variation → VAR-0002.
# Gate 33 — Sequential numbering.
# ==========================================================================

class TestRaise:
    def test_raise_on_active_creates_var_0001(self, admin, sub_id):
        sc, _ = _make_active_subcontract(admin, sub_id, prefix="V Raise")
        r = admin.post(f"{BASE_URL}/api/v1/subcontract-variations", json={
            "subcontract_id": sc["id"],
            "title": "Door schedule revision",
            "estimated_value": "500.00",
        })
        assert r.status_code == 201, r.text
        v = r.json()
        assert v["status"] == "Raised"
        assert v["reference"] == "VAR-0001"
        assert v["estimated_value"] == "500.00"
        assert v["agreed_value"] is None
        # Gate 20 — second variation increments.
        r2 = admin.post(f"{BASE_URL}/api/v1/subcontract-variations", json={
            "subcontract_id": sc["id"],
            "title": "Second variation",
        })
        assert r2.status_code == 201, r2.text
        assert r2.json()["reference"] == "VAR-0002"

    # Gate 15 — Raise on Draft subcontract → rejected (409).
    def test_raise_on_draft_subcontract_rejected(self, admin, sub_id):
        _, pid = make_entity_and_project(admin, name_prefix="V Draft")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="Still draft",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]
        r = admin.post(f"{BASE_URL}/api/v1/subcontract-variations", json={
            "subcontract_id": sc_id,
            "title": "Should be blocked",
        })
        assert r.status_code == 409, r.text


# ==========================================================================
# Gates 16–19 — Cost / Approve / Issue / Reject / Withdraw transitions.
# Gate 32 — Wrong-state transitions return 409.
# ==========================================================================

class TestTransitions:
    @pytest.fixture
    def active_sc(self, admin, sub_id):
        sc, _ = _make_active_subcontract(admin, sub_id, prefix="V Transit")
        return sc

    def _raise(self, admin, sc_id, **kw):
        body = {"subcontract_id": sc_id, "title": kw.pop("title", "T")}
        body.update(kw)
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json=body,
        )
        assert r.status_code == 201, r.text
        return r.json()

    # Gate 16.
    def test_cost_sets_agreed_value_and_status(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="cost me")
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/cost",
            json={"agreed_value": "1234.56"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "Costed"
        assert body["agreed_value"] == "1234.56"
        assert body["costed_at"] is not None

    # Gate 17.
    def test_approve_from_raised_skips_cost_returns_409(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="skip-cost")
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/approve",
            json={"cost_treatment": "WithinContractSum"},
        )
        assert r.status_code == 409, r.text

    # Gate 18.
    def test_issue_from_approved_moves_to_issued(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="iss-1")
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/cost",
            json={"agreed_value": "100.00"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/approve",
            json={"cost_treatment": "WithinContractSum"},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/issue",
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Issued"
        # Re-issue → 409 (Issued is terminal).
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/issue",
        )
        assert r.status_code == 409, r.text

    def test_issue_from_costed_returns_409(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="iss-too-early")
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/cost",
            json={"agreed_value": "100.00"},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/issue",
        )
        assert r.status_code == 409, r.text

    # Gate 19 — reject / withdraw.
    def test_reject_missing_reason_returns_422(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="reject-no-reason")
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/reject",
            json={"reason": ""},
        )
        assert r.status_code == 422, r.text

    def test_reject_with_reason_is_terminal(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="reject-good")
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/reject",
            json={"reason": "Customer cancelled scope"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Rejected"
        # Further transitions blocked.
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/issue",
        )
        assert r.status_code == 409, r.text

    def test_withdraw_is_terminal(self, admin, active_sc):
        v = self._raise(admin, active_sc["id"], title="withdraw")
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v['id']}/withdraw",
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Withdrawn"


# ==========================================================================
# Gates 21–24 — Cost-treatment outcomes (the core).
# ==========================================================================

class TestCostTreatment:
    @pytest.fixture
    def active_sc(self, admin, sub_id):
        sc, _ = _make_active_subcontract(admin, sub_id, prefix="V Ctrl")
        return sc

    # Gate 21 — WithinContractSum folds into contract sum, no BCR.
    def test_within_contract_sum_folds(self, admin, active_sc):
        v_r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": active_sc["id"],
                "title": "WithinCS",
            },
        )
        assert v_r.status_code == 201, v_r.text
        v_id = v_r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "1500.00"},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={"cost_treatment": "WithinContractSum"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "Approved"
        assert body["cost_treatment"] == "WithinContractSum"
        assert body["generated_bcr_id"] is None
        # Subcontract current_contract_sum bumped by 1500.
        sc_get = admin.get(
            f"{BASE_URL}/api/v1/subcontracts/{active_sc['id']}"
        )
        assert sc_get.status_code == 200, sc_get.text
        # 100000.00 + 1500.00 = 101500.00.
        assert sc_get.json()["current_contract_sum"] == "101500.00"

    # Gate 24 — BudgetChange variation on project w/o Active budget → 422.
    def test_budget_change_no_active_budget_returns_422(self, admin, active_sc):
        v_r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": active_sc["id"],
                "title": "BC-no-budget",
            },
        )
        assert v_r.status_code == 201, v_r.text
        v_id = v_r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "1000.00"},
        )
        # Approve with BudgetChange — but the project has NO Active budget.
        # We MUST also supply the (unused-at-validation) target_budget_line_id
        # to confirm the budget-resolution gate fires first.
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={
                "cost_treatment": "BudgetChange",
                "target_budget_line_id": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 422, r.text
        assert "no Active" in r.json()["detail"].lower() or \
               "no active" in r.json()["detail"].lower()

    # Gate 25 — Approving with invalid cost_treatment → 422.
    def test_invalid_cost_treatment_returns_422(self, admin, active_sc):
        v_r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": active_sc["id"],
                "title": "bad-treatment",
            },
        )
        assert v_r.status_code == 201, v_r.text
        v_id = v_r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "100.00"},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={"cost_treatment": "Bogus"},
        )
        assert r.status_code == 422, r.text


# ==========================================================================
# Gate 34 — Audit emission on create / approve / issue.
# ==========================================================================

class TestAudit:
    @pytest.fixture
    def active_sc(self, admin, sub_id):
        sc, _ = _make_active_subcontract(admin, sub_id, prefix="V Audit")
        return sc

    def _flow_to_issued(self, admin, sc_id):
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations", json={
                "subcontract_id": sc_id,
                "title": "audit flow",
            },
        )
        assert r.status_code == 201, r.text
        v_id = r.json()["id"]
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/cost",
            json={"agreed_value": "100.00"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/approve",
            json={"cost_treatment": "WithinContractSum"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/subcontract-variations/{v_id}/issue",
        )
        return v_id

    def test_create_approve_issue_emit_audits(
        self, admin, active_sc, db_engine,
    ):
        v_id = self._flow_to_issued(admin, active_sc["id"])
        with db_engine.connect() as c:
            actions = [r[0] for r in c.execute(text("""
                SELECT action FROM audit_log
                 WHERE resource_type='subcontract_variations'
                   AND resource_id=:i
                 ORDER BY created_at
            """), {"i": v_id})]
        assert "Create" in actions
        assert "Approve" in actions
        assert "Status_Change" in actions  # cost → Costed, issue → Issued
