"""Pytest config — loads backend .env before any app imports.

Also provides a session-scoped helper that logs in and auto-enrols MFA
for users holding an MFA-enforced role (super_admin / director / finance).
Those users cannot acquire a full access token without MFA under the
Prompt 1.2 gap-closure rules, so the fixture path must enrol them on
first use. The TOTP secret is cached in-process so subsequent logins in
the same pytest session can complete the MFA challenge instead of
skipping.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# Sanity check so tests fail fast with a clear message.
assert "DATABASE_URL" in os.environ, (
    "DATABASE_URL is not set; check /app/backend/.env"
)


# In-process per-session cache of TOTP secrets keyed by email.
# Populated when login_with_auto_enroll runs the enrolment flow so that
# follow-on logins (same session, different test module) can complete
# the MFA challenge without a fresh enrolment.
_MFA_SECRETS: dict[str, str] = {}


def login_with_auto_enroll(api_client, base_url: str, email: str, password: str) -> str:
    """Log in and return a full access token.

    - If the user is an MFA-enforced role that hasn't enrolled yet: run the
      enrolment flow (start → TOTP via pyotp → confirm) and return the full
      access token issued by /mfa/enroll/confirm. The secret is cached.
    - If the user is already enrolled AND we have a cached secret for them:
      complete the MFA challenge flow and return the resulting access token.
    - Otherwise: return the plain access token from the login response.
    """
    import pyotp

    r = api_client.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
    )
    if r.status_code != 200:
        import pytest
        pytest.skip(f"Login failed for {email}: {r.text}")
    data = r.json()

    if data.get("mfa_required"):
        # Already enrolled — need a live TOTP. Use the cached secret if we
        # have one from an earlier enrolment in this pytest session.
        secret = _MFA_SECRETS.get(email)
        if not secret:
            import pytest
            pytest.skip(
                f"{email} has MFA enabled but no cached secret is available. "
                f"Re-run `python scripts/seed_test_users.py` to reset, then "
                f"restart the test session."
            )
        challenge = data["mfa_challenge_token"]
        verify = api_client.post(
            f"{base_url}/api/auth/mfa/verify",
            json={
                "challenge_token": challenge,
                "code": pyotp.TOTP(secret).now(),
                "use_backup_code": False,
            },
        )
        assert verify.status_code == 200, f"mfa/verify failed: {verify.text}"
        return verify.json()["access_token"]

    if not data.get("mfa_enrollment_required"):
        return data["access_token"]

    # Enforced role + not enrolled → enrol via pyotp.
    pending = data["mfa_pending_token"]
    headers = {"Authorization": f"Bearer {pending}"}

    start = api_client.post(
        f"{base_url}/api/auth/mfa/enroll/start", headers=headers
    )
    assert start.status_code == 200, f"mfa/enroll/start failed: {start.text}"
    secret = start.json()["secret"]
    _MFA_SECRETS[email] = secret  # cache for this session

    confirm = api_client.post(
        f"{base_url}/api/auth/mfa/enroll/confirm",
        headers=headers,
        json={"secret": secret, "code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200, f"mfa/enroll/confirm failed: {confirm.text}"
    token = confirm.json().get("access_token")
    assert token, "Enrolment confirm did not return an access_token"
    return token
