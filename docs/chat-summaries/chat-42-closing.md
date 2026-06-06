# Chat 42 — Build Pack 2.7-FE-docupload closing summary

**Pack:** Build Pack 2.7-FE-docupload — Supplier-document file upload/download control (frontend only)
**Branch base:** main @ `0042_file_ref_text`, **132** permissions, 10 roles
**Head after this pack:** **`0042_file_ref_text`** (unchanged — backend frozen)
**Permissions:** **132** (unchanged)
**Roles:** 10 (unchanged)
**Backlog file (`docs/SY_Hub_Phase2_Backlog.md`):** NOT touched per the
opener (operator-owned).
**Auth flows touched:** none.
**Backend:** untouched — `git status --porcelain backend/` empty at
both gate-stop points and at push time. Alembic head and permission
count re-asserted at the Gate 2 VERIFY.

---

## Gate run timeline

| Gate | Scope | Status |
|---|---|---|
| Gate 1 | §R3 API layer (`uploadDocumentFile`, `downloadDocumentFile`, `parseContentDispositionFilename`) + §R4 upload hook + their tests | ✅ landed; VERIFY printed inline at the operator's STOP gate; operator verified on `origin/main` via raw-fetch before approving |
| Gate 2 | §R1 destructive cleanup (`file_ref` purge) + §R2 File column + `DocumentFileCell` + `FilePicker` + Replace + Download + §R5 component tests | ✅ landed; VERIFY printed inline at the operator's STOP gate (this close) |

Build Pack §R7 gating honoured: no auto-advance between gates, no
push outside of `Save to GitHub`, no closing docs written until
operator approved Gate 2 + reverified backend frozen state after a
preview-pod recovery.

---

## Files changed (frontend only)

### Modified

- `frontend/src/lib/api/supplierDocuments.js` — added
  `uploadDocumentFile(id, file)` (multipart POST through the shared
  axios `api` instance, field name `"file"`), `downloadDocumentFile(id)`
  (cookie-aware blob fetch via `authedFetch` against
  `${API_BASE}/v1/supplier-documents/{id}/file`, returns
  `{blob, filename}` parsed from Content-Disposition, throws a
  structured `{status, detail}` on non-2xx), and
  `parseContentDispositionFilename(header)` (RFC-5987
  `filename*=UTF-8''…` preferred over plain `filename="…"`,
  `null` on unparseable).
- `frontend/src/hooks/supplierDocuments.js` — added
  `useUploadDocumentFile(supplierId)`: `useMutation({id, file})` that
  calls `docsApi.uploadDocumentFile` and invalidates
  `docsKeys.all(supplierId)` on success (mirrors `useCreateDocument`).
  Download stays imperative (no hook) by design — it's a blob →
  object URL → click → revoke action, not cache-shaped.
- `frontend/src/components/suppliers/DocumentsTab.jsx` — §R1
  destructive cleanup of `file_ref` (Input, `emptyForm`, `rowToForm`,
  `onSubmit` payload, "File ref" `<SensitiveValue/>` column) and the
  full §R2 File column with `DocumentFileCell` (sub-component owning
  the conditional matrix for has_file × sensitive × edit × archived)
  and `FilePicker` (sub-component owning the mobile-first
  `<input type="file">` baseline + accept allowlist + uploading
  state). Constants `ALLOWED_MIME_TYPES` (frozen) and
  `MAX_FILE_BYTES = 25 MB` are exported so callers and tests share a
  single source of truth. Helpers `preCheckFile` / `formatFileSize` /
  `uploadErrorMessage` / `downloadErrorMessage` colocated.
- `frontend/src/components/suppliers/__tests__/DocumentsTab.test.jsx` —
  grew **10 → 30 tests**. All 13 §R5 acceptance cases covered, plus
  §R2.4 archived-row guard, §R2.5 mobile-first invariant, §R9
  uploading-state guard, and a rewrite of the original create-dialog
  test so the asserted payload no longer carries `file_ref`. Mocks:
  `@/hooks/supplierDocuments`, `@/lib/api/supplierDocuments`,
  `@/context/AuthContext`, `sonner`. NO real network.

### Added

- `frontend/src/lib/api/__tests__/supplierDocuments.test.js` — 17
  tests pinning the API-layer contracts: list / create / patch /
  archive / unarchive regression; upload multipart shape + propagated
  rejection; download authedFetch URL contract (hard negative against
  axios), Content-Disposition parsing (RFC-5987 + plain + null),
  structured error envelope on non-2xx; `parseContentDispositionFilename`
  helper edge cases.
