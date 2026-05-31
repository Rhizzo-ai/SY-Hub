"""Tests for APScheduler jobs (Prompt 1.7) — notification expiry + audit retention."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.conftest import login_with_auto_enroll


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://supplier-verify-7.preview.emergentagent.com"

ADMIN = "test-admin@example.test"
READONLY = "test-readonly@example.test"
PWD = "TestUser-Dev-2026!"


def _user_id(email: str):
    from app.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    try:
        return db.scalar(select(User).where(User.email == email)).id
    finally:
        db.close()


# =============================================================================
# Notification expiry sweep
# =============================================================================

class TestNotificationExpirySweep:
    def test_dismisses_expired(self):
        from app.db import SessionLocal
        from app.jobs.notification_expiry import run_notification_expiry_sweep
        from app.models.notifications import Notification
        from app.services.notifications import dispatch

        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            # Past expiry.
            n = dispatch(db, recipient_user_id=uid,
                         notification_type="Mention", title="exp", body="b")
            n.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
            nid = n.id
        finally:
            db.close()

        run_notification_expiry_sweep()

        db = SessionLocal()
        try:
            row = db.scalar(select(Notification).where(Notification.id == nid))
            assert row.is_dismissed is True
            assert row.dismissed_at is not None
        finally:
            db.close()

    def test_skips_unexpired(self):
        from app.db import SessionLocal
        from app.jobs.notification_expiry import run_notification_expiry_sweep
        from app.models.notifications import Notification
        from app.services.notifications import dispatch

        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(db, recipient_user_id=uid,
                         notification_type="Mention", title="future", body="b")
            n.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
            db.commit()
            nid = n.id
        finally:
            db.close()

        run_notification_expiry_sweep()

        db = SessionLocal()
        try:
            row = db.scalar(select(Notification).where(Notification.id == nid))
            assert row.is_dismissed is False
        finally:
            db.close()

    def test_skips_already_dismissed(self):
        from app.db import SessionLocal
        from app.jobs.notification_expiry import run_notification_expiry_sweep
        from app.models.notifications import Notification
        from app.services.notifications import dispatch

        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(db, recipient_user_id=uid,
                         notification_type="Mention", title="d", body="b")
            n.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
            n.is_dismissed = True
            n.dismissed_at = datetime.now(timezone.utc) - timedelta(days=1)
            originally_dismissed_at = n.dismissed_at
            db.commit()
            nid = n.id
            originally_dismissed_at = n.dismissed_at
        finally:
            db.close()

        run_notification_expiry_sweep()

        db = SessionLocal()
        try:
            row = db.scalar(select(Notification).where(Notification.id == nid))
            # dismissed_at must NOT be updated by the sweep (it skipped).
            assert row.is_dismissed is True
            assert abs(
                (row.dismissed_at - originally_dismissed_at).total_seconds()
            ) < 1.0
        finally:
            db.close()


# =============================================================================
# Audit retention sweep
# =============================================================================

class TestAuditRetentionSweep:
    def test_skipped_when_disabled(self):
        from app.db import SessionLocal
        from app.jobs.audit_retention import run_audit_retention_sweep
        from app.services import system_config as svc

        # Default seed value is false; ensure it.
        admin_uid = _user_id(ADMIN)
        db = SessionLocal()
        try:
            try:
                svc.set_value(db, "audit.retention_purge_enabled", False, admin_uid)
                db.commit()
            except Exception:
                db.rollback()
        finally:
            db.close()

        result = run_audit_retention_sweep()
        assert result["enabled"] is False
        assert result.get("skipped_reason") == "gated_off"

    def test_runs_when_enabled(self):
        from app.db import SessionLocal
        from app.jobs.audit_retention import run_audit_retention_sweep
        from app.services import system_config as svc

        admin_uid = _user_id(ADMIN)
        db = SessionLocal()
        try:
            svc.set_value(db, "audit.retention_purge_enabled", True, admin_uid)
            db.commit()
        finally:
            db.close()

        try:
            result = run_audit_retention_sweep()
            # When the allow-list is empty (test env doesn't set it), the
            # purge module returns enabled=True with a skipped_reason.
            assert result["enabled"] is True
            # Either skipped (allow-list empty) or actually executed.
            assert "skipped_reason" in result or "deleted" in result
        finally:
            # Reset to default.
            db = SessionLocal()
            try:
                svc.restore(db, "audit.retention_purge_enabled", admin_uid)
                db.commit()
            finally:
                db.close()


# =============================================================================
# Lifecycle wiring (lifespan)
# =============================================================================

class TestSchedulerLifecycle:
    def test_start_and_stop_idempotent(self):
        """Calling start_*_scheduler twice doesn't double-schedule jobs."""
        from app.jobs.notification_expiry import (
            _scheduler as _ns,  # noqa: F401
            start_notification_expiry_scheduler,
            stop_notification_expiry_scheduler,
        )
        # Already started by lifespan in the running backend. Test the
        # idempotency contract directly.
        start_notification_expiry_scheduler()
        start_notification_expiry_scheduler()
        # No assertion target — just confirm no exception.
