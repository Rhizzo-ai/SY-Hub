"""
Backend API tests for SY Homes MFA module (Prompt 1.2 addendum).
Migrated to cookies-only transport (audit remediation C1 — Feb 2026).
"""
import os
import time

import pyotp
import pytest
import requests

from tests.conftest import login_with_auto_enroll


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://governance-ui.preview.emergentagent.com"

TEST_PASSWORD = "TestUser-Dev-2026!"
TEST_ADMIN_EMAIL = "test-admin@example.test"
TEST_DIRECTOR_EMAIL = "test-director@example.test"
TEST_FINANCE_EMAIL = "test-finance@example.test"


@pytest.fixture(scope="module")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_session():
    """Admin session after MFA auto-enrol (super_admin role)."""
    return login_with_auto_enroll(None, BASE_URL, TEST_ADMIN_EMAIL, TEST_PASSWORD)


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _db_reset_mfa(email: str) -> None:
    import os as _os
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    load_dotenv("/app/backend/.env")
    e = create_engine(_os.environ["DATABASE_URL"])
    with e.begin() as c:
        c.execute(
            text(
                "UPDATE users SET mfa_enabled=false, mfa_secret_encrypted=NULL, "
                "mfa_backup_codes_encrypted=NULL, mfa_enrolled_at=NULL, "
                "mfa_method=NULL WHERE email=:em"
            ),
            {"em": email},
        )
    from tests.conftest import _MFA_SECRETS
    _MFA_SECRETS.pop(email, None)


# ============================================================
# MFA Enrollment Required Tests
# ============================================================

class TestMfaEnrollmentRequired:
    def test_super_admin_mfa_enrollment_required_true(self, anon_client):
        _db_reset_mfa(TEST_ADMIN_EMAIL)
        s = _new_session()
        login = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_PASSWORD,
        })
        assert login.status_code == 200
        data = login.json()
        assert data["mfa_enrollment_required"] is True
        assert data["enforced_role_name"]
        # Pending cookie set; no token in body.
        assert s.cookies.get("access_token")
        assert "mfa_pending_token" not in data
        assert "access_token" not in data

        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        m = me.json()
        assert m["mfa_enrollment_required"] is True
        assert m["mfa_enabled"] is False
        assert m["mfa_backup_codes_remaining"] == 0
        assert m["token_type"] == "mfa_pending"

    def test_director_mfa_enrollment_required_true(self):
        _db_reset_mfa(TEST_DIRECTOR_EMAIL)
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DIRECTOR_EMAIL, "password": TEST_PASSWORD,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["mfa_enrollment_required"] is True
        assert d["enforced_role_name"] == "Director"

    def test_finance_mfa_enrollment_required_true(self):
        _db_reset_mfa(TEST_FINANCE_EMAIL)
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_FINANCE_EMAIL, "password": TEST_PASSWORD,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["mfa_enrollment_required"] is True
        assert d["enforced_role_name"] == "Finance"


# ============================================================
# MFA Enrollment Flow Tests
# ============================================================

class TestMfaEnrollmentFlow:
    def test_mfa_enroll_start_returns_secret_and_qr(self, admin_session):
        """admin_session has already auto-enrolled, but /enroll/start still
        returns a fresh secret + QR. (Confirm would overwrite — we don't call it.)
        """
        response = admin_session.post(f"{BASE_URL}/api/auth/mfa/enroll/start")
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_data_uri" in data
        assert len(data["secret"]) >= 16
        assert data["qr_data_uri"].startswith("data:image/png;base64,")

    def test_mfa_enroll_confirm_with_invalid_totp_returns_400(self, admin_session):
        start_response = admin_session.post(f"{BASE_URL}/api/auth/mfa/enroll/start")
        assert start_response.status_code == 200
        secret = start_response.json()["secret"]
        confirm_response = admin_session.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": "000000"},
        )
        assert confirm_response.status_code == 400
        assert "Invalid TOTP code" in confirm_response.json()["detail"]


# ============================================================
# Backup Codes Tests
# ============================================================