- `frontend/src/hooks/__tests__/supplierDocuments.test.jsx` — 11
  tests pinning the hook contracts: query-key tagging by supplierId +
  include-archived flag; mutation invalidations for create/patch/
  archive/unarchive/upload; `useUploadDocumentFile` does NOT
  invalidate on rejection (so a 413/422/502 doesn't refetch).

### Untouched (per opener)

- `docs/SY_Hub_Phase2_Backlog.md` — operator-owned. Operator
  hand-marks **B76 — Supplier-document upload UI** as delivered.

---

## §R5 acceptance map (13/13 covered)

| # | Case | Where it lives |
|---|---|---|
| 1 | Cleanup — `document-form-file-ref` testid absent (add + edit dialog) | `DocumentsTab.test.jsx::§R5 #1` (2 tests) |
| 2 | Upload happy path — PDF pick → hook fired → row flips to file-present (name + size + Download for sensitive viewer) | `§R5 #2` |
| 3 | Empty file pre-check blocks; no request | `§R5 #3` |
| 4 | Disallowed type pre-check blocks; no request | `§R5 #4` |
| 5 | Oversize pre-check blocks; no request; message states the cap | `§R5 #5` |
| 6 | Server 413 → "File is too large — 25 MB cap." toast | `§R5 #6` |
| 7 | Server 422 → server `detail` echoed verbatim | `§R5 #7` |
| 8 | Download 404 → "File not found." toast | `§R5 #8` |
| 9 | 502 (upload + download) → friendly "storage temporarily unavailable" toast; raw detail NOT echoed | `§R5 #9` (2 tests) |
| 10 | Download triggers blob save: `URL.createObjectURL` + `<a>.click` + `URL.revokeObjectURL`; filename fallback to row.file_name when Content-Disposition absent | `§R5 #10` (2 tests) |
| 11 | Sensitive gating — no name/size/Download without `view_sensitive`; neutral indicator only; cell text does not contain filename | `§R5 #11` |
| 12 | Edit gating — no Upload/Replace without `edit`; archived rows: Download stays for sensitive viewers, Replace absent | `§R5 #12` (2 tests) |
| 13 | No URL leak — `cell.outerHTML` carries no `sharepoint`, `graph.microsoft`, or `https?://` (sensitive AND non-sensitive viewers) | `§R5 #13` (2 tests) |

Plus: `§R2.4` archived-row no-Upload guard; `§R2.5` mobile-first
contract (`<input type="file">` with every §R0.3 MIME in `accept`);
`§R9` uploading-state disables the picker.

---

## §R9 scope-creep — confirmed, not silent

1. **Uploading-state guard** — `uploadingId` component state plus
   `disabled` on the `<input>` and `cursor-not-allowed` styling on
   the `<label>` while a mutation is in flight ("Uploading…" copy on
   the affordance). Prevents double-submit on slow / mobile
   connections.
2. **Inline file-type / size hint text** — small caption under the
   empty-state Upload control ("PDF, image, Office docs · 25 MB
   max").
3. **Inline per-row pre-check error** — surfaced in the cell itself
   (`document-row-upload-error-{id}`), cleared on the next pick. We
   intentionally do NOT toast pre-check failures — a per-row inline
   message is closer to the affordance, mobile-first, and avoids
   toast spam when a user fumbles the pick.

All three are pure client-side affordances; the backend is genuinely
frozen.

---

## Gate 1 + Gate 2 VERIFY (canonical, 2nd-run, printed at STOP)

### Jest (full suite, 2nd run, post-Gate-2)

```
Test Suites: 80 passed, 80 total
Tests:       618 passed, 618 total
Snapshots:   1 passed, 1 total
Time:        17.1 s
```

Delta vs Gate 1 baseline: **+20 tests** (Gate 1 finished at 598 tests
across 80 suites). Delta vs pack-start baseline (78 suites / 570
tests): **+2 suites, +48 tests** (the two new lib/api + hooks
suites at Gate 1, plus the DocumentsTab.test.jsx 10 → 30 jump at
Gate 2).

### Jest (targeted, 2nd run)

```
PASS src/components/suppliers/__tests__/DocumentsTab.test.jsx
Test Suites: 1 passed, 1 total
Tests:       30 passed, 30 total
Time:        ~1.2 s
```

### Greps

```
$ grep -n "document-form-file-ref" frontend/src/components/suppliers/DocumentsTab.jsx
(zero matches — testid removed per §R1.1)

$ grep -n "file_ref" frontend/src/components/suppliers/DocumentsTab.jsx
(zero matches — emptyForm/rowToForm/payload all clean per §R1.2)

$ grep -niE "sharepoint|graph\.microsoft" frontend/src/components/suppliers/DocumentsTab.jsx
21: * URL → click → revoke. The SharePoint URL NEVER reaches the DOM.       ← doc comment
68:// SHAREPOINT_MAX_BYTES default — server is source of truth, this just     ← doc comment
242:// ─── §R2.6 Download — bytes-only via authedFetch, never SharePoint URL. ← doc comment

# Strict (block comments + line comments stripped):
#   (zero matches outside comments — no such string in any rendered output)
```

The §R5 #13 runtime assertions independently prove the rendered DOM
is clean (`cell.outerHTML.toLowerCase()` matches none of `sharepoint`,
`graph.microsoft`, `https?://`).

### Backend frozen state

```
$ git status --porcelain backend/
(empty)

$ ls backend/alembic/versions/ | sort | tail -1
0042_file_ref_text.py    ← alembic head unchanged

$ grep "step=verify.perms" $(latest bootstrap log)
expected=132 actual=132
```

Pod recovery during this run did NOT change the backend — the
recovery sequence (`provision_postgres.sh` → `python -m app.bootstrap`)
was a pure re-init that landed on the same head and same perm count.

---

## Push readiness

- Frontend-only diff, two files modified + two files added (Gate 1
  tests already verified on `origin/main` before Gate 2 began).
- Jest double-run green on both gates.
- All §R6 greps zero-hit (or comment-only with the strict variant).
- Backlog file untouched.
- §R8 closing docs (`CHANGELOG.md` + this file + `memory/PRD.md`)
  landed.

Ready for the operator's `Save to GitHub` + `origin/main` raw-fetch
verification. Holding here per §R7 — committed ≠ pushed.

Backlog **B76 — Supplier-document upload UI** is delivered.
Operator hand-marks `docs/SY_Hub_Phase2_Backlog.md`
(operator-owned — NOT touched here).
