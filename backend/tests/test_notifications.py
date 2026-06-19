"""Tests for notifications (Prompt 1.7) — service, endpoints, grouping, retro-wires."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import requests
from sqlalchemy import select

from tests.conftest import login_with_auto_enroll, plain_login


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://sdlt-audit-fix.preview.emergentagent.com"

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


def _user_id(email: str):
    from app.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    try:
        return db.scalar(select(User).where(User.email == email)).id
    finally:
        db.close()


def _wipe_inbox(email: str):
    """Hard-delete every notification for the given user (test isolation)."""
    from app.db import SessionLocal
    from app.models.notifications import Notification
    db = SessionLocal()
    try:
        uid = db.scalar(select(__import__('app.models.user', fromlist=['User']).User).where(
            __import__('app.models.user', fromlist=['User']).User.email == email
        )).id
        db.query(Notification).filter(Notification.recipient_user_id == uid).delete()
        db.commit()
    finally:
        db.close()


# =============================================================================
# NotificationService.dispatch
# =============================================================================

class TestDispatch:
    def test_dispatch_creates_row(self):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        from app.models.notifications import Notification

        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(
                db, recipient_user_id=uid,
                notification_type="System_Announcement",
                title="Hello", body="Body content",
            )
            db.commit()
            db.refresh(n)
            assert n.id is not None
            assert n.priority == "Normal"
            assert n.is_read is False
            assert n.is_dismissed is False
            assert n.email_sent is False
            assert n.sms_sent is False
        finally:
            db.close()

    def test_dispatch_default_expires_at_30_days(self):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(
                db, recipient_user_id=uid,
                notification_type="Mention",
                title="x", body="y",
            )
            db.commit()
            db.refresh(n)
            now = datetime.now(timezone.utc)
            delta = n.expires_at - now
            # Default is 30 days; allow ±1 day for clock skew.
            assert timedelta(days=29) <= delta <= timedelta(days=31)
        finally:
            db.close()

    def test_dispatch_high_sends_email(self):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(
                db, recipient_user_id=uid,
                notification_type="Security_Alert",
                title="High alert", body="content",
                priority="High",
            )
            db.commit()
            db.refresh(n)
            assert n.email_sent is True
            assert n.email_sent_at is not None
            assert n.sms_sent is False
        finally:
            db.close()

    def test_dispatch_critical_sends_email(self):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(
                db, recipient_user_id=uid,
                notification_type="Integration_Error",
                title="Critical", body="bad",
                priority="Critical",
            )
            db.commit()
            db.refresh(n)
            assert n.email_sent is True
            assert n.sms_sent is False
        finally:
            db.close()

    def test_dispatch_normal_no_email(self):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(
                db, recipient_user_id=uid,
                notification_type="Mention",
                title="t", body="b",
                priority="Normal",
            )
            db.commit()
            db.refresh(n)
            assert n.email_sent is False
            assert n.sms_sent is False
        finally:
            db.close()

    def test_dispatch_records_audit(self):
        from app.db import SessionLocal
        from app.models.audit import AuditLog
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(
                db, recipient_user_id=uid,
                notification_type="Task_Overdue",
                title="t", body="b",
            )
            db.commit()
            audit = db.scalar(
                select(AuditLog)
                .where(AuditLog.resource_type == "notifications",
                       AuditLog.resource_id == n.id,
                       AuditLog.action == "Create")
            )
            assert audit is not None
        finally:
            db.close()

    def test_dispatch_invalid_type_raises(self):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            with pytest.raises(ValueError):
                dispatch(
                    db, recipient_user_id=uid,
                    notification_type="NotARealType",
                    title="t", body="b",
                )
        finally:
            db.close()


# =============================================================================
# Inbox endpoints
# =============================================================================

class TestInbox:
    def test_inbox_own_only(self, readonly_session, director_session):
        """User A cannot see user B's notifications."""
        # Dispatch a uniquely-titled notification to readonly only.
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        title = f"isolated-{uuid4()}"
        db = SessionLocal()
        try:
            dispatch(db, recipient_user_id=uid,
                     notification_type="Mention", title=title, body="b")
            db.commit()
        finally:
            db.close()

        r1 = readonly_session.get(f"{BASE_URL}/api/v1/notifications")
        assert r1.status_code == 200
        titles_ro = {i["title"] for i in r1.json()["items"]}
        assert title in titles_ro

        r2 = director_session.get(f"{BASE_URL}/api/v1/notifications")
        assert r2.status_code == 200
        titles_dir = {i["title"] for i in r2.json()["items"]}
        assert title not in titles_dir

    def test_inbox_filter_by_type(self, readonly_session):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            dispatch(db, recipient_user_id=uid, notification_type="Mention",
                     title=f"m-{uuid4()}", body="x")
            dispatch(db, recipient_user_id=uid, notification_type="Task_Overdue",
                     title=f"t-{uuid4()}", body="x")
            db.commit()
        finally:
            db.close()
        r = readonly_session.get(
            f"{BASE_URL}/api/v1/notifications", params={"type": "Mention"},
        )
        assert r.status_code == 200
        types = {i["notification_type"] for i in r.json()["items"]}
        assert types == {"Mention"} or len(types) == 0 or types == set()
        for i in r.json()["items"]:
            assert i["notification_type"] == "Mention"

    def test_inbox_filter_by_read(self, readonly_session):
        r = readonly_session.get(
            f"{BASE_URL}/api/v1/notifications", params={"is_read": "false"},
        )
        assert r.status_code == 200
        for i in r.json()["items"]:
            assert i["is_read"] is False

    def test_unread_count_endpoint(self, readonly_session):
        r = readonly_session.get(f"{BASE_URL}/api/v1/notifications/unread-count")
        assert r.status_code == 200
        assert isinstance(r.json()["count"], int)


