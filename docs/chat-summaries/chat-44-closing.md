# Chat 44 — Build Pack 2.7-FE-docfix closing summary

**Pack:** Build Pack 2.7-FE-docfix — Supplier-document upload bugfix + dialog file-attach + desktop drag-drop (frontend only)
**Branch base:** main @ `0042_file_ref_text`, **132** permissions, 10 roles
**Head after this pack:** **`0042_file_ref_text`** (unchanged — backend frozen)
**Permissions:** **132** (unchanged)
**Roles:** 10 (unchanged)
**Backlog file (`docs/SY_Hub_Phase2_Backlog.md`):** NOT touched per the
opener (operator-owned).
**Auth flows touched:** none.
**Backend:** untouched — `git status --porcelain backend/` empty at
every gate-stop and at push time. Alembic head and permission
count re-asserted at every VERIFY block.

This pack stacked on top of Chat 43's B76 upload UI. It was split into
two scheduled gates as the Build Pack specified, plus a live-eyeball-
caught multipart bug between Gate 2 landing and the operator's first
real upload — fixed inside the same B78 envelope and verified end-to-
end on `origin/main` before closing docs.

---

## Gate run timeline

| Gate | Scope | Status |
|---|---|---|
| Gate 1 | §R1 over-strict client pre-check fix (extension-fallback) + 5 regression tests (#1–#5) | ✅ landed; VERIFY printed inline at the operator's STOP gate; operator verified on `origin/main` via raw-fetch before approving |
| Gate 2 | §R2 dialog file-attach + §R3 desktop drag-drop + §R5 hints (scope-creep, confirmed) + §R6 tests (#6–#14, plus #6b edit-path) | ✅ landed; VERIFY printed inline at the operator's STOP gate; operator verified on `origin/main` |
| Gate 2 follow-up | Multipart 422 live bug → per-request `Content-Type: undefined` override in `uploadDocumentFile` + new wire-level integration test closing the mocked-hook blind spot | ✅ landed; VERIFY printed inline at the operator's STOP gate; operator verified live upload + dialog attach + drag-drop end-to-end on `origin/main` before this close |

Build Pack §R8 gating honoured: no auto-advance between gates, no
push outside of `Save to GitHub`, no closing docs written until the
multipart fix landed on `main` AND the live upload was reproven
working.

---

## The Chat 44 arc — what actually happened

### Phase A — Gate 1 (over-strict pre-check)

The Chat-43 `preCheckFile` matched the picked File against
`ALLOWED_MIME_TYPES` only. Browsers in the wild — notably iOS Safari
for some PDF previews, and Windows Chromium/Edge for several Office
extensions — sometimes set `file.type` to `''` or to a generic
`application/octet-stream`. The result was a hard client-side reject
for files the backend would have accepted, with the toast
"Unsupported file type." giving the operator no path forward.

Fix: extension fallback. The file is accepted if **either** the MIME
matches **or** the lowercase last-token extension matches the
backend allowlist. Empty-file (`size === 0`) and `>25 MB` checks
unchanged. The server remains the source of truth — this client
pre-check is purely an early-fail UX nicety.

New module-level constant `ALLOWED_EXTENSIONS` + helper
`fileExtension(name)`. Five regression tests (#1–#5) added covering
the matrix.

### Phase B — Gate 2 (dialog attach + drag-drop + hints)

Layered onto the §R2.5 mobile baseline from Chat 43. **The mobile
`<input type="file">` baseline survives intact in every position**
— this is a hard constraint and is re-asserted by test #14.

- **Dialog attach (§R2).** New `document-form-attach` section in
  the Add/Edit dialog, below the archive checkbox. The staged File
  lives in a SEPARATE `useState` (`pendingFile`) — never in the
  create/patch JSON payload. Upload fires **after** create/patch
  settles: the new id from `create.mutateAsync` is forwarded into
  `upload.mutateAsync({id, file})`; for edit the existing `editing`
  id is reused. The success-toast / dialog-close path is gated on
  the full sequence (or, when the upload fails after the doc was
  saved, a "Document saved but upload failed" toast that leaves the
  doc in place — explicit per §R2.7).
- **Drag-drop (§R3).** New `DropZone` wrapper in two positions: the
  row Upload cell (`document-row-dropzone-{id}`) and the dialog
  attach (`document-form-dropzone`). `onDragOver` toggles a
  `data-dragover` attribute for the visual hover state; `onDrop`
  reads `e.dataTransfer?.files?.[0]` and routes through the SAME
  `preCheckFile` + `onPickFile` / `onStageDialogFile` paths the
  click flow uses. No duplicate validation, no duplicate toast
  mapping.
- **Hints (§R5, scope-creep confirmed).** `<input accept>` appends
  the `.ext` list to the MIME list (Windows + older Chromium
  pickers honour extensions more reliably). "or drag a file here"
  copy under the dialog attach AND the row Upload state.

§R6 tests (#6 – #14, plus #6b for the edit-path upload-after-patch
case) cover: create+upload happy path with id forwarding; edit+upload
happy path; no-file → create-only; payload purity on BOTH create and
patch (no `file`, no `file_ref` keys); pre-check on staged `.exe`;
dialog state reset on Cancel-then-reopen; row drop → upload; dialog
drop → stage; pre-check on drop; and the §R5 mobile-baseline
invariant in BOTH positions with the extension list in `accept`.

### Phase C — Gate 2 follow-up (the live multipart bug)

Gate 2 landed on `main`. Operator attempted the first live upload
from the row Upload control with a PDF. Server returned:

```json
{"type":"missing","loc":["body","file"],"msg":"Field required","input":null}
```

Diagnosis traced the File through the three layers cleanly —
`onPickFile(rowId, file)` → `useUploadDocumentFile.mutationFn({id,
file})` → `uploadDocumentFile(id, file)` — all of which were
forwarding the real `File` object intact. The bug was one step
deeper: the shared axios `api` instance in `frontend/src/lib/api.js`
declares `headers: { 'Content-Type': 'application/json' }` at
instance creation. axios 1.x's FormData auto-detection requires the
merged Content-Type to be absent so the browser can fill in
`multipart/form-data; boundary=…` at XHR `send()` time. The
instance-level JSON default short-circuited that detection — the
request shipped with `Content-Type: application/json` and an
unserialised FormData body, server-side multipart parser found no
`file` field → 422.

**Why the Chat-43 suite didn't catch it.** Both the component tests
and the hook tests `jest.mock('@/lib/api')` entirely. Nothing in the
suite exercised the real axios instance with its real defaults —
the bug lived strictly between the lib/api layer and axios's wire
serialiser, which all the existing tests bypassed.

**Fix.** One file, one option, scoped per-request:

```js
// frontend/src/lib/api/supplierDocuments.js
const { data } = await api.post(
  `/v1/supplier-documents/${id}/file`,
  fd,
  { headers: { 'Content-Type': undefined } },
);
```

axios 1.x interprets an undefined header value at the per-request
layer as "remove from merged headers", which unblocks the FormData
auto-detection. The shared `api` default stays `application/json`
for every other caller (zero blast radius). `lib/api.js` itself was
NOT touched. Use `undefined` — NOT the bare string
`'multipart/form-data'`, which would omit the boundary and 422
identically.

**Blind spot closed.** New file
`frontend/src/lib/api/__tests__/supplierDocuments.upload-multipart.test.js`
does NOT `jest.mock('@/lib/api')`. It imports the REAL `api`
instance, installs a request interceptor (post-merge / pre-
`transformRequest`) AND a custom adapter (post-transform), then
calls `uploadDocumentFile('D1', file)` and asserts:

1. The merged `Content-Type` at interceptor time is **undefined**
   (the per-request override stripped the JSON default during
   `mergeConfig`). If the bug were back, this would be
   `application/json`. ← **the smoking-gun assertion**
2. The merged `Content-Type` at adapter time is NOT
   `application/json` under any casing or header-bucket.
3. The FormData body carries the File on field `file`.
4. POST + `/v1/supplier-documents/D1/file` + `API_BASE` baseURL +
   `withCredentials: true` all intact.
5. `api.defaults.headers['Content-Type']` is STILL
   `application/json` after the call (no blast radius).
6. `axios.VERSION` major ≥ 1 (surfaces a future header-merge
   regression in the failure log).

A footnote on jsdom: at adapter time in jsdom, the captured
Content-Type is `application/x-www-form-urlencoded` because browser
FormData is not on axios's Node `form-data` code path. In a real
browser at runtime the XHR layer overwrites this with
`multipart/form-data; boundary=…` at `send()` time. The invariant
that matters — JSON did not win during merge — is what the
interceptor view pins, and it pins it correctly in both
environments.

Existing test `supplierDocuments.test.js`'s §R3.1 assertion that
had pinned the (now-buggy) `expect(opts).toBeUndefined()` shape was
updated to pin the new contract (`opts.headers['Content-Type']` is
undefined) and the misleading comment rewritten.

### Phase D — live confirmation

Save-to-GitHub of the multipart fix → operator repeated the exact
422-repro upload from the row Upload control with a PDF. **200,
`has_file=true`, filename + size returned, download round-trip
works.** Dialog attach + row drag-drop + dialog drag-drop re-tested
live in the same session. All paths green.

---

## Files changed (frontend only)

### Modified

- `frontend/src/components/suppliers/DocumentsTab.jsx`
  - **Gate 1:** `ALLOWED_EXTENSIONS` const, `fileExtension()` helper,
    rewrote `preCheckFile()` for extension fallback.
  - **Gate 2:** added `pendingFile` / `pendingFileError` state in the
    dialog form; `<DocumentForm>` rendered with a new
    `document-form-attach` section + `document-form-dropzone` /
    `document-form-file` testids; `onSubmit` flow now awaits
    `create.mutateAsync` / `patch.mutateAsync` and THEN
    `upload.mutateAsync({id, file})` when a file is staged; pending
    file resets on dialog open/close; `DocumentFileCell` and
    `FilePicker` wrapped in a new `DropZone`; `accept` attr in
    `FilePicker` appends the `.ext` list; copy hints under both
    Upload positions.
  - **No other touches** — the `file_ref` system-owned invariant
    from Chat 43's §R1 destructive cleanup is preserved (zero
    runtime references; 3 comments documenting the contract).
- `frontend/src/components/suppliers/__tests__/DocumentsTab.test.jsx`
  - **Gate 1:** added §R1 tests #1–#5 + `fileExtension` helper edge
    cases.
  - **Gate 2:** added §R6 tests #6, #6b, #7, #8, #9, #10, #11, #12,
    #13, #14. Net `DocumentsTab.test.jsx` count: 36 → 46.
- `frontend/src/lib/api/supplierDocuments.js` *(Gate-2 follow-up
  only)*
  - `uploadDocumentFile(id, file)` now passes `{ headers: { 'Content-
    Type': undefined } }` as the third argument to `api.post`.
    Inline rationale block included; nothing else touched.
    `downloadDocumentFile`, `parseContentDispositionFilename`, and
    every other export unchanged.
- `frontend/src/lib/api/__tests__/supplierDocuments.test.js` *(Gate-2
  follow-up only)*
  - Existing §R3.1 assertion updated from `expect(opts).toBeUndefined
    ()` to `expect(opts.headers['Content-Type']).toBeUndefined()`.
    Comment block rewritten to describe why the JSON default would
    otherwise poison the FormData request. No other tests in this
    file changed.

### Added

- `frontend/src/lib/api/__tests__/supplierDocuments.upload-
  multipart.test.js` *(Gate-2 follow-up — 5 tests)*. Wire-level
  integration test against the REAL `api` instance via request
  interceptor + custom adapter (no new packages, no real network).
  Placed alongside the existing API-layer tests per the operator's
  "match the existing house location, don't consolidate" guidance.

### NOT touched

- `frontend/src/lib/api.js` — the shared axios instance default
  stays `headers: { "Content-Type": "application/json" }`. The
  whole point of the per-request override pattern is to keep this
  default intact for every other caller. Re-pinned by the
  regression-guard test in the new test file.
- `frontend/src/hooks/supplierDocuments.js` — no change. The hook
  was already forwarding `{ id, file }` correctly.
- Anything under `/app/backend/` — see VERIFY below.

---

## VERIFY artefacts (canonical, second-run where applicable)

### Jest

| Run | Suites | Tests | Notes |
|---|---|---|---|
| Pre-pack baseline | 79 | 618 | inherited from Chat 43 close |
| Gate 1 full Jest | 80 | 624 | +1 suite (Gate-1 §R1 cases consolidated under `DocumentsTab.test.jsx`), +6 tests (5 §R1 cases + helper) |
| Gate 2 full Jest | 80 | 634 | +10 tests; `DocumentsTab.test.jsx` 30 → 46 |
| Gate 2 targeted Jest | 1 | 46 | `--testPathPattern="DocumentsTab"`, ~2 s; §R6 #6–#14 names all visible in run list |
| **Gate 2 follow-up full Jest (close)** | **81** | **639** | +1 suite (`supplierDocuments.upload-multipart.test.js`), +5 tests; double-run identical |

The Gate-2 follow-up suite output named the new tests verbatim:
```
PASS src/lib/api/__tests__/supplierDocuments.upload-multipart.test.js
  ✓ instance default Content-Type is still application/json (NOT changed by this fix)
  ✓ POSTs to /v1/supplier-documents/{id}/file with FormData body and overrides
    Content-Type to undefined per request — the JSON default does NOT survive merge
  ✓ cookies still ride along — instance is withCredentials:true
    (proves we did not nuke the shared instance config)
  ✓ the shared `api` default Content-Type remains application/json AFTER this upload
    (no blast radius on other callers)
  ✓ axios version sanity (1.x — the FormData auto-detection path this fix relies on)
```

### Greps (Gate 2 follow-up, canonical)

- **`file_ref` in `DocumentsTab.jsx` → 3 hits**, all `//` / `/*`
  comments documenting the system-owned invariant pinned by Gate 2
  test #8. **Zero runtime references.** Per the operator's allowance
  ("same as the SharePoint comments-only allowance in §R8"), the
  comments stay — they document why the test invariant exists.
- **`'type="file"'` in `DocumentsTab.jsx` →** the single shared
  `<FilePicker>` `<input>` survives in both the row Upload state
  and the dialog attach area. Re-pinned by §R6 test #14.
- **`sharepoint | graph.microsoft | https?://` in `DocumentsTab.jsx`
  →** comments-only; runtime DOM emptiness re-pinned by §R5 #13
  from Chat 43.
- **`lib/api.js` shared instance default →** still
  `headers: { "Content-Type": "application/json" }`. Re-pinned by
  the regression-guard test `instance default Content-Type is still
  application/json (NOT changed by this fix)`.

### Backend frozen (re-asserted at every gate-stop and at this close)

- `git status --porcelain backend/` → empty.
- `alembic` head → `0042_file_ref_text` (unchanged).
- Permissions count → **132** (AST-parsed from
  `backend/app/seed_rbac.py:PERMISSION_CATALOGUE` accumulator;
  Chat 43 invariant unbroken).
- Roles → 10 (unchanged).

---

## What changed in operator-side mental model

1. **The mobile baseline survives layered enhancements.** Drag-drop is
   a desktop-only layer on top of the tap-to-pick `<input type="file">`
   — never a replacement. Test #14 is the load-bearing pin.
2. **Payload purity is a hard contract.** Neither the create body nor
   the patch body may carry `file` or `file_ref`. Upload always
   happens as a separate multipart POST, gated on the save completing
   first. Test #8 + the `file_ref` zero-runtime grep enforce this.
3. **The shared axios `api` has a JSON default — multipart callers
   MUST opt out per-request.** Any future endpoint that uploads
   `FormData` through `api` must pass `{ headers: { 'Content-Type':
   undefined } }`. The new wire-level test is the recipe to copy.
4. **API-layer + hook-layer tests are not sufficient for wire-level
   axios behaviour.** Any future API helper that depends on the
   shared `api`'s merged headers / transformers / interceptors needs
   a sibling wire-level integration test that does NOT mock
   `@/lib/api`. The new file is the template.

---

## Backlog hand-off

**B78 — Supplier-document upload bugfix + dialog attach +
drag-drop** delivered. Operator hand-marks
`docs/SY_Hub_Phase2_Backlog.md` (operator-owned — NOT touched here).

No new backlog items emitted by this pack.

---

## Push readiness checklist (at this close)

- [x] Both gate VERIFY blocks printed inline before push.
- [x] Multipart Gate-2 follow-up VERIFY printed inline before push.
- [x] Live 422-repro reproven 200-OK on `origin/main` after the
      Save-to-GitHub of the multipart fix.
- [x] Backend frozen — `git status --porcelain backend/` empty;
      alembic head `0042_file_ref_text`; perms **132**; roles 10.
- [x] Operator-owned `docs/SY_Hub_Phase2_Backlog.md` untouched.
- [x] No auth flows touched.
- [x] No new third-party integrations.
- [x] No new env keys.
- [x] Double-run full Jest green (`81 / 639`).

Committed ≠ pushed. Holds at every gate were operator-driven; the
final push of these closing docs is via `Save to GitHub`.
