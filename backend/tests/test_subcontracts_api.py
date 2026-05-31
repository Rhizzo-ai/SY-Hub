"""Chat 34 §R5 (Prompt 2.8a) — Subcontracts API permission/auth tests.

Focuses on the HTTP surface that's NOT covered by the service tests:
permission gating (403), payload validation (422), and audit-row
emission on Create/Status_Change/Approve.

See `tests/test_subcontracts_service.py` for the lifecycle + LD1/LD2
business-rule coverage.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from tests._subcontracts_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, FINANCE_EMAIL, PM_EMAIL,
    PWD, READONLY_EMAIL,
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


@pytest.fixture(scope="module")
def readonly(db_engine):
    return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def sub_id(admin):
    return make_subcontractor(admin)


@pytest.fixture(scope="module")
def project_id(admin):
    _, pid = make_entity_and_project(admin, name_prefix="SC API")
    return pid


# ==========================================================================
# Validation
# ==========================================================================

class TestValidation:
    def test_empty_title_returns_422(self, admin, project_id, sub_id):
        r = create_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="",  # empty
        )
        # Pydantic min_length is not set; service-side ValueError → 422.
        assert r.status_code in (422,), r.text

    def test_unknown_subcontractor_returns_422(self, admin, project_id):
        r = create_subcontract(
            admin, project_id=project_id,
            subcontractor_id=str(uuid.uuid4()),
            title="bad sub",
        )
        assert r.status_code == 422, r.text

    def test_negative_contract_sum_rejected(self, admin, project_id, sub_id):
        r = create_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="neg", original_contract_sum="-1.00",
        )
        assert r.status_code == 422, r.text

    def test_retention_out_of_range_rejected(self, admin, project_id, sub_id):
        r = create_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="ret",
            extra={"retention_pct": "150.00"},
        )
        assert r.status_code == 422, r.text


# ==========================================================================
# Permission gates (Gate 30 surface).
# ==========================================================================

class TestPermissionGates:
    def test_readonly_cannot_create(self, readonly, project_id, sub_id):
        r = create_subcontract(
            readonly, project_id=project_id, subcontractor_id=sub_id,
            title="ro should fail",
        )
        assert r.status_code == 403, r.text

    def test_pm_cannot_approve_activate(self, admin, pm, sub_id):
        """PM can create + edit, but cannot activate (which is gated on
        `subcontracts.approve` — finance/director/super_admin only)."""
        _, pid = make_entity_and_project(admin, name_prefix="SC API PMNo")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="pm activate guard",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]
        # PM signs but cannot activate.
        r = pm.patch(
            f"{BASE_URL}/api/v1/subcontracts/{sc_id}",
            json={"signed_at": datetime.now(timezone.utc).isoformat()},
        )
        assert r.status_code == 200, r.text
        r = pm.post(f"{BASE_URL}/api/v1/subcontracts/{sc_id}/activate")
        assert r.status_code == 403, r.text

    def test_finance_can_activate(self, admin, finance, sub_id):
        _, pid = make_entity_and_project(admin, name_prefix="SC API FinOK")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="fin activate", original_contract_sum="0",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]
        r = admin.patch(
            f"{BASE_URL}/api/v1/subcontracts/{sc_id}",
            json={"signed_at": datetime.now(timezone.utc).isoformat()},
        )
        assert r.status_code == 200, r.text
        r = finance.post(
            f"{BASE_URL}/api/v1/subcontracts/{sc_id}/activate"
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Active"


# ==========================================================================
# Audit emission.
# ==========================================================================

class TestAudit:
    def test_create_emits_audit_row(self, admin, project_id, sub_id, db_engine):
        r = create_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="audit me",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]
        with db_engine.connect() as c:
            cnt = c.execute(text("""
                SELECT COUNT(*) FROM audit_log
                 WHERE resource_type='subcontracts'
                   AND resource_id=:i AND action='Create'
            """), {"i": sc_id}).scalar()
        assert cnt == 1

    def test_activate_emits_status_change_audit(
        self, admin, project_id, sub_id, db_engine,
    ):
        r = create_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="audit activate",
        )
        assert r.status_code == 201, r.text
        sc = sign_and_activate(admin, r.json()["id"])
        with db_engine.connect() as c:
            cnt = c.execute(text("""
                SELECT COUNT(*) FROM audit_log
                 WHERE resource_type='subcontracts'
                   AND resource_id=:i AND action='Status_Change'
            """), {"i": sc["id"]}).scalar()
        # Activate is one Status_Change; the test may also see no others.
        assert cnt >= 1


# ==========================================================================
# List filter behaviour.
# ==========================================================================

class TestList:
    def test_list_filter_by_status(self, admin, sub_id):
        _, pid = make_entity_and_project(admin, name_prefix="SC API Filter")
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="list-1", original_contract_sum="0",
        )
        assert r.status_code == 201
        r = create_subcontract(
            admin, project_id=pid, subcontractor_id=sub_id,
            title="list-2", original_contract_sum="0",
        )
        assert r.status_code == 201
        r = admin.get(
            f"{BASE_URL}/api/v1/subcontracts",
            params={"project_id": pid, "status": "Draft"},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 2
        assert all(it["status"] == "Draft" for it in items)

    def test_list_invalid_status_returns_422(self, admin, project_id):
        r = admin.get(
            f"{BASE_URL}/api/v1/subcontracts",
            params={"project_id": project_id, "status": "Bogus"},
        )
        assert r.status_code == 422, r.text
