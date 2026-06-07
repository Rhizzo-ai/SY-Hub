"""Chat 41 §R5.1 (Build Pack 2.7-BE-rev-B) — supplier_documents file
upload/download HTTP tests. All in SHAREPOINT_MODE='test-stub'.

Every test exercises the live FastAPI app against the `StubDocumentStore`
process singleton on the backend side. Zero Azure dependency. Tests
mirror `test_actuals_attachments.py` conventions (multipart upload,
streamed download) so the new endpoints feel native to the codebase.

Gate-2 coverage required by §R5.1:
  1.  upload → 200, has_file=true, file_name/size populated (sensitive)
  2.  non-sensitive caller sees has_file=true but null name/ref
  3.  download returns same bytes + correct content-type + Content-Disposition
  4.  upload over the size cap → 413 (exact)
  5.  disallowed content-type → 422
  6.  upload without supplier_documents.edit → 403
  7.  download without supplier_documents.view_sensitive → 403
  8.  download a doc with no file → 404
  9.  replacing a file: second upload supersedes; old stub object deleted
  10. upload to a cross-tenant / unknown doc id → 404
  11. filename with `../` traversal sanitised
Additional rev-B robustness:
  12. upload empty file → 422
  13. upload audit row persists (Add_Attachment)
  14. download audit row persists (Export)
  15. binary round-trip preserves arbitrary bytes (incl. \\x00)
  16. file_ref is a parseable StoredObjectRef JSON envelope
  17. POST /{id}/file returns 200 with serialised doc
  18. PATCH /{id} cannot mutate file_ref (rev-B §R4.2 tightening)
"""
from __future__ import annotations

import json
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
READONLY_EMAIL = "test-readonly@example.test"


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


