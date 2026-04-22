"""Backend tests for admin user-edit endpoint (Prompt 1.2 close-out patch #2).

Covers:
  - 200 on successful edit, diff reflected on subsequent GET
  - admin_notes stamped with "[Edited by <email> (<id>) at ...: <fields>]"
  - 409 on email collision
  - 403 when caller lacks users.admin
  - Email change flips email_verified=false
  - Suspended user cannot log in; Active again → login works
  - Self-deactivation blocked (400)
"""
from __future__ import annotations

import os
import pytest
import requests

from tests.conftest import login_with_auto_enroll


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://construction-command-5.preview.emergentagent.com"
)

TEST_PASSWORD = "TestUser-Dev-2026!"
ADMIN_EMAIL = "test-admin@example.test"
READONLY_EMAIL = "test-readonly@example.test"
PM_EMAIL = "test-pm@example.test"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api_client):
    return login_with_auto_enroll(api_client, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly_token(api_client):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": READONLY_EMAIL, "password": TEST_PASSWORD},
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.text}")
    return r.json()["access_token"]


def _find_user(api_client, token, email):
    lst = api_client.get(
        f"{BASE_URL}/api/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    return next(u for u in lst["items"] if u["email"] == email)


class TestEditUserSuccessPath:
    def test_edit_first_name_phone_success(self, api_client, admin_token):
        u = _find_user(api_client, admin_token, READONLY_EMAIL)
        r = api_client.put(
            f"{BASE_URL}/api/users/{u['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"first_name": "Edited", "phone": "+441234567890"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["first_name"] == "Edited"
        assert data["phone"] == "+441234567890"

        # admin_notes stamped
        detail = api_client.get(
            f"{BASE_URL}/api/users/{u['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert "Edited by test-admin@example.test" in (detail["admin_notes"] or "")
        assert "first_name" in (detail["admin_notes"] or "")
        assert "phone" in (detail["admin_notes"] or "")

        # Revert name for downstream tests
        api_client.put(
            f"{BASE_URL}/api/users/{u['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"first_name": "Test", "phone": None},
        )

    def test_edit_email_flips_verified_false(self, api_client, admin_token):
        u = _find_user(api_client, admin_token, READONLY_EMAIL)
        new_email = "test-readonly-renamed@example.test"
        try:
            r = api_client.put(
                f"{BASE_URL}/api/users/{u['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"email": new_email},
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["email"] == new_email
            assert d["email_verified"] is False
        finally:
            # Restore original email
            api_client.put(
                f"{BASE_URL}/api/users/{u['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"email": READONLY_EMAIL},
            )


class TestEditUserCollision:
    def test_email_collision_returns_409(self, api_client, admin_token):
        u = _find_user(api_client, admin_token, READONLY_EMAIL)
        r = api_client.put(
            f"{BASE_URL}/api/users/{u['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": ADMIN_EMAIL},
        )
        assert r.status_code == 409
        assert "already in use" in r.json()["detail"].lower()


class TestEditUserPermission:
    def test_non_admin_gets_403(self, api_client, readonly_token, admin_token):
        u = _find_user(api_client, admin_token, READONLY_EMAIL)
        r = api_client.put(
            f"{BASE_URL}/api/users/{u['id']}",
            headers={"Authorization": f"Bearer {readonly_token}"},
            json={"first_name": "Hacker"},
        )
        assert r.status_code == 403
        assert "users.admin" in r.json()["detail"]


class TestEditUserStatusToggle:
    def test_suspended_user_cannot_login(self, api_client, admin_token):
        u = _find_user(api_client, admin_token, PM_EMAIL)
        try:
            # Suspend
            r = api_client.put(
                f"{BASE_URL}/api/users/{u['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": "Suspended"},
            )
            assert r.status_code == 200
            # Try to log in
            lr = api_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": PM_EMAIL, "password": TEST_PASSWORD},
            )
            assert lr.status_code == 403
            assert "suspended" in lr.json()["detail"].lower()
            # Reactivate
            r = api_client.put(
                f"{BASE_URL}/api/users/{u['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": "Active"},
            )
            assert r.status_code == 200
            # Login now works
            lr = api_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": PM_EMAIL, "password": TEST_PASSWORD},
            )
            assert lr.status_code == 200
        finally:
            # Defensive — ensure Active if something above threw
            api_client.put(
                f"{BASE_URL}/api/users/{u['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": "Active"},
            )

    def test_self_deactivation_blocked(self, api_client, admin_token):
        me = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        r = api_client.put(
            f"{BASE_URL}/api/users/{me['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "Suspended"},
        )
        assert r.status_code == 400
        assert "cannot deactivate" in r.json()["detail"].lower()

    def test_archive_via_put_rejected(self, api_client, admin_token):
        u = _find_user(api_client, admin_token, READONLY_EMAIL)
        r = api_client.put(
            f"{BASE_URL}/api/users/{u['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "Archived"},
        )
        assert r.status_code == 400
        assert "scrub_pii" in r.json()["detail"]
