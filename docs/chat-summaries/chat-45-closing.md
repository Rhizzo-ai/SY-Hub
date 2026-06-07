# Chat 45 — Build Pack 2.7-DOCS-BE — Closing Summary

**Pack:** Build Pack 2.7-DOCS-BE · Document Folder Engine (Backend) · B79 Part 1 of 2
**Scope:** Backend only (folder-tree UI ships in 2.7-DOCS-FE, next chat).
**Status:** Committed; ready for operator to Save to GitHub.

## What shipped

A polymorphic logical folder tree (`document_folders`) attachable to
any owner record via `(owner_type, owner_id)`. Suppliers first;
projects + subcontracts will inherit later by widening the
`FOLDER_OWNER_TYPES` tuple + `OWNER_VIEW_PERM` map + the
`ck_document_folders_owner_type` CHECK — no endpoint changes.

Existing supplier compliance documents were migrated into one
**`Compliance`** folder per supplier (data step inside the alembic
revision, idempotent). `supplier_documents.doc_type` and `.title` are
now optional; `supplier_documents.folder_id` is the new optional FK
to `document_folders` (SET NULL on folder delete).

New `documents.move` permission gates folder + document moves. Per
the §R4.3 union rule, **finance** holds `documents.move` (because it
holds `supplier_documents.edit`); per the operator's §R4.3b broadening,
finance also gains `documents.create` + `documents.edit` (catalogue
codes already existed; only role-grant rows are new) so finance can
structure folders end-to-end.

Permission catalogue: **132 → 133.** Alembic head: **`0042_file_ref_text`
→ `0043_document_folders`.** Roles: **10** (unchanged).

The existing frontend `DocumentsTab.jsx` keeps working unchanged
because the `supplier_documents` endpoints stayed behaviourally
identical (mandatory fields relaxed; nothing previously required is
now rejected).

## Gate evidence

- **Gate 1 (model + migration).** `alembic upgrade head` clean,
  round-trip down/up clean. `document_folders` table created with
  all columns, three indexes plus the partial unique sibling-name
  index, `ck_document_folders_owner_type` CHECK present.
  `ck_supplier_documents_doc_type` gone; `doc_type`/`title` are
  nullable; `folder_id` column + `ix_supplier_documents_folder_id`
  added. `permission_action` enum contains `move`. Data step ran
  with the empty-DB invariant intact (zero pre-existing
  `supplier_documents` rows on this fresh pod — the migration's
  data block exercised every clause but had no rows to backfill).
- **Gate 2 (RBAC).** Permission catalogue count = **133** (bootstrap
  `verify.perms result=ok expected=133 actual=133`). Roles holding
  `documents.move`: `super_admin`, `director`, `project_manager`,
  `finance`. Finance also holds `documents.create` + `documents.edit`.
- **Gate 3 (service + router).** All 8 new/extended routes
  registered:
  - POST/GET/{id}/PATCH/MOVE/ARCHIVE/UNARCHIVE under
    `/api/v1/document-folders`
  - POST `/api/v1/supplier-documents/{id}/move`
  - Error mapping: `ValueError → 422`, `LookupError → 404`,
    missing-perm → 403, cross-tenant/cross-owner → 404.
  - Loop guard rejects self / descendant moves (tested).
- **Gate 4 (tests).** `EXIT=0`, **1376 passed + 3 X (xpassed/xfailed),
  0 failed, 0 errors**, 1379 collected. New test files:
  - `backend/tests/test_document_folders.py` — **30** functions.
  - `backend/tests/test_supplier_documents_folders.py` — **8**.
  - **Total new: 38** (Build Pack target ≥36).

## Design decisions and trade-offs

- **Logical-only folders.** This pack treats `document_folders` as
  pure metadata. Physical storage paths remain
  `Suppliers/{supplier_id}` (rev-B layout). Mirroring physical
  SharePoint structure onto the logical tree is a separate future
  build (interacts with the still-pending live-mode consent).
- **Loop guard implemented as ancestor walk on the destination.**
  Cheaper than walking descendants of the source. Both work; the
  ancestor walk is bounded by tree depth which is typically small.
- **Sibling-name uniqueness via partial unique index, NOT
  application-side.** The DB enforces it, the service catches the
  `IntegrityError` inside a `begin_nested()` savepoint and re-raises
  as `ValueError`. Avoids TOCTOU bugs under concurrent creates.
  `COALESCE(parent_id, '00000000-...-...-...-...000000000000'::uuid)`
  ensures root-level NULL parents de-duplicate (Postgres treats
  NULL distinct in plain UNIQUE).
- **Archive blocks non-empty folders.** v1 keeps cascade out of
  scope (backlog item; cascade-archive a possible future
  enhancement). Unarchive of a folder whose parent is archived is
  also blocked — preserves the "live folder lives in a live parent"
  invariant.
- **Folder reads follow owner-surface view perms (§R3.0).** Finance
  holds `supplier_documents.view` but not `documents.view`; gating
  folder reads on `supplier_documents.view` for supplier-owned
  folders prevents a silent viewing regression (test 35 + 35b are
  the regression guards).

## Backlog items raised (operator hand-adds; Emergent did not touch)

- **B79-FE** — Folder-tree UI. Mount swap at
  `frontend/src/pages/SupplierDetail.jsx:274`. Retires the flat
  `DocumentsTab` list (or wraps it). Next chat.
- **Role & Permissions Admin screen** — Buildertrend-style control
  panel over the 133 existing permissions; sizeable own build.
- **External-party folder access** — subcontractor/supplier/designer
  view + upload-into-specific-folders only. Wired with portal work
  (2.9). Externals are un-granted until then.
- **Physical storage path reorg** — mirror logical folders into
  SharePoint subfolders. Separate build; interacts with live-mode
  consent.
- **Cascade archive** — archive non-empty folders by cascading.
  Possible future enhancement; v1 blocks the operation.
- **Owner-type expansion** — `project`, `subcontract` owner types
  plus an enum-widen migration when those tracks adopt the engine.

## Files landed (full list)

See the §"Files landed" section in `CHANGELOG.md` for the canonical
list. **NOT touched:** `docs/SY_Hub_Phase2_Backlog.md`,
`frontend/**/*`.
