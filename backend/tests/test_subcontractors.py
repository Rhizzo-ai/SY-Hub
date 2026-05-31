"""Chat 32 §R5 (Prompt 2.7) — subcontractor field tests on /suppliers.

Acceptance gates 1-8 (schema/migration + suppliers extension).

Test users (re-uses the same fixture pattern as test_suppliers.py):
  - test-admin@example.test     — super_admin (all perms, incl sensitive)
  - test-pm@example.test        — project_manager (suppliers.view/create/edit;
                                  NOT suppliers.view_sensitive)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

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
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
    yield
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))


@pytest.fixture
def _wipe_between(engine):
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
    yield


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


# ---------------------------------------------------------------------------
# Schema / migration — gates 1-3
# ---------------------------------------------------------------------------

class TestSchema:
    def test_alembic_head_is_0035_subcontractors(self, engine):
        """Gate 1: alembic upgrade head clean; new revision present."""
        with engine.connect() as c:
            head = c.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar()
        assert head == "0037_subcontracts", (
            f"expected head 0037_subcontracts, got {head!r}"
        )

    def test_supplier_type_enum_exists(self, engine):
        """Gate 1: supplier_type PG enum exists with both values."""
        with engine.connect() as c:
            labels = [r[0] for r in c.execute(text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid='supplier_type'::regtype "
                "ORDER BY enumsortorder"
            )).all()]
        assert labels == ["Supplier", "Subcontractor"], labels

    def test_new_tables_present(self, engine):
        """Gate 1: subcontractor_cis_verifications + supplier_documents tables exist."""
        with engine.connect() as c:
            tables = {r[0] for r in c.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' "
                "AND table_name IN ('subcontractor_cis_verifications','supplier_documents')"
            )).all()}
        assert tables == {"subcontractor_cis_verifications", "supplier_documents"}

    def test_supplier_extension_columns_present(self, engine):
        """Gate 1: 5 new columns added to suppliers."""
        with engine.connect() as c:
            cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='suppliers'"
            )).all()}
        for required in (
            "supplier_type", "cis_subtype", "cis_registered",
            "utr", "current_cis_status",
        ):
            assert required in cols, f"missing supplier column: {required!r}"

    def test_existing_rows_backfill_supplier_type(self, engine):
        """Gate 3: existing rows backfill supplier_type='Supplier',
        cis_registered=false. NULL-safe even when table is empty."""
        with engine.connect() as c:
            nulls_type = c.execute(text(
                "SELECT count(*) FROM suppliers WHERE supplier_type IS NULL"
            )).scalar()
            nulls_reg = c.execute(text(
                "SELECT count(*) FROM suppliers WHERE cis_registered IS NULL"
            )).scalar()
            non_default = c.execute(text(
                "SELECT count(*) FROM suppliers "
                "WHERE supplier_type NOT IN ('Supplier','Subcontractor')"
            )).scalar()
        assert nulls_type == 0
        assert nulls_reg == 0
        assert non_default == 0


# ---------------------------------------------------------------------------
# Suppliers extension — gates 4-8
# ---------------------------------------------------------------------------

class TestSubcontractorCreate:
    def test_create_subcontractor_defaults_current_cis_status_unverified(
        self, admin, engine, _wipe_between,
    ):
        """Gate 4: create supplier with supplier_type='Subcontractor' +
        valid UTR persists; current_cis_status defaults to 'Unverified'."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"Sub-{sx}",
                "supplier_type": "Subcontractor",
                "cis_subtype": "Labour_Only",
                "cis_registered": True,
                "utr": "1234567890",
            },
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["supplier_type"] == "Subcontractor"
        assert out["cis_subtype"] == "Labour_Only"
        assert out["cis_registered"] is True
        assert out["utr"] == "1234567890"  # admin has sensitive
        assert out["current_cis_status"] == "Unverified"

    def test_plain_supplier_rejects_cis_subtype(
        self, admin, engine, _wipe_between,
    ):
        """Gate 5: cis_subtype on a Supplier (non-subcontractor) rejected."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"Plain-{sx}",
                "supplier_type": "Supplier",
                "cis_subtype": "Labour_Only",
            },
        )
        assert r.status_code == 422, r.text
        assert "cis_subtype" in r.json()["detail"]

    def test_malformed_utr_rejected(self, admin, engine, _wipe_between):
        """Gate 6: malformed UTR (not 10 digits) → 422."""
        sx = _suffix()
        for bad in ("123", "12345", "abcdefghij", "12345678901"):
            r = admin.post(
                f"{BASE_URL}/api/v1/suppliers",
                json={
                    "name": f"Bad-{sx}-{bad}",
                    "supplier_type": "Subcontractor",
                    "utr": bad,
                },
            )
            assert r.status_code == 422, f"UTR {bad!r}: {r.text}"
            assert "utr" in r.json()["detail"].lower()

    def test_utr_with_spaces_normalised(self, admin, engine, _wipe_between):
        """Gate 6 (also): UTR with internal whitespace strips down to
        10 digits and persists clean."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"Spaced-{sx}",
                "supplier_type": "Subcontractor",
                "utr": " 12 345  67890 ",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["utr"] == "1234567890"

    def test_plain_supplier_current_cis_status_is_null(
        self, admin, engine, _wipe_between,
    ):
        """Gate 4 (negative form): a Supplier (default) has current_cis_status=null."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Plain2-{sx}"},  # no supplier_type → defaults Supplier
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["supplier_type"] == "Supplier"
        assert out["current_cis_status"] is None


class TestSupplierTypeFilter:
    def test_list_filters_to_subcontractors_only(
        self, admin, engine, _wipe_between,
    ):
        """Gate 7: GET /suppliers?supplier_type=Subcontractor returns subs only."""
        sx = _suffix()
        admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Plain-{sx}", "supplier_type": "Supplier"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Sub-{sx}", "supplier_type": "Subcontractor",
                  "utr": "1111111111"},
        )

        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": sx, "supplier_type": "Subcontractor"},
        )
        assert r.status_code == 200
        names = {item["name"] for item in r.json()["items"]}
        assert f"Sub-{sx}" in names
        assert f"Plain-{sx}" not in names

        # Inverse filter
        r2 = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": sx, "supplier_type": "Supplier"},
        )
        names2 = {item["name"] for item in r2.json()["items"]}
        assert f"Plain-{sx}" in names2
        assert f"Sub-{sx}" not in names2

    def test_list_invalid_supplier_type_returns_422(
        self, admin, engine, _wipe_between,
    ):
        """Bad supplier_type filter value → 422."""
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"supplier_type": "Bogus"},
        )
        assert r.status_code == 422


class TestUTRSensitiveGating:
    def test_utr_visible_with_sensitive_perm_only(
        self, admin, pm, engine, _wipe_between,
    ):
        """Gate 8: UTR hidden without suppliers.view_sensitive; visible with it."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"GateUTR-{sx}",
                "supplier_type": "Subcontractor",
                "utr": "9876543210",
            },
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]

        # Admin (sensitive perm) sees the real UTR.
        admin_get = admin.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert admin_get.status_code == 200
        assert admin_get.json()["utr"] == "9876543210"

        # PM lacks suppliers.view_sensitive → UTR nulled.
        pm_get = pm.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert pm_get.status_code == 200, pm_get.text
        assert pm_get.json()["utr"] is None
        # Non-sensitive subcontractor fields still visible.
        assert pm_get.json()["supplier_type"] == "Subcontractor"
        assert pm_get.json()["current_cis_status"] == "Unverified"
