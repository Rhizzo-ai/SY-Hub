"""
Backend tests — MFA Gap Closure (Prompt 1.2 addendum).
Migrated to cookies-only transport (audit remediation C1 — Feb 2026).

The mfa_pending JWT now rides as an httpOnly cookie (`access_token`) set by
`/api/auth/login` rather than surfaced in the response body. Tests use
`requests.Session` cookie jars; no Bearer headers.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import pyotp
import pytest
import requests
import sqlalchemy as sa


def _read_env(path: str, key: str) -> Optional[str]:
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
    or ""
).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not found"
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = "TestUser-Dev-2026!"

DIRECTOR = "test-director@example.test"
FINANCE = "test-finance@example.test"
ADMIN = "test-admin@example.test"
READONLY = "test-readonly@example.test"
PM = "test-pm@example.test"


# ---------- helpers ----------

@pytest.fixture(scope="module")
def db_engine():
    eng = sa.create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _reset_user_mfa(db_engine, email: str) -> None:
    """Clear any leftover MFA state so the login path exercises the gap closure."""
    with db_engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE users SET
                  mfa_enabled = false,
                  mfa_method = NULL,
                  mfa_secret_encrypted = NULL,
                  mfa_backup_codes_encrypted = NULL,
                  mfa_enrolled_at = NULL,
                  failed_login_attempts = 0,
                  locked_until = NULL,
                  lockout_level = 0
                WHERE email = :email
                """
            ),
            {"email": email},
        )


def _login_fresh(email: str, password: str = PWD):
    """Log in on a brand-new session. Returns (session, body)."""
    s = _new_session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s, r.json()


def _fetch_mfa_enrolled_at(db_engine, email: str) -> Optional[object]:
    with db_engine.begin() as conn:
        row = conn.execute(
            sa.text("SELECT mfa_enrolled_at FROM users WHERE email = :e"),
            {"e": email},
        ).first()
    assert row is not None
    return row[0]


# Column-name sanity check.
def test_column_rename_applied(db_engine):
    with db_engine.begin() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='users'"
                )
            )
        }
    assert "mfa_enrolled_at" in cols
    assert "mfa_enforced_at" not in cols


# ---------- 1. Login hard-block for enforced role ----------

class TestEnforcedRoleLogin:
    def test_director_login_issues_mfa_pending(self, db_engine):
        _reset_user_mfa(db_engine, DIRECTOR)
        s, data = _login_fresh(DIRECTOR)
        assert data["mfa_enrollment_required"] is True
        # Audit C1: mfa_pending token rides via cookie, not body.
        assert "mfa_pending_token" not in data
        assert "access_token" not in data
        assert s.cookies.get("access_token"), "pending cookie not set"
        # Refresh cookie should be cleared defensively.
        assert not s.cookies.get("refresh_token")
        assert data["enforced_role_name"] == "Director"
        assert data["user"]["email"] == DIRECTOR
        assert data.get("mfa_required") in (False, None)

    def test_finance_login_issues_mfa_pending(self, db_engine):
        _reset_user_mfa(db_engine, FINANCE)
        _, data = _login_fresh(FINANCE)
        assert data["mfa_enrollment_required"] is True
        assert data["enforced_role_name"] == "Finance"

    def test_super_admin_login_issues_mfa_pending(self, db_engine):
        _reset_user_mfa(db_engine, ADMIN)
        _, data = _login_fresh(ADMIN)
        assert data["mfa_enrollment_required"] is True
        assert data["enforced_role_name"] == "Super Administrator"

    def test_readonly_login_is_normal_access(self, db_engine):
        _reset_user_mfa(db_engine, READONLY)
        s, data = _login_fresh(READONLY)
        assert data["mfa_enrollment_required"] is False
        assert s.cookies.get("access_token")
        assert s.cookies.get("refresh_token")
        assert data.get("enforced_role_name") in (None, "")

    def test_pm_login_is_normal_access(self, db_engine):
        _reset_user_mfa(db_engine, PM)
        s, data = _login_fresh(PM)
        assert data["mfa_enrollment_required"] is False
        assert s.cookies.get("access_token")


# ---------- 2. mfa_pending cookie gating ----------

class TestMfaPendingTokenGating:
    @pytest.fixture(scope="class")
    def pending_session(self, db_engine):
        _reset_user_mfa(db_engine, DIRECTOR)
        s, data = _login_fresh(DIRECTOR)
        assert data["mfa_enrollment_required"] is True
        return s

    def test_me_allowed(self, pending_session):
        r = pending_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "mfa_pending"
        assert body["permissions"] == []
        assert body["is_super_admin"] is False
        assert body["mfa_enrollment_required"] is True
        assert body["enforced_role_name"] == "Director"

    def test_mfa_enroll_start_allowed(self, pending_session):
        r = pending_session.post(f"{BASE_URL}/api/auth/mfa/enroll/start")
        assert r.status_code == 200
        assert "secret" in r.json()

    def test_entities_blocked(self, pending_session):
        r = pending_session.get(f"{BASE_URL}/api/entities")
        assert r.status_code in (401, 403)

    def test_users_blocked(self, pending_session):
        r = pending_session.get(f"{BASE_URL}/api/users")
        assert r.status_code in (401, 403)

    def test_logout_allowed(self, pending_session):
        r = pending_session.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 204


# ---------- 3. Enrol happy-path (mfa_pending → full access) ----------

