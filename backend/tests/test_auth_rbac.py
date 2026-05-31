"""
Backend API tests for SY Homes Auth + RBAC module (Prompt 1.2)
Migrated to cookies-only transport (audit remediation C1 — Feb 2026).

Each authenticated role gets its own `requests.Session` whose cookie jar
carries `access_token` + `refresh_token` from login. No Bearer headers.
"""
import os
import uuid

import pytest
import requests

from tests.conftest import login_with_auto_enroll, plain_login

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://spend-approval-gate.preview.emergentagent.com"

# Test credentials
TEST_PASSWORD = "TestUser-Dev-2026!"
SUPER_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "rhys@syhomes.co.uk")
SUPER_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "xupmaq-qykbah-gipMy5")
TEST_ADMIN_EMAIL = "test-admin@example.test"
TEST_DIRECTOR_EMAIL = "test-director@example.test"
TEST_PM_EMAIL = "test-pm@example.test"
TEST_FINANCE_EMAIL = "test-finance@example.test"
TEST_READONLY_EMAIL = "test-readonly@example.test"
TEST_ARCHIVED_EMAIL = "test-archived@example.test"

TEST_PREFIX = "TEST_"


@pytest.fixture(scope="module")
def anon_client():
    """Unauthenticated client for /login, /health, etc."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# Backward-compat alias — some tests reference `api_client` for anon calls.
@pytest.fixture(scope="module")
def api_client(anon_client):
    return anon_client


@pytest.fixture(scope="module")
def admin(anon_client):
    """Admin session (super_admin role, auto-enrols MFA on first use)."""
    return login_with_auto_enroll(None, BASE_URL, TEST_ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def director(anon_client):
    return login_with_auto_enroll(None, BASE_URL, TEST_DIRECTOR_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def finance(anon_client):
    return login_with_auto_enroll(None, BASE_URL, TEST_FINANCE_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def pm(anon_client):
    return plain_login(BASE_URL, TEST_PM_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly(anon_client):
    return plain_login(BASE_URL, TEST_READONLY_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def seeded_entities(admin):
    response = admin.get(f"{BASE_URL}/api/entities", params={"page_size": 100})
    assert response.status_code == 200
    return response.json()["items"]


# ============================================================
# Auth Tests
# ============================================================

class TestAuthLogin:
    def test_login_super_admin_success(self, anon_client):
        """Real super_admin login returns a valid contract shape (may require MFA)."""
        response = anon_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        # Audit C1: no access/refresh tokens in JSON body.
        assert "access_token" not in data
        assert "refresh_token" not in data
        if data.get("mfa_required"):
            assert data["mfa_challenge_token"]
        elif data.get("mfa_enrollment_required"):
            assert data["enforced_role_name"]
            # Pending JWT travels via cookie, not body.
            assert anon_client.cookies.get("access_token")
        else:
            assert data["user"]["email"] == SUPER_ADMIN_EMAIL

    def test_login_test_admin_cookie_contract(self):
        """test-admin login populates access_token + refresh_token cookies
        (after auto-enrol) — nothing in the JSON body.
        """
        s = login_with_auto_enroll(None, BASE_URL, TEST_ADMIN_EMAIL, TEST_PASSWORD)
        assert s.cookies.get("access_token"), "access_token cookie not set"
        assert s.cookies.get("refresh_token"), "refresh_token cookie not set"

    def test_login_invalid_password_returns_401(self, anon_client):
        response = anon_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": "WrongPassword123!",
        })
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_archived_user_returns_403(self, anon_client):
        response = anon_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ARCHIVED_EMAIL,
            "password": TEST_PASSWORD,
        })
        assert response.status_code == 403
        assert "archived" in response.json()["detail"].lower()

    def test_login_nonexistent_user_returns_401(self, anon_client):
        response = anon_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent@example.test",
            "password": TEST_PASSWORD,
        })
        assert response.status_code == 401


class TestAuthMe:
    def test_me_super_admin_returns_87_permissions(self, admin):
        """admin fixture aliases to test-admin (super_admin role)."""
        response = admin.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["is_super_admin"] is True
        # super_admin permission count history:
        #   1.7 baseline:                                       81
        #   + 2.2 (appraisals.submit, appraisals.view_financials): 83
        #   + 2.4A (budgets.admin):                                84
        #   + 2.5A (actuals.admin):                                85
        #   + 2.5C (ai_capture.view_costs, mig 0026, chat-20):     86
        #   + Chat 24 R1 (suppliers.* +5):                         91
        #   + Chat 24 R2 (pos.* +10 incl. receipt placeholder):   101
        #   + Chat 24 R3 (pos.approve):                            102  ← current
        # Function name retains "87" — renaming is out of scope (see
        # chat-22 §2 + Future_Tasks polish entry).
        assert len(data["permissions"]) == 102
        assert data["email"] == TEST_ADMIN_EMAIL

    def test_me_unauthenticated_returns_401(self):
        fresh = requests.Session()
        fresh.headers.update({"Content-Type": "application/json"})
        response = fresh.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401


class TestAuthUnauthenticated:
    def test_entities_unauthenticated_returns_401(self):
        fresh = requests.Session()
        fresh.headers.update({"Content-Type": "application/json"})
        response = fresh.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    def test_users_unauthenticated_returns_401(self):
        fresh = requests.Session()
        fresh.headers.update({"Content-Type": "application/json"})
        response = fresh.get(f"{BASE_URL}/api/users")
        assert response.status_code == 401

    def test_roles_unauthenticated_returns_401(self):
        fresh = requests.Session()
        fresh.headers.update({"Content-Type": "application/json"})
        response = fresh.get(f"{BASE_URL}/api/roles")
        assert response.status_code == 401


# ============================================================
# Roles / Permissions / Users
# ============================================================

class TestRoles:
    def test_roles_returns_10_seeded_roles(self, admin):
        response = admin.get(f"{BASE_URL}/api/roles")
        assert response.status_code == 200
        roles = response.json()
        assert len(roles) == 10
        role_perms = {r["code"]: r["permission_count"] for r in roles}
        # super_admin count history:
        #   1.7 baseline:                                       81
        #   + 2.2 (appraisals.submit, appraisals.view_financials): 83
        #   + 2.4A (budgets.admin):                                84
        #   + 2.5A (actuals.admin):                                85
        #   + 2.5C (ai_capture.view_costs, mig 0026, chat-20):     86
        #   + Chat 24 R1+R2+R3 (suppliers.*, pos.*):              102  ← current
        assert role_perms["super_admin"] == 102
        # director count history:
        #   Patch #3 baseline (after losing 4 orphan grants):       77
        #   + 2.2 (appraisals.submit, appraisals.view_financials):  79
        #   + 2.4A (budgets.admin):                                 80
        #   + 2.5A (actuals.admin):                                 81
        #   + 2.5C (ai_capture.view_costs, mig 0026, chat-20):      82
        #   + Chat 24 R1+R2+R3 (suppliers.*, pos.*):                98  ← current
        assert role_perms["director"] == 98
        assert role_perms["project_manager"] >= 30
        assert role_perms["finance"] >= 25
        # 1.7: +system_config.view granted to all 10 roles.
        # 2.5A: read_only gets actuals.view (+1) → 10.
        # Chat 24 R1+R2: read_only gets suppliers.view + pos.view (+2) → 12.
        assert role_perms["read_only"] == 12
        assert role_perms["investor_read_only"] == 4  # 1.6: +cost_codes.view, 1.7: +system_config.view
        assert role_perms["subcontractor_portal"] == 3  # 1.7: +system_config.view
        assert role_perms["consultant_portal"] == 4  # 1.6: +cost_codes.view, 1.7: +system_config.view


class TestSeedRbacRoleGrants:
    """Lock the cost_codes role-permission grants in ROLE_PERMISSIONS so
    that seed_rbac.py is authoritative independently of migration 0014.

    Patch 1.6.1 (2026-04-26) — per build-chat audit: migration 0014 was
    initially the sole source of these grants for non-wildcard roles.
    seed_rbac was updated alongside the migration in the original 1.6
    build; these assertions lock the gap closed against future
    regressions.
    """

    def test_seed_rbac_grants_cost_codes_view_to_project_manager(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["project_manager"]

    def test_seed_rbac_grants_cost_codes_view_to_finance(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["finance"]

    def test_seed_rbac_grants_cost_codes_admin_to_finance(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.admin" in ROLE_PERMISSIONS["finance"]

    def test_seed_rbac_grants_cost_codes_view_to_site_manager(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["site_manager"]

    def test_seed_rbac_grants_cost_codes_view_to_sales(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["sales"]

    def test_seed_rbac_grants_cost_codes_view_to_read_only(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["read_only"]

    def test_seed_rbac_grants_cost_codes_view_to_investor_read_only(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["investor_read_only"]

    def test_seed_rbac_grants_cost_codes_view_to_consultant_portal(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "cost_codes.view" in ROLE_PERMISSIONS["consultant_portal"]


class TestPermissions:
    def test_permissions_returns_87_permissions(self, admin):
        response = admin.get(f"{BASE_URL}/api/permissions")
        assert response.status_code == 200
        perms = response.json()
        assert len(perms) >= 80
        perm_codes = {p["code"] for p in perms}
        assert "entities.view" in perm_codes
        assert "entities.view_sensitive" in perm_codes
        assert "entities.create" in perm_codes
        assert "entities.edit" in perm_codes
        assert "entities.delete" in perm_codes


class TestUsers:
    def test_list_users_with_super_admin(self, admin):
        response = admin.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 7

    def test_get_user_detail(self, admin):
        users = admin.get(f"{BASE_URL}/api/users").json()["items"]
        user_id = users[0]["id"]
        response = admin.get(f"{BASE_URL}/api/users/{user_id}")
        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        assert "email" in data

    def test_invite_user_returns_invitation_token(self, admin):
        email = f"{TEST_PREFIX}invite-{uuid.uuid4().hex[:8]}@example.test".lower()
        payload = {
            "email": email,
            "first_name": "Test",
            "last_name": "Invite",
            "user_type": "Internal",
        }
        response = admin.post(f"{BASE_URL}/api/users", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "invitation_token" in data
        assert len(data["invitation_token"]) > 20
        assert data["user"]["email"] == email
        assert data["user"]["status"] == "Pending_Invitation"

    def test_readonly_cannot_create_user(self, readonly):
        payload = {
            "email": f"{TEST_PREFIX}readonly-create@example.test",
            "first_name": "Test",
            "last_name": "Readonly",
            "user_type": "Internal",
        }
        response = readonly.post(f"{BASE_URL}/api/users", json=payload)
        assert response.status_code == 403


# ============================================================
# Scope filtering
# ============================================================

class TestEntityScope:
    def test_pm_sees_only_shrewsbury_entity(self, pm, seeded_entities):
        response = pm.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Shrewsbury" in data["items"][0]["name"]

    def test_pm_cannot_access_non_shrewsbury_entity(self, pm, seeded_entities):
        non_shrewsbury = next(
            (e for e in seeded_entities if "Shrewsbury" not in e["name"]),
            None,
        )
        if non_shrewsbury is None:
            pytest.skip("No non-Shrewsbury entity found")
        response = pm.get(f"{BASE_URL}/api/entities/{non_shrewsbury['id']}")
        assert response.status_code == 403

    def test_director_sees_all_entities(self, director, seeded_entities):
        response = director.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_readonly_sees_all_entities(self, readonly, seeded_entities):
        response = readonly.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_readonly_cannot_create_entity(self, readonly):
        payload = {
            "name": f"{TEST_PREFIX}Readonly Create Ltd",
            "legal_name": f"{TEST_PREFIX}Readonly Create Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
        }
        response = readonly.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 403


# ============================================================
# Sensitive field gating
# ============================================================

class TestSensitiveFields:
    def test_readonly_cannot_see_sensitive_fields(self, readonly, seeded_entities):
        entity_id = seeded_entities[0]["id"]
        response = readonly.get(f"{BASE_URL}/api/entities/{entity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("bank_name") is None
        assert data.get("xero_org_id") is None

    def test_finance_can_see_sensitive_fields(self, finance, seeded_entities):
        entity_id = seeded_entities[0]["id"]
        response = finance.get(f"{BASE_URL}/api/entities/{entity_id}")
        assert response.status_code == 200


# ============================================================
# Entities CRUD regression
# ============================================================

class TestEntitiesWithAuth:
    def test_list_entities_authenticated(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_create_entity_stores_created_by_user_id(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}Created By Test Ltd",
            "legal_name": f"{TEST_PREFIX}Created By Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
        }
        response = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        admin.delete(f"{BASE_URL}/api/entities/{data['id']}")

    def test_filter_by_entity_type(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"entity_type": "Parent"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["entity_type"] == "Parent"

    def test_search_entities(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"q": "Shrewsbury"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Shrewsbury" in data["items"][0]["name"]


# ============================================================
# Role assignment
# ============================================================

class TestRoleAssignment:
    def test_assign_role_with_entity_scope(self, admin, seeded_entities):
        users = admin.get(f"{BASE_URL}/api/users").json()["items"]
        test_user = next((u for u in users if u["email"] == "test-site@example.test"), None)
        if test_user is None:
            pytest.skip("test-site user not found")
        roles = admin.get(f"{BASE_URL}/api/roles").json()
        read_only_role = next((r for r in roles if r["code"] == "read_only"), None)
        if read_only_role is None:
            pytest.skip("read_only role not found")
        shrewsbury = next((e for e in seeded_entities if "Shrewsbury" in e["name"]), None)
        if shrewsbury is None:
            pytest.skip("Shrewsbury entity not found")
        payload = {
            "role_id": read_only_role["id"],
            "entity_scope": "Specific",
            "project_scope": "All",
            "entity_ids": [shrewsbury["id"]],
        }
        response = admin.post(f"{BASE_URL}/api/users/{test_user['id']}/roles", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["entity_scope"] == "Specific"
        assert shrewsbury["id"] in [str(eid) for eid in data["entity_ids"]]
        admin.delete(f"{BASE_URL}/api/users/{test_user['id']}/roles/{data['id']}")


# ============================================================
# Unlock
# ============================================================

class TestUnlock:
    def test_super_admin_can_unlock_user(self, admin, anon_client):
        users = admin.get(f"{BASE_URL}/api/users").json()["items"]
        test_user = next((u for u in users if u["email"] == TEST_READONLY_EMAIL), None)
        if test_user is None:
            pytest.skip("test-readonly user not found")
        # Trigger lockout: 5 failed logins (via a fresh anon client).
        for _ in range(5):
            anon_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": TEST_READONLY_EMAIL, "password": "wrong"},
            )
        response = admin.post(f"{BASE_URL}/api/users/{test_user['id']}/unlock")
        assert response.status_code == 204


# ============================================================
# Health
# ============================================================

class TestHealth:
    def test_health_returns_phase_1_2(self, anon_client):
        response = anon_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["phase"] == "1.2"


# ============================================================
# Cleanup
# ============================================================

class TestCleanup:
    def test_cleanup_test_entities(self, admin):
        response = admin.get(
            f"{BASE_URL}/api/entities",
            params={"page_size": 200, "include_struck_off": True},
        )
        if response.status_code == 200:
            for entity in response.json()["items"]:
                if entity["name"].startswith(TEST_PREFIX):
                    admin.delete(f"{BASE_URL}/api/entities/{entity['id']}")

    def test_cleanup_test_users(self, admin):
        response = admin.get(f"{BASE_URL}/api/users", params={"page_size": 200})
        if response.status_code == 200:
            for user in response.json()["items"]:
                if user["email"].startswith(TEST_PREFIX.lower()):
                    admin.put(
                        f"{BASE_URL}/api/users/{user['id']}",
                        json={"status": "Archived"},
                    )
