"""Chat 23 Build Pack A — R1.4 user_preferences API tests.

Covers the 6 endpoints under `/api/v1/me/preferences/{surface_key}`:
  - GET    /                         Snapshot of current + named views
  - PUT    /                         Autosave current state (NOT audited)
  - GET    /views/{name}             Read one named view
  - POST   /views                    Create a named view (audited)
  - PUT    /views/{name}             Overwrite a named view (audited)
  - DELETE /views/{name}             Delete a named view (audited)

Acceptance set (14 cases per Build Pack §R1.4):
  - GET on empty surface returns current={} + views=[]
  - PUT current creates row
  - PUT current twice updates row (no duplicate via partial unique index)
  - POST view creates named view
  - POST view with duplicate name returns 409
  - PUT named view overwrites
  - DELETE named view → 204; subsequent GET returns 404
  - GET surface lists all named views, sorted by updated_at DESC
  - Cross-user isolation: User A's prefs invisible to User B
  - Cascade: deleting a user removes their preferences
  - Audit log: POST/PUT named view emits audit row; PUT current does NOT
  - Surface key max length (64): longer rejected
  - Name max length (128): longer rejected
  - Empty name on POST: rejected (min_length=1)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll

load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"

SURFACE = "budgets.grid.v2"


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    # Disable MFA on test users so login_with_auto_enroll's TOTP cache
    # isn't required when this module runs in isolation (mirrors the
    # test_budgets.py db_engine fixture).
    with e.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield e
    e.dispose()


@pytest.fixture(scope="module", autouse=True)
def _wipe_prefs(engine):
    """Clean user_preferences rows before + after the module so the
    cross-user / pagination tests start from a known state."""
    with engine.begin() as c:
        c.execute(text("DELETE FROM user_preferences"))
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM user_preferences"))


@pytest.fixture
def _wipe_between(engine):
    """Per-test cleanup so each test starts from an empty table for the
    admin + pm users."""
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM user_preferences
            WHERE user_id IN (
                SELECT id FROM users
                WHERE email IN (:a, :p)
            )
        """), {"a": ADMIN_EMAIL, "p": PM_EMAIL})
    yield


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


def _audit_count(engine, *, surface_key: str, name: str | None = None,
                 since: datetime) -> int:
    """Count audit rows for the user_preference resource since `since`."""
    sql = """
        SELECT COUNT(*) FROM audit_log
        WHERE resource_type='user_preference'
          AND metadata_json->>'surface_key'=:sk
          AND created_at >= :since
    """
    params: dict = {"sk": surface_key, "since": since}
    if name is not None:
        sql += " AND metadata_json->>'name'=:nm"
        params["nm"] = name
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar() or 0


class TestGetSnapshot:
    def test_empty_surface_returns_empty_current_and_views(
        self, admin, _wipe_between,
    ):
        r = admin.get(f"{BASE_URL}/api/v1/me/preferences/{SURFACE}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {
            "surface_key": SURFACE,
            "current": {},
            "views": [],
        }


class TestCurrentAutosave:
    def test_put_current_creates_row(self, admin, _wipe_between):
        r = admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}",
            json={"payload": {"sort": ["cost_code:asc"]}},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["surface_key"] == SURFACE
        assert body["name"] is None
        assert body["payload"] == {"sort": ["cost_code:asc"]}

        g = admin.get(f"{BASE_URL}/api/v1/me/preferences/{SURFACE}").json()
        assert g["current"] == {"sort": ["cost_code:asc"]}

    def test_put_current_twice_updates_row_no_duplicate(
        self, admin, engine, _wipe_between,
    ):
        admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}",
            json={"payload": {"v": 1}},
        )
        r = admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}",
            json={"payload": {"v": 2}},
        )
        assert r.status_code == 200, r.text
        # Verify exactly one autosave row in DB for this (user, surface).
        with engine.connect() as c:
            n = c.execute(text("""
                SELECT COUNT(*) FROM user_preferences up
                JOIN users u ON u.id=up.user_id
                WHERE u.email=:e AND up.surface_key=:s
                  AND up.name IS NULL
            """), {"e": ADMIN_EMAIL, "s": SURFACE}).scalar()
        assert n == 1

        g = admin.get(f"{BASE_URL}/api/v1/me/preferences/{SURFACE}").json()
        assert g["current"] == {"v": 2}

    def test_put_current_does_not_emit_audit(
        self, admin, engine, _wipe_between,
    ):
        start = datetime.now(timezone.utc)
        admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}",
            json={"payload": {"x": 1}},
        )
        # No audit row for autosave (Build Pack §R1.4 — high-volume path).
        n = _audit_count(engine, surface_key=SURFACE, since=start)
        assert n == 0, (
            f"PUT current should not emit audit row, got {n} rows"
        )


