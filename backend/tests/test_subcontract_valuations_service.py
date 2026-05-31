"""Chat 35 §R5 — Subcontract valuation service-level tests.

Covers Build Pack 2.8b §R5 gates 3–17 (lifecycle + certification
math + cumulative model + CIS-rate-from-status mapping + audit
trail + actuals integration round-trip).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._sc_valuations_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, PWD,
    certify_valuation, create_subcontract, create_valuation,
    make_active_subcontract, make_entity_and_project, make_subcontractor,
    reject_valuation, seed_budget_for_project,
    set_cis_status_for_supplier, submit_valuation,
    wipe_2_8b,
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
    wipe_2_8b(db_engine)
    yield
    wipe_2_8b(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


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
def project_id(admin):
    _, pid = make_entity_and_project(admin, name_prefix="VAL test")
    seed_budget_for_project(admin, pid)
    return pid


@pytest.fixture(scope="module")
def sub_id(admin):
    sid = make_subcontractor(admin)
    set_cis_status_for_supplier(sid, "Net")  # default 20% CIS
    return sid


# ==========================================================================
# Lifecycle
# ==========================================================================

class TestValuationCreate:
    def test_create_on_active_subcontract_is_draft_val0001(
        self, admin, project_id, sub_id,
    ):
        """Gate 3 — Create on Active subcontract → Draft, VAL-0001, n=1."""
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="Gate3", original_contract_sum="50000.00",
            retention_pct="5.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="10000.00",
            labour_portion="6000.00",
            materials_portion="4000.00",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "Draft"
        assert body["reference"] == "VAL-0001"
        assert body["valuation_number"] == 1

    def test_create_on_draft_subcontract_rejected(
        self, admin, project_id, sub_id,
    ):
        """Gate 4 — Create on Draft subcontract → rejected (409)."""
        r = create_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="Gate4 — Draft SC",
            original_contract_sum="1000.00",
        )
        assert r.status_code == 201, r.text
        sc_id = r.json()["id"]  # still Draft
        r = create_valuation(
            admin, subcontract_id=sc_id,
            gross_applied_to_date="100.00",
            labour_portion="100.00",
            materials_portion="0.00",
        )
        assert r.status_code == 409, r.text


class TestValuationStateMachine:
    def test_certify_from_draft_is_409(self, admin, project_id, sub_id):
        """Gate 5 — certify from Draft (skip submit) → 409."""
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="Gate5", original_contract_sum="50000.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="100.00",
            labour_portion="100.00", materials_portion="0.00",
        )
        val_id = r.json()["id"]
        r = certify_valuation(admin, val_id)
        assert r.status_code == 409, r.text

    def test_submit_moves_to_submitted(self, admin, project_id, sub_id):
        """Submit transitions Draft → Submitted."""
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="Submit", original_contract_sum="50000.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="100.00",
            labour_portion="100.00", materials_portion="0.00",
        )
        val_id = r.json()["id"]
        r = submit_valuation(admin, val_id)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Submitted"

    def test_second_valuation_gets_val0002(
        self, admin, project_id, sub_id,
    ):
        """Gate 6 — 2nd valuation → VAL-0002, valuation_number=2."""
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="Gate6", original_contract_sum="50000.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="1000.00",
            labour_portion="1000.00", materials_portion="0.00",
        )
        assert r.json()["reference"] == "VAL-0001"
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="2000.00",
            labour_portion="2000.00", materials_portion="0.00",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["reference"] == "VAL-0002"
        assert body["valuation_number"] == 2

    def test_reject_requires_reason(self, admin, project_id, sub_id):
        """Gate 7 — reject (reason required); missing reason → 422."""
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub_id,
            title="Gate7", original_contract_sum="50000.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="100.00",
            labour_portion="100.00", materials_portion="0.00",
        )
        val_id = r.json()["id"]
        submit_valuation(admin, val_id)
        # Empty reason — Pydantic min_length=1 should reject it.
        r = admin.post(
            f"{BASE_URL}/api/v1/subcontract-valuations/{val_id}/reject",
            json={"reason": ""},
        )
        assert r.status_code == 422, r.text
        # Valid reason → 200.
        r = reject_valuation(admin, val_id, reason="Disputed work")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Rejected"


# ==========================================================================
# Certification math (gates 8–17) — the core
# ==========================================================================

def _certify_first(
    admin, *, project_id, subcontractor_id,
    retention_pct: str = "5.00", cis_applies: bool = True,
    gross: str = "10000.00", labour: str = "6000.00",
    materials: str = "4000.00",
    contract_sum: str = "100000.00",
):
    sc = make_active_subcontract(
        admin, project_id=project_id, subcontractor_id=subcontractor_id,
        original_contract_sum=contract_sum,
        retention_pct=retention_pct,
        cis_applies=cis_applies,
    )
    r = create_valuation(
        admin, subcontract_id=sc["id"],
        gross_applied_to_date=gross,
        labour_portion=labour,
        materials_portion=materials,
    )
    assert r.status_code == 201, r.text
    val_id = r.json()["id"]
    submit_valuation(admin, val_id)
    cr = certify_valuation(admin, val_id)
    assert cr.status_code == 200, cr.text
    return sc, cr.json()


class TestCertificationMath:
    def test_first_cert_net_minus_retention_minus_cis_net20(
        self, admin, project_id, sub_id,
    ):
        """Gate 8 — net = gross − retention − CIS; Net status → 20% on labour."""
        sub = sub_id  # CIS status = Net (20%)
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="5.00", gross="10000.00",
            labour="6000.00", materials="4000.00",
        )
        # gross_this_cert = 10000
        # retention = 10000 × 5% = 500
        # CIS = 6000 × 20% = 1200 (labour only)
        # net = 10000 − 500 − 1200 = 8300
        assert Decimal(body["retention_this_cert"]) == Decimal("500.00")
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("1200.00")
        assert Decimal(body["net_payable_this_cert"]) == Decimal("8300.00")
        assert Decimal(body["cis_rate_pct"]) == Decimal("20.00")

    def test_cis_only_on_labour_not_materials(
        self, admin, project_id,
    ):
        """Gate 9 — CIS on labour ONLY (materials are CIS-exempt)."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="0.00", gross="1000.00",
            labour="500.00", materials="500.00",
        )
        # CIS = 500 × 20% = 100; materials portion contributes ZERO CIS.
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("100.00")
        # If CIS applied to whole gross, it'd be 200 — assert it does not.

    def test_cis_status_gross_means_zero(
        self, admin, project_id,
    ):
        """Gate 10 — Gross status (0%) → no CIS deduction."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Gross")
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="0.00", gross="1000.00",
            labour="1000.00", materials="0.00",
        )
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("0.00")
        assert Decimal(body["cis_rate_pct"]) == Decimal("0.00")

    def test_cis_status_unmatched_means_30(
        self, admin, project_id,
    ):
        """Gate 11 — Unmatched status → 30% CIS."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Unmatched")
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="0.00", gross="1000.00",
            labour="1000.00", materials="0.00",
        )
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("300.00")
        assert Decimal(body["cis_rate_pct"]) == Decimal("30.00")

    def test_cis_status_unverified_means_30(
        self, admin, project_id,
    ):
        """LD3 — Unverified (live default for new subcontractors) → 30%."""
        sub = make_subcontractor(admin)
        # Subcontractor seeds default to 'Unverified' — but we set
        # explicitly just to be unambiguous.
        set_cis_status_for_supplier(sub, "Unverified")
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="0.00", gross="1000.00",
            labour="1000.00", materials="0.00",
        )
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("300.00")

    def test_cis_status_null_defaults_to_30(
        self, admin, project_id,
    ):
        """Defensive — NULL current_cis_status (never-verified case) → 30%."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, None)
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="0.00", gross="1000.00",
            labour="1000.00", materials="0.00",
        )
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("300.00")

    def test_subcontract_cis_applies_false_means_zero(
        self, admin, project_id,
    ):
        """Gate 12 — subcontract.cis_applies=false → no CIS regardless."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")  # would be 20% if applied
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="0.00", gross="1000.00",
            labour="1000.00", materials="0.00",
            cis_applies=False,
        )
        assert Decimal(body["cis_deduction_this_cert"]) == Decimal("0.00")
        assert Decimal(body["cis_rate_pct"]) == Decimal("0.00")

    def test_cumulative_second_cert_only_movement_posts(
        self, admin, project_id,
    ):
        """Gate 13 — 2nd cert: gross_this_cert from previous_gross_certified."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub,
            original_contract_sum="100000.00", retention_pct="5.00",
        )
        # First cert: 10000.
        r1 = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="10000.00",
            labour_portion="6000.00", materials_portion="4000.00",
        )
        v1 = r1.json()["id"]
        submit_valuation(admin, v1)
        certify_valuation(admin, v1)
        # Second cert: 25000 cumulative.
        r2 = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="25000.00",
            labour_portion="9000.00", materials_portion="6000.00",
        )
        v2_id = r2.json()["id"]
        submit_valuation(admin, v2_id)
        cr = certify_valuation(admin, v2_id)
        assert cr.status_code == 200, cr.text
        body = cr.json()
        # gross_this_cert = 25000 - 10000 = 15000 (matches labour+materials).
        assert Decimal(body["gross_this_cert"]) == Decimal("15000.00")

    def test_retention_movement_on_2nd_cert(
        self, admin, project_id,
    ):
        """Gate 14 — retention computed on cumulative; only MOVEMENT posts."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub,
            original_contract_sum="100000.00", retention_pct="5.00",
        )
        # First cert 10000 → retention 500.
        r1 = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="10000.00",
            labour_portion="6000.00", materials_portion="4000.00",
        )
        v1 = r1.json()["id"]
        submit_valuation(admin, v1)
        certify_valuation(admin, v1)
        # Second cert 25000 cumulative → cumulative retention 1250,
        # movement = 1250 - 500 = 750.
        r2 = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="25000.00",
            labour_portion="9000.00", materials_portion="6000.00",
        )
        v2_id = r2.json()["id"]
        submit_valuation(admin, v2_id)
        cr = certify_valuation(admin, v2_id)
        body = cr.json()
        assert Decimal(body["retention_this_cert"]) == Decimal("750.00")

    def test_over_claim_warns_not_blocks(
        self, admin, project_id,
    ):
        """Gate 15 — gross_applied_to_date > current_contract_sum → WARN."""
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")
        sc = make_active_subcontract(
            admin, project_id=project_id, subcontractor_id=sub,
            original_contract_sum="5000.00",  # tight ceiling
            retention_pct="0.00",
        )
        r = create_valuation(
            admin, subcontract_id=sc["id"],
            gross_applied_to_date="6000.00",  # OVER claim
            labour_portion="6000.00", materials_portion="0.00",
        )
        val_id = r.json()["id"]
        submit_valuation(admin, val_id)
        cr = certify_valuation(admin, val_id)
        assert cr.status_code == 200, cr.text  # not blocked
        body = cr.json()
        assert body["over_claim_flag"] is True
        assert body["over_claim_note"] is not None

    def test_certify_posts_actual_no_double_deduction(
        self, admin, project_id,
    ):
        """Gate 16 — §R0.2 backstop. Posted actual: net_amount=gross_this_cert
        and retention_amount/cis_deduction_amount are recorded separately;
        their algebraic net equals net_payable_this_cert EXACTLY."""
        from app.db import SessionLocal
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="5.00", gross="10000.00",
            labour="6000.00", materials="4000.00",
        )
        posted_id = body["posted_actual_id"]
        assert posted_id is not None
        db = SessionLocal()
        try:
            row = db.execute(text("""
                SELECT source_type, related_subcontract_id,
                       net_amount, retention_amount, cis_deduction_amount
                  FROM actuals WHERE id=:i
            """), {"i": posted_id}).fetchone()
        finally:
            db.close()
        assert row is not None
        source_type, rel_sc, net, ret, cis = row
        assert source_type == "SC_Valuation"
        assert str(rel_sc) == sc["id"]
        # §R0.2 wiring: net_amount = gross_this_cert (PRE-deduction).
        assert Decimal(net) == Decimal("10000.00")
        assert Decimal(ret) == Decimal("500.00")
        assert Decimal(cis) == Decimal("1200.00")
        # The backstop: effective net = net - retention - CIS == net_payable.
        effective = Decimal(net) - Decimal(ret) - Decimal(cis)
        assert effective == Decimal(body["net_payable_this_cert"])
        assert effective == Decimal("8300.00")

    def test_snapshot_fields_match_computed_values(
        self, admin, project_id,
    ):
        """Gate 17 — stored snapshot fields equal what was computed."""
        from app.db import SessionLocal
        sub = make_subcontractor(admin)
        set_cis_status_for_supplier(sub, "Net")
        sc, body = _certify_first(
            admin, project_id=project_id, subcontractor_id=sub,
            retention_pct="5.00", gross="2000.00",
            labour="1500.00", materials="500.00",
        )
        db = SessionLocal()
        try:
            row = db.execute(text("""
                SELECT cis_rate_pct, retention_this_cert,
                       net_payable_this_cert, cis_deduction_this_cert
                  FROM subcontract_valuations WHERE id=:i
            """), {"i": body["id"]}).fetchone()
        finally:
            db.close()
        cis_rate, ret, net, cis_d = row
        # Should equal: retention 100, CIS 300, net 1600.
        assert Decimal(cis_rate) == Decimal("20.00")
        assert Decimal(ret) == Decimal("100.00")
        assert Decimal(cis_d) == Decimal("300.00")
        assert Decimal(net) == Decimal("1600.00")


# ==========================================================================
# CIS rate mapping unit coverage (gate 35)
# ==========================================================================

class TestCISRateMapping:
    def test_cis_rate_for_status_pure_function(self):
        from app.services.subcontract_valuations import cis_rate_for_status
        assert cis_rate_for_status("Gross") == Decimal("0")
        assert cis_rate_for_status("Net") == Decimal("20")
        assert cis_rate_for_status("Unmatched") == Decimal("30")
        assert cis_rate_for_status("Unverified") == Decimal("30")
        assert cis_rate_for_status(None) == Decimal("30")
        # Defensive default for any unknown string.
        assert cis_rate_for_status("Bogus") == Decimal("30")
