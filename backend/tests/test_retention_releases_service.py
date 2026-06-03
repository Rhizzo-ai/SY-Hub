"""Chat 35 §R5 — Retention releases service tests.

Gates 22–26 of Build Pack 2.8b.
"""
from __future__ import annotations

from decimal import Decimal

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
    _, pid = make_entity_and_project(admin, name_prefix="RR test")
    seed_budget_for_project(admin, pid)
    return pid


@pytest.fixture
def sc_with_retention(admin, project_id):
    """Fresh subcontract + a single certified valuation that holds
    £500 in retention.
    """
    sub_id = make_subcontractor(admin)
    set_cis_status_for_supplier(sub_id, "Gross")  # no CIS noise
    sc = make_active_subcontract(
        admin, project_id=project_id, subcontractor_id=sub_id,
        original_contract_sum="100000.00", retention_pct="5.00",
    )
    r = create_valuation(
        admin, subcontract_id=sc["id"],
        gross_applied_to_date="10000.00",
        labour_portion="10000.00", materials_portion="0.00",
    )
    val_id = r.json()["id"]
    submit_valuation(admin, val_id)
    # Chat 39 §R2 A4: budget_line_id required.
    from app.db import SessionLocal as _SL
    from sqlalchemy import text as _t
    _db = _SL()
    try:
        bl_id = _db.scalar(_t("""
            SELECT bl.id FROM budget_lines bl
              JOIN budgets b ON b.id = bl.budget_id
             WHERE b.project_id=:p LIMIT 1
        """), {"p": project_id})
    finally:
        _db.close()
    cr = certify_valuation(admin, val_id, body={"budget_line_id": str(bl_id)})
    assert cr.status_code == 200, cr.text
    # Retention held = 500.
    return sc


def _release(admin, sc_id: str, *, release_type: str, release_pct=None):
    body = {"release_type": release_type}
    if release_pct is not None:
        body["release_pct"] = release_pct
    return admin.post(
        f"{BASE_URL}/api/v1/subcontracts/{sc_id}/retention-release",
        json=body,
    )


# ==========================================================================
# Gates 22–25
# ==========================================================================

class TestRetentionReleaseLifecycle:
    def test_pc_release_default_50_pct(self, admin, sc_with_retention):
        """Gate 22 — PC release defaults to 50%."""
        r = _release(admin, sc_with_retention["id"], release_type="PC")
        assert r.status_code == 201, r.text
        body = r.json()
        # 500 × 50% = 250.
        assert Decimal(body["amount_released"]) == Decimal("250.00")
        assert Decimal(body["release_pct"]) == Decimal("50.00")
        assert body["release_type"] == "PC"
        # Negative-retention actual posted.
        assert body["posted_actual_id"] is not None

    def test_dlp_release_remaining(self, admin, sc_with_retention):
        """Gate 23 — DLP release after PC."""
        _release(admin, sc_with_retention["id"], release_type="PC")
        # 500 - 250 = 250 still held; DLP at default 100% releases 250.
        r = _release(admin, sc_with_retention["id"], release_type="DLP")
        assert r.status_code == 201, r.text
        body = r.json()
        assert Decimal(body["amount_released"]) == Decimal("250.00")
        assert body["release_type"] == "DLP"

    def test_release_same_type_twice_rejected(self, admin, sc_with_retention):
        """Gate 24 — same release_type twice → 409 / unique constraint."""
        r1 = _release(admin, sc_with_retention["id"], release_type="PC")
        assert r1.status_code == 201, r1.text
        r2 = _release(admin, sc_with_retention["id"], release_type="PC")
        assert r2.status_code == 409, r2.text

    def test_release_amount_equals_held_times_pct(
        self, admin, sc_with_retention,
    ):
        """Gate 25 — amount = retention_held × release_pct."""
        # 500 held × 40% = 200.
        r = _release(
            admin, sc_with_retention["id"],
            release_type="PC", release_pct="40",
        )
        assert r.status_code == 201, r.text
        assert Decimal(r.json()["amount_released"]) == Decimal("200.00")

    def test_custom_release_pct_honoured(self, admin, sc_with_retention):
        """Gate 26 — Custom release_pct honoured."""
        r = _release(
            admin, sc_with_retention["id"],
            release_type="PC", release_pct="75",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # 500 × 75% = 375.
        assert Decimal(body["release_pct"]) == Decimal("75.00")
        assert Decimal(body["amount_released"]) == Decimal("375.00")


# ==========================================================================
# State guards
# ==========================================================================

class TestRetentionReleaseGuards:
    def test_unknown_release_type_returns_422(self, admin, sc_with_retention):
        r = _release(admin, sc_with_retention["id"], release_type="BOGUS")
        assert r.status_code == 422, r.text

    def test_release_with_no_retention_held_rejected(
        self, admin, project_id,
    ):
        """If no retention has accumulated → 409."""
        sub_id = make_subcontractor(admin)
        set_cis_status_for_supplier(sub_id, "Gross")
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            original_contract_sum="100000.00",
            retention_pct="0.00",  # no retention at all
        )
        r = _release(admin, sc["id"], release_type="PC")
        assert r.status_code == 409, r.text
        assert "retention" in r.json()["detail"].lower()