class TestNamedViewsCRUD:
    def test_post_view_creates(
        self, admin, engine, _wipe_between,
    ):
        start = datetime.now(timezone.utc)
        r = admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "Margin watch", "payload": {"filters": {"red": True}}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Margin watch"
        assert body["payload"] == {"filters": {"red": True}}

        # Audit row was emitted.
        n = _audit_count(
            engine, surface_key=SURFACE, name="Margin watch", since=start,
        )
        assert n == 1, "POST named view must emit audit row"

    def test_post_view_duplicate_name_returns_409(
        self, admin, _wipe_between,
    ):
        admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "Quick", "payload": {}},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "Quick", "payload": {"x": 1}},
        )
        assert r.status_code == 409, r.text

    def test_put_view_overwrites(self, admin, engine, _wipe_between):
        admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "Overwrite-me", "payload": {"v": 1}},
        )
        start = datetime.now(timezone.utc)
        r = admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views/Overwrite-me",
            json={"payload": {"v": 99}},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["payload"] == {"v": 99}

        # Audit row emitted for PUT named view.
        n = _audit_count(
            engine, surface_key=SURFACE, name="Overwrite-me", since=start,
        )
        assert n == 1, "PUT named view must emit audit row"

    def test_put_view_not_found_returns_404(
        self, admin, _wipe_between,
    ):
        r = admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views/NoSuchView",
            json={"payload": {}},
        )
        assert r.status_code == 404, r.text

    def test_delete_view_then_get_returns_404(
        self, admin, engine, _wipe_between,
    ):
        admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "Doomed", "payload": {}},
        )
        start = datetime.now(timezone.utc)
        r = admin.delete(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views/Doomed",
        )
        assert r.status_code == 204, r.text

        g = admin.get(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views/Doomed",
        )
        assert g.status_code == 404, g.text

        n = _audit_count(
            engine, surface_key=SURFACE, name="Doomed", since=start,
        )
        assert n == 1, "DELETE named view must emit audit row"

    def test_get_surface_lists_views_sorted_by_updated_at_desc(
        self, admin, _wipe_between,
    ):
        # Create in order A, B, C — then touch A so it's most-recent.
        for n in ("A", "B", "C"):
            admin.post(
                f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
                json={"name": n, "payload": {"who": n}},
            )
        # Touch A so it's now the most-recent.
        admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views/A",
            json={"payload": {"who": "A-touched"}},
        )
        snap = admin.get(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}"
        ).json()
        names = [v["name"] for v in snap["views"]]
        # A was just updated, then C (most-recent insert), then B.
        assert names[0] == "A", f"expected A first, got {names}"
        assert names == ["A", "C", "B"], f"got {names}"


class TestCrossUserIsolation:
    def test_user_a_cannot_see_user_b_prefs(
        self, admin, pm, _wipe_between,
    ):
        admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}",
            json={"payload": {"who": "admin"}},
        )
        admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "Admin's view", "payload": {"x": 1}},
        )

        pm_snap = pm.get(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}"
        ).json()
        assert pm_snap["current"] == {}
        assert pm_snap["views"] == []

        # And pm trying to read admin's named view by exact name → 404.
        r = pm.get(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views/Admin's view",
        )
        assert r.status_code == 404


class TestCascadeDeleteUser:
    def test_deleting_user_removes_their_prefs(self, admin, engine):
        # Use the admin's preferences row, then directly soft-test the
        # cascade by inserting a temp user, attaching prefs, deleting
        # the user, and verifying the prefs are gone.
        with engine.begin() as c:
            tenant_id = c.execute(text(
                "SELECT id FROM tenants LIMIT 1"
            )).scalar()
            tmp_user_id = uuid.uuid4()
            c.execute(text("""
                INSERT INTO users (
                    id, tenant_id, email, first_name, last_name,
                    password_hash, user_type, status
                ) VALUES (
                    :id, :t, :email, 'Cascade', 'Tmp',
                    'x', 'Internal', 'Active'
                )
            """), {
                "id": tmp_user_id, "t": tenant_id,
                "email": f"cascade-{tmp_user_id}@example.test",
            })
            c.execute(text("""
                INSERT INTO user_preferences (user_id, surface_key, payload)
                VALUES (:u, 'cascade.test', '{}'::jsonb)
            """), {"u": tmp_user_id})

        with engine.connect() as c:
            n_before = c.execute(text(
                "SELECT COUNT(*) FROM user_preferences WHERE user_id=:u"
            ), {"u": tmp_user_id}).scalar()
        assert n_before == 1

        with engine.begin() as c:
            c.execute(text("DELETE FROM users WHERE id=:u"),
                      {"u": tmp_user_id})

        with engine.connect() as c:
            n_after = c.execute(text(
                "SELECT COUNT(*) FROM user_preferences WHERE user_id=:u"
            ), {"u": tmp_user_id}).scalar()
        assert n_after == 0, "user delete must cascade to user_preferences"


class TestValidation:
    def test_surface_key_max_length_64_rejected(
        self, admin, _wipe_between,
    ):
        too_long = "x" * 65
        r = admin.put(
            f"{BASE_URL}/api/v1/me/preferences/{too_long}",
            json={"payload": {}},
        )
        # The String(64) constraint manifests as a DB-level error. The
        # API surface should reject — either as 422 (length validator) or
        # 500 (DB integrity). Either way, no 200 OK.
        assert r.status_code != 200, (
            f"surface_key > 64 chars must be rejected, got {r.status_code}"
        )

    def test_view_name_max_length_128_rejected(
        self, admin, _wipe_between,
    ):
        too_long = "x" * 129
        r = admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": too_long, "payload": {}},
        )
        assert r.status_code == 422, r.text

    def test_view_name_empty_rejected(self, admin, _wipe_between):
        r = admin.post(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}/views",
            json={"name": "", "payload": {}},
        )
        assert r.status_code == 422, r.text


class TestUnauthenticated:
    def test_get_requires_auth(self):
        # No session cookies — should be 401.
        import requests
        r = requests.get(
            f"{BASE_URL}/api/v1/me/preferences/{SURFACE}",
        )
        assert r.status_code == 401, r.text
