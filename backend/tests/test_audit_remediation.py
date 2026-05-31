"""Audit remediation regression tests (Feb 2026).

One test per patch — plus three residuals discovered during the close-out.
All seven guard against future drift on the decisions captured in the
corresponding PRD entry.

Patches covered:
  1. (I6) MFA enforcement honours user_role.expires_at
  2. (M8) CORS startup guard refuses wildcard + credentials
  3. (I3) Rate-limit bypass requires APP_ENV=test
  4. (C1) Cookies-only auth transport — no tokens in JSON bodies

Residuals:
  5. /auth/refresh with no cookie → 401 (not 500 — guards against the
     `payload.refresh_token` AttributeError regression)
  6. /auth/mfa/enroll/confirm body carries no access_token / refresh_token
  7. /auth/login body carries no mfa_pending_token field
"""
from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
import requests
import sqlalchemy as sa
from dotenv import load_dotenv


load_dotenv("/app/backend/.env")

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://workflow-surface.preview.emergentagent.com"
)
DATABASE_URL = os.environ["DATABASE_URL"]

TEST_PASSWORD = "TestUser-Dev-2026!"
DIRECTOR = "test-director@example.test"
FINANCE = "test-finance@example.test"
ADMIN = "test-admin@example.test"
READONLY = "test-readonly@example.test"


@pytest.fixture(scope="module")
def db_engine():
    eng = sa.create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _reset_user_mfa(db_engine, email: str) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE users SET mfa_enabled=false, mfa_method=NULL, "
                "mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL, "
                "mfa_enrolled_at=NULL, failed_login_attempts=0, "
                "locked_until=NULL, lockout_level=0 WHERE email=:e"
            ),
            {"e": email},
        )


# ======================================================================
# Patch 1 — MFA enforcement honours user_role.expires_at  (finding I6)
# ======================================================================

class TestPatch1_MfaEnforcementHonoursRoleExpiry:
    """`_most_senior_enforced_role` must filter out Active rows whose
    `expires_at` is in the past. Otherwise a director whose role was
    granted with a past expiry date would be forced into MFA enrolment
    even though the permission resolver considers the role dead.
    """

    def test_expired_user_role_does_not_trigger_enforcement(self, db_engine):
        """Scenario:
          1. test-director has an Active user_role on 'director' (MFA-enforced).
          2. Back-date its expires_at to yesterday.
          3. Log in: should NOT receive `mfa_enrollment_required=true`.
          4. Restore expires_at for suite isolation.
        """
        _reset_user_mfa(db_engine, DIRECTOR)

        with db_engine.begin() as conn:
            # Capture original expires_at so we can restore.
            row = conn.execute(
                sa.text("""
                    SELECT ur.id, ur.expires_at
                    FROM user_roles ur
                    JOIN users u ON u.id = ur.user_id
                    JOIN roles r ON r.id = ur.role_id
                    WHERE u.email = :e AND r.code = 'director'
                      AND ur.status = 'Active'
                    LIMIT 1
                """),
                {"e": DIRECTOR},
            ).first()
            assert row is not None, "test-director should hold an Active 'director' role"
            ur_id, original_expiry = row
            # Back-date to yesterday.
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            conn.execute(
                sa.text("UPDATE user_roles SET expires_at = :e WHERE id = :id"),
                {"e": yesterday, "id": ur_id},
            )

        try:
            s = _new_session()
            r = s.post(f"{BASE_URL}/api/auth/login",
                       json={"email": DIRECTOR, "password": TEST_PASSWORD})
            assert r.status_code == 200, r.text
            data = r.json()
            # With the role expired, the user should reach the normal
            # access path, not the forced-enrolment hard-block.
            assert data.get("mfa_enrollment_required") is False, (
                "Expired user_role still triggered MFA enforcement — I6 regression"
            )
            assert data.get("enforced_role_name") in (None, "")
            # Full session cookies issued.
            assert s.cookies.get("access_token")
            assert s.cookies.get("refresh_token")
        finally:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text("UPDATE user_roles SET expires_at = :e WHERE id = :id"),
                    {"e": original_expiry, "id": ur_id},
                )

    def test_active_nonexpired_role_still_enforces(self, db_engine):
        """Control: with the role un-expired, enforcement still kicks in."""
        _reset_user_mfa(db_engine, DIRECTOR)
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": DIRECTOR, "password": TEST_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert data["mfa_enrollment_required"] is True
        assert data["enforced_role_name"] == "Director"


