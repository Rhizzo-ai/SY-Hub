"""
Backend tests — MFA Gap Closure (Prompt 1.2 addendum).

Covers:
  - Hard-block login for MFA-enforced roles (super_admin / director / finance)
    not yet enrolled → mfa_pending token
  - Non-enforced roles get a normal access token when MFA is off
  - mfa_pending token only permits the whitelisted endpoints
  - /auth/me shape under mfa_pending
  - Enrolment confirm swaps mfa_pending → full access token
  - /mfa/disable requires current_password (422 / 400 / 204)
  - /mfa/backup-codes/regenerate requires current_password + current_totp
  - mfa_enrolled_at column is stamped on confirm, cleared on disable
  - Existing MFA-challenge flow (already-enrolled user) still works
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
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def db_engine():
    eng = sa.create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


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


def _login(http, email: str, password: str = PWD) -> dict:
    r = http.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()


def _fetch_mfa_enrolled_at(db_engine, email: str) -> Optional[object]:
    with db_engine.begin() as conn:
        row = conn.execute(
            sa.text("SELECT mfa_enrolled_at FROM users WHERE email = :e"),
            {"e": email},
        ).first()
    assert row is not None
    return row[0]


# Column-name sanity check — migration 0003 renamed mfa_enforced_at → mfa_enrolled_at.
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
    assert "mfa_enrolled_at" in cols, "mfa_enrolled_at column missing"
    assert "mfa_enforced_at" not in cols, "old mfa_enforced_at column still present"


# ---------- 1. Login hard-block for enforced role ----------

class TestEnforcedRoleLogin:
    def test_director_login_issues_mfa_pending(self, http, db_engine):
        _reset_user_mfa(db_engine, DIRECTOR)
        data = _login(http, DIRECTOR)
        assert data["mfa_enrollment_required"] is True
        assert data["mfa_pending_token"], "mfa_pending_token missing"
        # access_token should equal the mfa_pending token (per spec)
        assert data["access_token"] == data["mfa_pending_token"]
        assert data["enforced_role_name"] == "Director"
        assert data["user"]["email"] == DIRECTOR
        assert data.get("mfa_required") in (False, None)

    def test_finance_login_issues_mfa_pending(self, http, db_engine):
        _reset_user_mfa(db_engine, FINANCE)
        data = _login(http, FINANCE)
        assert data["mfa_enrollment_required"] is True
        assert data["enforced_role_name"] == "Finance"

    def test_super_admin_login_issues_mfa_pending(self, http, db_engine):
        _reset_user_mfa(db_engine, ADMIN)
        data = _login(http, ADMIN)
        assert data["mfa_enrollment_required"] is True
        # super_admin is priority 1 → most senior
        assert data["enforced_role_name"] == "Super Administrator"

    def test_readonly_login_is_normal_access(self, http, db_engine):
        _reset_user_mfa(db_engine, READONLY)
        data = _login(http, READONLY)
        assert data["mfa_enrollment_required"] is False
        assert data["access_token"]
        assert data.get("mfa_pending_token") in (None, "")
        assert data.get("enforced_role_name") in (None, "")

    def test_pm_login_is_normal_access(self, http, db_engine):
        _reset_user_mfa(db_engine, PM)
        data = _login(http, PM)
        assert data["mfa_enrollment_required"] is False
        assert data["access_token"]


# ---------- 2. mfa_pending token gating ----------

class TestMfaPendingTokenGating:
    @pytest.fixture(scope="class")
    def pending_token(self, http, db_engine):
        _reset_user_mfa(db_engine, DIRECTOR)
        data = _login(http, DIRECTOR)
        return data["mfa_pending_token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_me_allowed(self, http, pending_token):
        r = http.get(f"{BASE_URL}/api/auth/me", headers=self._auth(pending_token))
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "mfa_pending"
        assert body["permissions"] == []
        assert body["is_super_admin"] is False
        assert body["mfa_enrollment_required"] is True
        assert body["enforced_role_name"] == "Director"

    def test_mfa_enroll_start_allowed(self, http, pending_token):
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers=self._auth(pending_token),
        )
        assert r.status_code == 200
        assert "secret" in r.json()

    def test_entities_blocked(self, http, pending_token):
        r = http.get(f"{BASE_URL}/api/entities", headers=self._auth(pending_token))
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_users_blocked(self, http, pending_token):
        r = http.get(f"{BASE_URL}/api/users", headers=self._auth(pending_token))
        assert r.status_code in (401, 403)

    def test_logout_allowed(self, http, pending_token):
        r = http.post(f"{BASE_URL}/api/auth/logout", headers=self._auth(pending_token))
        assert r.status_code == 204


# ---------- 3. Enrol happy-path (mfa_pending → full access) ----------

class TestEnforcedEnrolmentHappyPath:
    def test_full_flow_login_enrol_access_entities(self, http, db_engine):
        _reset_user_mfa(db_engine, DIRECTOR)
        login = _login(http, DIRECTOR)
        pending = login["mfa_pending_token"]
        assert pending

        # /mfa/enroll/start
        start = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {pending}"},
        )
        assert start.status_code == 200
        secret = start.json()["secret"]

        # Confirm with live TOTP
        totp = pyotp.TOTP(secret)
        code = totp.now()
        confirm = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": code},
            headers={"Authorization": f"Bearer {pending}"},
        )
        assert confirm.status_code == 200, confirm.text
        body = confirm.json()
        assert len(body["backup_codes"]) == 10
        new_access = body["access_token"]
        assert new_access and new_access != pending

        # mfa_enrolled_at stamped
        stamped = _fetch_mfa_enrolled_at(db_engine, DIRECTOR)
        assert stamped is not None, "mfa_enrolled_at was not set on confirm"

        # /api/auth/me with new token → full access principal
        me = http.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert me.status_code == 200
        assert me.json()["token_type"] == "access"
        assert len(me.json()["permissions"]) > 0

        # /api/entities now reachable
        ent = http.get(
            f"{BASE_URL}/api/entities",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert ent.status_code == 200, f"entities blocked: {ent.status_code} {ent.text}"

        # Subsequent login — user now enrolled → mfa_challenge path (regression)
        login2 = http.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DIRECTOR, "password": PWD},
        ).json()
        assert login2.get("mfa_required") is True
        assert login2.get("mfa_challenge_token")

        # Verify TOTP completes the challenge
        time.sleep(1)
        verify = http.post(
            f"{BASE_URL}/api/auth/mfa/verify",
            json={
                "challenge_token": login2["mfa_challenge_token"],
                "code": totp.now(),
                "use_backup_code": False,
            },
        )
        assert verify.status_code == 200, verify.text
        assert verify.json().get("access_token")


# ---------- 4. /mfa/disable requires current_password ----------

class TestMfaDisablePasswordGate:
    @pytest.fixture(scope="class")
    def enrolled_token_and_secret(self, http, db_engine):
        _reset_user_mfa(db_engine, ADMIN)
        login = _login(http, ADMIN)
        pending = login["mfa_pending_token"]
        start = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {pending}"},
        ).json()
        secret = start["secret"]
        code = pyotp.TOTP(secret).now()
        confirm = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": code},
            headers={"Authorization": f"Bearer {pending}"},
        ).json()
        return confirm["access_token"], secret

    def test_missing_body_returns_422(self, http, enrolled_token_and_secret):
        token, _ = enrolled_token_and_secret
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/disable",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_wrong_password_returns_400(self, http, enrolled_token_and_secret):
        token, _ = enrolled_token_and_secret
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/disable",
            json={"current_password": "totally-wrong"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "Current password is incorrect" in r.json()["detail"]

    def test_correct_password_returns_204_and_clears(self, http, db_engine, enrolled_token_and_secret):
        token, _ = enrolled_token_and_secret
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/disable",
            json={"current_password": PWD},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204

        # mfa_enabled false and mfa_enrolled_at cleared
        with db_engine.begin() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT mfa_enabled, mfa_enrolled_at FROM users WHERE email = :e"
                ),
                {"e": ADMIN},
            ).first()
        assert row[0] is False
        assert row[1] is None


# ---------- 5. /mfa/backup-codes/regenerate requires password + TOTP ----------

class TestRegenerateBackupCodes:
    @pytest.fixture(scope="class")
    def enrolled(self, http, db_engine):
        _reset_user_mfa(db_engine, FINANCE)
        login = _login(http, FINANCE)
        pending = login["mfa_pending_token"]
        start = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {pending}"},
        ).json()
        secret = start["secret"]
        code = pyotp.TOTP(secret).now()
        confirm = http.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": code},
            headers={"Authorization": f"Bearer {pending}"},
        ).json()
        return confirm["access_token"], secret

    def test_missing_fields_returns_422(self, http, enrolled):
        token, _ = enrolled
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_missing_totp_returns_422(self, http, enrolled):
        token, _ = enrolled
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": PWD},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_wrong_password_returns_400(self, http, enrolled):
        token, secret = enrolled
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": "nope", "current_totp": pyotp.TOTP(secret).now()},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "Current password is incorrect" in r.json()["detail"]

    def test_wrong_totp_returns_400(self, http, enrolled):
        token, _ = enrolled
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": PWD, "current_totp": "000000"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "Invalid authenticator code" in r.json()["detail"]

    def test_valid_returns_10_new_codes(self, http, enrolled):
        token, secret = enrolled
        time.sleep(1)
        r = http.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": PWD, "current_totp": pyotp.TOTP(secret).now()},
            headers={"Authorization": f"Bearer {token}"},
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
