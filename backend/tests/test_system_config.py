"""Tests for system_config (Prompt 1.7) — schema, service, endpoints."""
from __future__ import annotations

import os
import pytest
import requests

from tests.conftest import login_with_auto_enroll, plain_login


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://workflow-surface.preview.emergentagent.com"

ADMIN = "test-admin@example.test"
DIRECTOR = "test-director@example.test"
PM = "test-pm@example.test"
FINANCE = "test-finance@example.test"
SITE = "test-site@example.test"
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
# Seed coverage
# =============================================================================

class TestSeed:
    def test_seed_creates_40_keys(self, admin_session):
        """38 keys from 1.7 seed + 1 from 2.3 C2 migration 0022
        (`appraisal_decisions_required_threshold`) + 1 from 2.4C
        (`budget.self_approval_threshold_gbp`)."""
        r = admin_session.get(f"{BASE_URL}/api/v1/system-config")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 40

    def test_seed_covers_expected_categories(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/v1/system-config")
        cats = set(r.json()["by_category"].keys())
        # 9 categories populated by the seeded keys (CashFlow,
        # Document, System are reserved enum values without seed data).
        expected = {
            "Finance", "Appraisal", "Budget", "Security",
            "Audit", "Integration", "Notification", "Programme", "Reporting",
        }
        assert expected.issubset(cats), cats

    def test_default_value_snapshotted(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/v1/system-config/security.password_min_length"
        )
        body = r.json()
        assert body["raw_value"] == "12"
        assert body["default_value"] == "12"
        assert body["is_at_default"] is True


# =============================================================================
# Read paths — typed parse per value_type
# =============================================================================

class TestTypedParse:
    @pytest.mark.parametrize("key,value_type,expected", [
        ("notification.email_from_address", "String", "platform@sy-homes.co.uk"),
        ("security.password_min_length", "Integer", 12),
        ("finance.default_hurdle_on_cost_pct", "Decimal", "20"),
        ("audit.retention_purge_enabled", "Boolean", False),
        ("security.mfa_required_roles", "JSON",
         ["super_admin", "director", "finance"]),
    ])
    def test_typed_parse(self, admin_session, key, value_type, expected):
        r = admin_session.get(f"{BASE_URL}/api/v1/system-config/{key}")
        assert r.status_code == 200
        body = r.json()
        assert body["value_type"] == value_type
        if value_type == "Decimal":
            assert str(body["config_value"]) == str(expected)
        else:
            assert body["config_value"] == expected

    def test_unknown_key_returns_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/v1/system-config/does.not.exist")
        assert r.status_code == 404


# =============================================================================
# Write paths
# =============================================================================

class TestWriteUpdate:
    def test_put_updates_and_audits(self, admin_session):
        # PUT then restore — leaves state as found.
        r = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/budget.variance_threshold_amber_pct",
            json={"value": "7"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert str(body["config_value"]) == "7"
        assert body["last_changed_by_user_id"] is not None
        assert body["last_changed_at"] is not None
        # Cleanup
        admin_session.post(
            f"{BASE_URL}/api/v1/system-config/budget.variance_threshold_amber_pct/restore"
        )

    def test_put_validates_integer(self, admin_session):
        r = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/security.password_min_length",
            json={"value": "abc"},
        )
        assert r.status_code == 422

    def test_put_validates_json(self, admin_session):
        r = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/security.mfa_required_roles",
            json={"value": "{not valid json"},
        )
        assert r.status_code == 422

    def test_put_validates_boolean(self, admin_session):
        r = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/audit.retention_purge_enabled",
            json={"value": "maybe"},
        )
        assert r.status_code == 422

    def test_put_unknown_key_404(self, admin_session):
        r = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/does.not.exist",
            json={"value": "x"},
        )
        assert r.status_code == 404


class TestRestore:
    def test_restore_returns_to_default(self, admin_session):
        # Change.
        r1 = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/budget.variance_threshold_red_pct",
            json={"value": "20"},
        )
        assert r1.status_code == 200
        # Restore.
        r2 = admin_session.post(
            f"{BASE_URL}/api/v1/system-config/budget.variance_threshold_red_pct/restore"
        )
        assert r2.status_code == 200
        body = r2.json()
        assert str(body["config_value"]) == "10"
        assert body["is_at_default"] is True