# ======================================================================
# Patch 2 — CORS wildcard + credentials startup guard  (finding M8)
# ======================================================================

class TestPatch2_CorsStartupGuard:
    """`_resolve_cors_origins()` must raise RuntimeError when
    `CORS_ORIGINS` is empty or contains `*`. The server must not start
    with a permissive CORS policy that accepts credentials.

    The helper reads `CORS_ORIGINS` at call time, so we manipulate the
    env var via monkeypatch and invoke directly — no module reload needed
    (which would also re-trigger `app.add_middleware(...)`).
    """

    @pytest.fixture(scope="class")
    def resolve(self):
        from server import _resolve_cors_origins  # type: ignore
        return _resolve_cors_origins

    def test_wildcard_raises_runtime_error(self, monkeypatch, resolve):
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError) as exc:
            resolve()
        msg = str(exc.value)
        assert "wildcard" in msg.lower()
        assert "credentials" in msg.lower()

    def test_empty_raises_runtime_error(self, monkeypatch, resolve):
        monkeypatch.setenv("CORS_ORIGINS", "")
        with pytest.raises(RuntimeError):
            resolve()

    def test_star_amongst_others_still_raises(self, monkeypatch, resolve):
        """Even if the operator adds a wildcard alongside explicit origins,
        we refuse — one bad entry is enough to make the policy permissive.
        """
        monkeypatch.setenv("CORS_ORIGINS", "https://app.syhomes.co.uk,*")
        with pytest.raises(RuntimeError):
            resolve()

    def test_explicit_origins_list_accepted(self, monkeypatch, resolve):
        monkeypatch.setenv(
            "CORS_ORIGINS",
            "https://app.syhomes.co.uk,https://preview.emergentagent.com",
        )
        got = resolve()
        assert got == [
            "https://app.syhomes.co.uk",
            "https://preview.emergentagent.com",
        ]


# ======================================================================
# Patch 3 — Rate-limit bypass requires APP_ENV=test  (finding I3)
# ======================================================================

