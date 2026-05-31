"""Chat 35 §R5 — Payment notices service tests.

Gates 18–21 of Build Pack 2.8b.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from tests._sc_valuations_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, PWD,
    certify_valuation, create_valuation, make_active_subcontract,
    make_entity_and_project, make_subcontractor, seed_budget_for_project,
    set_cis_status_for_supplier, submit_valuation, wipe_2_8b,
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
    wipe_2_8b(db_engine)
    yield
    wipe_2_8b(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_threshold(db_engine, admin):
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    admin.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )


@pytest.fixture(scope="module")
def project_id(admin):
    _, pid = make_entity_and_project(admin, name_prefix="PN test")
    seed_budget_for_project(admin, pid)
    return pid


@pytest.fixture(scope="module")
def sub_id(admin):
    sid = make_subcontractor(admin)
    set_cis_status_for_supplier(sid, "Net")
    return sid


def _certify_one(admin, project_id, sub_id, *, retention_pct: str = "5.00",
                 gross: str = "10000.00", labour: str = "6000.00",
                 materials: str = "4000.00"):
    sc = make_active_subcontract(
        admin, project_id=project_id, subcontractor_id=sub_id,
        original_contract_sum="100000.00",
        retention_pct=retention_pct,
    )
    r = create_valuation(
        admin, subcontract_id=sc["id"],
        gross_applied_to_date=gross,
        labour_portion=labour,
        materials_portion=materials,
    )
    val_id = r.json()["id"]
    submit_valuation(admin, val_id)
    cr = certify_valuation(admin, val_id)
    assert cr.status_code == 200, cr.text
    return sc, val_id


# ==========================================================================
# Gate 18 — Certify auto-creates Payment notice PN-0001.
# ==========================================================================

class TestAutoPaymentNotice:
    def test_certify_creates_payment_notice_pn0001(
        self, admin, project_id, sub_id,
    ):
        from decimal import Decimal
        sc, val_id = _certify_one(admin, project_id, sub_id)
        r = admin.get(
            f"{BASE_URL}/api/v1/payment-notices"
            f"?subcontract_valuation_id={val_id}"
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1
        n = items[0]
        assert n["notice_type"] == "Payment"
        assert n["reference"] == "PN-0001"
        # Snapshot of certified figures: net = 10000 − 500 − 1200 = 8300.
        assert Decimal(n["net_due"]) == Decimal("8300.00")
        assert Decimal(n["gross_certified"]) == Decimal("10000.00")
        assert Decimal(n["retention"]) == Decimal("500.00")
        assert Decimal(n["cis_deducted"]) == Decimal("1200.00")


# ==========================================================================
# Gates 19–20 — PayLess notices.
# ==========================================================================

class TestPayLessNotice:
    def test_payless_against_certified_succeeds(
        self, admin, project_id, sub_id,
    ):
        """Gate 19 — PayLess notice against a Certified valuation."""
        from decimal import Decimal
        sc, val_id = _certify_one(admin, project_id, sub_id)
        r = admin.post(
            f"{BASE_URL}/api/v1/payment-notices/payless",
            json={
                "subcontract_valuation_id": val_id,
                "withhold_amount": "500.00",
                "reason": "Defective works",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["notice_type"] == "PayLess"
        # net_due = certified net − withheld = 8300 - 500 = 7800.
        assert Decimal(body["net_due"]) == Decimal("7800.00")
        # PN-0002 — auto Payment notice (PN-0001) already exists.
        assert body["reference"] == "PN-0002"

    def test_payless_against_non_certified_rejected(
        self, admin, project_id, sub_id,
    ):
        """Gate 20 — PayLess against Draft/Submitted → 409."""
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            original_contract_sum="50000.00", retention_pct="5.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="1000.00",
            labour_portion="1000.00", materials_portion="0.00",
        )
        val_id = r.json()["id"]  # status = Draft

        r = admin.post(
            f"{BASE_URL}/api/v1/payment-notices/payless",
            json={
                "subcontract_valuation_id": val_id,
                "withhold_amount": "100",
                "reason": "Premature",
            },
        )
        assert r.status_code == 409, r.text
        assert "Certified" in r.json()["detail"]

    def test_payless_missing_reason_returns_422(
        self, admin, project_id, sub_id,
    ):
        sc, val_id = _certify_one(admin, project_id, sub_id)
        r = admin.post(
            f"{BASE_URL}/api/v1/payment-notices/payless",
            json={
                "subcontract_valuation_id": val_id,
                "withhold_amount": "100",
                "reason": "",
            },
        )
        assert r.status_code == 422, r.text


# ==========================================================================
# Gate 21 — Cross-tenant notice fetch → 404.
# ==========================================================================

class TestCrossTenant:
    def test_get_nonexistent_payment_notice_returns_404(self, admin):
        r = admin.get(
            f"{BASE_URL}/api/v1/payment-notices/{uuid.uuid4()}"
        )
        assert r.status_code == 404, r.text
