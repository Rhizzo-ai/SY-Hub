"""
Backend API tests for SY Homes MFA module (Prompt 1.2 addendum)
Tests: MFA enrollment, verification, backup codes, regeneration, disable
"""
import os
import pytest
import requests
import pyotp
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://construction-command-5.preview.emergentagent.com"

from tests.conftest import login_with_auto_enroll

# Test credentials
TEST_PASSWORD = "TestUser-Dev-2026!"
TEST_ADMIN_EMAIL = "test-admin@example.test"
TEST_DIRECTOR_EMAIL = "test-director@example.test"
TEST_FINANCE_EMAIL = "test-finance@example.test"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_admin_token(api_client):
    """Get test-admin token (super_admin role - auto-enrol MFA)"""
    return login_with_auto_enroll(api_client, BASE_URL, TEST_ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def test_director_token(api_client):
    """Get test-director token (director role - MFA enforced; auto-enrol)"""
    return login_with_auto_enroll(api_client, BASE_URL, TEST_DIRECTOR_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def test_finance_token(api_client):
    """Get test-finance token (finance role - MFA enforced; auto-enrol)"""
    return login_with_auto_enroll(api_client, BASE_URL, TEST_FINANCE_EMAIL, TEST_PASSWORD)


def _db_reset_mfa(email: str) -> None:
    """Force MFA state to 'not enrolled' at the DB level so tests that
    validate the hard-block path can run regardless of whether a previous
    test already auto-enrolled the user.
    """
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
    # Also clear cached secret so login_with_auto_enroll will re-enrol.
    from tests.conftest import _MFA_SECRETS
    _MFA_SECRETS.pop(email, None)


# ============================================================
# MFA Enrollment Required Tests
# ============================================================

class TestMfaEnrollmentRequired:
    """Tests for mfa_enrollment_required flag on /api/auth/me"""
    
    def test_super_admin_mfa_enrollment_required_true(self, api_client):
        """An un-enrolled super_admin login returns an mfa_pending token, and
        /auth/me on that token reports mfa_enrollment_required=true."""
        _db_reset_mfa(TEST_ADMIN_EMAIL)

        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_PASSWORD,
        })
        assert login_response.status_code == 200
        data = login_response.json()
        assert data["mfa_enrollment_required"] is True
        assert data["enforced_role_name"]  # populated with most-senior role
        pending = data["mfa_pending_token"]

        me = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {pending}"},
        )
        assert me.status_code == 200
        m = me.json()
        assert m["mfa_enrollment_required"] is True
        assert m["mfa_enabled"] is False
        assert m["mfa_backup_codes_remaining"] == 0
        assert m["token_type"] == "mfa_pending"

    def test_director_mfa_enrollment_required_true(self, api_client):
        """Director login without MFA returns mfa_pending + enforced_role_name."""
        _db_reset_mfa(TEST_DIRECTOR_EMAIL)
        r = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DIRECTOR_EMAIL, "password": TEST_PASSWORD,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["mfa_enrollment_required"] is True
        assert d["enforced_role_name"] == "Director"

    def test_finance_mfa_enrollment_required_true(self, api_client):
        """Finance login without MFA returns mfa_pending + enforced_role_name."""
        _db_reset_mfa(TEST_FINANCE_EMAIL)
        r = api_client.post(f"{BASE_URL}/api/auth/login", json={
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
    """Tests for MFA enrollment start/confirm flow"""
    
    def test_mfa_enroll_start_returns_secret_and_qr(self, api_client, test_admin_token):
        """POST /api/auth/mfa/enroll/start returns secret and qr_data_uri"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_data_uri" in data
        # Secret should be base32 encoded
        assert len(data["secret"]) >= 16
        # QR should be a data URI
        assert data["qr_data_uri"].startswith("data:image/png;base64,")
    
    def test_mfa_enroll_confirm_with_valid_totp(self, api_client, test_admin_token):
        """POST /api/auth/mfa/enroll/confirm with valid TOTP code returns backup codes"""
        # Start enrollment to get secret
        start_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert start_response.status_code == 200
        secret = start_response.json()["secret"]
        
        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        # Confirm enrollment
        confirm_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": code},
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10
        # Backup codes should be in format XXXXX-XXXXX
        for bc in data["backup_codes"]:
            assert "-" in bc
            assert len(bc) == 11
    
    def test_mfa_enroll_confirm_with_invalid_totp_returns_400(self, api_client, test_admin_token):
        """POST /api/auth/mfa/enroll/confirm with invalid TOTP code returns 400"""
        # Start enrollment to get secret
        start_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert start_response.status_code == 200
        secret = start_response.json()["secret"]
        
        # Try with invalid code
        confirm_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": "000000"},
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert confirm_response.status_code == 400
        assert "Invalid TOTP code" in confirm_response.json()["detail"]


# ============================================================
# MFA Verification Tests
# ============================================================

class TestMfaVerification:
    """Tests for MFA verification during login"""
    
    def test_mfa_login_flow_with_totp(self, api_client):
        """Full MFA login flow: login -> mfa_required -> verify with TOTP"""
        # First, ensure MFA is enabled for test-admin
        # Login to get initial token
        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_PASSWORD
        })
        
        # If MFA is already enabled, we'll get mfa_required=true
        if login_response.json().get("mfa_required"):
            # MFA is enabled, test the verification flow
            challenge_token = login_response.json()["mfa_challenge_token"]
            
            # We need the secret to generate TOTP - this test assumes MFA was enrolled
            # For a complete test, we'd need to store the secret from enrollment
            # Skip this test if we can't verify
            pytest.skip("MFA already enabled but secret not available for verification")
        else:
            # MFA not enabled yet, enroll first
            token = login_response.json()["access_token"]
            
            # Start enrollment
            start_response = api_client.post(
                f"{BASE_URL}/api/auth/mfa/enroll/start",
                headers={"Authorization": f"Bearer {token}"}
            )
            secret = start_response.json()["secret"]
            
            # Confirm enrollment
            totp = pyotp.TOTP(secret)
            code = totp.now()
            api_client.post(
                f"{BASE_URL}/api/auth/mfa/enroll/confirm",
                json={"secret": secret, "code": code},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Now login again - should require MFA
            login_response2 = api_client.post(f"{BASE_URL}/api/auth/login", json={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_PASSWORD
            })
            assert login_response2.json().get("mfa_required") is True
            challenge_token = login_response2.json()["mfa_challenge_token"]
            
            # Verify with TOTP
            # Wait a moment to ensure TOTP window is fresh
            time.sleep(1)
            code = totp.now()
            verify_response = api_client.post(f"{BASE_URL}/api/auth/mfa/verify", json={
                "challenge_token": challenge_token,
                "code": code,
                "use_backup_code": False
            })
            assert verify_response.status_code == 200
            assert "access_token" in verify_response.json()


# ============================================================
# Backup Codes Tests
# ============================================================

class TestBackupCodes:
    """Tests for backup code functionality"""
    
    def test_regenerate_backup_codes_requires_mfa_enabled(self, api_client):
        """POST /api/auth/mfa/backup-codes/regenerate requires mfa_enabled=true"""
        # Login as test-director (MFA not enabled by default; login returns
        # mfa_pending token under Prompt 1.2 gap-closure). Either token type
        # reaches the enrolment dependency, so we can assert the 400 response.
        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DIRECTOR_EMAIL,
            "password": TEST_PASSWORD
        })

        if login_response.json().get("mfa_required"):
            pytest.skip("MFA already enabled for test-director")

        token = login_response.json()["access_token"]

        # New contract requires password + current_totp in the body; endpoint
        # should still reject with 400 because MFA is not enrolled.
        regen_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": TEST_PASSWORD, "current_totp": "123456"},
        )
        assert regen_response.status_code == 400
        assert "MFA not enrolled" in regen_response.json()["detail"]

    def test_regenerate_backup_codes_returns_10_new_codes(self, api_client, test_admin_token):
        """POST /api/auth/mfa/backup-codes/regenerate returns 10 new codes when MFA enabled"""
        # test_admin_token fixture auto-enrols MFA, so MFA is already active.
        # We still need a fresh TOTP + password to satisfy the re-auth check.
        # Log in fresh via the auto-enrol helper to capture the live secret.
        # The helper already returned a valid access_token + active MFA; to
        # generate a fresh TOTP here we re-enrol (resets the secret).
        from tests.conftest import login_with_auto_enroll

        # Disable first (with password) so the helper re-enrols cleanly.
        api_client.post(
            f"{BASE_URL}/api/auth/mfa/disable",
            headers={"Authorization": f"Bearer {test_admin_token}"},
            json={"current_password": TEST_PASSWORD},
        )
        # Re-enrol and capture the secret via a manual flow
        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_PASSWORD,
        })
        pending = login_response.json()["mfa_pending_token"]
        headers = {"Authorization": f"Bearer {pending}"}
        start = api_client.post(f"{BASE_URL}/api/auth/mfa/enroll/start", headers=headers)
        secret = start.json()["secret"]
        totp = pyotp.TOTP(secret)
        confirm = api_client.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            headers=headers,
            json={"secret": secret, "code": totp.now()},
        )
        access = confirm.json()["access_token"]

        # Regenerate backup codes with the new required body
        regen_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            headers={"Authorization": f"Bearer {access}"},
            json={
                "current_password": TEST_PASSWORD,
                "current_totp": totp.now(),
            },
        )
        assert regen_response.status_code == 200, regen_response.text
        data = regen_response.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10


# ============================================================
# MFA Disable Tests
# ============================================================

class TestMfaDisable:
    """Tests for MFA disable functionality"""
    
    def test_mfa_disable_clears_mfa_state(self, api_client, test_admin_token):
        """POST /api/auth/mfa/disable clears MFA state"""
        # Check current MFA state
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )

        if me_response.json().get("mfa_enabled"):
            # Disable MFA (now requires password re-auth)
            disable_response = api_client.post(
                f"{BASE_URL}/api/auth/mfa/disable",
                headers={"Authorization": f"Bearer {test_admin_token}"},
                json={"current_password": TEST_PASSWORD},
            )
            assert disable_response.status_code == 204

            # Verify MFA is disabled
            me_response2 = api_client.get(
                f"{BASE_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {test_admin_token}"}
            )
            assert me_response2.json()["mfa_enabled"] is False
            assert me_response2.json()["mfa_method"] is None
            assert me_response2.json()["mfa_backup_codes_remaining"] == 0
        else:
            # MFA not enabled, endpoint still validates the password guard
            disable_response = api_client.post(
                f"{BASE_URL}/api/auth/mfa/disable",
                headers={"Authorization": f"Bearer {test_admin_token}"},
                json={"current_password": TEST_PASSWORD},
            )
            assert disable_response.status_code == 204


# ============================================================
# Password Change Tests
# ============================================================

class TestPasswordChange:
    """Tests for password change functionality"""
    
    def test_password_change_wrong_current_returns_400(self, api_client, test_admin_token):
        """POST /api/auth/password/change with wrong current password returns 400"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/password/change",
            json={
                "current_password": "WrongPassword123!",
                "new_password": "NewSecurePassword123!"
            },
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert response.status_code == 400
        assert "Current password is incorrect" in response.json()["detail"]
    
    def test_password_change_reuse_returns_400(self, api_client, test_admin_token):
        """POST /api/auth/password/change rejects a password already in history"""
        # Populate history first by doing one successful change away from
        # TEST_PASSWORD, then a second change attempting to reuse it.
        temp_pw = "TempDev-Password-Change-2026!"

        step1 = api_client.post(
            f"{BASE_URL}/api/auth/password/change",
            json={"current_password": TEST_PASSWORD, "new_password": temp_pw},
            headers={"Authorization": f"Bearer {test_admin_token}"},
        )
        if step1.status_code != 204:
            pytest.skip(f"Couldn't set temp password: {step1.text}")

        try:
            # Attempt to revert to the original TEST_PASSWORD — now in history.
            response = api_client.post(
                f"{BASE_URL}/api/auth/password/change",
                json={"current_password": temp_pw, "new_password": TEST_PASSWORD},
                headers={"Authorization": f"Bearer {test_admin_token}"},
            )
            assert response.status_code == 400
            assert "cannot match" in response.json()["detail"].lower()
        finally:
            # Restore TEST_PASSWORD so downstream tests keep working.
            # Need to pick a second throwaway to push temp_pw down the history,
            # then a third change back to TEST_PASSWORD (which by now has aged
            # out IF history size ≥ 1; default is 5 so still blocked — so use
            # the raw DB to wipe history + password instead of chaining).
            import os
            from sqlalchemy import create_engine, text
            e = create_engine(os.environ["DATABASE_URL"])
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
    """Tests for logout functionality"""
    
    def test_logout_returns_204(self, api_client, test_admin_token):
        """POST /api/auth/logout returns 204"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert response.status_code == 204


# ============================================================
# Cleanup - Reset test user MFA state
# ============================================================

class TestCleanup:
    """Cleanup test data - disable MFA for test users"""
    
    def test_cleanup_disable_mfa_test_admin(self, api_client):
        """Disable MFA for test-admin to reset state"""
        # Login
        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_PASSWORD
        })

        if login_response.json().get("mfa_required"):
            # Already enrolled — cleanup needs a live TOTP; skip.
            return

        # Either a full access_token OR an mfa_pending token — both accepted
        # by the enrolment-whitelist endpoints (including /mfa/disable).
        token = login_response.json().get("access_token") or login_response.json().get("mfa_pending_token")
        if not token:
            return

        # Disable MFA (requires password re-auth now)
        api_client.post(
            f"{BASE_URL}/api/auth/mfa/disable",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": TEST_PASSWORD},
        )
