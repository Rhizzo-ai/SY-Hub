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
    """Get test-admin token (super_admin role)"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_ADMIN_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Test admin login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def test_director_token(api_client):
    """Get test-director token (director role - MFA enforced)"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_DIRECTOR_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Test director login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def test_finance_token(api_client):
    """Get test-finance token (finance role - MFA enforced)"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_FINANCE_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Test finance login failed: {response.text}")
    return response.json()["access_token"]


# ============================================================
# MFA Enrollment Required Tests
# ============================================================

class TestMfaEnrollmentRequired:
    """Tests for mfa_enrollment_required flag on /api/auth/me"""
    
    def test_super_admin_mfa_enrollment_required_true(self, api_client, test_admin_token):
        """GET /api/auth/me for super_admin with mfa_enabled=false returns mfa_enrollment_required=true"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # super_admin role is in MFA_ENFORCED_ROLES, so should require enrollment
        assert data["mfa_enrollment_required"] is True
        assert data["mfa_enabled"] is False
        assert data["mfa_backup_codes_remaining"] == 0
    
    def test_director_mfa_enrollment_required_true(self, api_client, test_director_token):
        """GET /api/auth/me for director with mfa_enabled=false returns mfa_enrollment_required=true"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {test_director_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # director role is in MFA_ENFORCED_ROLES
        assert data["mfa_enrollment_required"] is True
        assert data["mfa_enabled"] is False
    
    def test_finance_mfa_enrollment_required_true(self, api_client, test_finance_token):
        """GET /api/auth/me for finance with mfa_enabled=false returns mfa_enrollment_required=true"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {test_finance_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # finance role is in MFA_ENFORCED_ROLES
        assert data["mfa_enrollment_required"] is True
        assert data["mfa_enabled"] is False


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
        # Login as test-director (MFA not enabled by default)
        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DIRECTOR_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if login_response.json().get("mfa_required"):
            pytest.skip("MFA already enabled for test-director")
        
        token = login_response.json()["access_token"]
        
        # Try to regenerate without MFA enabled
        regen_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert regen_response.status_code == 400
        assert "MFA not enrolled" in regen_response.json()["detail"]
    
    def test_regenerate_backup_codes_returns_10_new_codes(self, api_client, test_admin_token):
        """POST /api/auth/mfa/backup-codes/regenerate returns 10 new codes when MFA enabled"""
        # Check if MFA is enabled
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        
        if not me_response.json().get("mfa_enabled"):
            # Enable MFA first
            start_response = api_client.post(
                f"{BASE_URL}/api/auth/mfa/enroll/start",
                headers={"Authorization": f"Bearer {test_admin_token}"}
            )
            secret = start_response.json()["secret"]
            totp = pyotp.TOTP(secret)
            code = totp.now()
            api_client.post(
                f"{BASE_URL}/api/auth/mfa/enroll/confirm",
                json={"secret": secret, "code": code},
                headers={"Authorization": f"Bearer {test_admin_token}"}
            )
        
        # Regenerate backup codes
        regen_response = api_client.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        assert regen_response.status_code == 200
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
            # Disable MFA
            disable_response = api_client.post(
                f"{BASE_URL}/api/auth/mfa/disable",
                headers={"Authorization": f"Bearer {test_admin_token}"}
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
            # MFA not enabled, just verify disable doesn't error
            disable_response = api_client.post(
                f"{BASE_URL}/api/auth/mfa/disable",
                headers={"Authorization": f"Bearer {test_admin_token}"}
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
        """POST /api/auth/password/change with same password returns 400"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/password/change",
            json={
                "current_password": TEST_PASSWORD,
                "new_password": TEST_PASSWORD
            },
            headers={"Authorization": f"Bearer {test_admin_token}"}
        )
        # Should fail due to password reuse policy
        assert response.status_code == 400
        assert "cannot match" in response.json()["detail"].lower()


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
            # Can't disable without completing MFA - skip cleanup
            return
        
        token = login_response.json()["access_token"]
        
        # Disable MFA
        api_client.post(
            f"{BASE_URL}/api/auth/mfa/disable",
            headers={"Authorization": f"Bearer {token}"}
        )
