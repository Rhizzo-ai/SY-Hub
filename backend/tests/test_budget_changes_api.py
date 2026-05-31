"""Chat 33 §R5 (Prompt 2.6) — BCR HTTP API tests.

Covers Build Pack 2.6 acceptance gates 14–20 (workflow transitions),
26–30 (LD2 self-approval guard on GROSS movement basis), and gates 35
(API surface: cross-tenant 404, list filtering, change-log endpoint,
RBAC 403 on missing-permission paths).

Pattern follows tests/test_budgets.py: HTTP-based, cookies-only auth
via the `requests.Session` from `login_with_auto_enroll`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._bcr_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, DIRECTOR_EMAIL,
    READONLY_EMAIL, PWD, PRIMARY_ENTITY_NAME,
    create_transfer, make_active_budget, wipe,
)
from tests.conftest import login_with_auto_enroll, plain_login


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


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_self_approval_threshold(db_engine, admin):
    """Default £10k threshold would block admin self-activate on
    £250k+ seeded budgets. Bump high for lifecycle tests; the
    `TestSelfApprovalGuard` class lowers it transiently per test
    via the `low_threshold` fixture.
    """
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    r = admin.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )
    assert r.status_code == 200, r.text
    yield
    admin.post(f"{BASE_URL}/api/v1/system-config/{key}/restore")


@pytest.fixture(scope="module")
def entity_id(db_engine):
    with db_engine.connect() as c:
        pid = c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": PRIMARY_ENTITY_NAME},
        ).scalar()
    assert pid
    return str(pid)


@pytest.fixture(scope="module")
def project(admin, entity_id):
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": "BCR Test Project (API)",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 BCR API Way, Shrewsbury",
        "site_postcode": "SY1 2BB",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


# ==========================================================================
# Workflow  (gates 14–20)
# ==========================================================================

class TestWorkflow:
    def test_happy_path_draft_to_applied(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        bid = bcr["id"]
        r1 = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bid}/submit")
        assert r1.status_code == 200 and r1.json()["status"] == "Submitted"
        r2 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bid}/approve")
        assert r2.status_code == 200 and r2.json()["status"] == "Approved"
        r3 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bid}/apply")
        assert r3.status_code == 200 and r3.json()["status"] == "Applied"

    def test_approve_from_draft_rejected(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 409, r.text

    def test_apply_from_submitted_rejected(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r.status_code == 409, r.text

    def test_reject_requires_reason(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        r1 = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/reject", json={},
        )
        assert r1.status_code == 422
        r2 = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/reject",
            json={"reason": "Out of scope"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "Rejected"
        assert r2.json()["rejection_reason"] == "Out of scope"

    def test_withdraw_from_draft_and_submitted(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        # From Draft
        a = create_transfer(admin, b, title="WithdrawDraft")
        rd = admin.post(f"{BASE_URL}/api/v1/budget-changes/{a['id']}/withdraw")
        assert rd.status_code == 200 and rd.json()["status"] == "Withdrawn"
        # From Submitted
        c = create_transfer(admin, b, title="WithdrawSubmitted")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{c['id']}/submit")
        rs = admin.post(f"{BASE_URL}/api/v1/budget-changes/{c['id']}/withdraw")
        assert rs.status_code == 200 and rs.json()["status"] == "Withdrawn"
        # From Approved → 409
        e = create_transfer(admin, b, title="WithdrawApproved")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{e['id']}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{e['id']}/approve")
        ra = admin.post(f"{BASE_URL}/api/v1/budget-changes/{e['id']}/withdraw")
        assert ra.status_code == 409, ra.text

    def test_patch_non_draft_rejected(self, admin, db_engine, project):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}",
            json={"title": "new title"},
        )
        assert r.status_code == 409, r.text

    def test_apply_twice_rejected(self, admin, director, db_engine, project):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        r1 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r1.status_code == 200
        r2 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r2.status_code == 409, r2.text


# ==========================================================================
# Self-approval (LD2 / 2.4C)  (gates 26–30)
# ==========================================================================

@pytest.fixture
def low_threshold(admin):
    """Context-manager fixture that **callers** invoke around the approve
    step ONLY — the parent budget's `activate()` also consults the same
    threshold, so we must NOT lower it during budget setup.

    Returns an object with `apply()` and `restore()` methods.
    """
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY

    class _Ctx:
        def apply(self):
            admin.put(
                f"{BASE_URL}/api/v1/system-config/{key}",
                json={"value": "10000.00"},
            )

        def restore(self):
            admin.put(
                f"{BASE_URL}/api/v1/system-config/{key}",
                json={"value": "999999999.00"},
            )

    ctx = _Ctx()
    yield ctx
    # Defensive restore in case the test body didn't.
    ctx.restore()


class TestSelfApprovalGuard:
    def test_self_approve_above_threshold_blocked(
        self, admin, db_engine, project, low_threshold,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        # £15k transfer — gross 30k > 10k threshold.
        bcr = create_transfer(admin, b, amount="15000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 403, r.text
        assert ("self-approve" in r.json()["detail"].lower()
                or "gross movement" in r.json()["detail"].lower()
                or "self_approve" in r.json()["detail"].lower())

    def test_self_approve_below_threshold_allowed(
        self, admin, db_engine, project, low_threshold,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        # £2k transfer — gross 4k < 10k threshold.
        bcr = create_transfer(admin, b, amount="2000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Approved"

    def test_different_user_approves_high_value(
        self, admin, director, db_engine, project, low_threshold,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b, amount="15000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Approved"

    def test_self_approve_gross_movement_basis_not_net(
        self, admin, db_engine, project, low_threshold,
    ):
        """A £50k↔£50k Transfer has net_impact=0 but gross 100k —
        must still block per LD2."""
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b, amount="50000.00")
        assert Decimal(bcr["net_impact"]) == Decimal("0.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 403, r.text

    def test_null_creator_fail_open(
        self, admin, db_engine, project, low_threshold,
    ):
        """Legacy BCRs with NULL created_by must remain approvable."""
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b, amount="15000.00")
        # Strip created_by to simulate legacy.
        with db_engine.begin() as c:
            c.execute(text(
                "UPDATE budget_changes SET created_by=NULL WHERE id=:i"
            ), {"i": bcr["id"]})
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        # Even admin (who'd normally be self-approval-blocked) succeeds —
        # NULL creator can never equal admin.id.
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 200, r.text


# ==========================================================================
# API surface: 404 / 403 / list / change-log  (gate 35)
# ==========================================================================

class TestApiSurface:
    def test_create_missing_perm_403(
        self, readonly, db_engine, project, admin,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        r = readonly.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": b["id"],
            "change_type": "Adjustment", "title": "x",
            "lines": [{"budget_line_id": b["lines"][0]["id"], "delta": "1.00"}],
        })
        assert r.status_code == 403, r.text

    def test_approve_missing_perm_403(self, admin, db_engine, project):
        """Project_manager holds .approve per the live map. To hit the
        403 path we use read_only, which lacks .approve."""
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        ro = plain_login(BASE_URL, READONLY_EMAIL, PWD)
        r = ro.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 403, r.text

    def test_cross_tenant_get_returns_404(self, admin):
        """Cross-tenant or missing fetches must NOT leak existence —
        the router maps to 404."""
        r = admin.get(
            f"{BASE_URL}/api/v1/budget-changes/{uuid.uuid4()}"
        )
        assert r.status_code == 404, r.text

    def test_change_log_endpoint(self, admin, db_engine, project):
        b = make_active_budget(admin, db_engine, project["id"])
        create_transfer(admin, b, title="x1")
        create_transfer(admin, b, title="x2")
        r = admin.get(f"{BASE_URL}/api/v1/budgets/{b['id']}/change-log")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        # Newest first by created_at.
        titles = [item["title"] for item in body["items"]]
        assert titles == ["x2", "x1"]

    def test_list_filter_by_status(self, admin, db_engine, project):
        b = make_active_budget(admin, db_engine, project["id"])
        # Two Drafts, one Submitted.
        a = create_transfer(admin, b, title="a")
        create_transfer(admin, b, title="b")
        create_transfer(admin, b, title="c")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{a['id']}/submit")
        r1 = admin.get(
            f"{BASE_URL}/api/v1/budget-changes",
            params={"budget_id": b["id"], "status": "Draft"},
        )
        r2 = admin.get(
            f"{BASE_URL}/api/v1/budget-changes",
            params={"budget_id": b["id"], "status": "Submitted"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["total"] == 2
        assert r2.json()["total"] == 1
        assert r2.json()["items"][0]["id"] == a["id"]
