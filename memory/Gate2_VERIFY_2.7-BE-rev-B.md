# Gate 2 VERIFY — Build Pack 2.7-BE-rev-B (SharePoint via Microsoft Graph)

Date: 2026-02 (rev-B Gate 2)
Scope: §R3 (service wiring) + §R4 (router) on top of Gate 1.
Stopped at Gate 2 per §R7 — §R6 (smoke-test) + closing docs deferred to Gate 3.

---

## A) Pytest double-run — test_supplier_documents.py + test_supplier_document_files.py

Command:
    cd backend && python -m pytest \
        tests/test_supplier_documents.py \
        tests/test_supplier_document_files.py

Run 1 result:    **32 passed in 6.62s**   (12 metadata tests + 20 new file tests)
Run 2 result:    **32 passed in 6.60s**

### test_supplier_documents.py — 12 tests
(file_ref dropped from create body; new ignore-client-file_ref test added;
serialiser test updated for rev-B has_file shape)

    TestCreate
      test_create_document_persists                  (rev-B reshape)
      test_create_ignores_client_supplied_file_ref   (NEW — §R4.2)
      test_invalid_doc_type_rejected
      test_create_without_perm_returns_403
    TestListArchiveFlag
      test_list_excludes_archived_by_default
    TestArchiveLifecycle
      test_archive_unarchive_round_trip
    TestCrossTenant
      test_get_unknown_id_returns_404
      test_list_unknown_supplier_returns_404
    TestExpiryStoredOnly
      test_expiry_date_stored_and_returned_no_scan_side_effect
    TestUpdate
      test_patch_updates_title_and_audits
    TestReadonlyCannotView
      test_readonly_get_returns_403
    TestSerialiserGating
      test_serialise_omits_sensitive_when_flag_off   (rev-B has_file shape)

### test_supplier_document_files.py — 20 new tests (≥18 required)

    TestUploadHappyPath (4)
      test_upload_returns_200_with_has_file_true_and_metadata
      test_upload_returns_serialised_doc_shape
      test_file_ref_is_parseable_stored_object_ref_json
      test_get_after_upload_shows_has_file_true
    TestDownload (4)
      test_download_returns_same_bytes_and_headers
      test_download_round_trip_binary_arbitrary_bytes
      test_download_no_file_returns_404
      test_download_unknown_doc_returns_404
    TestValidation (4)
      test_upload_over_size_cap_returns_413
      test_upload_disallowed_content_type_returns_422
      test_upload_empty_file_returns_422
      test_filename_with_traversal_is_sanitised
    TestPermissions (2)
      test_upload_without_edit_perm_returns_403
      test_download_without_view_sensitive_returns_403
    TestCrossTenant (1)
      test_upload_to_unknown_doc_returns_404
    TestReplaceSupersedes (1)
      test_second_upload_supersedes_first
    TestPatchCannotMutateFileRef (1)
      test_patch_body_with_file_ref_is_silently_ignored
    TestAudit (2)
      test_upload_records_add_attachment_audit_row
      test_download_records_export_audit_row
    TestSerialiserNonSensitive (1)
      test_non_sensitive_caller_sees_has_file_true_but_null_name_and_ref

Total new tests: **20** (Build Pack target: ≥18). All in
`SHAREPOINT_MODE='test-stub'` — zero Azure dependency.

---

## B) §R4.2 VERIFY — `file_ref` removed from create/update request bodies

Static introspection of the Pydantic schemas:

    >>> from app.routers.supplier_documents import (
    ...     SupplierDocumentCreateBody, SupplierDocumentUpdateBody)
    >>> list(SupplierDocumentCreateBody.model_fields.keys())
    ['supplier_id', 'doc_type', 'title', 'issued_on', 'expires_on', 'notes']
    >>> list(SupplierDocumentUpdateBody.model_fields.keys())
    ['doc_type', 'title', 'issued_on', 'expires_on', 'notes']

`file_ref` is **absent** from both bodies. Run-time behaviour:
- `test_create_ignores_client_supplied_file_ref` — POST a body with
  `"file_ref": "s3://attacker-supplied/evil.pdf"` → 201 OK, response
  shows `file_ref: null`, GET round-trip confirms it never persisted.