# =============================================================================
# Lazy grouping
# =============================================================================

class TestGrouping:
    def test_groups_three_or_more_same_type_same_window(self):
        from app.services.notification_grouping import group_for_panel
        from app.models.notifications import Notification

        # Build 4 fake Mention rows in same hour bucket.
        now = datetime.now(timezone.utc).replace(minute=10, second=0, microsecond=0)
        rows = []
        for i in range(4):
            n = Notification(
                id=uuid4(), recipient_user_id=uuid4(),
                notification_type="Mention", priority="Normal",
                title=f"m{i}", body="b",
                is_read=False, is_dismissed=False,
                email_sent=False, sms_sent=False,
                created_at=now + timedelta(minutes=i),
            )
            rows.append(n)
        out = group_for_panel(rows, threshold=3, window_minutes=60)
        assert len(out) == 1
        assert out[0]["kind"] == "group"
        assert out[0]["count"] == 4

    def test_does_not_group_below_threshold(self):
        from app.services.notification_grouping import group_for_panel
        from app.models.notifications import Notification

        now = datetime.now(timezone.utc).replace(minute=10, second=0, microsecond=0)
        rows = []
        for i in range(2):
            n = Notification(
                id=uuid4(), recipient_user_id=uuid4(),
                notification_type="Mention", priority="Normal",
                title=f"m{i}", body="b",
                is_read=False, is_dismissed=False,
                email_sent=False, sms_sent=False,
                created_at=now + timedelta(minutes=i),
            )
            rows.append(n)
        out = group_for_panel(rows, threshold=3, window_minutes=60)
        assert len(out) == 2
        assert all(e["kind"] == "single" for e in out)

    def test_does_not_group_across_window(self):
        from app.services.notification_grouping import group_for_panel
        from app.models.notifications import Notification

        # 2 in bucket A + 2 in bucket B → no groups (each bucket below thresh).
        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        rows = []
        for i in range(2):
            rows.append(Notification(
                id=uuid4(), recipient_user_id=uuid4(),
                notification_type="Mention", priority="Normal",
                title="x", body="b",
                is_read=False, is_dismissed=False,
                email_sent=False, sms_sent=False,
                created_at=base + timedelta(minutes=i),
            ))
        for i in range(2):
            rows.append(Notification(
                id=uuid4(), recipient_user_id=uuid4(),
                notification_type="Mention", priority="Normal",
                title="x", body="b",
                is_read=False, is_dismissed=False,
                email_sent=False, sms_sent=False,
                created_at=base + timedelta(hours=2, minutes=i),
            ))
        out = group_for_panel(rows, threshold=3, window_minutes=60)
        assert all(e["kind"] == "single" for e in out)
        assert len(out) == 4


# =============================================================================
# PATCH read / dismiss
# =============================================================================

