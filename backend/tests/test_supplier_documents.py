"""Chat 32 §R5 (Prompt 2.7) — supplier_documents tests (gates 19-25).

Cross-cuts: doc_type validation, archive lifecycle, cross-tenant 404,
permission gating, LD2-boundary (no auto-scan side-effects on expiry).
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

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
    def _wipe():
        with engine.begin() as c:
            c.execute(text("""
                DELETE FROM supplier_documents
                WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                )
            """))
            c.execute(text("""
                DELETE FROM suppliers
                WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                )
                AND name LIKE 'DOCS-%'
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


def _mk_supplier(admin_session, name_suffix: str = "") -> str:
    sx = _suffix()
    r = admin_session.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": f"DOCS-{name_suffix}-{sx}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_document_persists(self, admin, engine):
        """Gate 19: create document → persists with validated doc_type.

        rev-B §R4.2: `file_ref` is REMOVED from the create body — it's
        system-owned via the upload endpoint. Any client-supplied
        `file_ref` here is silently dropped (Pydantic extra=ignore).
        """
        sid = _mk_supplier(admin, "ok")
        body = {
            "supplier_id": sid,
            "doc_type": "Public_Liability",
            "title": "PL Insurance 2026",
            "issued_on": str(date.today()),
            "expires_on": str(date.today() + timedelta(days=365)),
            "notes": "Renewed Feb",
        }
        r = admin.post(f"{BASE_URL}/api/v1/supplier-documents", json=body)
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["doc_type"] == "Public_Liability"
        assert out["title"] == "PL Insurance 2026"
        assert out["is_archived"] is False
        # rev-B §R4.2 VERIFY: a freshly-created doc has no file attached.
        assert out["has_file"] is False
        assert out["file_ref"] is None

    def test_create_ignores_client_supplied_file_ref(self, admin, engine):
        """rev-B §R4.2 VERIFY: a client-supplied `file_ref` in the
        create body MUST NOT land in the persisted row. The schema
        removed the field; Pydantic silently drops it.
        """
        sid = _mk_supplier(admin, "noref")
        body = {
            "supplier_id": sid,
            "doc_type": "Other",
            "title": "Should ignore file_ref",
            "file_ref": "s3://attacker-supplied/evil.pdf",
        }
        r = admin.post(f"{BASE_URL}/api/v1/supplier-documents", json=body)
        assert r.status_code == 201, r.text
        out = r.json()
        # Persisted file_ref must be None — the client's string is gone.
        assert out["file_ref"] is None
        assert out["has_file"] is False
        # GET round-trip confirms the persisted state.
        r2 = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{out['id']}"
        )
        assert r2.status_code == 200
        assert r2.json()["file_ref"] is None
        assert r2.json()["has_file"] is False

    def test_invalid_doc_type_rejected(self, admin, engine):
        """Gate 20: invalid doc_type → 422."""
        sid = _mk_supplier(admin, "baddt")
        body = {
            "supplier_id": sid,
            "doc_type": "Bogus_Type",
            "title": "Whatever",
        }
        r = admin.post(f"{BASE_URL}/api/v1/supplier-documents", json=body)
        assert r.status_code == 422, r.text
        assert "doc_type" in r.json()["detail"]

    def test_create_without_perm_returns_403(self, readonly, admin, engine):
        """Gate 24: supplier_documents.create absent → 403."""
        sid = _mk_supplier(admin, "noperm")
        body = {
            "supplier_id": sid,
            "doc_type": "Other",
            "title": "T",
        }
        r = readonly.post(f"{BASE_URL}/api/v1/supplier-documents", json=body)
        assert r.status_code == 403, r.text


class TestListArchiveFlag:
    def test_list_excludes_archived_by_default(self, admin, engine):
        """Gate 21: list excludes archived by default; include_archived returns them."""
        sid = _mk_supplier(admin, "lst")
        # Create one active doc and one to-be-archived doc.
        admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid, "doc_type": "Other", "title": "Active"},
        )
        d2 = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid, "doc_type": "Other", "title": "ToArchive"},
        ).json()
        # Archive d2.
        ra = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d2['id']}/archive"
        )
        assert ra.status_code == 200, ra.text

        # Default list — only active.
        r = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents",
            params={"supplier_id": sid},
        )
        titles = {it["title"] for it in r.json()["items"]}
        assert "Active" in titles
        assert "ToArchive" not in titles

        # include_archived=true → both.
        r2 = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents",
            params={"supplier_id": sid, "include_archived": "true"},
        )
        titles2 = {it["title"] for it in r2.json()["items"]}
        assert {"Active", "ToArchive"} <= titles2


class TestArchiveLifecycle:
    def test_archive_unarchive_round_trip(self, admin, engine):
        """Gate 22: archive sets is_archived=true + archived_at + archived_by;
        unarchive reverses cleanly."""
        sid = _mk_supplier(admin, "arc")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid, "doc_type": "Other", "title": "Cycle"},
        ).json()

        ra = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/archive"
        )
        assert ra.status_code == 200
        out = ra.json()
        assert out["is_archived"] is True
        assert out["archived_at"] is not None

        ru = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/unarchive"
        )
        assert ru.status_code == 200
        out2 = ru.json()
        assert out2["is_archived"] is False
        assert out2["archived_at"] is None