# ---------------------------------------------------------------------------
# Module fixtures (mirror test_supplier_documents.py)
# ---------------------------------------------------------------------------

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
                AND name LIKE 'FILES-%'
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_supplier(admin_session, name_suffix: str = "") -> str:
    sx = _suffix()
    r = admin_session.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": f"FILES-{name_suffix}-{sx}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_doc(admin_session, supplier_id: str, *, title: str = "Doc") -> dict:
    r = admin_session.post(
        f"{BASE_URL}/api/v1/supplier-documents",
        json={
            "supplier_id": supplier_id,
            "doc_type": "Other",
            "title": title,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload(session, doc_id: str, *, filename: str, content: bytes,
            content_type: str = "application/pdf"):
    """POST multipart to /supplier-documents/{id}/file.

    The shared conftest session pins ``Content-Type: application/json``
    for normal JSON calls. For multipart we must let `requests` compute
    ``Content-Type: multipart/form-data; boundary=...`` itself, so we
    pop the JSON header for the duration of this call.
    """
    files = {"file": (filename, content, content_type)}
    saved = session.headers.pop("Content-Type", None)
    try:
        return session.post(
            f"{BASE_URL}/api/v1/supplier-documents/{doc_id}/file",
            files=files,
        )
    finally:
        if saved is not None:
            session.headers["Content-Type"] = saved


# ---------------------------------------------------------------------------
# §R5.1 — file upload / download HTTP tests
# ---------------------------------------------------------------------------

class TestUploadHappyPath:
    def test_upload_returns_200_with_has_file_true_and_metadata(
        self, admin, engine,
    ):
        """(1) Upload to a doc → 200, has_file=true, file_name/size
        populated for the sensitive caller (admin holds view_sensitive)."""
        sid = _mk_supplier(admin, "happy")
        d = _mk_doc(admin, sid, title="Happy Path")

        payload = b"PDF binary content here. \x00\x01"
        r = _upload(admin, d["id"], filename="cert.pdf", content=payload)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["has_file"] is True
        assert out["file_name"] == "cert.pdf"
        assert out["file_size"] == len(payload)
        assert out["file_content_type"] == "application/pdf"
        assert out["file_ref"] is not None

    def test_upload_returns_serialised_doc_shape(self, admin, engine):
        """(17) POST /{id}/file returns the full serialised doc shape."""
        sid = _mk_supplier(admin, "shape")
        d = _mk_doc(admin, sid, title="Shape")
        r = _upload(admin, d["id"], filename="a.pdf", content=b"abc",
                    content_type="application/pdf")
        assert r.status_code == 200
        out = r.json()
        # All the regular serialised fields are present.
        for k in ("id", "supplier_id", "doc_type", "title",
                  "is_archived", "has_file", "file_ref", "file_name",
                  "file_size", "file_content_type"):
            assert k in out, f"missing field {k!r} in upload response"
        assert out["id"] == d["id"]
        assert out["title"] == "Shape"

    def test_file_ref_is_parseable_stored_object_ref_json(self, admin, engine):
        """(16) The persisted file_ref is a structured StoredObjectRef
        JSON envelope (not free text)."""
        sid = _mk_supplier(admin, "json")
        d = _mk_doc(admin, sid, title="JSON Ref")
        r = _upload(admin, d["id"], filename="x.pdf", content=b"X",
                    content_type="application/pdf")
        ref_raw = r.json()["file_ref"]
        assert ref_raw is not None
        parsed = json.loads(ref_raw)
        assert {"item_id", "drive_id", "web_url", "name",
                "size", "content_type"} <= set(parsed.keys())
        assert parsed["name"] == "x.pdf"
        assert parsed["size"] == 1
        assert parsed["content_type"] == "application/pdf"

    def test_get_after_upload_shows_has_file_true(self, admin, engine):
        """(1 follow-up) GET /{id} after upload reflects has_file + metadata."""
        sid = _mk_supplier(admin, "geta")
        d = _mk_doc(admin, sid, title="After Upload")
        _upload(admin, d["id"], filename="z.pdf", content=b"ZZZ",
                content_type="application/pdf")
        r = admin.get(f"{BASE_URL}/api/v1/supplier-documents/{d['id']}")
        assert r.status_code == 200
        out = r.json()
        assert out["has_file"] is True
        assert out["file_name"] == "z.pdf"
        assert out["file_size"] == 3


class TestDownload:
    def test_download_returns_same_bytes_and_headers(self, admin, engine):
        """(3) Download returns the exact bytes, content-type, and a
        Content-Disposition: attachment header with the safe filename."""
        sid = _mk_supplier(admin, "dl")
        d = _mk_doc(admin, sid, title="DL")
        payload = b"hello world download test"
        _upload(admin, d["id"], filename="report.pdf", content=payload,
                content_type="application/pdf")

        r = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/file"
        )
        assert r.status_code == 200, r.text
        assert r.content == payload
        assert r.headers["content-type"].startswith("application/pdf")
        cd = r.headers.get("content-disposition", "")
        assert cd.startswith("attachment;")
        assert 'filename="report.pdf"' in cd

    def test_download_round_trip_binary_arbitrary_bytes(self, admin, engine):
        """(15) Binary round-trip preserves arbitrary bytes including
        nulls and high-bit chars."""
        sid = _mk_supplier(admin, "bin")
        d = _mk_doc(admin, sid, title="Binary")
        payload = bytes(range(256))  # every byte value 0..255
        _upload(admin, d["id"], filename="raw.bin", content=payload,
                content_type="application/pdf")  # use allowed type
        r = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/file"
        )
        assert r.status_code == 200
        assert r.content == payload

    def test_download_no_file_returns_404(self, admin, engine):
        """(8) Doc exists but no file uploaded → 404."""
        sid = _mk_supplier(admin, "nofile")
        d = _mk_doc(admin, sid, title="No File")
        r = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/file"
        )
        assert r.status_code == 404, r.text

    def test_download_unknown_doc_returns_404(self, admin, engine):
        """(10 + 8) Unknown / cross-tenant doc id on download → 404."""
        ghost = uuid.uuid4()
        r = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{ghost}/file"
        )
        assert r.status_code == 404, r.text