class TestReadDismiss:
    def test_patch_read(self, readonly_session):
        # Create a fresh notification, then mark read.
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(db, recipient_user_id=uid,
                         notification_type="Mention", title=f"t-{uuid4()}", body="b")
            db.commit()
            nid = str(n.id)
        finally:
            db.close()
        r = readonly_session.patch(f"{BASE_URL}/api/v1/notifications/{nid}/read")
        assert r.status_code == 200
        assert r.json()["is_read"] is True
        assert r.json()["read_at"] is not None

    def test_patch_dismiss(self, readonly_session):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            n = dispatch(db, recipient_user_id=uid,
                         notification_type="Mention", title=f"t-{uuid4()}", body="b")
            db.commit()
            nid = str(n.id)
        finally:
            db.close()
        r = readonly_session.patch(f"{BASE_URL}/api/v1/notifications/{nid}/dismiss")
        assert r.status_code == 200
        assert r.json()["is_dismissed"] is True

    def test_patch_others_notification_403(self, readonly_session):
        # Create a notification belonging to director, attempt PATCH as readonly.
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid_dir = _user_id(DIRECTOR)
        db = SessionLocal()
        try:
            n = dispatch(db, recipient_user_id=uid_dir,
                         notification_type="Mention", title=f"x-{uuid4()}", body="b")
            db.commit()
            nid = str(n.id)
        finally:
            db.close()
        r = readonly_session.patch(f"{BASE_URL}/api/v1/notifications/{nid}/read")
        assert r.status_code == 403

    def test_mark_all_read(self, readonly_session):
        from app.db import SessionLocal
        from app.services.notifications import dispatch
        uid = _user_id(READONLY)
        db = SessionLocal()
        try:
            for _ in range(3):
                dispatch(db, recipient_user_id=uid,
                         notification_type="Mention", title=f"x-{uuid4()}", body="b")
            db.commit()
        finally:
            db.close()
        r = readonly_session.post(f"{BASE_URL}/api/v1/notifications/mark-all-read")
        assert r.status_code == 200
        assert r.json()["rows_updated"] >= 3
        # Now unread-count should be 0 for this user.
        r2 = readonly_session.get(f"{BASE_URL}/api/v1/notifications/unread-count")
        assert r2.json()["count"] == 0


# =============================================================================
# ON DELETE CASCADE
# =============================================================================

class TestCascade:
    def test_user_delete_cascades(self):
        from app.db import SessionLocal
        from app.models.notifications import Notification
        from app.models.user import User
        from app.services.notifications import dispatch
        from app.auth.passwords import hash_password
        from app.models.tenant import Tenant
        from datetime import datetime as _dt, timezone as _tz

        db = SessionLocal()
        try:
            tenant = db.scalar(select(Tenant))
            now = _dt.now(_tz.utc)
            tmp_user = User(
                tenant_id=tenant.id,
                email=f"cascade-{uuid4()}@example.test",
                email_verified=True,
                email_verified_at=now,
                password_hash=hash_password("Cascade-Test-2026!"),
                password_algorithm="argon2id",
                password_changed_at=now,
                password_history=[],
                first_name="Cascade", last_name="Tester",
                user_type="Internal", status="Active",
            )
            db.add(tmp_user)
            db.flush()

            n = dispatch(db, recipient_user_id=tmp_user.id,
                         notification_type="Mention", title="t", body="b")
            db.commit()
            nid = n.id

            db.delete(tmp_user)
            db.commit()

            still_exists = db.scalar(
                select(Notification).where(Notification.id == nid)
            )
            assert still_exists is None
        finally:
            db.close()



# =============================================================================
# Bell polling — rate limiter must NOT trip on /unread-count
# =============================================================================

class TestPolling:
    def test_polling_does_not_trip_rate_limiter(self, readonly_session):
        """Simulate the bell's 30s polling cadence at full speed: 60
        consecutive calls in tight succession (~= 30 minutes of real
        polling). All must return 200; none should ever return 429.

        This is the contract documented in `backend/README.md` §
        'Rate limiting and the bell endpoint' and in the route docstring
        `app/routers/notifications.py::unread_count`.
        """
        for i in range(60):
            r = readonly_session.get(f"{BASE_URL}/api/v1/notifications/unread-count")
            assert r.status_code == 200, (
                f"poll #{i} returned {r.status_code} — global rate-limit "
                f"middleware may have been added without exempting "
                f"/api/v1/notifications/unread-count. See README §"
                f"'Rate limiting and the bell endpoint'."
            )
            assert "count" in r.json()

    def test_unread_count_no_limits_registered(self):
        """Hard guard: the rate-limit module's LIMITS dict must NOT carry
        an entry for the bell. If someone adds one, this test will
        force them to (a) confirm it's intentional, (b) update the
        README, and (c) add an exemption fixture.
        """
        from app.services.rate_limit import LIMITS
        bell_keys = [k for k in LIMITS.keys() if "unread" in k or "notification" in k]
        assert bell_keys == [], (
            f"Rate-limit LIMITS now contains bell-related keys {bell_keys}. "
            f"If this is intentional, update tests/test_notifications.py and "
            f"backend/README.md § 'Rate limiting and the bell endpoint'."
        )