class TestPatch3_RateLimitBypassHardening:
    """`SYHOMES_RATE_LIMIT_DISABLED=1` alone MUST NOT bypass the limiter
    in production. The disable flag only takes effect when paired with
    `APP_ENV=test`.
    """

    def _reload_module(self):
        import app.services.rate_limit as rl
        return importlib.reload(rl)

    def test_disabled_flag_alone_is_refused(self, monkeypatch, caplog):
        monkeypatch.setenv("SYHOMES_RATE_LIMIT_DISABLED", "1")
        monkeypatch.setenv("APP_ENV", "production")
        rl = self._reload_module()
        with caplog.at_level("ERROR", logger="syhomes.rate_limit"):
            assert rl._is_bypass_active() is False
        # And the footgun is logged at ERROR so ops can catch it.
        assert any("REMAINS ACTIVE" in rec.message for rec in caplog.records), (
            "Stray SYHOMES_RATE_LIMIT_DISABLED in production must log ERROR"
        )

    def test_disabled_flag_without_app_env_is_refused(self, monkeypatch):
        monkeypatch.setenv("SYHOMES_RATE_LIMIT_DISABLED", "1")
        monkeypatch.delenv("APP_ENV", raising=False)
        rl = self._reload_module()
        assert rl._is_bypass_active() is False

    def test_both_flags_required_for_bypass(self, monkeypatch):
        monkeypatch.setenv("SYHOMES_RATE_LIMIT_DISABLED", "1")
        monkeypatch.setenv("APP_ENV", "test")
        rl = self._reload_module()
        assert rl._is_bypass_active() is True

    def test_disabled_flag_off_is_always_refused(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.delenv("SYHOMES_RATE_LIMIT_DISABLED", raising=False)
        rl = self._reload_module()
        assert rl._is_bypass_active() is False


# ======================================================================
# Patch 4 — Cookies-only auth transport  (finding C1, critical)
# ======================================================================

class TestPatch4_CookiesOnlyTransport:
    """No access/refresh tokens leak in ANY JSON response. Cookies are the
    sole transport. Bearer authentication no longer works.
    """

    def test_login_sets_cookies_no_body_tokens(self, db_engine):
        """Non-enforced login: cookies set, body metadata-only."""
        _reset_user_mfa(db_engine, READONLY)
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": READONLY, "password": TEST_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" not in body
        assert "refresh_token" not in body
        # Cookies must be HttpOnly + SameSite=Lax (visible on Set-Cookie).
        set_cookie = " ".join(r.raw.headers.getlist("Set-Cookie")) if r.raw else ""
        if not set_cookie:  # fall back via requests header view
            set_cookie = "; ".join(
                v for k, v in r.headers.items() if k.lower() == "set-cookie"
            )
        assert s.cookies.get("access_token"), "access_token cookie not set"
        assert s.cookies.get("refresh_token"), "refresh_token cookie not set"
        # Headers include HttpOnly + SameSite attributes.
        cookie_header_blob = ";".join(
            [v for k, v in r.headers.items() if k.lower() == "set-cookie"]
        )
        assert "HttpOnly" in cookie_header_blob
        assert "SameSite" in cookie_header_blob or "samesite" in cookie_header_blob

    def test_refresh_returns_204_and_rotates_cookie(self, db_engine):
        _reset_user_mfa(db_engine, READONLY)
        s = _new_session()
        s.post(f"{BASE_URL}/api/auth/login",
               json={"email": READONLY, "password": TEST_PASSWORD})
        old_refresh = s.cookies.get("refresh_token")
        r = s.post(f"{BASE_URL}/api/auth/refresh")
        assert r.status_code == 204, r.text
        assert r.text == "" or r.text == "null"
        new_refresh = s.cookies.get("refresh_token")
        assert new_refresh and new_refresh != old_refresh

    def test_logout_clears_cookies(self, db_engine):
        _reset_user_mfa(db_engine, READONLY)
        s = _new_session()
        s.post(f"{BASE_URL}/api/auth/login",
               json={"email": READONLY, "password": TEST_PASSWORD})
        r = s.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 204
        # requests.Session drops expired cookies, so the jar should be empty
        # for these two.
        assert not s.cookies.get("access_token")
        assert not s.cookies.get("refresh_token")

    def test_bearer_header_not_accepted(self, db_engine):
        """A stolen cookie re-cast as a Bearer header must not authenticate —
        proves `_extract_token` ignores `Authorization` completely.
        """
        _reset_user_mfa(db_engine, READONLY)
        s = _new_session()
        s.post(f"{BASE_URL}/api/auth/login",
               json={"email": READONLY, "password": TEST_PASSWORD})
        cookie = s.cookies.get("access_token")
        assert cookie
        # New clean client, token in Authorization header only.
        bearer = requests.Session()
        bearer.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cookie}",
        })
        r = bearer.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401, (
            "Bearer header was accepted — C1 regression (bearer path not removed)"
        )


# ======================================================================
# Residual 5 — /auth/refresh with no cookie returns 401, not 500
# ======================================================================