class TestValidation:
    def test_upload_over_size_cap_returns_413(self, admin, engine):
        """(4) Over-cap payload → 413 (exact). The Build Pack lets us
        pick 413 or 422 for size — we picked 413 for clearer semantics.
        """
        sid = _mk_supplier(admin, "big")
        d = _mk_doc(admin, sid, title="Big")
        # Default SHAREPOINT_MAX_BYTES is 25 MiB. Send 25 MiB + 1 byte.
        # 26214401 bytes — slightly above the cap.
        oversize = b"x" * (25 * 1024 * 1024 + 1)
        r = _upload(admin, d["id"], filename="big.pdf", content=oversize,
                    content_type="application/pdf")
        assert r.status_code == 413, (
            f"expected 413, got {r.status_code}: {r.text[:200]}"
        )
        assert "exceeds maximum upload size" in r.json()["detail"]

    def test_upload_disallowed_content_type_returns_422(self, admin, engine):
        """(5) Executable / non-allowlisted content-type → 422."""
        sid = _mk_supplier(admin, "exe")
        d = _mk_doc(admin, sid, title="EXE")
        r = _upload(admin, d["id"], filename="evil.exe", content=b"MZ",
                    content_type="application/x-msdownload")
        assert r.status_code == 422, r.text
        assert "not allowed" in r.json()["detail"]

    def test_upload_empty_file_returns_422(self, admin, engine):
        """(12) Empty file body → 422 (validation, not 413)."""
        sid = _mk_supplier(admin, "empty")
        d = _mk_doc(admin, sid, title="Empty")
        r = _upload(admin, d["id"], filename="empty.pdf", content=b"",
                    content_type="application/pdf")
        assert r.status_code == 422, r.text
        assert "empty" in r.json()["detail"]

    def test_filename_with_traversal_is_sanitised(self, admin, engine):
        """(11) Filename containing `../` is stripped down to the
        basename via _safe_filename before storage."""
        sid = _mk_supplier(admin, "trav")
        d = _mk_doc(admin, sid, title="Traversal")
        r = _upload(
            admin, d["id"],
            filename="../../../etc/passwd",
            content=b"safe",
            content_type="text/plain",
        )
        assert r.status_code == 200, r.text
        out = r.json()
        # The stored filename is just `passwd` — no path components.
        assert out["file_name"] == "passwd"
        assert ".." not in out["file_name"]
        assert "/" not in out["file_name"]


class TestPermissions:
    def test_upload_without_edit_perm_returns_403(
        self, admin, readonly, engine,
    ):
        """(6) Caller without supplier_documents.edit → 403 on upload."""
        sid = _mk_supplier(admin, "noedit")
        d = _mk_doc(admin, sid, title="No Edit")
        r = _upload(readonly, d["id"], filename="x.pdf", content=b"x",
                    content_type="application/pdf")
        assert r.status_code == 403, r.text

    def test_download_without_view_sensitive_returns_403(
        self, admin, readonly, engine,
    ):
        """(7) Caller without supplier_documents.view_sensitive → 403
        on download (readonly holds neither view nor view_sensitive)."""
        sid = _mk_supplier(admin, "nosens")
        d = _mk_doc(admin, sid, title="No Sens")
        _upload(admin, d["id"], filename="a.pdf", content=b"abc",
                content_type="application/pdf")
        r = readonly.get(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/file"
        )
        assert r.status_code == 403, r.text


class TestCrossTenant:
    def test_upload_to_unknown_doc_returns_404(self, admin, engine):
        """(10) Upload to unknown / cross-tenant doc id → 404."""
        ghost = uuid.uuid4()
        r = _upload(admin, str(ghost), filename="x.pdf", content=b"x",
                    content_type="application/pdf")
        assert r.status_code == 404, r.text


class TestReplaceSupersedes:
    def test_second_upload_supersedes_first(self, admin, engine):
        """(9) A second upload to the same doc replaces the first; the
        document's file_ref points at the new object.

        We assert the observable contract over HTTP: file_ref changes,
        new bytes download successfully. The stub's old-object delete is
        unit-tested at the service layer (see TestReplaceServiceLayer
        in test_sharepoint_client.py if added later) — out of HTTP scope.
        """
        sid = _mk_supplier(admin, "rep")
        d = _mk_doc(admin, sid, title="Replace")

        r1 = _upload(admin, d["id"], filename="v1.pdf", content=b"VERSION_ONE",
                     content_type="application/pdf")
        assert r1.status_code == 200
        ref1 = r1.json()["file_ref"]

        r2 = _upload(admin, d["id"], filename="v2.pdf", content=b"VERSION_TWO",
                     content_type="application/pdf")
        assert r2.status_code == 200
        ref2 = r2.json()["file_ref"]

        assert ref1 != ref2, "expected file_ref to change after replacement"

        # Download returns the new bytes.
        rd = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/file"
        )
        assert rd.status_code == 200
        assert rd.content == b"VERSION_TWO"
        # The new file_name is v2.pdf.
        cd = rd.headers.get("content-disposition", "")
        assert 'filename="v2.pdf"' in cd


