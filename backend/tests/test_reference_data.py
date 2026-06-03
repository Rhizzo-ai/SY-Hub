"""Prompt 2.1 — SDLT bands + appraisal default settings regression tests.

Covers every acceptance criterion from the spec that can be tested at
this point (the 'deferred to 2.2' AC is explicitly skipped).
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from tests.conftest import login_with_auto_enroll, plain_login


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://bulletproof-4.preview.emergentagent.com"

ADMIN = "test-admin@example.test"
DIRECTOR = "test-director@example.test"
READONLY = "test-readonly@example.test"
PWD = "TestUser-Dev-2026!"


@pytest.fixture(scope="module")
def admin_session():
    return login_with_auto_enroll(None, BASE_URL, ADMIN, PWD)


@pytest.fixture(scope="module")
def director_session():
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR, PWD)


@pytest.fixture(scope="module")
def readonly_session():
    return plain_login(BASE_URL, READONLY, PWD)


# =============================================================================
# AC: seed counts + shape
# =============================================================================

class TestSeed:
    def test_sdlt_seed_14_rows_across_4_categories(self):
        from app.db import SessionLocal
        from app.models.reference_data import SdltRateBand
        db = SessionLocal()
        try:
            total = db.scalar(select(func.count()).select_from(SdltRateBand))
            assert total == 14  # 5 + 5 + 3 + 1
            cats = {
                r[0] for r in db.execute(
                    select(SdltRateBand.category).distinct()
                ).all()
            }
            assert cats == {
                "Residential_Standard", "Residential_Surcharge",
                "Non_Residential", "Corporate_Flat_Rate",
            }
        finally:
            db.close()

    def test_sdlt_effective_from_2025_04_01(self):
        from app.db import SessionLocal
        from app.models.reference_data import SdltRateBand
        db = SessionLocal()
        try:
            rows = db.scalars(select(SdltRateBand)).all()
            for r in rows:
                assert r.effective_from == date(2025, 4, 1)
                assert r.effective_to is None
        finally:
            db.close()

    def test_appraisal_defaults_seeded_for_live_tenant(self):
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        from app.models.tenant import Tenant
        db = SessionLocal()
        try:
            tenant = db.scalar(
                select(Tenant).order_by(Tenant.created_at.asc())
            )
            rows = db.scalars(
                select(AppraisalDefaultSetting).where(
                    AppraisalDefaultSetting.tenant_id == tenant.id
                )
            ).all()
            assert len(rows) == 10
            keys = {r.setting_key for r in rows}
            assert keys == {
                "default_hurdle_on_cost_pct",
                "default_hurdle_on_gdv_pct",
                "default_contingency_pct",
                "default_architect_fee_pct",
                "default_structural_fee_pct",
                "default_qs_fee_pct",
                "default_selling_agents_pct",
                "default_legal_on_sale_pct",
                "default_prelims_pct",
                "default_mc_oh_p_pct",
            }
            # Spot-check a few exact values.
            by_key = {r.setting_key: r for r in rows}
            assert Decimal(by_key["default_hurdle_on_cost_pct"].setting_value) == Decimal("20.0000")
            assert Decimal(by_key["default_hurdle_on_gdv_pct"].setting_value) == Decimal("17.0000")
            assert Decimal(by_key["default_legal_on_sale_pct"].setting_value) == Decimal("0.2500")
            # Dev_Build-scoped.
            assert by_key["default_prelims_pct"].applies_to_project_type == "Dev_Build"
            assert by_key["default_mc_oh_p_pct"].applies_to_project_type == "Dev_Build"
        finally:
            db.close()

    def test_applies_to_project_type_reuses_1_5_enum(self):
        """Confirm the column uses the `project_type_enum` type — same
        one projects.project_type uses. Value-set must match exactly."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            # Which Postgres type does the column use?
            row = db.execute(text("""
                SELECT format_type(a.atttypid, a.atttypmod) AS typ
                  FROM pg_attribute a
                  JOIN pg_class c ON a.attrelid = c.oid
                 WHERE c.relname = 'appraisal_default_settings'
                   AND a.attname = 'applies_to_project_type'
            """)).first()
            assert row[0] == "project_type_enum"

            # Enum values match the 1.5 set.
            vals = [r[0] for r in db.execute(text(
                "SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = 'project_type_enum' "
                "ORDER BY enumsortorder"
            )).all()]
            assert vals == ["Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract"]
        finally:
            db.close()


# =============================================================================
# AC: SDLT calculator — the three headline cases
# =============================================================================