class TestBackupCodes:
    def test_regenerate_backup_codes_requires_mfa_enabled(self):
        # Login as a non-enrolled enforced-role user — endpoint should reject
        # with 400 because MFA is not enrolled. Both the mfa_pending cookie
        # and a real access cookie reach the enrolment dep.
        _db_reset_mfa(TEST_DIRECTOR_EMAIL)
        s = _new_session()
        login = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DIRECTOR_EMAIL, "password": TEST_PASSWORD,
        })
        assert login.status_code == 200
        if login.json().get("mfa_required"):
            pytest.skip("MFA already enabled for test-director")

        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": TEST_PASSWORD, "current_totp": "123456"},
        )
        assert r.status_code == 400
        assert "MFA not enrolled" in r.json()["detail"]

    def test_regenerate_backup_codes_returns_10_new_codes(self):
        """Fresh enrol via cookies flow, then regenerate."""
        _db_reset_mfa(TEST_ADMIN_EMAIL)
        s = _new_session()
        login = s.post(f"{BASE_URL}/api/auth/login",
                       json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD})
        assert login.status_code == 200
        assert login.json()["mfa_enrollment_required"] is True

        start = s.post(f"{BASE_URL}/api/auth/mfa/enroll/start")
        secret = start.json()["secret"]
        totp = pyotp.TOTP(secret)
        confirm = s.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": totp.now()},
        )
        assert confirm.status_code == 200
        # Cookies now full session; regenerate.
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": TEST_PASSWORD, "current_totp": totp.now()},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["backup_codes"]) == 10


# ============================================================
# MFA Disable Tests
# ============================================================

class TestMfaDisable:
    def test_mfa_disable_clears_mfa_state(self, admin_session):
        me_response = admin_session.get(f"{BASE_URL}/api/auth/me")
        if me_response.json().get("mfa_enabled"):
            disable_response = admin_session.post(
                f"{BASE_URL}/api/auth/mfa/disable",
                json={"current_password": TEST_PASSWORD},
            )
            assert disable_response.status_code == 204
            me2 = admin_session.get(f"{BASE_URL}/api/auth/me")
            assert me2.json()["mfa_enabled"] is False
            assert me2.json()["mfa_method"] is None
            assert me2.json()["mfa_backup_codes_remaining"] == 0
        else:
            disable_response = admin_session.post(
                f"{BASE_URL}/api/auth/mfa/disable",
                json={"current_password": TEST_PASSWORD},
            )
            assert disable_response.status_code == 204


# ============================================================
# Password Change Tests
# ============================================================

class TestPasswordChange:
    def test_password_change_wrong_current_returns_400(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/auth/password/change",
            json={"current_password": "WrongPassword123!", "new_password": "NewSecurePassword123!"},
        )
        assert r.status_code == 400
        assert "Current password is incorrect" in r.json()["detail"]

    def test_password_change_reuse_returns_400(self, admin_session):
        temp_pw = "TempDev-Password-Change-2026!"
        step1 = admin_session.post(
            f"{BASE_URL}/api/auth/password/change",
            json={"current_password": TEST_PASSWORD, "new_password": temp_pw},
        )
        if step1.status_code != 204:
            pytest.skip(f"Couldn't set temp password: {step1.text}")
        try:
            r = admin_session.post(
                f"{BASE_URL}/api/auth/password/change",
                json={"current_password": temp_pw, "new_password": TEST_PASSWORD},
            )
            assert r.status_code == 400
            assert "cannot match" in r.json()["detail"].lower()
        finally:
            import os as _os
            from sqlalchemy import create_engine, text
            e = create_engine(_os.environ["DATABASE_URL"])
            from app.auth.passwords import hash_password
            with e.begin() as c:
                c.execute(
                    text("UPDATE users SET password_hash=:h, password_history='[]'::jsonb WHERE email=:em"),
                    {"h": hash_password(TEST_PASSWORD), "em": TEST_ADMIN_EMAIL},
                )


# ============================================================
# Logout Tests
# ============================================================

class TestLogout:
    def test_logout_returns_204(self):
        """Use a dedicated throw-away session so we don't kill admin_session."""
        s = login_with_auto_enroll(None, BASE_URL, TEST_ADMIN_EMAIL, TEST_PASSWORD)
        r = s.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 204


# ============================================================
# Cleanup
# ============================================================

class TestCleanup:
    def test_cleanup_disable_mfa_test_admin(self):
        """Reset test-admin MFA state via DB so subsequent sessions enrol fresh."""
        _db_reset_mfa(TEST_ADMIN_EMAIL)
