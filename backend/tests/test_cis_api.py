"""Chat 32 §R5 (Prompt 2.7) — CIS verification API tests.

Acceptance gates 16-18 (HTTP layer): cross-tenant 404, sensitive-field
gating on list, permission gating on POST.

Test users:
  - test-admin@example.test     — super_admin (all)
  - test-pm@example.test        — PM (cis.view + cis.verify; NOT
                                  cis.view_sensitive)
  - test-readonly@example.test  — read_only (cis.view only; NO verify)
"""
from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"
READONLY_EMAIL = "test-readonly@example.test"


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    with e.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield e
    e.dispose()


@pytest.fixture(scope="module", autouse=True)
def _wipe_module(engine):
    """Wipe rows created by this module's test users at start + end."""
    def _wipe():
        with engine.begin() as c:
            c.execute(text("""
                DELETE FROM subcontractor_cis_verifications
                WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                )
            """))
            c.execute(text("""
                DELETE FROM suppliers
                WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                )
                AND name LIKE 'CISAPI-%'
            """))
    _wipe()
    yield
    _wipe()


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(engine):
    return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)


def _mk_sub(admin_session, name_suffix: str = "") -> str:
    """Helper — POST a CIS subcontractor (supplier_type='Contractor' per
    Chat 41 §R3.2) and return its id.
    """
    sx = _suffix()
    r = admin_session.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={
            "name": f"CISAPI-{name_suffix}-{sx}",
            "supplier_type": "Contractor",
            "utr": "1234567890",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPermissionGating:
    def test_post_without_cis_verify_returns_403(self, readonly, admin, engine):
        """Gate 18: cis.verify absent → 403 on POST."""
        sid = _mk_sub(admin, name_suffix="403")
        body = {
            "supplier_id": sid,
            "match_status": "Gross",
            "verified_on": str(date.today()),
        }
        r = readonly.post(f"{BASE_URL}/api/v1/cis/verifications", json=body)
        assert r.status_code == 403, r.text
        assert "cis.verify" in r.json()["detail"]


class TestPostHappyPath:
    def test_admin_post_returns_201_and_updates_cache(self, admin, engine):
        sid = _mk_sub(admin, name_suffix="ok")
        body = {
            "supplier_id": sid,
            "verification_number": "V-OK",
            "match_status": "Gross",
            "tax_rate_pct": 0,
            "verified_on": str(date.today()),
        }
        r = admin.post(f"{BASE_URL}/api/v1/cis/verifications", json=body)
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["match_status"] == "Gross"
        # Creator sees verification_number on the 201 response regardless
        # of view_sensitive.
        assert out["verification_number"] == "V-OK"

        # Supplier's current_cis_status was repointed.
        s = admin.get(f"{BASE_URL}/api/v1/suppliers/{sid}").json()
        assert s["current_cis_status"] == "Gross"


class TestPlainSupplierConflict:
    def test_post_on_plain_supplier_returns_409(self, admin, engine):
        """§R4.2: 409 if supplier is not a subcontractor."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"CISAPI-plain-{sx}"},  # default supplier_type=Supplier
        )
        assert r.status_code == 201
        sid = r.json()["id"]
        body = {
            "supplier_id": sid,
            "match_status": "Gross",
            "verified_on": str(date.today()),
        }
        r = admin.post(f"{BASE_URL}/api/v1/cis/verifications", json=body)
        assert r.status_code == 409, r.text


class TestCrossTenant:
    def test_post_with_unknown_supplier_id_returns_404(self, admin, engine):
        """Gate 16: cross-tenant (or unknown) supplier_id → 404 (NOT 403)."""
        ghost = uuid.uuid4()
        body = {
            "supplier_id": str(ghost),
            "match_status": "Gross",
            "verified_on": str(date.today()),
        }
        r = admin.post(f"{BASE_URL}/api/v1/cis/verifications", json=body)
        assert r.status_code == 404, r.text


class TestSensitiveFieldGating:
    def test_pm_list_omits_verification_number(self, admin, pm, engine):
        """Gate 17: cis.view without cis.view_sensitive → list omits
        verification_number (rendered as null)."""
        sid = _mk_sub(admin, name_suffix="sens")
        admin.post(
            f"{BASE_URL}/api/v1/cis/verifications",
            json={
                "supplier_id": sid,
                "verification_number": "V-SECRET",
                "match_status": "Gross",
                "verified_on": str(date.today()),
            },
        )

        # PM has cis.view + cis.verify but NOT cis.view_sensitive.
        r = pm.get(
            f"{BASE_URL}/api/v1/cis/verifications",
            params={"supplier_id": sid},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 1
        for item in items:
            assert item["verification_number"] is None, (
                "PM (no cis.view_sensitive) must not see verification_number"
            )

        # Admin sees the real value.
        r_admin = admin.get(
            f"{BASE_URL}/api/v1/cis/verifications",
            params={"supplier_id": sid},
        )
        assert r_admin.status_code == 200
        admin_items = r_admin.json()["items"]
        assert any(
            it["verification_number"] == "V-SECRET" for it in admin_items
        )


class TestNoUpdateDeleteEndpoints:
    def test_no_patch_endpoint_on_verifications(self, admin, engine):
        """Gate 15 (API form): the OpenAPI schema has no PATCH/DELETE
        on /cis/verifications — append-only at the API layer."""
        r = admin.get(f"{BASE_URL}/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        # Find any CIS verification path
        cis_paths = {k: v for k, v in paths.items() if "/cis/verifications" in k}
        assert cis_paths, "expected /cis/verifications paths to be registered"
        for path, methods in cis_paths.items():
            verbs = set(methods.keys())
            assert "patch" not in verbs, f"unexpected PATCH on {path}"
            assert "delete" not in verbs, f"unexpected DELETE on {path}"


class TestCurrentEndpoint:
    def test_get_current_returns_latest(self, admin, engine):
        sid = _mk_sub(admin, name_suffix="cur")
        admin.post(
            f"{BASE_URL}/api/v1/cis/verifications",
            json={"supplier_id": sid, "match_status": "Net",
                  "verified_on": "2024-01-01"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/cis/verifications",
            json={"supplier_id": sid, "match_status": "Gross",
                  "verified_on": "2025-06-01"},
        )
        r = admin.get(
            f"{BASE_URL}/api/v1/cis/verifications/current",
            params={"supplier_id": sid},
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out is not None
        assert out["match_status"] == "Gross"
        assert out["verified_on"] == "2025-06-01"
