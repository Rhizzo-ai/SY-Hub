"""Pytest config — loads backend .env before any app imports.

Provides a session-scoped helper that logs a user in under the new
cookies-only auth contract (audit remediation C1). The helper returns a
`requests.Session` whose cookie jar carries `access_token` + (optionally)
`refresh_token` — exactly what the production frontend will hold after
login. Tests should call methods on the returned session directly;
`Authorization: Bearer` headers are no longer used anywhere.

MFA-enforced roles (super_admin / director / finance) whose users haven't
enrolled yet are auto-enrolled via pyotp on first login. The TOTP secret
is cached in-process so subsequent logins in the same pytest session can
complete the MFA challenge instead of skipping.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# Sanity check so tests fail fast with a clear message.
assert "DATABASE_URL" in os.environ, (
    "DATABASE_URL is not set; check /app/backend/.env"
)


# In-process per-session cache of TOTP secrets keyed by email.
_MFA_SECRETS: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-process rate limiter between tests so bursts of login
    attempts in the suite don't trip the production limit. Tests that
    specifically exercise the limit should call enforce() themselves.
    """
    from app.services.rate_limit import rate_limiter
    rate_limiter.reset()
    yield


def _new_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def login_with_auto_enroll(_unused_client, base_url: str, email: str, password: str,
                           remember_me: bool = False) -> requests.Session:
    """Log in under the cookies-only contract and return a `requests.Session`.

    The returned session's cookie jar carries the access_token (and refresh
    token if the login path issued one). Callers use it like any other
    requests.Session — `s.get(...)`, `s.post(...)` — and auth rides
    transparently via cookies.

    The first positional argument is accepted but ignored so old call sites
    `login_with_auto_enroll(api_client, BASE_URL, email, pw)` keep working.
    Each call returns a *new* session so multi-user / multi-session tests
    don't cross-contaminate cookie jars.

    - If the user is an MFA-enforced role that hasn't enrolled yet: run the
      enrolment flow (start → TOTP via pyotp → confirm). The final session
      carries the full access + refresh cookies from /mfa/enroll/confirm.
    - If the user is already enrolled AND we have a cached secret for them:
      complete the mfa_challenge flow and return the verified session.
    - Otherwise: return the session populated by the plain /login response.
    """
    import pyotp

    s = _new_client()
    r = s.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password, "remember_me": remember_me},
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.text}")
    data = r.json()
    # Attach login metadata for tests that want to assert on user fields.
    setattr(s, "login_body", data)

    if data.get("mfa_required"):
        # Already enrolled — need a live TOTP. Use the cached secret if we
        # have one from an earlier enrolment in this pytest session.
        secret = _MFA_SECRETS.get(email)
        if not secret:
            pytest.skip(
                f"{email} has MFA enabled but no cached secret is available. "
                f"Re-run `python scripts/seed_test_users.py` to reset, then "
                f"restart the test session."
            )
        challenge = data["mfa_challenge_token"]
        verify = s.post(
            f"{base_url}/api/auth/mfa/verify",
            json={
                "challenge_token": challenge,
                "code": pyotp.TOTP(secret).now(),
                "use_backup_code": False,
            },
        )
        assert verify.status_code == 200, f"mfa/verify failed: {verify.text}"
        setattr(s, "login_body", verify.json())
        return s

    if not data.get("mfa_enrollment_required"):
        # Normal login — cookies already on the session.
        return s

    # Enforced role + not enrolled → enrol via pyotp.
    # The mfa_pending cookie was set on `s` by the /login response, so the
    # following calls ride on cookies (no Bearer header).
    start = s.post(f"{base_url}/api/auth/mfa/enroll/start")
    assert start.status_code == 200, f"mfa/enroll/start failed: {start.text}"
    secret = start.json()["secret"]
    _MFA_SECRETS[email] = secret  # cache for this session

    confirm = s.post(
        f"{base_url}/api/auth/mfa/enroll/confirm",
        json={"secret": secret, "code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200, f"mfa/enroll/confirm failed: {confirm.text}"
    body = confirm.json()
    assert body.get("session_issued") is True, (
        "Enrolment confirm did not issue a session; expected cookies to "
        "have been replaced with access_token + refresh_token."
    )
    # Cookies are now full-session access + refresh — ready to use.
    setattr(s, "login_body", body)
    return s


def plain_login(base_url: str, email: str, password: str,
                remember_me: bool = False) -> requests.Session:
    """Log a non-MFA user in. Returns a session with the access_token +
    refresh_token cookies set. Fails the test rather than skipping if login
    doesn't succeed with a plain access cookie.
    """
    s = _new_client()
    r = s.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password, "remember_me": remember_me},
    )
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    data = r.json()
    assert not data.get("mfa_required"), f"{email} has MFA enabled — use login_with_auto_enroll"
    assert not data.get("mfa_enrollment_required"), (
        f"{email} is MFA-enforced but not enrolled — use login_with_auto_enroll"
    )
    setattr(s, "login_body", data)
    return s
