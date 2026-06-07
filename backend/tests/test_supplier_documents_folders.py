"""Chat 45 §R5 (Build Pack 2.7-DOCS-BE) — supplier_documents <-> folder
association tests (gates 25-32 + 34b doc-move regression).

Covers the relaxed create/update (doc_type + title optional), folder_id
on create + patch, the /move endpoint, and the "archived doc no longer
counts as live" invariant on folder archive-empty check.
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
                DELETE FROM document_folders
                 WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                 )
            """))
            c.execute(text("""
                DELETE FROM suppliers
                 WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                 )
                AND name LIKE 'DOCFL-%'
            """))
    _wipe()
    yield
    _wipe()


@pytest.fixture(scope="module")
def admin():
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


def _mk_supplier(s, suffix: str = "") -> str:
    r = s.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": f"DOCFL-{suffix}-{_suffix()}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_folder(s, supplier_id: str, name: str,
               parent_id: str | None = None) -> dict:
    payload = {
        "owner_type": "supplier",
        "owner_id": supplier_id,
        "name": name,
    }
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = s.post(f"{BASE_URL}/api/v1/document-folders", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ===========================================================================
# Relaxed create (tests 25-28)
# ===========================================================================

class TestRelaxedCreate:
    def test_25_create_without_doc_type_or_title(self, admin):
        """§R2.9: doc_type + title now both optional. Create succeeds
        with neither supplied → both columns NULL."""
        sid = _mk_supplier(admin, "rel1")
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid},
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["doc_type"] is None
        assert out["title"] is None
        # Folder unfiled by default.
        assert out["folder_id"] is None
        # has_file invariant untouched.
        assert out["has_file"] is False

    def test_26_invalid_doc_type_still_422_when_supplied(self, admin):
        """Validator still runs when a non-null doc_type is supplied."""
        sid = _mk_supplier(admin, "rel2")
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid, "doc_type": "Bogus_Type"},
        )
        assert r.status_code == 422, r.text
        assert "doc_type" in r.json()["detail"]

    def test_27_create_with_valid_folder_id(self, admin):
        sid = _mk_supplier(admin, "rel3")
        f = _mk_folder(admin, sid, "Compliance")
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid,
                "title": "Filed at create",
                "folder_id": f["id"],
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["folder_id"] == f["id"]

    def test_28_create_with_other_supplier_folder_returns_422(self, admin):
        s1 = _mk_supplier(admin, "rel4a")
        s2 = _mk_supplier(admin, "rel4b")
        f_s1 = _mk_folder(admin, s1, "S1-Folder")
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": s2,
                "title": "wrong supplier",
                "folder_id": f_s1["id"],
            },
        )
        assert r.status_code == 422, r.text
        assert "different supplier" in r.json()["detail"].lower()


# ===========================================================================
# Document move (tests 29-31)
# ===========================================================================

class TestDocumentMove:
    def test_29_move_document_to_folder(self, admin):
        sid = _mk_supplier(admin, "mv1")
        f = _mk_folder(admin, sid, "Target")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": sid, "title": "doc"},
        ).json()
        assert d["folder_id"] is None
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/move",
            json={"folder_id": f["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["folder_id"] == f["id"]

        # Audit row was written.
        from sqlalchemy import create_engine, text as _text
        eng = create_engine(DATABASE_URL, future=True)
        try:
            with eng.connect() as c:
                n = c.execute(_text(
                    "SELECT count(*) FROM audit_log "
                    " WHERE resource_id = :rid AND action = 'Update'"
                ), {"rid": d["id"]}).scalar()
            assert n >= 1
        finally:
            eng.dispose()

    def test_30_move_document_to_null(self, admin):
        sid = _mk_supplier(admin, "mv2")
        f = _mk_folder(admin, sid, "Origin")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid,
                "title": "doc",
                "folder_id": f["id"],
            },
        ).json()
        assert d["folder_id"] == f["id"]
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/move",
            json={"folder_id": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["folder_id"] is None

    def test_31_move_to_different_supplier_folder_422(self, admin):
        s1 = _mk_supplier(admin, "mv3a")
        s2 = _mk_supplier(admin, "mv3b")
        f_s2 = _mk_folder(admin, s2, "Wrong-target")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={"supplier_id": s1, "title": "doc-s1"},
        ).json()
        r = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/move",
            json={"folder_id": f_s2["id"]},
        )
        assert r.status_code == 422, r.text


# ===========================================================================
# Archive-empty interaction (test 32)
# ===========================================================================

class TestArchiveLiveDocOnly:
    def test_32_archived_document_does_not_block_folder_archive(
        self, admin,
    ):
        """§R5 #32 — archive-empty check counts LIVE docs only; an
        archived doc inside a folder must NOT block folder archive."""
        sid = _mk_supplier(admin, "blk")
        f = _mk_folder(admin, sid, "Cleanup")
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid,
                "title": "old doc",
                "folder_id": f["id"],
            },
        ).json()
        # Folder archive blocked while doc is live.
        r1 = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}/archive"
        )
        assert r1.status_code == 422

        # Archive the doc.
        admin.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/archive"
        )
        # Now folder archive should succeed (archived doc doesn't count).
        r2 = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}/archive"
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["is_archived"] is True