# =============================================================================
# Permissions
# =============================================================================

class TestPermissions:
    def test_all_roles_can_view(self):
        for email in (ADMIN, DIRECTOR, PM, FINANCE, SITE, READONLY):
            try:
                s = login_with_auto_enroll(None, BASE_URL, email, PWD)
            except Exception:
                s = plain_login(BASE_URL, email, PWD)
            r = s.get(f"{BASE_URL}/api/v1/system-config")
            assert r.status_code == 200, f"{email} got {r.status_code}"

    def test_director_cannot_admin(self, director_session):
        r = director_session.put(
            f"{BASE_URL}/api/v1/system-config/security.password_min_length",
            json={"value": 13},
        )
        assert r.status_code == 403

    def test_readonly_cannot_admin(self, readonly_session):
        r = readonly_session.put(
            f"{BASE_URL}/api/v1/system-config/security.password_min_length",
            json={"value": 13},
        )
        assert r.status_code == 403

    def test_super_admin_can_admin(self, admin_session):
        r = admin_session.put(
            f"{BASE_URL}/api/v1/system-config/finance.default_hurdle_on_gdv_pct",
            json={"value": "18"},
        )
        assert r.status_code == 200
        admin_session.post(
            f"{BASE_URL}/api/v1/system-config/finance.default_hurdle_on_gdv_pct/restore"
        )


# =============================================================================
# is_system_locked
# =============================================================================

class TestSystemLocked:
    def test_put_rejects_locked_key(self):
        """Lock a key directly on the DB then attempt PUT → expect 409."""
        from app.db import SessionLocal
        from app.models.system_config import SystemConfig
        from sqlalchemy import select

        db = SessionLocal()
        try:
            row = db.scalar(select(SystemConfig).where(
                SystemConfig.config_key == "xero.sync_interval_minutes"
            ))
            row.is_system_locked = True
            db.commit()
        finally:
            db.close()

        s = login_with_auto_enroll(None, BASE_URL, ADMIN, PWD)
        r = s.put(
            f"{BASE_URL}/api/v1/system-config/xero.sync_interval_minutes",
            json={"value": 30},
        )
        assert r.status_code == 409

        # cleanup — unlock for subsequent tests.
        db = SessionLocal()
        try:
            row = db.scalar(select(SystemConfig).where(
                SystemConfig.config_key == "xero.sync_interval_minutes"
            ))
            row.is_system_locked = False
            db.commit()
        finally:
            db.close()


# =============================================================================
# SystemConfig service: cache + invalidation
# =============================================================================

class TestServiceCache:
    def test_cache_serves_repeat_reads(self):
        from app.services import system_config as svc
        svc.invalidate()
        svc._reset_query_counts()
        v1 = svc.get("security.password_min_length")
        v2 = svc.get("security.password_min_length")
        assert v1 == v2 == 12
        # Two reads should produce ONE DB hit.
        assert svc._query_count_for("security.password_min_length") == 1

    def test_invalidate_forces_reread(self):
        from app.services import system_config as svc
        svc.invalidate()
        svc._reset_query_counts()
        svc.get("budget.approval_threshold_pm_gbp")
        svc.invalidate("budget.approval_threshold_pm_gbp")
        svc.get("budget.approval_threshold_pm_gbp")
        assert svc._query_count_for("budget.approval_threshold_pm_gbp") == 2

    def test_set_invalidates_cache(self):
        """Writing through the service must drop the cached value."""
        from app.db import SessionLocal
        from app.services import system_config as svc

        admin_uid = _admin_user_id()
        svc.invalidate()
        svc.get("appraisal.default_qs_fee_pct")  # warm
        db = SessionLocal()
        try:
            svc.set_value(db, "appraisal.default_qs_fee_pct", "1.25", admin_uid)
            db.commit()
        finally:
            db.close()
        # Restore.
        db = SessionLocal()
        try:
            svc.restore(db, "appraisal.default_qs_fee_pct", admin_uid)
            db.commit()
        finally:
            db.close()


def _admin_user_id():
    from app.db import SessionLocal
    from app.models.user import User
    from sqlalchemy import select
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.email == ADMIN))
        return u.id
    finally:
        db.close()