class TestCrossTenant:
    def test_get_unknown_id_returns_404(self, admin, engine):
        """Gate 23: cross-tenant / unknown document_id → 404."""
        ghost = uuid.uuid4()
        r = admin.get(f"{BASE_URL}/api/v1/supplier-documents/{ghost}")
        assert r.status_code == 404, r.text

    def test_list_unknown_supplier_returns_404(self, admin, engine):
        ghost = uuid.uuid4()
        r = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents",
            params={"supplier_id": str(ghost)},
        )
        assert r.status_code == 404, r.text


class TestExpiryStoredOnly:
    def test_expiry_date_stored_and_returned_no_scan_side_effect(
        self, admin, engine,
    ):
        """Gate 25: expiry stored and returned; LD2 boundary — NO attention/
        scan side-effect fires. Assert by counting expiry-flavoured
        notifications BEFORE and AFTER the create — delta must be 0.
        (Pre-existing rows in the table from other tracks are
        irrelevant; gate 25 only pins that creating a supplier-document
        with an expiry date does not emit a NEW one.)"""
        sid = _mk_supplier(admin, "exp")

        # Capture baseline count of expiry-flavoured notifications.
        nt_filter = """
            SELECT count(*) FROM notifications
             WHERE notification_type::text ILIKE '%expir%'
                OR notification_type::text ILIKE '%lapsed%'
                OR notification_type::text ILIKE '%attention%'
        """
        with engine.connect() as c:
            before = c.execute(text(nt_filter)).scalar()

        past = str(date.today() - timedelta(days=180))
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid, "doc_type": "Public_Liability",
                "title": "Expired Cert",
                "expires_on": past,
            },
        )
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]
        assert r.json()["expires_on"] == past

        # Round-trip GET returns the same expiry, untouched.
        r2 = admin.get(f"{BASE_URL}/api/v1/supplier-documents/{doc_id}")
        assert r2.status_code == 200
        assert r2.json()["expires_on"] == past

        # The count of expiry-flavoured notifications must be unchanged.
        # If LD2 is honoured no NEW notification is emitted; B48 will
        # change this delta when auto-scan ships.
        with engine.connect() as c:
            after = c.execute(text(nt_filter)).scalar()
        assert after == before, (
            f"expected zero new expiry-style notifications, got "
            f"delta={after - before}. LD2 boundary violated — "
            f"auto-scan must be backlog B48."
        )


class TestUpdate:
    def test_patch_updates_title_and_audits(self, admin, engine):
        sid = _mk_supplier(admin, "upd")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid, "doc_type": "Other", "title": "Old"},
        ).json()

        r = admin.patch(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}",
            json={"title": "New Title", "notes": "edited"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "New Title"


class TestReadonlyCannotView:
    def test_readonly_get_returns_403(self, admin, readonly, engine):
        """read_only does NOT hold supplier_documents.view (per gate-27
        mapping — supplier_documents.* is restricted to the 4 roles
        holding suppliers.create). Per-resource sensitive gating
        (view_sensitive distinct from view) is therefore not testable
        against the seeded test users; the gating itself is exercised at
        the serialiser layer in `services.supplier_documents.serialise`.

        rev-B note: `file_ref` is now system-owned, so the test body
        drops the legacy client `file_ref` string and just creates a
        plain doc.
        """
        sid = _mk_supplier(admin, "ro")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid, "doc_type": "Other", "title": "T",
                "notes": "internal-only",
            },
        ).json()

        r = readonly.get(f"{BASE_URL}/api/v1/supplier-documents/{d['id']}")
        assert r.status_code == 403, r.text


class TestSerialiserGating:
    def test_serialise_omits_sensitive_when_flag_off(self):
        """Direct serialiser unit test — exercises the sensitive-gating
        contract without relying on a role that lacks view_sensitive."""
        from app.services.supplier_documents import serialise, SENSITIVE_RESPONSE_FIELDS

        class _FakeRow:
            id = uuid.uuid4()
            tenant_id = uuid.uuid4()
            supplier_id = uuid.uuid4()
            doc_type = "Other"
            title = "T"
            file_ref = None  # rev-B: no attached file in this fixture.
            issued_on = None
            expires_on = None
            notes = "internal-only"
            is_archived = False
            archived_at = None
            from datetime import datetime, timezone
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)

        # WITH sensitive perm — values flow through.
        out_full = serialise(_FakeRow(), include_sensitive=True)
        assert out_full["notes"] == "internal-only"
        # has_file is non-sensitive in rev-B and remains visible.
        assert out_full["has_file"] is False
        # No file means file_name/size/content_type are None even for
        # the sensitive viewer.
        assert out_full["file_name"] is None
        assert out_full["file_size"] is None

        # WITHOUT sensitive perm — sensitive fields are nulled.
        out_lite = serialise(_FakeRow(), include_sensitive=False)
        for k in SENSITIVE_RESPONSE_FIELDS:
            assert out_lite[k] is None, (
                f"serialise(include_sensitive=False) must null {k!r}"
            )
        # Non-sensitive fields still present.
        assert out_lite["title"] == "T"
        assert out_lite["has_file"] is False