class TestResidual_RefreshNoCookie401NotAttributeError:
    """Guards the AttributeError that slipped through when the C1 patch
    stripped `refresh_token` from `RefreshRequest` but left
    `payload.refresh_token` in the handler.
    """

    def test_missing_refresh_cookie_returns_401(self):
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/auth/refresh")
        assert r.status_code == 401, (
            f"Expected 401 (missing cookie), got {r.status_code}: {r.text}. "
            "If this is 500 with 'AttributeError: refresh_token' then the "
            "handler has regressed back to reading payload.refresh_token."
        )
        assert "cookie" in r.json()["detail"].lower() or \
               "refresh" in r.json()["detail"].lower()

    def test_missing_refresh_cookie_with_body_still_401(self):
        """A client posting `{"refresh_token": "..."}` in the body (as the
        pre-C1 contract did) must still get 401 — the body is ignored.
        """
        s = _new_session()
        r = s.post(
            f"{BASE_URL}/api/auth/refresh",
            json={"refresh_token": "some-legacy-string-in-the-body"},
        )
        assert r.status_code == 401


# ======================================================================
# Residual 6 — MfaEnrollConfirmResponse body has no tokens
# ======================================================================

class TestResidual_EnrollConfirmBodyHasNoTokens:
    """Enrolling a fresh MFA-enforced user must return cookies + a minimal
    body ({backup_codes, session_issued}). No access_token / refresh_token
    leak in the JSON.
    """

    def test_enroll_confirm_body_shape(self, db_engine):
        _reset_user_mfa(db_engine, ADMIN)
        s = _new_session()
        login = s.post(f"{BASE_URL}/api/auth/login",
                       json={"email": ADMIN, "password": TEST_PASSWORD})
        assert login.status_code == 200
        assert login.json()["mfa_enrollment_required"] is True

        start = s.post(f"{BASE_URL}/api/auth/mfa/enroll/start")
        secret = start.json()["secret"]
        confirm = s.post(
            f"{BASE_URL}/api/auth/mfa/enroll/confirm",
            json={"secret": secret, "code": pyotp.TOTP(secret).now()},
        )
        assert confirm.status_code == 200
        body = confirm.json()
        # C1: no tokens in body.
        assert "access_token" not in body
        assert "refresh_token" not in body
        # Expected contract shape.
        assert body["session_issued"] is True
        assert isinstance(body["backup_codes"], list)
        assert len(body["backup_codes"]) == 10
        # Cookies actually rotated from mfa_pending → full session.
        assert s.cookies.get("access_token")
        assert s.cookies.get("refresh_token")

        # Clean up so suite isolation holds.
        _reset_user_mfa(db_engine, ADMIN)


# ======================================================================
# Residual 7 — LoginResponse has no mfa_pending_token field
# ======================================================================

class TestResidual_LoginBodyHasNoMfaPendingToken:
    """The mfa_pending JWT rides via cookie only. The body signals the
    pending state through `mfa_enrollment_required: true` +
    `enforced_role_name` — never through a raw token field.
    """

    def test_login_body_omits_mfa_pending_token_field(self, db_engine):
        _reset_user_mfa(db_engine, FINANCE)
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": FINANCE, "password": TEST_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        # The field must not exist in the serialised response.
        assert "mfa_pending_token" not in body, (
            "mfa_pending_token still serialised in LoginResponse body — C1 regression"
        )
        assert "access_token" not in body
        # But the routing signals ARE present.
        assert body["mfa_enrollment_required"] is True
        assert body["enforced_role_name"] == "Finance"
        # And the cookie is set.
        assert s.cookies.get("access_token")

    def test_openapi_schema_excludes_mfa_pending_token(self):
        """Belt-and-braces: the OpenAPI schema must not advertise the field.

        `/openapi.json` is served at the FastAPI app root, outside the `/api`
        ingress rewrite — hit it on localhost.
        """
        r = requests.get("http://localhost:8001/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        login_resp_schema = schema.get("components", {}).get("schemas", {}).get(
            "LoginResponse", {}
        )
        props = login_resp_schema.get("properties", {})
        assert "mfa_pending_token" not in props
        assert "access_token" not in props
        assert "refresh_token" not in props