class TestEnforcedEnrolmentHappyPath:
    def test_full_flow_login_enrol_access_entities(self, db_engine):
        _reset_user_mfa(db_engine, DIRECTOR)
        s, login = _login_fresh(DIRECTOR)
        assert login["mfa_enrollment_required"] is True
        pending_cookie = s.cookies.get("access_token")
        assert pending_cookie

        # /mfa/enroll/start
        start = s.post(f"{BASE_URL}/api/auth/mfa/enroll/start")
        assert start.status_code == 200
        secret = start.json()["secret"]

        # Confirm with live TOTP.
        totp = pyotp.TOTP(secret)
        confirm = s.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": totp.now()},
        )
        assert confirm.status_code == 200, confirm.text
        body = confirm.json()
        assert len(body["backup_codes"]) == 10
        # Audit C1: no token leak in body.
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["session_issued"] is True
        # Cookies were rotated from pending → full session.
        new_access = s.cookies.get("access_token")
        assert new_access and new_access != pending_cookie
        assert s.cookies.get("refresh_token")

        # mfa_enrolled_at stamped.
        stamped = _fetch_mfa_enrolled_at(db_engine, DIRECTOR)
        assert stamped is not None

        # /auth/me with the new cookie → full access principal.
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["token_type"] == "access"
        assert len(me.json()["permissions"]) > 0

        # /entities now reachable.
        ent = s.get(f"{BASE_URL}/api/entities")
        assert ent.status_code == 200

        # Subsequent login — user now enrolled → mfa_challenge path (regression).
        s2 = _new_session()
        login2 = s2.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DIRECTOR, "password": PWD},
        ).json()
        assert login2.get("mfa_required") is True
        assert login2.get("mfa_challenge_token")

        # Verify TOTP completes the challenge.
        time.sleep(1)
        verify = s2.post(
            f"{BASE_URL}/api/auth/mfa/verify",
            json={
                "challenge_token": login2["mfa_challenge_token"],
                "code": totp.now(),
                "use_backup_code": False,
            },
        )
        assert verify.status_code == 200, verify.text
        # Full session cookies set.
        assert s2.cookies.get("access_token")
        assert s2.cookies.get("refresh_token")


# ---------- 4. /mfa/disable requires current_password ----------

class TestMfaDisablePasswordGate:
    @pytest.fixture(scope="class")
    def enrolled_session(self, db_engine):
        _reset_user_mfa(db_engine, ADMIN)
        s, _ = _login_fresh(ADMIN)
        start = s.post(f"{BASE_URL}/api/auth/mfa/enroll/start").json()
        secret = start["secret"]
        confirm = s.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": pyotp.TOTP(secret).now()},
        )
        assert confirm.status_code == 200
        return s, secret

    def test_missing_body_returns_422(self, enrolled_session):
        s, _ = enrolled_session
        r = s.post(f"{BASE_URL}/api/auth/mfa/disable")
        assert r.status_code == 422

    def test_wrong_password_returns_400(self, enrolled_session):
        s, _ = enrolled_session
        r = s.post(f"{BASE_URL}/api/auth/mfa/disable", json={"current_password": "totally-wrong"})
        assert r.status_code == 400
        assert "Current password is incorrect" in r.json()["detail"]

    def test_correct_password_returns_204_and_clears(self, db_engine, enrolled_session):
        s, _ = enrolled_session
        r = s.post(f"{BASE_URL}/api/auth/mfa/disable", json={"current_password": PWD})
        assert r.status_code == 204

        with db_engine.begin() as conn:
            row = conn.execute(
                sa.text("SELECT mfa_enabled, mfa_enrolled_at FROM users WHERE email = :e"),
                {"e": ADMIN},
            ).first()
        assert row[0] is False
        assert row[1] is None


# ---------- 5. /mfa/backup-codes/regenerate requires password + TOTP ----------

class TestRegenerateBackupCodes:
    @pytest.fixture(scope="class")
    def enrolled(self, db_engine):
        _reset_user_mfa(db_engine, FINANCE)
        s, _ = _login_fresh(FINANCE)
        start = s.post(f"{BASE_URL}/api/auth/mfa/enroll/start").json()
        secret = start["secret"]
        confirm = s.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": pyotp.TOTP(secret).now()},
        )
        assert confirm.status_code == 200
        return s, secret

    def test_missing_fields_returns_422(self, enrolled):
        s, _ = enrolled
        r = s.post(f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate", json={})
        assert r.status_code == 422

    def test_missing_totp_returns_422(self, enrolled):
        s, _ = enrolled
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": PWD},
        )
        assert r.status_code == 422

    def test_wrong_password_returns_400(self, enrolled):
        s, secret = enrolled
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": "nope", "current_totp": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 400
        assert "Current password is incorrect" in r.json()["detail"]

    def test_wrong_totp_returns_400(self, enrolled):
        s, _ = enrolled
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": PWD, "current_totp": "000000"},
        )
        assert r.status_code == 400
        assert "Invalid authenticator code" in r.json()["detail"]

    def test_valid_returns_10_new_codes(self, enrolled):
        s, secret = enrolled
        time.sleep(1)
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": PWD, "current_totp": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["backup_codes"]) == 10
        for c in body["backup_codes"]:
            assert "-" in c


# ---------- 6. Cleanup ----------

def test_zz_cleanup_reset_users(db_engine):
    for e in (ADMIN, DIRECTOR, FINANCE, READONLY, PM):
        _reset_user_mfa(db_engine, e)
