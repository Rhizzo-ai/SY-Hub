"""Backend tests for sessions + refresh tokens + login history + password reset.

Prompt 1.3 stage 1b.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://construction-command-5.preview.emergentagent.com"
)
TEST_PASSWORD = "TestUser-Dev-2026!"
READONLY_EMAIL = "test-readonly@example.test"
ADMIN_EMAIL = "test-admin@example.test"

load_dotenv("/app/backend/.env")
engine = create_engine(os.environ["DATABASE_URL"])


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login_readonly(api_client, remember_me=False):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": READONLY_EMAIL, "password": TEST_PASSWORD, "remember_me": remember_me},
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestLoginIssuesSession:
    def test_login_returns_access_and_refresh_tokens(self, api_client):
        d = _login_readonly(api_client)
        assert d["access_token"]
        assert d["refresh_token"]
        assert d["token_type"] == "bearer"
        assert d["access_token_expires_in"] == 900  # 15 min

    def test_session_row_created_with_hashed_refresh(self, api_client):
        d = _login_readonly(api_client)
        refresh_hash = hashlib.sha256(d["refresh_token"].encode()).hexdigest()
        with engine.connect() as c:
            row = c.execute(
                text("SELECT refresh_token_hash, device_name, remember_me FROM user_sessions "
                     "WHERE refresh_token_hash=:h"), {"h": refresh_hash},
            ).first()
        assert row is not None
        assert row[0] == refresh_hash
        assert row[1]  # device_name populated from UA
        assert row[2] is False

    def test_remember_me_extends_expiry_to_90d(self, api_client):
        d = _login_readonly(api_client, remember_me=True)
        refresh_hash = hashlib.sha256(d["refresh_token"].encode()).hexdigest()
        with engine.connect() as c:
            row = c.execute(
                text("SELECT expires_at, remember_me FROM user_sessions WHERE refresh_token_hash=:h"),
                {"h": refresh_hash},
            ).first()
        assert row[1] is True
        days = (row[0] - datetime.now(timezone.utc)).days
        assert 88 <= days <= 90


class TestRefreshRotation:
    def test_refresh_rotates_token(self, api_client):
        d = _login_readonly(api_client)
        r = api_client.post(f"{BASE_URL}/api/auth/refresh",
                            json={"refresh_token": d["refresh_token"]})
        assert r.status_code == 200
        d2 = r.json()
        assert d2["access_token"]
        assert d2["refresh_token"]
        assert d2["refresh_token"] != d["refresh_token"]

    def test_old_refresh_after_rotate_is_replay(self, api_client):
        d = _login_readonly(api_client)
        # First rotate
        r = api_client.post(f"{BASE_URL}/api/auth/refresh",
                            json={"refresh_token": d["refresh_token"]})
        assert r.status_code == 200
        new_access = r.json()["access_token"]
        # Replay old refresh → should revoke ALL sessions
        r2 = api_client.post(f"{BASE_URL}/api/auth/refresh",
                             json={"refresh_token": d["refresh_token"]})
        assert r2.status_code == 401
        assert "replay" in r2.json()["detail"].lower()
        # The new access should ALSO now fail (session revoked)
        r3 = api_client.get(f"{BASE_URL}/api/auth/me",
                            headers={"Authorization": f"Bearer {new_access}"})
        assert r3.status_code == 401

    def test_invalid_refresh_returns_401(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/auth/refresh",
                            json={"refresh_token": "not-a-real-token-xxxxxxxxxxxxxx"})
        assert r.status_code == 401


class TestLogoutRevokesSession:
    def test_logout_clears_cookies_and_revokes(self, api_client):
        d = _login_readonly(api_client)
        refresh_hash = hashlib.sha256(d["refresh_token"].encode()).hexdigest()
        s = requests.Session()
        s.cookies.set("refresh_token", d["refresh_token"])
        r = s.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 204
        with engine.connect() as c:
            row = c.execute(
                text("SELECT revoked_reason FROM user_sessions WHERE refresh_token_hash=:h"),
                {"h": refresh_hash},
            ).first()
        assert row is not None
        assert row[0] == "Logout"


class TestPasswordChangeRevokesOthers:
    def test_password_change_revokes_other_sessions(self, api_client):
        # Session A
        a = _login_readonly(api_client)
        # Session B (fresh login)
        b = _login_readonly(api_client)
        assert a["refresh_token"] != b["refresh_token"]

        # Change password from session B
        new_pw = "NewPwd-Change-Revokes-2026!"
        r = api_client.post(f"{BASE_URL}/api/auth/password/change",
                            json={"current_password": TEST_PASSWORD, "new_password": new_pw},
                            headers={"Authorization": f"Bearer {b['access_token']}"})
        assert r.status_code == 204

        # Session A is now revoked; /me should 401
        r2 = api_client.get(f"{BASE_URL}/api/auth/me",
                            headers={"Authorization": f"Bearer {a['access_token']}"})
        assert r2.status_code == 401

        # Session B survives (current session kept alive per spec)
        r3 = api_client.get(f"{BASE_URL}/api/auth/me",
                            headers={"Authorization": f"Bearer {b['access_token']}"})
        assert r3.status_code == 200

        # Restore original password via DB
        with engine.begin() as c:
            from app.auth.passwords import hash_password
            c.execute(
                text("UPDATE users SET password_hash=:h, password_history='[]'::jsonb "
                     "WHERE email=:em"),
                {"h": hash_password(TEST_PASSWORD), "em": READONLY_EMAIL},
            )


class TestLoginHistoryRecords:
    def test_login_failed_creates_row_without_user_id(self, api_client):
        api_client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": "nobody-xyz-123@example.test", "password": "x"})
        with engine.connect() as c:
            r = c.execute(
                text("SELECT user_id, failure_reason, event_type FROM user_login_history "
                     "WHERE email_attempted='nobody-xyz-123@example.test' "
                     "ORDER BY created_at DESC LIMIT 1"),
            ).first()
        assert r is not None
        assert r[0] is None
        assert r[1] == "Unknown_Email"
        assert r[2] == "Login_Failed"

    def test_login_success_creates_row(self, api_client):
        before = _count_history(READONLY_EMAIL, "Login_Success")
        _login_readonly(api_client)
        after = _count_history(READONLY_EMAIL, "Login_Success")
        assert after == before + 1

    def test_login_history_append_only(self):
        with engine.begin() as c:
            # UPDATE should raise
            with pytest.raises(Exception) as exc:
                c.execute(text("UPDATE user_login_history SET event_type='Login_Failed' "
                               "WHERE id = (SELECT id FROM user_login_history LIMIT 1)"))
            assert "append-only" in str(exc.value).lower()
        with engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text("DELETE FROM user_login_history "
                               "WHERE id = (SELECT id FROM user_login_history LIMIT 1)"))
            assert "append-only" in str(exc.value).lower()


def _count_history(email: str, event_type: str) -> int:
    with engine.connect() as c:
        row = c.execute(
            text("SELECT COUNT(*) FROM user_login_history "
                 "WHERE email_attempted=:em AND event_type=:et"),
            {"em": email, "et": event_type},
        ).first()
    return int(row[0])


class TestSessionEndpoints:
    def test_list_my_sessions_marks_current(self, api_client):
        d = _login_readonly(api_client)
        r = api_client.get(f"{BASE_URL}/api/users/me/sessions",
                           headers={"Authorization": f"Bearer {d['access_token']}"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        current = [r for r in rows if r["is_current"]]
        assert len(current) == 1

    def test_revoke_other_session(self, api_client):
        a = _login_readonly(api_client)
        b = _login_readonly(api_client)
        # List from B
        rows = api_client.get(
            f"{BASE_URL}/api/users/me/sessions",
            headers={"Authorization": f"Bearer {b['access_token']}"},
        ).json()
        a_session = [r for r in rows if not r["is_current"] and r["revoked_at"] is None]
        assert a_session, "Expected a session belonging to login A"
        target = a_session[0]
        r = api_client.post(
            f"{BASE_URL}/api/users/me/sessions/{target['id']}/revoke",
            headers={"Authorization": f"Bearer {b['access_token']}"},
        )
        assert r.status_code == 204
        # A token is now invalid
        r2 = api_client.get(f"{BASE_URL}/api/auth/me",
                            headers={"Authorization": f"Bearer {a['access_token']}"})
        assert r2.status_code == 401

    def test_revoke_others_keeps_current(self, api_client):
        a = _login_readonly(api_client)
        b = _login_readonly(api_client)
        # From B, revoke others
        r = api_client.post(f"{BASE_URL}/api/users/me/sessions/revoke-others",
                            headers={"Authorization": f"Bearer {b['access_token']}"})
        assert r.status_code == 204
        # Current (B) still works
        assert api_client.get(f"{BASE_URL}/api/auth/me",
                              headers={"Authorization": f"Bearer {b['access_token']}"}).status_code == 200
        # Older (A) is dead
        assert api_client.get(f"{BASE_URL}/api/auth/me",
                              headers={"Authorization": f"Bearer {a['access_token']}"}).status_code == 401

    def test_admin_revoke_all(self, api_client):
        # Ensure readonly has at least one active session
        _login_readonly(api_client)
        admin = login_with_auto_enroll(api_client, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)
        # Find readonly id
        lst = api_client.get(f"{BASE_URL}/api/users",
                             headers={"Authorization": f"Bearer {admin}"}).json()
        ro = next(u for u in lst["items"] if u["email"] == READONLY_EMAIL)
        r = api_client.post(f"{BASE_URL}/api/users/{ro['id']}/sessions/revoke-all",
                            headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 204
        # Confirm all readonly sessions now revoked
        sess = api_client.get(f"{BASE_URL}/api/users/{ro['id']}/sessions",
                              headers={"Authorization": f"Bearer {admin}"}).json()
        active = [s for s in sess if s["revoked_at"] is None]
        assert active == []


class TestLoginHistoryAdminView:
    def test_admin_can_list_history(self, api_client):
        admin = login_with_auto_enroll(api_client, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)
        lst = api_client.get(f"{BASE_URL}/api/users",
                             headers={"Authorization": f"Bearer {admin}"}).json()
        ro = next(u for u in lst["items"] if u["email"] == READONLY_EMAIL)
        r = api_client.get(
            f"{BASE_URL}/api/users/{ro['id']}/login-history?page_size=20",
            headers={"Authorization": f"Bearer {admin}"},
        )
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "total" in j
        assert j["total"] >= 1

    def test_non_admin_forbidden(self, api_client):
        d = _login_readonly(api_client)
        lst = api_client.get(f"{BASE_URL}/api/users",
                             headers={"Authorization": f"Bearer {d['access_token']}"})
        # Readonly may or may not be able to GET /users — what matters is the
        # history endpoint itself requires users.admin.
        # Use own id regardless.
        me = api_client.get(f"{BASE_URL}/api/auth/me",
                            headers={"Authorization": f"Bearer {d['access_token']}"}).json()
        r = api_client.get(f"{BASE_URL}/api/users/{me['id']}/login-history",
                           headers={"Authorization": f"Bearer {d['access_token']}"})
        assert r.status_code == 403

    def test_csv_export_downloads(self, api_client):
        admin = login_with_auto_enroll(api_client, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)
        lst = api_client.get(f"{BASE_URL}/api/users",
                             headers={"Authorization": f"Bearer {admin}"}).json()
        ro = next(u for u in lst["items"] if u["email"] == READONLY_EMAIL)
        r = api_client.get(f"{BASE_URL}/api/users/{ro['id']}/login-history.csv",
                           headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "timestamp_utc,event_type" in r.text


class TestPasswordResetSelfService:
    def test_request_returns_200_for_unknown_email(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/auth/password-reset/request",
                            json={"email": "nobody@example.test"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_request_returns_200_for_known_email(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/auth/password-reset/request",
                            json={"email": READONLY_EMAIL})
        assert r.status_code == 200

    def test_complete_valid_token_resets_password_and_revokes_sessions(self, api_client):
        # Log in to have a live session
        session_tok = _login_readonly(api_client)["access_token"]
        # Seed a known reset token via DB
        raw = secrets.token_urlsafe(32)
        th = hashlib.sha256(raw.encode()).hexdigest()
        with engine.begin() as c:
            c.execute(
                text("UPDATE users SET password_reset_token_hash=:h, "
                     "password_reset_expires_at=:exp WHERE email=:em"),
                {"h": th, "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                 "em": READONLY_EMAIL},
            )
        new_pw = "Reset-Complete-TestPw-2026!"
        r = api_client.post(f"{BASE_URL}/api/auth/password-reset/complete",
                            json={"token": raw, "new_password": new_pw})
        assert r.status_code == 204
        # Existing session dead
        r2 = api_client.get(f"{BASE_URL}/api/auth/me",
                            headers={"Authorization": f"Bearer {session_tok}"})
        assert r2.status_code == 401
        # New pw works
        r3 = api_client.post(f"{BASE_URL}/api/auth/login",
                             json={"email": READONLY_EMAIL, "password": new_pw})
        assert r3.status_code == 200
        # Restore for other tests
        from app.auth.passwords import hash_password
        with engine.begin() as c:
            c.execute(
                text("UPDATE users SET password_hash=:h, password_history='[]'::jsonb "
                     "WHERE email=:em"),
                {"h": hash_password(TEST_PASSWORD), "em": READONLY_EMAIL},
            )

    def test_expired_token_rejected(self, api_client):
        raw = secrets.token_urlsafe(32)
        th = hashlib.sha256(raw.encode()).hexdigest()
        with engine.begin() as c:
            c.execute(
                text("UPDATE users SET password_reset_token_hash=:h, "
                     "password_reset_expires_at=:exp WHERE email=:em"),
                {"h": th, "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
                 "em": READONLY_EMAIL},
            )
        r = api_client.post(f"{BASE_URL}/api/auth/password-reset/complete",
                            json={"token": raw, "new_password": "Valid-NewPw-2026!"})
        assert r.status_code == 400
        assert "expired" in r.json()["detail"].lower()

    def test_used_token_rejected_second_time(self, api_client):
        raw = secrets.token_urlsafe(32)
        th = hashlib.sha256(raw.encode()).hexdigest()
        with engine.begin() as c:
            c.execute(
                text("UPDATE users SET password_reset_token_hash=:h, "
                     "password_reset_expires_at=:exp WHERE email=:em"),
                {"h": th, "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                 "em": READONLY_EMAIL},
            )
        r = api_client.post(f"{BASE_URL}/api/auth/password-reset/complete",
                            json={"token": raw, "new_password": "Valid-NewPw-2026-X!"})
        assert r.status_code == 204
        # Second attempt
        r2 = api_client.post(f"{BASE_URL}/api/auth/password-reset/complete",
                             json={"token": raw, "new_password": "Different-NewPw-2026-Y!"})
        assert r2.status_code == 400
        # Restore
        from app.auth.passwords import hash_password
        with engine.begin() as c:
            c.execute(
                text("UPDATE users SET password_hash=:h, password_history='[]'::jsonb "
                     "WHERE email=:em"),
                {"h": hash_password(TEST_PASSWORD), "em": READONLY_EMAIL},
            )

    def test_complete_weak_password_rejected(self, api_client):
        raw = secrets.token_urlsafe(32)
        th = hashlib.sha256(raw.encode()).hexdigest()
        with engine.begin() as c:
            c.execute(
                text("UPDATE users SET password_reset_token_hash=:h, "
                     "password_reset_expires_at=:exp WHERE email=:em"),
                {"h": th, "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                 "em": READONLY_EMAIL},
            )
        r = api_client.post(f"{BASE_URL}/api/auth/password-reset/complete",
                            json={"token": raw, "new_password": "too-weak"})
        assert r.status_code == 422


class TestEmailSendLog:
    def test_password_reset_request_logs_email(self, api_client):
        api_client.post(f"{BASE_URL}/api/auth/password-reset/request",
                        json={"email": READONLY_EMAIL})
        with engine.connect() as c:
            row = c.execute(
                text("SELECT template_id, status FROM email_send_log "
                     "WHERE to_address=:em AND template_id='password_reset_email' "
                     "ORDER BY created_at DESC LIMIT 1"),
                {"em": READONLY_EMAIL},
            ).first()
        assert row is not None
        assert row[0] == "password_reset_email"
        assert row[1] == "dev_console"
