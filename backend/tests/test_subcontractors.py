"""Chat 32 §R5 (Prompt 2.7) — subcontractor field tests on /suppliers.
Chat 41 §R5 (Prompt 2.7-BE-rev-A) — reworked for the contact-book reshape:

  - alembic head bumped to 0040_contact_book_rework.
  - supplier_type enum is now 4 values (`Contractor` replaces
    `Subcontractor`; +Consultant +Other).
  - `cis_subtype` column / API field DROPPED.
  - `default_vat_rate` column DROPPED — independent `vat_registered`
    boolean added.
  - CIS gating now keys off `'Contractor'` (the new CIS subcontractor type).

Test users (re-uses the same fixture pattern as test_suppliers.py):
  - test-admin@example.test     — super_admin (all perms, incl sensitive)
  - test-pm@example.test        — project_manager (suppliers.view/create/edit;
                                  NOT suppliers.view_sensitive)
"""
from __future__ import annotations

import os
import uuid

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
# Schema / migration — gates 1-3 (Chat 41 §R5 reworked)
# ---------------------------------------------------------------------------

class TestSchema:
    def test_alembic_head_is_0040_contact_book_rework(self, engine):
        """Gate 1: alembic upgrade head clean; new revision present.

        Chat 41 §R5 — head bumped from 0039 → 0040.
        """
        with engine.connect() as c:
            head = c.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar()
        assert head == "0040_contact_book_rework", (
            f"expected head 0040_contact_book_rework, got {head!r}"
        )

    def test_supplier_type_enum_has_four_values(self, engine):
        """Chat 41 §R1.3 — enum has exactly 4 values in the new order."""
        with engine.connect() as c:
            labels = [r[0] for r in c.execute(text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid='supplier_type'::regtype "
                "ORDER BY enumsortorder"
            )).all()]
        assert labels == ["Contractor", "Supplier", "Consultant", "Other"], labels

    def test_new_tables_present(self, engine):
        """Subcontractor verifications + supplier_documents tables retained.

        These were the Chat 32 additions; rev-A does NOT touch them.
        """
        with engine.connect() as c:
            tables = {r[0] for r in c.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' "
                "AND table_name IN ('subcontractor_cis_verifications','supplier_documents')"
            )).all()}
        assert tables == {"subcontractor_cis_verifications", "supplier_documents"}

    def test_dropped_columns_absent(self, engine):
        """Chat 41 §R1.2 — cis_subtype and default_vat_rate columns dropped."""
        with engine.connect() as c:
            cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='suppliers'"
            )).all()}
        for dropped in ("cis_subtype", "default_vat_rate"):
            assert dropped not in cols, (
                f"expected dropped column {dropped!r} to be absent, "
                f"but it is still present"
            )

    def test_new_columns_present(self, engine):
        """Chat 41 §R1.2 — vat_registered + trade_id added.

        Existing rev-A columns (supplier_type, cis_registered, utr,
        current_cis_status) are still expected.
        """
        with engine.connect() as c:
            cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='suppliers'"
            )).all()}
        for required in (
            "supplier_type", "cis_registered", "utr", "current_cis_status",
            # Chat 41 §R1.2 additions:
            "vat_registered", "trade_id",
        ):
            assert required in cols, f"missing supplier column: {required!r}"


# ---------------------------------------------------------------------------
# Contractor (CIS subcontractor) fields — gates 4-8 (Chat 41 §R5 reworked)
# ---------------------------------------------------------------------------

class TestContractorCreate:
    def test_create_contractor_defaults_current_cis_status_unverified(
        self, admin, engine, _wipe_between,
    ):
        """Gate 4: create supplier with supplier_type='Contractor' +
        valid UTR persists; current_cis_status defaults to 'Unverified'.

        Chat 41 §R5 — 'Subcontractor' was renamed to 'Contractor'.
        cis_subtype is no longer sent / persisted.
        """
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"Con-{sx}",
                "supplier_type": "Contractor",
                "cis_registered": True,
                "utr": "1234567890",
            },
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["supplier_type"] == "Contractor"
        assert "cis_subtype" not in out, "cis_subtype must be dropped from response"
        assert out["cis_registered"] is True
        assert out["utr"] == "1234567890"  # admin has sensitive
        assert out["current_cis_status"] == "Unverified"

    def test_malformed_utr_rejected(self, admin, engine, _wipe_between):
        """Gate 6: malformed UTR (not 10 digits) → 422.

        Unchanged from 2.7 except for supplier_type label.
        """
        sx = _suffix()
        for bad in ("123", "12345", "abcdefghij", "12345678901"):
            r = admin.post(
                f"{BASE_URL}/api/v1/suppliers",
                json={
                    "name": f"Bad-{sx}-{bad}",
                    "supplier_type": "Contractor",
                    "utr": bad,
                },
            )
            assert r.status_code == 422, f"UTR {bad!r}: {r.text}"
            assert "utr" in r.json()["detail"].lower()

    def test_utr_with_spaces_normalised(self, admin, engine, _wipe_between):
        """Gate 6 (also): UTR with internal whitespace strips down to
        10 digits and persists clean.
        """
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"Spaced-{sx}",
                "supplier_type": "Contractor",
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
            json={"name": f"Plain-{sx}"},  # no supplier_type → defaults Supplier
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["supplier_type"] == "Supplier"
        assert out["current_cis_status"] is None

    def test_consultant_and_other_types_accepted(
        self, admin, engine, _wipe_between,
    ):
        """Chat 41 §R5 — the two new contact-type labels work and do NOT
        get a default current_cis_status (only Contractor gets 'Unverified').
        """
        sx = _suffix()
        for stype in ("Consultant", "Other"):
            r = admin.post(
                f"{BASE_URL}/api/v1/suppliers",
                json={"name": f"{stype}-{sx}", "supplier_type": stype},
            )
            assert r.status_code == 201, r.text
            out = r.json()
            assert out["supplier_type"] == stype
            assert out["current_cis_status"] is None


class TestSupplierTypeFilter:
    def test_list_filters_to_contractors_only(
        self, admin, engine, _wipe_between,
    ):
        """Gate 7: GET /suppliers?supplier_type=Contractor returns
        contractors only.
        """
        sx = _suffix()
        admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Plain-{sx}", "supplier_type": "Supplier"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Con-{sx}", "supplier_type": "Contractor",
                  "utr": "1111111111"},
        )

        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": sx, "supplier_type": "Contractor"},
        )
        assert r.status_code == 200
        names = {item["name"] for item in r.json()["items"]}
        assert f"Con-{sx}" in names
        assert f"Plain-{sx}" not in names

        # Inverse filter
        r2 = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": sx, "supplier_type": "Supplier"},
        )
        names2 = {item["name"] for item in r2.json()["items"]}
        assert f"Plain-{sx}" in names2
        assert f"Con-{sx}" not in names2

    def test_list_invalid_supplier_type_returns_422(
        self, admin, engine, _wipe_between,
    ):
        """Bad supplier_type filter value → 422.

        'Subcontractor' is now invalid (it was replaced by 'Contractor').
        """
        for bogus in ("Bogus", "Subcontractor"):
            r = admin.get(
                f"{BASE_URL}/api/v1/suppliers",
                params={"supplier_type": bogus},
            )
            assert r.status_code == 422, (
                f"supplier_type={bogus!r} should be 422, got {r.status_code}"
            )


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
                "supplier_type": "Contractor",
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
        # Non-sensitive contractor fields still visible.
        assert pm_get.json()["supplier_type"] == "Contractor"
        assert pm_get.json()["current_cis_status"] == "Unverified"