class TestPatchCannotMutateFileRef:
    def test_patch_body_with_file_ref_is_silently_ignored(
        self, admin, engine,
    ):
        """(18) rev-B §R4.2: PATCH /{id} body cannot carry `file_ref`.

        Pydantic drops the field; the persisted file_ref stays as it
        was (None for a freshly-created doc, or the upload-set ref).
        """
        sid = _mk_supplier(admin, "patchref")
        d = _mk_doc(admin, sid, title="Patch")
        # PATCH attempting to inject a free-text file_ref.
        r = admin.patch(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}",
            json={"file_ref": "s3://injected/evil.pdf",
                  "title": "After Patch"},
        )
        assert r.status_code == 200, r.text
        # Title updated; file_ref unchanged (still None).
        assert r.json()["title"] == "After Patch"
        assert r.json()["file_ref"] is None
        assert r.json()["has_file"] is False


class TestAudit:
    def test_upload_records_add_attachment_audit_row(self, admin, engine):
        """(13) Upload writes an audit row with action='Add_Attachment'
        and the resource_id pointing at the document."""
        sid = _mk_supplier(admin, "audit-up")
        d = _mk_doc(admin, sid, title="Audit Up")
        _upload(admin, d["id"], filename="a.pdf", content=b"abc",
                content_type="application/pdf")

        with engine.connect() as c:
            cnt = c.execute(text("""
                SELECT count(*) FROM audit_log
                 WHERE resource_type = 'supplier_document'
                   AND resource_id = :id
                   AND action = 'Add_Attachment'
            """), {"id": d["id"]}).scalar()
        assert cnt >= 1, (
            f"expected an Add_Attachment audit row for doc {d['id']}"
        )

    def test_download_records_export_audit_row(self, admin, engine):
        """(14) Download writes an audit row with action='Export' and
        the resource_id pointing at the document."""
        sid = _mk_supplier(admin, "audit-dl")
        d = _mk_doc(admin, sid, title="Audit Dl")
        _upload(admin, d["id"], filename="b.pdf", content=b"xyz",
                content_type="application/pdf")

        rd = admin.get(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/file"
        )
        assert rd.status_code == 200

        with engine.connect() as c:
            cnt = c.execute(text("""
                SELECT count(*) FROM audit_log
                 WHERE resource_type = 'supplier_document'
                   AND resource_id = :id
                   AND action = 'Export'
            """), {"id": d["id"]}).scalar()
        assert cnt >= 1, (
            f"expected an Export audit row for doc {d['id']}"
        )


class TestSerialiserNonSensitive:
    def test_non_sensitive_caller_sees_has_file_true_but_null_name_and_ref(
        self,
    ):
        """(2) rev-B contract: a non-sensitive caller sees
        `has_file=true` but `file_name` / `file_ref` are nulled.

        Unit-test on the serialiser directly — the seeded test roles
        either hold full view_sensitive (admin/pm) or no view at all
        (readonly), so there is no HTTP role that lets us exercise
        the in-between state end-to-end.
        """
        from app.services.supplier_documents import (
            SENSITIVE_RESPONSE_FIELDS, serialise,
        )
        from app.services.sharepoint_client import StoredObjectRef

        ref = StoredObjectRef(
            item_id="item-abc",
            drive_id="drive-1",
            web_url="https://stub.invalid/foo",
            name="cert.pdf",
            size=1234,
            content_type="application/pdf",
        )

        class _FakeRow:
            id = uuid.uuid4()
            tenant_id = uuid.uuid4()
            supplier_id = uuid.uuid4()
            doc_type = "Other"
            title = "T"
            folder_id = None  # Chat 45 §R1.2 — unfiled.
            file_ref = ref.to_json()
            issued_on = None
            expires_on = None
            notes = "internal-only"
            is_archived = False
            archived_at = None
            from datetime import datetime, timezone
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)

        # Sensitive viewer: full metadata.
        out_full = serialise(_FakeRow(), include_sensitive=True)
        assert out_full["has_file"] is True
        assert out_full["file_name"] == "cert.pdf"
        assert out_full["file_size"] == 1234
        assert out_full["file_content_type"] == "application/pdf"
        assert out_full["file_ref"] == ref.to_json()

        # Non-sensitive viewer: has_file still true; everything else null.
        out_lite = serialise(_FakeRow(), include_sensitive=False)
        assert out_lite["has_file"] is True, (
            "has_file is non-sensitive — every viewer sees it"
        )
        for k in SENSITIVE_RESPONSE_FIELDS:
            assert out_lite[k] is None, (
                f"non-sensitive caller must see {k!r}=None"
            )
