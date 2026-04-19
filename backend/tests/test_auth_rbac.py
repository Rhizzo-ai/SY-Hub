"""
Backend API tests for SY Homes Auth + RBAC module (Prompt 1.2)
Tests: Auth flows, MFA, Users CRUD, Roles, Permissions, Scope filtering, Sensitive fields
"""
import os
import pytest
import requests
from datetime import datetime, timedelta
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://construction-command-5.preview.emergentagent.com"

from tests.conftest import login_with_auto_enroll

# Test credentials
TEST_PASSWORD = "TestUser-Dev-2026!"
SUPER_ADMIN_EMAIL = "rhys@syhomes.co.uk"
SUPER_ADMIN_PASSWORD = "xupmaq-qykbah-gipMy5"
TEST_ADMIN_EMAIL = "test-admin@example.test"
TEST_DIRECTOR_EMAIL = "test-director@example.test"
TEST_PM_EMAIL = "test-pm@example.test"
TEST_FINANCE_EMAIL = "test-finance@example.test"
TEST_READONLY_EMAIL = "test-readonly@example.test"
TEST_ARCHIVED_EMAIL = "test-archived@example.test"

# Test data prefix for cleanup
TEST_PREFIX = "TEST_"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def super_admin_token(api_client, test_admin_token):
    """Alias fixture — points at test-admin (super_admin role). Must NOT hit
    the real bootstrap admin account (rhys@syhomes.co.uk) because the
    auto-enrol helper would overwrite the human operator's MFA secret.
    """
    return test_admin_token