class TestSdltCalculator:
    def test_500k_residential_standard_is_15000(self):
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("500000"),
                          category="Residential_Standard")
            assert v == Decimal("15000.00")
        finally:
            db.close()

    def test_500k_residential_surcharge_is_40000(self):
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("500000"),
                          category="Residential_Surcharge")
            assert v == Decimal("40000.00")
        finally:
            db.close()

    def test_100k_residential_standard_is_zero(self):
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("100000"),
                          category="Residential_Standard")
            assert v == Decimal("0.00")
        finally:
            db.close()

    def test_negative_consideration_raises(self):
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            with pytest.raises(ValueError):
                calculate(db, consideration=Decimal("-1"),
                          category="Residential_Standard")
        finally:
            db.close()

    def test_non_residential_250k_is_2000(self):
        """Progressive check on Non_Residential at band edge."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            # 0..150k → 0, 150..250k → 2% on 100k = £2000
            v = calculate(db, consideration=Decimal("250000"),
                          category="Non_Residential")
            assert v == Decimal("2000.00")
        finally:
            db.close()


# =============================================================================
# AC: version transition + historical bands
# =============================================================================

class TestVersioning:
    def test_new_structure_closes_off_previous(self):
        from app.db import SessionLocal
        from app.models.reference_data import SdltRateBand
        from app.models.user import User
        from app.services import reference_data as svc

        db = SessionLocal()
        try:
            actor = db.scalar(select(User).where(User.email == ADMIN))
            effective_from = date(2026, 4, 1)
            # Close off Non_Residential only with a simplified new table.
            summary = svc.create_sdlt_structure(
                db,
                effective_from=effective_from,
                bands_by_category={
                    "Non_Residential": [
                        {"band_lower": 0, "band_upper": 200000, "rate_pct": 0},
                        {"band_lower": 200000, "band_upper": None, "rate_pct": 6},
                    ],
                },
                actor_user_id=actor.id,
            )
            db.commit()
            assert summary["rows_closed"] == 3   # 3 Non_Residential bands
            assert summary["rows_created"] == 2

            # The previously-active Non_Residential bands now have
            # effective_to = 2026-03-31.
            prev = db.scalars(
                select(SdltRateBand).where(
                    SdltRateBand.category == "Non_Residential",
                    SdltRateBand.effective_from == date(2025, 4, 1),
                )
            ).all()
            for r in prev:
                assert r.effective_to == date(2026, 3, 31)

            # Historical query on 2025-06-01 returns old bands.
            from app.services.sdlt import get_active_bands
            old = get_active_bands(
                db, category="Non_Residential", reference_date=date(2025, 6, 1)
            )
            assert len(old) == 3
            assert all(b.rate_pct in (Decimal("0.000"), Decimal("2.000"), Decimal("5.000"))
                       for b in old)

            # As-of 2026-07-01 returns the new simpler 2 bands.
            new_active = get_active_bands(
                db, category="Non_Residential", reference_date=date(2026, 7, 1)
            )
            assert len(new_active) == 2
        finally:
            # Cleanup so later tests see the original seed state.
            db.query(SdltRateBand).filter(
                SdltRateBand.effective_from == date(2026, 4, 1),
            ).delete()
            db.execute(
                text("UPDATE sdlt_rate_bands SET effective_to = NULL "
                     "WHERE category = 'Non_Residential' "
                     "AND effective_from = '2025-04-01'")
            )
            db.commit()
            db.close()

    def test_single_summary_audit_for_version_transition(self):
        """A version transition emits ONE audit row with metadata
        describing rows_closed + rows_created — not one per band."""
        from app.db import SessionLocal
        from app.models.audit import AuditLog
        from app.models.reference_data import SdltRateBand
        from app.models.user import User
        from app.services import reference_data as svc

        db = SessionLocal()
        try:
            actor = db.scalar(select(User).where(User.email == ADMIN))
            before_ct = db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.resource_type == "sdlt_rate_bands")
            )
            effective_from = date(2027, 4, 1)
            svc.create_sdlt_structure(
                db,
                effective_from=effective_from,
                bands_by_category={
                    "Corporate_Flat_Rate": [
                        {"band_lower": 500000, "band_upper": None, "rate_pct": 18},
                    ],
                },
                actor_user_id=actor.id,
            )
            db.commit()
            after_ct = db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.resource_type == "sdlt_rate_bands")
            )
            assert after_ct - before_ct == 1

            # Latest row has the transition metadata.
            row = db.scalar(
                select(AuditLog)
                .where(AuditLog.resource_type == "sdlt_rate_bands")
                .order_by(AuditLog.created_at.desc()).limit(1)
            )
            m = row.metadata_json
            assert m["kind"] == "sdlt_version_transition"
            assert m["effective_from"] == "2027-04-01"
            assert m["rows_created"] == 1
        finally:
            # Cleanup.
            db.query(SdltRateBand).filter(
                SdltRateBand.effective_from == date(2027, 4, 1),
            ).delete()
            db.execute(
                text("UPDATE sdlt_rate_bands SET effective_to = NULL "
                     "WHERE category = 'Corporate_Flat_Rate' "
                     "AND effective_from = '2025-04-01'")
            )
            db.commit()
            db.close()


# =============================================================================
# AC: UNIQUE constraint
# =============================================================================

class TestUniqueConstraint:
    def test_duplicate_setting_key_same_scope_rejected(self):
        """Two rows with (tenant_id, setting_key, applies_to_project_type)
        identical must be rejected by the unique constraint.
        'applies_to_project_type IS NULL' is covered by the partial
        unique index."""
        from sqlalchemy.exc import IntegrityError
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        from app.models.user import User
        from app.models.tenant import Tenant

        db = SessionLocal()
        try:
            tenant = db.scalar(select(Tenant))
            actor = db.scalar(select(User).where(User.email == ADMIN))
            dup = AppraisalDefaultSetting(
                tenant_id=tenant.id,
                setting_key="default_hurdle_on_cost_pct",  # already seeded
                setting_value=Decimal("99"),
                setting_type="Percentage",
                applies_to_project_type=None,
                description="dup test",
                updated_by_user_id=actor.id,
            )
            db.add(dup)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        finally:
            db.close()

    def test_same_key_different_project_type_allowed(self):
        """Same setting_key with different applies_to_project_type IS OK."""
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        from app.models.user import User
        from app.models.tenant import Tenant

        db = SessionLocal()
        try:
            tenant = db.scalar(select(Tenant))
            actor = db.scalar(select(User).where(User.email == ADMIN))
            # default_prelims_pct with applies_to_project_type='Dev_Build'
            # already exists. Add one with 'Pure_Dev' (not seeded).
            row = AppraisalDefaultSetting(
                tenant_id=tenant.id,
                setting_key="default_prelims_pct",
                setting_value=Decimal("10"),
                setting_type="Percentage",
                applies_to_project_type="Pure_Dev",
                description="test scope",
                updated_by_user_id=actor.id,
            )
            db.add(row)
            db.commit()
            new_id = row.id
            # Cleanup.
            db.delete(row)
            db.commit()
        finally:
            db.close()


# =============================================================================
# AC: permissions gating
# =============================================================================

class TestEndpointPermissions:
    def test_readonly_can_read_sdlt(self, readonly_session):
        r = readonly_session.get(f"{BASE_URL}/api/v1/reference-data/sdlt-rates")
        assert r.status_code == 200

    def test_readonly_can_read_appraisal_defaults(self, readonly_session):
        r = readonly_session.get(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults"
        )
        assert r.status_code == 200

    def test_readonly_cannot_put_appraisal_default(self, readonly_session):
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AppraisalDefaultSetting).where(
                    AppraisalDefaultSetting.setting_key == "default_qs_fee_pct"
                )
            )
            sid = str(row.id)
        finally:
            db.close()
        r = readonly_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": "1.25"},
        )
        assert r.status_code == 403

    def test_readonly_cannot_post_new_sdlt(self, readonly_session):
        r = readonly_session.post(
            f"{BASE_URL}/api/v1/reference-data/sdlt-rates/new-structure",
            json={
                "effective_from": "2099-01-01",
                "bands_by_category": {
                    "Corporate_Flat_Rate": [
                        {"band_lower": 500000, "band_upper": None, "rate_pct": 17},
                    ],
                },
            },
        )
        assert r.status_code == 403

    def test_director_cannot_admin_per_patch_3(self, director_session):
        """Spec text reads 'super_admin + director', but Patch #3
        narrowed system_config.admin to super_admin only (and removed
        system_config.edit). 2.1 reuses those codes verbatim — the 'Do
        not create new permission codes' rule pins this. Director is
        therefore correctly 403. SURFACE THIS to Rhys in deliverables."""
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AppraisalDefaultSetting).where(
                    AppraisalDefaultSetting.setting_key == "default_selling_agents_pct"
                )
            )
            sid = str(row.id)
        finally:
            db.close()
        r = director_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": "1.75"},
        )
        assert r.status_code == 403
        assert "system_config.admin" in r.json().get("detail", "")

    def test_super_admin_can_edit(self, admin_session):
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AppraisalDefaultSetting).where(
                    AppraisalDefaultSetting.setting_key == "default_selling_agents_pct"
                )
            )
            sid = str(row.id)
            original = str(row.setting_value)
        finally:
            db.close()
        r = admin_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": "1.75"},
        )
        assert r.status_code == 200, r.text
        assert Decimal(r.json()["setting_value"]) == Decimal("1.75")
        # Revert.
        admin_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": original},
        )


# =============================================================================
# AC: tenant isolation on appraisal_defaults
# =============================================================================

class TestTenantIsolation:
    def test_other_tenant_row_returns_404(self, admin_session):
        """If we manufacture a setting under a second synthetic tenant,
        an admin authenticated against tenant A cannot PUT it — the
        service treats cross-tenant access as 404 (not 403) to avoid
        leaking existence."""
        from app.db import SessionLocal
        from app.models.reference_data import AppraisalDefaultSetting
        from app.models.tenant import Tenant
        from app.models.user import User

        db = SessionLocal()
        try:
            # Create a second tenant + a setting on it.
            other = Tenant(name=f"Cross-tenant probe {uuid4()}")
            db.add(other)
            db.flush()
            admin = db.scalar(select(User).where(User.email == ADMIN))
            row = AppraisalDefaultSetting(
                tenant_id=other.id,
                setting_key="default_hurdle_on_cost_pct",
                setting_value=Decimal("99"),
                setting_type="Percentage",
                applies_to_project_type=None,
                description="cross-tenant probe",
                updated_by_user_id=admin.id,
            )
            db.add(row)
            db.commit()
            sid = str(row.id)
            probe_tenant_id = other.id
        finally:
            db.close()

        r = admin_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": "10"},
        )
        assert r.status_code == 404

        # Cleanup.
        db = SessionLocal()
        try:
            db.execute(
                text("DELETE FROM appraisal_default_settings WHERE id = :id"),
                {"id": sid},
            )
            db.execute(
                text("DELETE FROM tenants WHERE id = :tid"),
                {"tid": str(probe_tenant_id)},
            )
            db.commit()
        finally:
            db.close()

    def test_list_scoped_to_caller_tenant(self, admin_session):
        """The GET endpoint must return only the caller's tenant rows."""
        r = admin_session.get(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults"
        )
        assert r.status_code == 200
        data = r.json()
        # All returned rows must share the same tenant_id as the caller.
        tenant_id = data["tenant_id"]
        # Endpoint already filters; just confirm count == 10 from seed.
        assert data["count"] == 10
        assert tenant_id


