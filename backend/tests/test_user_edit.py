"""Backend tests for admin user-edit endpoint (Prompt 1.2 close-out patch #2).

Migrated to cookies-only transport (audit remediation C1 — Feb 2026).
"""
from __future__ import annotations

import os
import pytest
import requests

from tests.conftest import login_with_auto_enroll, plain_login


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://pg-heal.preview.emergentagent.com"
)

TEST_PASSWORD = "TestUser-Dev-2026!"
ADMIN_EMAIL = "test-admin@example.test"
READONLY_EMAIL = "test-readonly@example.test"
PM_EMAIL = "test-pm@example.test"


@pytest.fixture(scope="module")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly():
    return plain_login(BASE_URL, READONLY_EMAIL, TEST_PASSWORD)


def _find_user(session, email):
    lst = session.get(f"{BASE_URL}/api/users").json()
    return next(u for u in lst["items"] if u["email"] == email)


class TestEditUserSuccessPath:
    def test_edit_first_name_phone_success(self, admin):
        u = _find_user(admin, READONLY_EMAIL)
        r = admin.put(
            f"{BASE_URL}/api/users/{u['id']}",
            json={"first_name": "Edited", "phone": "+441234567890"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["first_name"] == "Edited"
        assert data["phone"] == "+441234567890"

        detail = admin.get(f"{BASE_URL}/api/users/{u['id']}").json()
        assert "Edited by test-admin@example.test" in (detail["admin_notes"] or "")
        assert "first_name" in (detail["admin_notes"] or "")
        assert "phone" in (detail["admin_notes"] or "")

        admin.put(
            f"{BASE_URL}/api/users/{u['id']}",
            json={"first_name": "Test", "phone": None},
        )

    def test_edit_email_flips_verified_false(self, admin):
        u = _find_user(admin, READONLY_EMAIL)
        new_email = "test-readonly-renamed@example.test"
        try:
            r = admin.put(
                f"{BASE_URL}/api/users/{u['id']}",
                json={"email": new_email},
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["email"] == new_email
            assert d["email_verified"] is False
        finally:
            admin.put(
                f"{BASE_URL}/api/users/{u['id']}",
                json={"email": READONLY_EMAIL},
            )


class TestEditUserCollision:
    def test_email_collision_returns_409(self, admin):
        u = _find_user(admin, READONLY_EMAIL)
        r = admin.put(
            f"{BASE_URL}/api/users/{u['id']}",
            json={"email": ADMIN_EMAIL},
        )
        assert r.status_code == 409
        assert "already in use" in r.json()["detail"].lower()


class TestEditUserPermission:
    def test_non_admin_gets_403(self, readonly, admin):
        u = _find_user(admin, READONLY_EMAIL)
        r = readonly.put(
            f"{BASE_URL}/api/users/{u['id']}",
            json={"first_name": "Hacker"},
        )
        assert r.status_code == 403
        assert "users.admin" in r.json()["detail"]


class TestEditUserStatusToggle:
    def test_suspended_user_cannot_login(self, admin, anon_client):
        u = _find_user(admin, PM_EMAIL)
        try:
            r = admin.put(
                f"{BASE_URL}/api/users/{u['id']}",
                json={"status": "Suspended"},
            )
            assert r.status_code == 200
            lr = anon_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": PM_EMAIL, "password": TEST_PASSWORD},
            )
            assert lr.status_code == 403
            assert "suspended" in lr.json()["detail"].lower()
            r = admin.put(
                f"{BASE_URL}/api/users/{u['id']}",
                json={"status": "Active"},
            )
            assert r.status_code == 200
            lr = anon_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": PM_EMAIL, "password": TEST_PASSWORD},
            )
            assert lr.status_code == 200
        finally:
            admin.put(
                f"{BASE_URL}/api/users/{u['id']}",
                json={"status": "Active"},
            )

    def test_self_deactivation_blocked(self, admin):
        me = admin.get(f"{BASE_URL}/api/auth/me").json()
        r = admin.put(
            f"{BASE_URL}/api/users/{me['id']}",
            json={"status": "Suspended"},
        )
        assert r.status_code == 400
        assert "cannot deactivate" in r.json()["detail"].lower()

    def test_archive_via_put_rejected(self, admin):
        u = _find_user(admin, READONLY_EMAIL)
        r = admin.put(
            f"{BASE_URL}/api/users/{u['id']}",
            json={"status": "Archived"},
        )
        assert r.status_code == 400
        assert "scrub_pii" in r.json()["detail"]
