"""Backend tests for password complexity rules (Prompt 1.2 close-out patch).

Migrated to cookies-only transport (audit remediation C1 — Feb 2026).
"""
from __future__ import annotations

import os
import pytest
import requests

from tests.conftest import plain_login, login_with_auto_enroll


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://robust-foundation-2.preview.emergentagent.com"
)

READONLY_EMAIL = "test-readonly@example.test"
ADMIN_EMAIL = "test-admin@example.test"
DEFAULT_PASSWORD = "TestUser-Dev-2026!"


@pytest.fixture(scope="module")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def readonly(anon_client):
    return plain_login(BASE_URL, READONLY_EMAIL, DEFAULT_PASSWORD)


def _try_change(session, current, new):
    return session.post(
        f"{BASE_URL}/api/auth/password/change",
        json={"current_password": current, "new_password": new},
    )


class TestPasswordPolicyEndpoint:
    def test_policy_endpoint_lists_5_rules(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/auth/password-policy")
        assert r.status_code == 200
        data = r.json()
        codes = {rule["code"] for rule in data["rules"]}
        assert codes == {"length", "uppercase", "lowercase", "number", "symbol"}
        assert data["history_size"] == 5


class TestPasswordComplexity:
    """Each weak example breaks exactly one rule the policy enforces."""

    def test_too_short_rejects(self, readonly):
        r = _try_change(readonly, DEFAULT_PASSWORD, "Ab1!xyz")
        assert r.status_code == 422
        assert "12 characters" in r.json()["detail"]

    def test_missing_uppercase_rejects(self, readonly):
        r = _try_change(readonly, DEFAULT_PASSWORD, "password123456")
        assert r.status_code == 422
        assert "uppercase" in r.json()["detail"].lower()

    def test_missing_lowercase_rejects(self, readonly):
        r = _try_change(readonly, DEFAULT_PASSWORD, "PASSWORD1234!")
        assert r.status_code == 422
        assert "lowercase" in r.json()["detail"].lower()

    def test_missing_number_rejects(self, readonly):
        r = _try_change(readonly, DEFAULT_PASSWORD, "PasswordNoNums!")
        assert r.status_code == 422
        assert "number" in r.json()["detail"].lower()

    def test_missing_symbol_rejects(self, readonly):
        r = _try_change(readonly, DEFAULT_PASSWORD, "Password123456")
        assert r.status_code == 422
        assert "symbol" in r.json()["detail"].lower()

    def test_strong_password_accepts(self, readonly):
        r = _try_change(readonly, DEFAULT_PASSWORD, "MyStr0ng!Pass")
        assert r.status_code == 204

        # Revert to the deterministic seed password via DB (bypassing history).
        import os as _os
        from sqlalchemy import create_engine, text
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from app.auth.passwords import hash_password
        e = create_engine(_os.environ["DATABASE_URL"])
        with e.begin() as c:
            c.execute(
                text("UPDATE users SET password_hash=:h, password_history='[]'::jsonb WHERE email=:em"),
                {"h": hash_password(DEFAULT_PASSWORD), "em": READONLY_EMAIL},
            )


class TestUnlockEndpoint:
    """Admin unlock — exercises the permission gate, lock requirement,
    and audit stamp on admin_notes.
    """

    def test_unlock_locked_user_succeeds(self, anon_client):
        # 1. Lock test-readonly via 5 failed logins (anon client).
        for _ in range(5):
            anon_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": READONLY_EMAIL, "password": "wrong"},
            )

        # 2. Admin session (auto-enrol MFA).
        admin = login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, DEFAULT_PASSWORD)

        # 3. Find test-readonly in the list and confirm it's locked.
        lst = admin.get(f"{BASE_URL}/api/users").json()
        ro = next(u for u in lst["items"] if u["email"] == READONLY_EMAIL)
        assert ro["locked_until"] is not None

        # 4. Unlock.
        r = admin.post(f"{BASE_URL}/api/users/{ro['id']}/unlock")
        assert r.status_code == 204

        # 5. Verify list + detail now show the user unlocked.
        detail = admin.get(f"{BASE_URL}/api/users/{ro['id']}").json()
        assert detail["locked_until"] is None
        assert detail["failed_login_attempts"] == 0
        assert "Unlocked by" in (detail["admin_notes"] or "")

        # 6. Second unlock now returns 400 (user is not locked).
        r2 = admin.post(f"{BASE_URL}/api/users/{ro['id']}/unlock")
        assert r2.status_code == 400
        assert "not locked" in r2.json()["detail"].lower()

    def test_unlock_without_permission_forbidden(self, readonly):
        # Readonly has no users.admin; try unlocking self.
        me = readonly.get(f"{BASE_URL}/api/auth/me").json()
        r = readonly.post(f"{BASE_URL}/api/users/{me['id']}/unlock")
        assert r.status_code == 403