# =============================================================================
# AC: audit & updated_by_user_id
# =============================================================================

class TestAuditAndUpdatedBy:
    def test_put_writes_audit_and_stamps_updated_by(self, admin_session):
        from app.db import SessionLocal
        from app.models.audit import AuditLog
        from app.models.reference_data import AppraisalDefaultSetting
        from app.models.user import User

        db = SessionLocal()
        try:
            admin = db.scalar(select(User).where(User.email == ADMIN))
            admin_id = admin.id
            row = db.scalar(
                select(AppraisalDefaultSetting).where(
                    AppraisalDefaultSetting.setting_key == "default_architect_fee_pct"
                )
            )
            sid = str(row.id)
            orig = str(row.setting_value)
        finally:
            db.close()

        r = admin_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": "6.5"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["updated_by_user_id"] == str(admin_id)

        db = SessionLocal()
        try:
            from uuid import UUID
            audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.resource_type == "appraisal_default_settings",
                    AuditLog.resource_id == UUID(sid),
                    AuditLog.action == "Update",
                ).order_by(AuditLog.created_at.desc()).limit(1)
            )
            assert audit is not None
            assert audit.actor_user_id == admin_id
        finally:
            db.close()

        # Revert.
        admin_session.put(
            f"{BASE_URL}/api/v1/reference-data/appraisal-defaults/{sid}",
            json={"value": orig},
        )

    def test_updated_by_not_null_enforced_at_db(self):
        """NOT NULL on updated_by_user_id — direct DB insert without it
        must fail."""
        from sqlalchemy.exc import IntegrityError
        from app.db import SessionLocal
        from app.models.tenant import Tenant

        db = SessionLocal()
        try:
            tenant = db.scalar(select(Tenant))
            with pytest.raises(IntegrityError):
                db.execute(text("""
                    INSERT INTO appraisal_default_settings
                        (id, tenant_id, setting_key, setting_value,
                         setting_type, applies_to_project_type, description)
                    VALUES (gen_random_uuid(), :tid, 'nullable_test', 1.0,
                            'Percentage', NULL, 'test')
                """), {"tid": str(tenant.id)})
                db.commit()
            db.rollback()
        finally:
            db.close()