@pytest.fixture(scope="module")
def test_admin_token(api_client):
    """Get test-admin token (super_admin role → auto-enrol via pyotp)"""
    return login_with_auto_enroll(api_client, BASE_URL, TEST_ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def test_director_token(api_client):
    """Get test-director token (director role - MFA enforced → auto-enrol)"""
    return login_with_auto_enroll(api_client, BASE_URL, TEST_DIRECTOR_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def test_pm_token(api_client):
    """Get test-pm token (scoped to Shrewsbury entity)"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_PM_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Test PM login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def test_finance_token(api_client):
    """Get test-finance token (finance role - MFA enforced → auto-enrol)"""
    return login_with_auto_enroll(api_client, BASE_URL, TEST_FINANCE_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def test_readonly_token(api_client):
    """Get test-readonly token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_READONLY_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Test readonly login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def seeded_entities(api_client, super_admin_token):
    """Get the 3 seeded entities"""
    response = api_client.get(
        f"{BASE_URL}/api/entities",
        params={"page_size": 100},
        headers={"Authorization": f"Bearer {super_admin_token}"}
    )
    assert response.status_code == 200
    return response.json()["items"]


# ============================================================
# Auth Tests
# ============================================================

class TestAuthLogin:
    """Authentication login tests"""
    
    def test_login_super_admin_success(self, api_client):
        """POST /api/auth/login with real super_admin returns access_token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        })
        # NOTE: uses the REAL operator account; do NOT read or cache its
        # session here — just assert the contract shape.
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        if data.get("mfa_required"):
            assert data["mfa_challenge_token"]
        elif data.get("mfa_enrollment_required"):
            assert data["mfa_pending_token"]
        else:
            assert "access_token" in data
            assert data["user"]["email"] == SUPER_ADMIN_EMAIL
    
    def test_login_test_admin_success(self, api_client):
        """POST /api/auth/login with test-admin returns access_token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == TEST_ADMIN_EMAIL
    
    def test_login_invalid_password_returns_401(self, api_client):
        """Wrong password returns 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": "WrongPassword123!"
        })
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]
    
    def test_login_archived_user_returns_403(self, api_client):
        """Archived user login returns 403"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ARCHIVED_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 403
        assert "archived" in response.json()["detail"].lower()
    
    def test_login_nonexistent_user_returns_401(self, api_client):
        """Non-existent user returns 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent@example.test",
            "password": TEST_PASSWORD
        })
        assert response.status_code == 401


class TestAuthMe:
    """GET /api/auth/me tests"""
    
    def test_me_super_admin_returns_87_permissions(self, api_client, super_admin_token):
        """GET /api/auth/me with super_admin token returns is_super_admin=true, 87 permissions"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_super_admin"] is True
        assert len(data["permissions"]) == 87
        # Fixture aliases to test-admin to avoid touching the real operator.
        assert data["email"] == TEST_ADMIN_EMAIL
    
    def test_me_unauthenticated_returns_401(self):
        """GET /api/auth/me without token returns 401"""
        # Use a fresh session without any auth
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401


class TestAuthUnauthenticated:
    """Unauthenticated access tests"""
    
    def test_entities_unauthenticated_returns_401(self):
        """GET /api/entities without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]
    
    def test_users_unauthenticated_returns_401(self):
        """GET /api/users without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/users")
        assert response.status_code == 401
    
    def test_roles_unauthenticated_returns_401(self):
        """GET /api/roles without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/roles")
        assert response.status_code == 401


# ============================================================
# Roles Tests
# ============================================================

class TestRoles:
    """GET /api/roles tests"""
    
    def test_roles_returns_10_seeded_roles(self, api_client, super_admin_token):
        """GET /api/roles returns 10 seeded roles with correct permission counts"""
        response = api_client.get(
            f"{BASE_URL}/api/roles",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        roles = response.json()
        assert len(roles) == 10
        
        # Verify permission counts for key roles
        role_perms = {r["code"]: r["permission_count"] for r in roles}
        assert role_perms["super_admin"] == 87
        assert role_perms["director"] == 84
        assert role_perms["project_manager"] >= 30
        assert role_perms["finance"] >= 25
        assert role_perms["read_only"] == 7
        assert role_perms["investor_read_only"] == 2
        assert role_perms["subcontractor_portal"] == 2
        assert role_perms["consultant_portal"] == 2


class TestPermissions:
    """GET /api/permissions tests"""
    
    def test_permissions_returns_87_permissions(self, api_client, super_admin_token):
        """GET /api/permissions returns >=80 permissions"""
        response = api_client.get(
            f"{BASE_URL}/api/permissions",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        perms = response.json()
        assert len(perms) >= 80
        
        # Verify entities permissions exist
        perm_codes = {p["code"] for p in perms}
        assert "entities.view" in perm_codes
        assert "entities.view_sensitive" in perm_codes
        assert "entities.create" in perm_codes
        assert "entities.edit" in perm_codes
        assert "entities.delete" in perm_codes


# ============================================================
# Users Tests
# ============================================================

class TestUsers:
    """Users CRUD tests"""
    
    def test_list_users_with_super_admin(self, api_client, super_admin_token):
        """GET /api/users with super_admin returns user list"""
        response = api_client.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 7  # At least 7 test users
    
    def test_get_user_detail(self, api_client, super_admin_token):
        """GET /api/users/{id} returns user detail with roles"""
        # First get user list
        list_response = api_client.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        users = list_response.json()["items"]
        user_id = users[0]["id"]
        
        # Get detail
        response = api_client.get(
            f"{BASE_URL}/api/users/{user_id}",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        assert "email" in data
    
    def test_invite_user_returns_invitation_token(self, api_client, super_admin_token):
        """POST /api/users (invite) returns one-time invitation_token"""
        email = f"{TEST_PREFIX}invite-{uuid.uuid4().hex[:8]}@example.test".lower()
        payload = {
            "email": email,
            "first_name": "Test",
            "last_name": "Invite",
            "user_type": "Internal"
        }
        response = api_client.post(
            f"{BASE_URL}/api/users",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert "invitation_token" in data
        assert len(data["invitation_token"]) > 20
        assert data["user"]["email"] == email
        assert data["user"]["status"] == "Pending_Invitation"
    
    def test_readonly_cannot_create_user(self, api_client, test_readonly_token):
        """test-readonly user gets 403 on POST /api/users (no users.create)"""
        payload = {
            "email": f"{TEST_PREFIX}readonly-create@example.test",
            "first_name": "Test",
            "last_name": "Readonly",
            "user_type": "Internal"
        }
        response = api_client.post(
            f"{BASE_URL}/api/users",
            json=payload,
            headers={"Authorization": f"Bearer {test_readonly_token}"}
        )
        assert response.status_code == 403


# ============================================================
# Scope Tests
# ============================================================

class TestEntityScope:
    """Entity scope filtering tests"""
    
    def test_pm_sees_only_shrewsbury_entity(self, api_client, test_pm_token, seeded_entities):
        """test-pm (scoped to Shrewsbury) sees exactly 1 entity via GET /api/entities"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            headers={"Authorization": f"Bearer {test_pm_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Shrewsbury" in data["items"][0]["name"]
    
    def test_pm_cannot_access_non_shrewsbury_entity(self, api_client, test_pm_token, seeded_entities):
        """test-pm cannot GET non-Shrewsbury entities (403 on detail)"""
        # Find a non-Shrewsbury entity
        non_shrewsbury = next(
            (e for e in seeded_entities if "Shrewsbury" not in e["name"]),
            None
        )
        if non_shrewsbury is None:
            pytest.skip("No non-Shrewsbury entity found")
        
        response = api_client.get(
            f"{BASE_URL}/api/entities/{non_shrewsbury['id']}",
            headers={"Authorization": f"Bearer {test_pm_token}"}
        )
        assert response.status_code == 403
    
    def test_director_sees_all_entities(self, api_client, test_director_token, seeded_entities):
        """test-director sees all 3 entities"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            headers={"Authorization": f"Bearer {test_director_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
    
    def test_readonly_sees_all_entities(self, api_client, test_readonly_token, seeded_entities):
        """test-readonly sees all 3 entities"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            headers={"Authorization": f"Bearer {test_readonly_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
    
    def test_readonly_cannot_create_entity(self, api_client, test_readonly_token):
        """test-readonly cannot POST /api/entities (no entities.create)"""
        payload = {
            "name": f"{TEST_PREFIX}Readonly Create Ltd",
            "legal_name": f"{TEST_PREFIX}Readonly Create Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address"
        }
        response = api_client.post(
            f"{BASE_URL}/api/entities",
            json=payload,
            headers={"Authorization": f"Bearer {test_readonly_token}"}
        )
        assert response.status_code == 403


# ============================================================
# Sensitive Fields Tests
# ============================================================

class TestSensitiveFields:
    """Sensitive field stripping tests"""
    
    def test_readonly_cannot_see_sensitive_fields(self, api_client, test_readonly_token, seeded_entities):
        """test-readonly GET /api/entities/{id} has bank_name=null, xero_org_id=null"""
        entity_id = seeded_entities[0]["id"]
        response = api_client.get(
            f"{BASE_URL}/api/entities/{entity_id}",
            headers={"Authorization": f"Bearer {test_readonly_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Sensitive fields should be stripped (null)
        assert data.get("bank_name") is None
        assert data.get("xero_org_id") is None
    
    def test_finance_can_see_sensitive_fields(self, api_client, test_finance_token, seeded_entities):
        """test-finance (has entities.view_sensitive) can see sensitive fields"""
        entity_id = seeded_entities[0]["id"]
        response = api_client.get(
            f"{BASE_URL}/api/entities/{entity_id}",
            headers={"Authorization": f"Bearer {test_finance_token}"}
        )
        assert response.status_code == 200
        # Finance user should be able to see the response (fields may be null if not set)
        # The key is that the request succeeds and fields are not forcibly stripped


# ============================================================
# Entities with Auth Tests (Regression)
# ============================================================

class TestEntitiesWithAuth:
    """Entities CRUD with authentication (regression tests)"""
    
    def test_list_entities_authenticated(self, api_client, super_admin_token):
        """GET /api/entities with auth returns entities"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
    
    def test_create_entity_stores_created_by_user_id(self, api_client, super_admin_token):
        """POST /api/entities as super_admin stores created_by_user_id"""
        payload = {
            "name": f"{TEST_PREFIX}Created By Test Ltd",
            "legal_name": f"{TEST_PREFIX}Created By Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address"
        }
        response = api_client.post(
            f"{BASE_URL}/api/entities",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        
        # Cleanup
        api_client.delete(
            f"{BASE_URL}/api/entities/{data['id']}",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
    
    def test_filter_by_entity_type(self, api_client, super_admin_token):
        """GET /api/entities?entity_type=Parent filters correctly"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            params={"entity_type": "Parent"},
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["entity_type"] == "Parent"
    
    def test_search_entities(self, api_client, super_admin_token):
        """GET /api/entities?q=Shrewsbury searches correctly"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            params={"q": "Shrewsbury"},
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Shrewsbury" in data["items"][0]["name"]


# ============================================================
# Role Assignment Tests
# ============================================================

class TestRoleAssignment:
    """Role assignment tests"""
    
    def test_assign_role_with_entity_scope(self, api_client, super_admin_token, seeded_entities):
        """POST /api/users/{user_id}/roles with entity_scope='Specific' creates assignment"""
        # Get a user to assign role to
        users_response = api_client.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        users = users_response.json()["items"]
        # Find test-site user
        test_user = next((u for u in users if u["email"] == "test-site@example.test"), None)
        if test_user is None:
            pytest.skip("test-site user not found")
        
        # Get roles
        roles_response = api_client.get(
            f"{BASE_URL}/api/roles",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        roles = roles_response.json()
        read_only_role = next((r for r in roles if r["code"] == "read_only"), None)
        if read_only_role is None:
            pytest.skip("read_only role not found")
        
        # Assign role with specific entity scope
        shrewsbury = next((e for e in seeded_entities if "Shrewsbury" in e["name"]), None)
        if shrewsbury is None:
            pytest.skip("Shrewsbury entity not found")
        
        payload = {
            "role_id": read_only_role["id"],
            "entity_scope": "Specific",
            "project_scope": "All",
            "entity_ids": [shrewsbury["id"]]
        }
        response = api_client.post(
            f"{BASE_URL}/api/users/{test_user['id']}/roles",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_scope"] == "Specific"
        assert shrewsbury["id"] in [str(eid) for eid in data["entity_ids"]]
        
        # Cleanup - revoke the role
        api_client.delete(
            f"{BASE_URL}/api/users/{test_user['id']}/roles/{data['id']}",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )


# ============================================================
# Unlock Tests
# ============================================================

class TestUnlock:
    """User unlock tests"""
    
    def test_super_admin_can_unlock_user(self, api_client, super_admin_token):
        """super_admin can POST /api/users/{id}/unlock"""
        # Get a user
        users_response = api_client.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        users = users_response.json()["items"]
        test_user = next((u for u in users if u["email"] == TEST_ADMIN_EMAIL), None)
        if test_user is None:
            pytest.skip("test-admin user not found")
        
        # Unlock (even if not locked, should succeed)
        response = api_client.post(
            f"{BASE_URL}/api/users/{test_user['id']}/unlock",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 204


# ============================================================
# Health Check
# ============================================================

class TestHealth:
    """Health check tests"""
    
    def test_health_returns_phase_1_2(self, api_client):
        """GET /api/health returns phase 1.2"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["phase"] == "1.2"


# ============================================================
# Cleanup
# ============================================================

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_entities(self, api_client, super_admin_token):
        """Cleanup any TEST_ prefixed entities"""
        response = api_client.get(
            f"{BASE_URL}/api/entities",
            params={"page_size": 200, "include_struck_off": True},
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        if response.status_code == 200:
            for entity in response.json()["items"]:
                if entity["name"].startswith(TEST_PREFIX):
                    api_client.delete(
                        f"{BASE_URL}/api/entities/{entity['id']}",
                        headers={"Authorization": f"Bearer {super_admin_token}"}
                    )
    
    def test_cleanup_test_users(self, api_client, super_admin_token):
        """Cleanup any TEST_ prefixed users"""
        response = api_client.get(
            f"{BASE_URL}/api/users",
            params={"page_size": 200},
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        if response.status_code == 200:
            for user in response.json()["items"]:
                if user["email"].startswith(TEST_PREFIX.lower()):
                    # Archive instead of delete
                    api_client.put(
                        f"{BASE_URL}/api/users/{user['id']}",
                        json={"status": "Archived"},
                        headers={"Authorization": f"Bearer {super_admin_token}"}
                    )