- `test_patch_body_with_file_ref_is_silently_ignored` — PATCH with
  `"file_ref": "s3://injected/evil.pdf", "title": "After Patch"` → 200,
  title updated, `file_ref` stays `None`.

Service-layer belt-and-braces: even if a caller bypasses the router and
calls `services.supplier_documents.update_document(...)` with a
`file_ref` key, the service explicitly ignores it (see comment in the
update_document body).

---

## C) Error mapping — verified at router + service layer

| Service-layer exception | Router status | Detail string |
| --- | --- | --- |
| `ValueError("file exceeds maximum upload size ...")` | **413** | propagated `str(e)` |
| `ValueError("content_type ... not allowed")` | **422** | propagated `str(e)` |
| `ValueError("file is empty")` | **422** | propagated `str(e)` |
| `LookupError` (doc not in tenant) | **404** | "Supplier document not found" |
| `LookupError` (doc has no file) | **404** | "Supplier document file not found" |
| `SharePointError` | **502** | "document storage unavailable" |

Grep proof — `SharePointError` → `HTTPException` blocks in the router
(static analysis of `routers/supplier_documents.py`):

    SharePointError -> HTTPException blocks: 2
      [1] status_code=502, detail="document storage unavailable",
      [2] status_code=502, detail="document storage unavailable",
    OK: SharePointError -> 502 "document storage unavailable", no Graph
    internals leaked (no "token", "bearer", "graph.microsoft", or
    "sharepoint.com" in any of the SharePointError → 502 details).

The 413/422 split was the implementer's choice per §R4.1 ("pick one,
document it"). We picked **413** for size-cap (clean Payload Too
Large semantics) and **422** for everything else.

Pytest live coverage:
- `test_upload_over_size_cap_returns_413` (asserts exact 413)
- `test_upload_disallowed_content_type_returns_422`
- `test_upload_empty_file_returns_422`
- `test_download_no_file_returns_404`
- `test_upload_to_unknown_doc_returns_404`

---

## D) Permission count — unchanged at 132

    $ psql -c "SELECT count(*) AS perm_count FROM permissions;"
     perm_count
    ------------
            132
    (1 row)

No new permissions were added at Gate 2. Upload reuses
`supplier_documents.edit`; download reuses
`supplier_documents.view_sensitive` (the same permission already gating
the response-level sensitive fields).

---

## E) Alembic head — still 0042_file_ref_text

    $ alembic current
    INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
    INFO  [alembic.runtime.migration] Will assume transactional DDL.
    0042_file_ref_text (head)

No new migration in Gate 2. The structured `StoredObjectRef` JSON is
serialised into the existing `file_ref` `Text` column widened by
0042; file metadata (name, size, content_type) is derived from the
JSON envelope rather than carried in new columns.

---

## F) Files touched at Gate 2

    backend/app/services/supplier_documents.py    (+upload_document_file, +download_document_file,
                                                  +_supplier_folder_path, +ALLOWED_DOC_MIME_TYPES,
                                                  has_file/file metadata in serialise,
                                                  removed client-settable file_ref)
    backend/app/routers/supplier_documents.py     (rewrote — file_ref dropped from create/update
                                                  bodies, +POST/{id}/file, +GET/{id}/file,
                                                  +_document_store_dep, +_value_error_to_http)
    backend/tests/test_supplier_documents.py      (rev-B reshape — no client file_ref,
                                                  +test_create_ignores_client_supplied_file_ref,
                                                  serialiser test updated for has_file)
    backend/tests/test_supplier_document_files.py (new — 20 tests, ≥18 required)
    memory/Gate2_VERIFY_2.7-BE-rev-B.md           (this file)
    CHANGELOG.md                                  (rev-B Gate 2 append)

Not touched: `backend/scripts/sharepoint_smoke_test.py` (Gate 3),
`docs/chat-summaries/chat-41-closing.md` (Gate 3),
`docs/SY_Hub_Phase2_Backlog.md` (operator-owned).

---

## STOPPED at Gate 2 per §R7. Awaiting operator approval before Gate 3.
