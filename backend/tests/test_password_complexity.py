"""Backend tests for password complexity rules (Prompt 1.2 close-out patch).

Covers: policy endpoint, each complexity rule (length, uppercase, lowercase,
number, symbol) rejects weak, accepts strong. Uses a non-enforced role
(test-readonly) so the token path is clean.
"""
from __future__ import annotations

import os
import pytest
import requests


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://construction-command-5.preview.emergentagent.com"
)

READONLY_EMAIL = "test-readonly@example.test"
DEFAULT_PASSWORD = "TestUser-Dev-2026!"  # deterministic seed password
# Must be policy-compliant (12+, mixed, digit, symbol):
TEMP_STRONG = "TempDev-Password-Change-2026!"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def readonly_token(api_client):
    """Login as test-readonly (no MFA enforcement) → plain access token."""
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": READONLY_EMAIL, "password": DEFAULT_PASSWORD},
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.text}")
    return r.json()["access_token"]


def _try_change(api_client, token, current, new):
    return api_client.post(
        f"{BASE_URL}/api/auth/password/change",
        json={"current_password": current, "new_password": new},
        headers={"Authorization": f"Bearer {token}"},
    )


class TestPasswordPolicyEndpoint:
    def test_policy_endpoint_lists_5_rules(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/auth/password-policy")
        assert r.status_code == 200
        data = r.json()
        codes = {rule["code"] for rule in data["rules"]}
        assert codes == {"length", "uppercase", "lowercase", "number", "symbol"}
        assert data["history_size"] == 5


class TestPasswordComplexity:
    """Each weak example breaks exactly one rule the policy enforces."""

    def test_too_short_rejects(self, api_client, readonly_token):
        r = _try_change(api_client, readonly_token, DEFAULT_PASSWORD, "Ab1!xyz")
        assert r.status_code == 422
        assert "12 characters" in r.json()["detail"]

    def test_missing_uppercase_rejects(self, api_client, readonly_token):
        # password123456 — no uppercase, no symbol. Expect the uppercase error
        # (first rule checked after length).
        r = _try_change(api_client, readonly_token, DEFAULT_PASSWORD, "password123456")
        assert r.status_code == 422
        assert "uppercase" in r.json()["detail"].lower()

    def test_missing_lowercase_rejects(self, api_client, readonly_token):
        r = _try_change(api_client, readonly_token, DEFAULT_PASSWORD, "PASSWORD1234!")
        assert r.status_code == 422
        assert "lowercase" in r.json()["detail"].lower()

    def test_missing_number_rejects(self, api_client, readonly_token):
        r = _try_change(api_client, readonly_token, DEFAULT_PASSWORD, "PasswordNoNums!")
        assert r.status_code == 422
        assert "number" in r.json()["detail"].lower()

    def test_missing_symbol_rejects(self, api_client, readonly_token):
        r = _try_change(api_client, readonly_token, DEFAULT_PASSWORD, "Password123456")
        assert r.status_code == 422
        assert "symbol" in r.json()["detail"].lower()

    def test_strong_password_accepts(self, api_client, readonly_token):
        # MyStr0ng!Pass — exactly 13 chars, meets every rule.
        r = _try_change(api_client, readonly_token, DEFAULT_PASSWORD, "MyStr0ng!Pass")
        assert r.status_code == 204

        # Revert to the deterministic seed password via an intermediate (the
        # history table would otherwise block DEFAULT_PASSWORD on the way back).
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

    def test_unlock_locked_user_succeeds(self, api_client):
        # 1. Lock test-readonly via 5 failed logins
        for _ in range(5):
            api_client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": READONLY_EMAIL, "password": "wrong"},
            )

        # 2. Get an admin token (auto-enrol MFA via conftest helper)
        from tests.conftest import login_with_auto_enroll
        admin_token = login_with_auto_enroll(
            api_client, BASE_URL, "test-admin@example.test", DEFAULT_PASSWORD,
        )

        # 3. Find test-readonly in the list and confirm it's locked
        lst = api_client.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        ro = next(u for u in lst["items"] if u["email"] == READONLY_EMAIL)
        assert ro["locked_until"] is not None

        # 4. Unlock
        r = api_client.post(
            f"{BASE_URL}/api/users/{ro['id']}/unlock",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 204

        # 5. Verify list + detail now show the user unlocked
        detail = api_client.get(
            f"{BASE_URL}/api/users/{ro['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert detail["locked_until"] is None
        assert detail["failed_login_attempts"] == 0
        assert "Unlocked by" in (detail["admin_notes"] or "")

        # 6. Second unlock now returns 400 (user is not locked)
        r2 = api_client.post(
            f"{BASE_URL}/api/users/{ro['id']}/unlock",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r2.status_code == 400
        assert "not locked" in r2.json()["detail"].lower()

    def test_unlock_without_permission_forbidden(self, api_client, readonly_token):
        # Readonly account has no users.admin; try unlocking anyone.
        from app.auth.passwords import hash_password  # noqa: F401
        # Get another user's id via self /me
        me = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {readonly_token}"},
        ).json()
        r = api_client.post(
            f"{BASE_URL}/api/users/{me['id']}/unlock",
            headers={"Authorization": f"Bearer {readonly_token}"},
        )
        assert r.status_code == 403
