# SY-Hub Platform — PRD

## Original problem statement

Execute strict prompts (Build Packs) to extend the SY-Hub backend per the
SY Homes Phase 1 / Phase 2 brief. Each prompt has 15 locked decisions, an
exact migration count, an exact endpoint count, and a target test delta.
Frontend / actuals / commitments / Xero are out of scope until later prompts.

## Stack
- FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16
- Pytest with cookies-only auth contract (no Bearer headers)
- Pattern α tenant scoping: project-id resolution + `_visible_project_ids`
  filter, mirroring `routers/appraisals.py`. **No** `tenant_id` columns on
  Track-2+ tables (exception: `purchase_orders.tenant_id` is denormalised
  for list-time tenant filtering — see Chat 24 R2).
- Audit append-only via `audit_log` + `audit_log_no_modify()` trigger.

## Build Pack B88 Pack 1 — Cost-Code Group Hierarchy + Cost-Code Admin

**STATUS: COMPLETE.** All 5 gates raw-fetch verified on `origin/main`,
live eyeball passed (tree renders, super_admin sees delete, director
correctly does NOT, in-use delete shows inline block-reasons + Retire
instead). Closing docs landed in `CHANGELOG.md` (Chat-50 entry) and
`docs/chat-summaries/chat-50-closing.md`. Next pack: **B88 Pack 2 —
Job-Costing grid + two budget screens**.

### Gate 5 follow-up (2026-02-XX) — `?status=All` 500 fix

Caught during live eyeball: `GET /api/cost-codes?status=All` passed
`'All'` straight into `WHERE status = :s` against the
`cost_code_status` enum `{Active, Retired}` → Postgres
`InvalidTextRepresentation` → bare 500. Fix in
`routers/cost_codes.py::list_cost_codes`:

```python
if status:
    if status.lower() == "all":
        pass
    elif status in ("Active", "Retired"):
        query = query.where(CostCode.status == status)
    else:
        raise HTTPException(422, f"invalid status filter: {status!r}")
```

Regression suite `tests/test_cost_codes_status_filter.py` — 7 tests
covering case-insensitive `All` / `all`, exact `Active` / `Retired`,
6 bogus values → 422 (not 500), omitted-param parity, composition
with `section_id`.

Full warm-DB pytest suite (2nd run): **1449 passed · 3 xpassed · 0
failed**.

### Gate 5 (2026-02-XX) — Cost-Code Admin frontend screen

New page `frontend/src/pages/CostCodeAdmin.jsx` at route
`/cost-codes/admin`. Tree view (parent → subgroup → code), full
permission-gated CRUD, inline 409 block-reasons, retire / reactivate
affordances. Brand colours locked: teal `#0F6A7A` primary, orange
`#FC7827` accent, grey `#CECECE` neutral.

Permission gating reads off the **live** `me.permissions` set via
`useAuth().hasPerm(code)` (`AuthContext.jsx:168`). Wiring:
* `+ New group`, `+ Code`, pencil, archive (retire), ↺ (reactivate)
  → `cost_codes.create` / `cost_codes.edit` — visible to
  super_admin · director · finance.
* Trash (delete) → `cost_codes.delete` — visible to
  **super_admin only**. Director sees a faded `ShieldOff` icon with
  tooltip "Delete requires super_admin (cost_codes.delete)". Backend
  defence-in-depth at `routers/cost_codes.py:767`.

409 contract consumed: `{detail: {message, blockers: []}}`. Frontend
renders blockers inline within the delete modal (NOT a raw toast),
with an orange accent border and a "Retire instead" affordance that
opens the retire modal pre-targeted at the same code. Toast fallback
only fires for non-409 errors.

Tree depth fixed at 2 by design (Build Pack §2.2 rule 3 — no
three-tier nesting). First build attempt used a recursive
`<SectionNode>` and crashed CRA's babel-loader chain with
"Maximum call stack size exceeded"; refactored to two non-recursive
components (`<ParentSectionNode>` + `<SubgroupNode>`), builds clean.

Legacy pages kept alive intentionally: `CostCodesList.jsx` gets a
new teal "Open Cost-Code Admin →" link in its header (subhead also
updated 129 → 130 codes). `ProjectCostCodes.jsx` is a separate
per-project enrolment surface; not in Gate-5 scope.

Backend regression unchanged: 1442 passed / 0 failed (Gate 4
double-green still holds — Gate 5 is frontend-only).

Operator will **live-eyeball** as both super_admin and director to
confirm the delete-gate differs and the 409 panel renders inline.

**Stop at Gate 5 — do not advance to final acceptance until operator
clicks through both roles live and confirms.**

### Gate 4 — RE-SUBMISSION against corrected canonical master (2026-02-XX)

The initial Gate 4 submission was REJECTED — built against a stale
129-code list with 5 ACC "extras" preserved and an invented SAL-10
"Reservation Fees". Operator provided the authoritative master
`BTCostCodes_20260609 (1) (3).xlsx`, which locks in **130 codes**
under 9 parent groups + 10 Construction subgroups. The seed and
tests have been rebuilt against that master from scratch.

Key corrections vs the rejected submission:
* Total = **130 canonical** (no extras). The "§5.3 preserve extras"
  rule is gone for the canonical prefix-set.
* SAL-10 canonical name = **"Other sales & disposal costs"** (was
  invented as "Reservation Fees" — discarded).
* SAL-09 renamed in-place to **"Post-completion holding &
  maintenance"** (its slot was taken by what is now SAL-10).
* **OHD-09 newly seeded** — "HR, recruitment & employee welfare"
  (previous DB had OHD=8; canonical OHD=9).
* **ACC-04..08 hard-deleted** — all 5 rows had zero FK references
  so the seed's `_try_hard_delete_code` succeeded; 0 codes were
  retired in this submission.
* Parent group names updated: 1 = "Land & Acquisition",
  3 = "Professional Fees", 5 = "Sales & Marketing",
  8 = "Accounting", and 38 cost-code names re-set to the master
  strings.
* **SER-10 un-retired** — legacy migration
  `0016_audit_remediation_patch_3` had retired SER-10 in favour of
  SER-06; the corrected master has BOTH active. The seed now clears
  `replaced_by_code_id` / `retired_at` / `retired_reason` on any
  canonical row that still carries them. `TestPatch3SER10Retired`
  inverted to assert the post-Gate-4 truth.

Reconciliation semantics implemented (operator instruction):
* Hard-delete non-canonical rows when no FK reference exists.
* Retire (status='Retired') if a RESTRICT FK blocks deletion.
* Names always set to the canonical master value — no preservation
  of legacy strings.
* Idempotent: run-2 = 0 changes; row counts identical.

Two warm-DB full pytest runs: **1442 passed, 3 xpassed, 0 failed**
both runs (~4 min 17 s avg). Net +5 vs rejected submission (+7 new
structure tests, -2 dropped from the rejected model).

Full report at `/app/test_reports/B88_pack1_gate4_resubmission_report.md`.

**STOPPED at Gate 4** awaiting operator raw-fetch verification
on `origin/main`.

### Gate 4 (REJECTED — superseded by corrected canonical master)

`backend/scripts/seed_cost_code_structure.py` (idempotent) reconciles
the live DB against Build Pack §5.1–§5.3:

* 9 parent groups recoded slug → numeric (`acquisition→1`, ..., `contingency→9`).
* 10 Construction subgroups created (`4.00`–`4.09`), the duplicate-4.08
  spreadsheet collision resolved per operator: 4.06=Prefab/MMC,
  4.07=Existing Buildings, 4.08=External Works.
* 129 canonical cost codes re-pointed onto the right (sub)group; SAL-10
  newly seeded ("Reservation Fees"); ACC-04..08 retained as extras per
  §5.3 (5 rows kept, not deleted, awaiting operator instruction).

`backend/tests/test_cost_code_seed_structure.py` — 15 tests, all green.
Covers parent count, allows_subgroups invariants, subgroup naming +
parentage, the operator-resolved 4.06/4.07/4.08 renumbering, no-collision
proof, canonical 129 total, per-prefix counts, every-code-canonical
pointer, no-Construction-orphan check, SAL-10 presence, ACC extras
preservation, run-twice idempotency, and reconciliation (move a code
off its canonical subgroup → seed moves it back).

Gate-3 carry-overs landed in this gate: `TestSeed::test_nine_sections`
un-xfailed and recoded for numeric parent codes; `test_133_total_cost_codes`
→ canonical 129; `test_per_prefix_counts` SAL=10/ACC=3; `test_filter_by_section`
rewritten to query Construction's 10 subgroups since codes no longer
hang directly off the Construction parent; bulk-toggle + audit tests
updated for numeric `section_code`; cosmetic rename
`test_total_permissions_is_129` → `test_total_permissions_in_db`.

Migration-round-trip safety: `test_migration_0025_actuals.py`'s
downgrade-then-upgrade walks past `0044_cost_code_groups`, dropping
+ re-creating `parent_section_id` + `allows_subgroups` and erasing
the canonical structure. The test now finalises with a re-call of
`scripts.seed_cost_code_structure.run()` so downstream test modules
see a healed structure. The seed itself was hardened with a
`by_code → by_legacy_slug → by_display_order` matcher and a
re-parent path for orphaned subgroups so the re-call converges
cleanly from the post-round-trip state.

Two legacy frontend pages (`CostCodesList.jsx`, `ProjectCostCodes.jsx`)
were patched in this gate (not Gate 5) to keep them alive across the
slug → numeric rename: `SECTION_HEADER_ORDER` recoded to `["1".."9"]`;
`showSubgroups` check switched to `code === "4"`; the `grouped`
look-up now walks `parent_section_id` up to its tier-1 parent so
Construction codes roll up under "4" for display. Gate 5 will
replace these screens with a proper Cost-Code Admin screen.

Full pytest suite (warm DB), twice: **1437 passed, 3 xpassed,
0 failed** both runs (~4 min 23 s avg). Delta from Gate 3 baseline:
+16 net (1437 vs 1421 — +15 new structure tests + 1 un-xfailed test).

**Stop at Gate 4 — do not advance to Gate 5 (frontend admin
screen) until operator clears Gate 4 on origin/main.**

### Gate 3 (2026-02-XX) — partial-acceptance follow-ups

Three required changes against the previously-submitted Gate 3 code
were completed before re-asking for verification on main:

1. **Un-skipped two delete-guard tests** that previously called
   `pytest.skip` when the R7 spotcheck budget seed was absent on the
   pod. The `spotcheck_budget_row` fixture in
   `tests/test_cost_code_delete_guard.py` now self-seeds a probe
   Approved appraisal + Active budget (idempotent, with module
   teardown that deletes the probe rows so other test modules can
   still wipe appraisals/budgets without FK collisions). G2
   (`test_delete_blocked_by_budget_line`) and G3
   (`test_delete_blocked_by_appraisal_cost_line`) now run
   unconditionally and exercise the real 409 block path. 15/15
   delete-guard tests green.

2. **Fixed 25 stale baseline tests** — alembic head bumps
   `0043_document_folders → 0044_cost_code_groups`, permission counts
   `super_admin 133 → 136` and `director 129 → 131` (delete excluded
   per operator decision), catalogue size `133 → 136`, retired
   tests inverted (`test_no_delete_endpoint_exists_for_cost_codes`
   → `test_delete_endpoint_wired_for_cost_codes`, patch-3 orphan
   list trimmed to keep the 3 still-orphan codes), function rename
   `test_permission_catalogue_count_in_python_is_129` →
   `test_total_permissions_matches_catalogue`. One xfail added on
   `TestSeed::test_nine_sections` with a TODO pointing at Gate 4.

3. **Full pytest suite ran twice on warm DB**, both runs returning
   **1421 passed, 3 xfailed, 1 xpassed, 0 failed** (~4 min 43 s).

Gate 3 is now ready for raw-fetch verification on main. **Stop** at
Gate 3 — do not advance to Gate 4 (`seed_cost_code_structure`) until
operator clears Gate 3 on origin/main.


## What's been implemented

### Chat 47 — Build Pack 2.8-FE-i · Subcontracts surface (Frontend, scope-fenced)

Frontend-only pack. First of the subcontract / commercial screens.
Lights up the supplier **Contracts** tab with an inline master-detail
list + selected-detail, create/edit form, and Activate / Complete /
Terminate lifecycle. Scope is fenced to **subcontracts only** —
valuations / payment notices / retention / variations are explicitly
NOT in this pack (later 2.8-FE-ii / 2.8-FE-iii). No placeholders for
any of them.

**Files (new):**
- API: `frontend/src/lib/api/subcontracts.js` (7 fns) + `hooks/subcontracts.js` (7 hooks).
- Capability: `frontend/src/lib/poCapability.js` — 7 helpers + `nextActionsForSubcontractStatus` + `SUBCONTRACT_TERMINAL_STATUSES`.
- Components: `SubcontractStatusPill`, `SubcontractActionButtons`, `SubcontractFormDialog`, `SubcontractDetail`, `SubcontractsTab` (all under `components/suppliers/`).
- Mount: `pages/SupplierDetail.jsx` — placeholder removed, `<SubcontractsTab supplierId={s.id} />` mounted under the existing `isContractor` gate.

**Tests:**
- `lib/api/__tests__/subcontracts.test.js` — 20 wire-level tests.
- `components/suppliers/__tests__/SubcontractsTab.test.jsx` — 23 integration tests.
- `pages/__tests__/SupplierDetail.test.jsx` — placeholder test replaced by mounted-tab test.

**Full FE suite 2nd-run: 85 suites / 710 tests.** Delta vs the 83/667 baseline: **+2 suites / +43 tests**.

**Surfaced deviations (operator-confirmed before Gate 1):**
1. **FLAG 1b — `complete` perm.** Build Pack §R0.3 says `subcontracts.approve`; backend router uses `subcontracts.edit`. The §R2.0 single helper was split; `canCompleteSubcontract = edit OR approve` (matches backend). Test pin: editor-only persona sees Complete on Active. Backlog: correct §R0.3 docs.
2. **FLAG 2a — `signed_at` on Edit only.** Backend `activate_subcontract` 409s if `signed_at IS NULL`. Signature block (`signed_at` + signed-by-me toggle) lives on Edit only; Create doesn't have it. Activate 409 against unsigned is rewritten to "A signed date is required before this subcontract can be activated. Edit the subcontract to set it." Test pin: friendly-message regex assertion on `toast.error`.

**§R9 backlog (not built):**
- Backend: add `subcontractor_id` query param to `GET /v1/subcontracts` (currently client-side filter; fine at present scale).
- Backend Build Pack docs §R0.3: correct `complete` row to `subcontracts.edit`.
- Future packs: Valuations (2.8-FE-ii), Variations (2.8-FE-iii), Payment notices, Retention movements, Subcontract documents.

Full closing summary in `/app/docs/chat-summaries/chat-47-closing.md`.


### Chat 46 (continued) — Build Pack 2.7-DOCS-FE-fix · B81 — FolderNode build-crash fix + demo seed (2026-02)

Targeted fix-pack. Closes the live dev/preview crash introduced by
Chat 46's recursive `<FolderNode/>` component:
`RangeError: Maximum call stack size exceeded` inside
`babel-traverse` whenever the Documents tab loaded. Root cause: the
upstream `@emergentbase/visual-edits` babel plugin chokes on the
(correct) recursive JSX. The earlier patch covered Jest only; this
pack fixes the actual dev preview path.

**Strategy — Option A (surgical):** investigation of
`node_modules/@emergentbase/visual-edits/dist/` showed the plugin has
no per-file exclude option but its babel plugin is standard
`{ name, visitor }` shape, so a babel-plugin-level shim wrapping each
visitor + short-circuiting on `state.filename === FolderNode.jsx` is
the right surgical fix. Visual-edits stays active for the rest of
the app; only `FolderNode.jsx` is excluded. `FolderPicker.jsx` and
`DocumentFolderView.jsx` are not self-recursive and keep full
coverage.

**Did NOT change:** `FolderNode.jsx`, `DocumentFolderView.jsx`,
`FolderPicker.jsx`, `backend/**/*`, `docs/SY_Hub_Phase2_Backlog.md`,
any test file. The `NODE_ENV=test` exclusion already in
`craco.config.js` from Chat 46 stays in place
(defence-in-depth alongside visual-edits's own
`NODE_ENV=production` short-circuit).

**Gate 1 — dev-server proof (not jest):** truncated logs, cleared
`node_modules/.cache`, restarted frontend → `Compiled with warnings.`
+ `webpack compiled with 1 warning` (lint-only, pre-existing
exhaustive-deps notices, identical before+after); **zero "Maximum
call stack" errors**; `HTTP 200` on `:3000/`. Shim's visitor-skip
path was instrumented during investigation and confirmed firing on
every `FolderNode.jsx` compile before debug logs were removed for
landing.

**Gate 2 — production + test paths:** `NODE_ENV=production yarn build`
→ `Compiled with warnings.` + EXIT 0; `suppliers-po.cdd57866.chunk.js`
(the chunk containing `FolderNode`) emitted at 32.91 kB.
Visual-edits's own `NODE_ENV==='production'` short-circuit means
the shim isn't even instantiated in prod. `craco test` 2nd-run
warm: **83 / 83 suites, 667 / 667 tests passing, 0 failures, 1
snapshot** — exact match with the Chat-46 baseline (no tests added).

**Gate 3 — demo seed:**
`python scripts/seed_doc_folders_demo.py` ran twice in a row →
identical `2 suppliers, 6 folders, 4 documents`. Idempotent.
`[DEMO]`-marker scoped — never touches non-demo data. Lint clean.

Demo dataset (operator-eyeball fodder, all in default tenant):
- `[DEMO] Northgate Builders Ltd` →
  `Compliance/` (PL + EL docs), `Insurance/2024/`, `Insurance/2025/`
  (PI doc), `Contracts/` (empty — for the archive-empty UX test).
- `[DEMO] Severn Plant Hire` → single `Compliance/` (1 doc) —
  mirrors the migrated-supplier shape.

**Webpack-cache caveat (one-off after the GitHub save lands):** if
the preview still crashes after pull, run
`rm -rf frontend/node_modules/.cache && sudo supervisorctl restart frontend`
ONCE to evict the stale errored-compilation cache. Documented in
the closing summary.

**Files landed:** 1 modified (`frontend/craco.config.js`), 1 new
(`scripts/seed_doc_folders_demo.py`), 3 closing
(`CHANGELOG.md`, `docs/chat-summaries/chat-46-closing.md` addendum,
this entry).

**Backlog:** B81 CLOSED. Upstream `@emergentbase/visual-edits`
recursion bug flagged for revisit if/when the plugin updates and
the exclusion can be removed. B72 demo-dataset (carried) — this
script is a precursor scoped to document folders only.

**Operator-only verification step:** click into a `[DEMO]` supplier
in the Suppliers list, open Documents tab; confirm the two-pane
folder browser renders, the tree shows `Compliance / Insurance
(2024, 2025) / Contracts`, file counts match (2 / 0+1 / 0), and
clicking around the docs works. Then drag a doc → folder, "Move
to…" → Unfiled, archive an empty folder vs a non-empty one.

---

### Chat 46 — Build Pack 2.7-DOCS-FE · Document Folder Tree UI (Frontend, B79 Part 2 of 2) (2026-02)

Frontend-only delivery on top of Chat 45's B79-BE folder engine.
Replaces the flat `<DocumentsTab/>` with a **two-pane folder
browser** (tree left, files right). Folders nest unlimited depth;
docs move by drag-and-drop AND by a "Move to…" button (button =
canonical testable path, drag = polish). All upload / replace /
download primitives reused verbatim from a new shared module.
**Closes backlog B79** (-BE + -FE).

**Backend FROZEN throughout** — zero `backend/` touches, alembic
head stays `0043_document_folders`, permissions stay 133, roles
stay 10.

**Operator-pinned decisions honoured:** F1 desktop-first two-pane
(mobile is a separate future build; the narrow-viewport fallback is
a graceful placeholder, not a real mobile UX); F2 drag primary +
button canonical; F3 reuse file primitives; F4 `doc_type` + `title`
optional with auto-fill-from-filename placeholder.

**Gate 1 — shared module extraction:** new
`components/suppliers/documentFileShared.jsx` carries the §R0.3
allowlist + `ACCEPT_ATTR` + `fileExtension` + `formatFileSize` +
`preCheckFile` (four-step) + `uploadErrorMessage` +
`downloadErrorMessage` + `<FilePicker/>` + `<DropZone/>` +
`<DocumentFileCell/>`. The retiring `DocumentsTab.jsx` re-imports
them and its existing **46-test suite stayed green unchanged** —
refactor-safety proven. New `documentFileShared.test.jsx` ports the
relevant coverage: **37 tests** (precheck, allowlists, fileExtension,
formatFileSize, error mappers, FilePicker uploading-state +
key-reset, DropZone drag handlers, DocumentFileCell branches incl.
the no-URL-leak guard).

**Gate 2 — API + hooks:** new `lib/api/documentFolders.js`
(`listFolderTree`, `getFolder`, `createFolder`, `renameFolder`,
`moveFolder` null→root, `archiveFolder`, `unarchiveFolder`). New
`hooks/documentFolders.js` (`folderKeys`, `useFolderTree`, plus the
five mutations with cross-resource invalidation: archive/unarchive
of a folder invalidates BOTH the tree AND the docs list).
`lib/api/supplierDocuments.js` gains `moveDocument(id, folderId)`;
`hooks/supplierDocuments.js` gains `useMoveDocument` (invalidates
docs + the broad folder tree). `lib/poCapability.js` gains
`canCreateFolder` (`documents.create`), `canEditFolder`
(`documents.edit`), `canMoveDocs` (`documents.move`). New
`lib/api/__tests__/documentFolders.test.js` — **16 wire-level tests**
asserting exact URL + body / params (Chat 44 lesson — mocked-hook
tests never cross the wire).

**Gate 3 — folder view:** new `components/suppliers/DocumentFolderView.jsx`
(top-level state + dialogs + 4 layout helpers + 3 sub-tables) +
`FolderNode.jsx` (recursive tree with the action menu + drop
target) + `FolderPicker.jsx` (flat indented radio list with
`excludeId` for folder-move). **No useEffect**: default-root-expanded
is a pure `useMemo` overlay of `overrides ∪ every-root-open` so the
lint rule `react-hooks/set-state-in-effect` stays clean and no
re-entrant render path appears when the tree refetches. Direct
contents only (right pane filter matches backend `file_count` —
non-recursive). Error mapping centralised in a `mapMoveError`
helper. New `DocumentFolderView.test.jsx` — **21 tests** covering
R6 #1-#21 verbatim: tree render/expand/select/All/archived, folder
CRUD (create from header, create-sub from node, rename, archive +
422 message, move + 422 message, perm-gating), files (DocumentFileCell
reuse, prefill folder_id on Add, optional fields submit cleanly,
"Move to…" → folder / null / hidden without `documents.move`),
drag (dragStart sets payload, drop invokes the mutation), desktop
notice, refactor-safety tracer.

**Gate 4 — mount + retire:** `pages/SupplierDetail.jsx` swapped to
`<DocumentFolderView/>` at the `<TabsContent value="documents">`
block. `SupplierDetail.test.jsx` mock retargeted from
`DocumentsTab` to `DocumentFolderView`. **Deleted**
`components/suppliers/DocumentsTab.jsx` +
`components/suppliers/__tests__/DocumentsTab.test.jsx`. Grep confirms
zero remaining `DocumentsTab` runtime imports.

**Final 2nd-run FE suite:** **83 suites passed, 667 tests passed,
0 failures, 0 errors.** Baseline (Chat 44 close): 81 / 639. Net:
**+2 suites (+3 new − 1 deleted), +28 tests** (+74 ported/new
across 3 new files − 46 from the deleted DocumentsTab suite).
Direction up, accounting balances.

**Deviations flagged for review (none silent):**
- `craco.config.js` `isDevServer` excludes `NODE_ENV=test` —
  `@emergentbase/visual-edits/craco` (dev-only) was loading under
  Jest and crashing babel-traverse on recursive `<FolderNode/>` with
  a stack overflow. One-line guard. `start`/`develop` untouched.
- The view split into 3 files (`DocumentFolderView` + `FolderNode`
  + `FolderPicker`) instead of one. Build Pack §R4.1 describes one
  component; the split is a structural refinement (small files,
  dodges the babel-stack issue, follows the house
  "keep components small" guideline). Semantics unchanged.

**Live eyeball test items (operator must run before declaring
done):** create folder; create subfolder via per-node "+"; drag a
doc to a folder; "Move to…" → Unfiled; upload a file via row
control + via dialog attach; rename folder; archive non-empty
folder to see the 422 message surface; move folder into itself/
descendant to see the loop-guard 422; confirm narrow notice at
<768px.

**Backlog surfaced (operator hand-adds; this agent did NOT touch
`docs/SY_Hub_Phase2_Backlog.md`):** B79 CLOSED; mobile-optimised
document/folder UX; Role & Permissions Admin screen (carried);
external-party folder access (portal 2.9, carried); folder UI
enhancements (multi-select bulk move, folder zip download,
drag-folder-onto-folder); physical storage path reorg; cascade
archive; owner-type expansion (project, subcontract).

**Files landed:** see `CHANGELOG.md` §Chat-46. 9 new, 6 modified,
2 deleted — all confined to `frontend/`.

---

### Chat 45 — Build Pack 2.7-DOCS-BE · Document Folder Engine (Backend, B79 Part 1 of 2) (2026-02)

Backend-only. Polymorphic logical folder tree (`document_folders`)
attachable to any owner record via `(owner_type, owner_id)` (D3) —
suppliers first; projects + subcontracts inherit later for free by
widening `FOLDER_OWNER_TYPES` + `OWNER_VIEW_PERM` + the
`ck_document_folders_owner_type` CHECK. No frontend touched; existing
`DocumentsTab.jsx` keeps working unchanged because the
`supplier_documents` endpoints stay behaviourally identical.

**Alembic head:** `0042_file_ref_text → 0043_document_folders`.
**Permissions:** `132 → 133` (+1: `documents.move`). **Roles:** 10.

**Gate 1 — model + migration:**
- New model `app/models/document_folders.py` (`DocumentFolder` +
  `FOLDER_OWNER_TYPES = ("supplier",)`). UUID PK with
  `gen_random_uuid()` server default, tenant FK ON DELETE RESTRICT,
  polymorphic `(owner_type, owner_id)` with no FK on `owner_id`
  (cannot FK to multiple tables), self-referential `parent_id` ON
  DELETE RESTRICT, audit timestamp/user columns, soft-delete via
  `is_archived`.
- `app/models/supplier_documents.py` reshaped: `doc_type` + `title`
  → `Optional[str]`; new `folder_id` FK ON DELETE SET NULL so
  deleting a folder UN-files docs rather than cascade-deleting.
- `alembic/versions/0043_document_folders.py` — single revision
  chaining from `0042_file_ref_text` does all of: (1) creates
  `document_folders` table + 4 indexes + CHECK + partial unique
  sibling-name index using
  `COALESCE(parent_id, '00000000-...-000000000000'::uuid)` so root
  NULL-parent siblings de-duplicate; (2) drops
  `ck_supplier_documents_doc_type`, alters `doc_type`/`title` to
  nullable, adds `folder_id` FK; (3) idempotent DATA STEP — one
  `Compliance` root folder per supplier with documents + UPDATEs
  all that supplier's docs (archived included) to point at it,
  guarded by a "skip if Compliance folder already exists" sub-SELECT.
  Enum widen `permission_action += 'move'` uses the exact
  `autocommit_block` idiom from `0020_permission_action_submit.py`.
  Down/up round-trip clean (best-effort downgrade; FAILS only if
  NULL doc_type/title rows were created post-upgrade — documented
  in the migration docstring).

**Gate 2 — RBAC:**
- `app/models/rbac.py` — `ACTIONS += "move"`.
- `app/seed_rbac.py` — `documents` resource `_perms_for` extended to
  `include=["view","create","edit","delete","move"]`. New
  permission code **`documents.move`** (non-sensitive).
- Role grants for `.move` (§R4.3 union rule: roles holding
  `documents.edit` OR `supplier_documents.edit`):
  - `super_admin` (wildcard), `director` (wildcard minus
    exclusions), `project_manager` (already holds both edit perms),
  - **`finance`** — holds `supplier_documents.edit`, gains `.move`
    (the **§R4.3 distribution-gotcha fix**: had `.move` followed
    `documents.edit` alone, finance would have lost the ability to
    file the very docs it edits every day).
- **§R4.3b (operator broadening):** finance also gains
  `documents.create` + `documents.edit` (catalogue codes already
  existed; only role-grant rows are new) so finance can create,
  rename, and archive folders.
- Permission catalogue: **132 → 133**; bootstrap
  `verify.perms result=ok expected=133 actual=133`.

**Gate 3 — service + router:**
- `app/services/document_folders.py` (new) — mirrors
  `services/supplier_documents.py` 1:1 (`ValueError` → 422,
  `LookupError` → 404, `record_audit` AFTER `db.flush()`,
  tenant-scoped queries). Functions: `create_folder`,
  `list_folder_tree`, `get_folder`, `get_folder_detail`,
  `rename_folder`, `move_folder` (loop guard implemented as
  ancestor walk on the new parent — cheaper than descendant walk),
  `set_folder_archived` (blocks archive of non-empty folders;
  blocks unarchive when parent archived), `serialise_folder`. Small
  extensible `OWNER_VIEW_PERM` map (`"supplier" →
  "supplier_documents.view"`) so the router resolves the right
  view perm per the §R3.0 owner-surface read rule. Sibling-name
  uniqueness enforced by the partial unique index; `IntegrityError`
  is caught inside a `begin_nested()` savepoint and re-raised as
  `ValueError`. Audit verbs reused — `Create`, `Update` (with
  `metadata.moved_from`/`moved_to` for moves), `Archive`, `Restore`
  (all already in `AUDIT_ACTIONS`).
- `app/services/supplier_documents.py` — `_validate_doc_type` is
  now optional; `create_document` accepts optional doc_type +
  optional title + optional folder_id; new
  `move_document_to_folder`; `serialise` exposes `folder_id`;
  `_AUDIT_COLS` includes `folder_id`.
- `app/routers/document_folders.py` (new) — mounted under
  `/api/v1/document-folders` via `backend/server.py` (NOT
  `backend/app/server.py`). Endpoints + gates per §R0.4 + §R3.0:
  POST create → `documents.create`; GET tree + GET detail →
  `_owner_view_perm(owner_type) = supplier_documents.view` for
  supplier-owned folders; PATCH rename → `documents.edit`; POST
  move → `documents.move`; POST archive/unarchive →
  `documents.edit`.
- `app/routers/supplier_documents.py` — Pydantic bodies relaxed
  (`doc_type` + `title` optional, new optional `folder_id`); new
  `POST /supplier-documents/{id}/move` gated on `documents.move`.
- 8 new/extended routes registered (verified in route table):
  POST/GET tree/GET detail/PATCH/move/archive/unarchive under
  `/api/v1/document-folders` plus `POST .../supplier-documents/
  {id}/move`.

**Gate 4 — tests:**
- `backend/tests/test_document_folders.py` — **30** functions
  (CRUD 9, move + loop guard 6, archive 6, tree 3, permissions 5,
  migration / catalogue invariants 1).
- `backend/tests/test_supplier_documents_folders.py` — **8**
  (relaxed-create 4, doc move 3, archive-live-doc interaction 1).
- **Total new test functions: 38** (target ≥36).
- Baseline-drift literal bumps (chat-15 §3 convention): alembic
  head sentinel `0041_drop_vat_registered → 0043_document_folders`
  across `test_subcontracts_migration`,
  `test_budget_changes_migration`, `test_migration_0025_actuals`,
  `test_migration_0028_user_preferences`,
  `test_migration_0040_contact_book`,
  `test_migration_0041_drop_vat_registered`,
  `test_sc_valuations_migration`, `test_subcontractors`,
  `test_bootstrap`. Permission count literal `132 → 133` across
  `test_permissions_2_{6,7,8a,8b}`, `test_patch_3`,
  `test_retro_wires`, `test_auth_rbac` (super_admin 132→133,
  director 128→129). `_FakeRow` stubs in
  `test_supplier_documents.py` + `test_supplier_document_files.py`
  extended with `folder_id = None` (matches new serialise read path).
- **Pytest 2nd-run WARM-DB: EXIT=0, 1376 passed + 3 X (xpassed/
  xfailed), 0 failed, 0 errors, 1379 collected.**

**Files landed:** see CHANGELOG.md §Chat-45 for the full list.
**NOT touched:** `docs/SY_Hub_Phase2_Backlog.md` (operator-owned),
all of `frontend/**/*` (zero changes).

**Backlog surfaced (operator hand-adds):** B79-FE folder-tree UI;
Role & Permissions Admin screen; external-party folder access
(portal work 2.9); physical storage path reorg; cascade archive;
owner-type expansion (project, subcontract).

---

### Chat 44 — Build Pack 2.7-FE-docfix · Supplier-document upload bugfix + dialog file-attach + desktop drag-drop (Frontend only) (2026-02)

**Stacks on Chat 43's B76 upload UI. Two scheduled gates per the
Build Pack plus a live-eyeball-caught multipart bug between Gate 2
landing and the operator's first real upload, fixed inside the same
B78 envelope and verified end-to-end on `origin/main` before close.**
Backend FROZEN — zero changes; permissions stay **132**, alembic
head stays **`0042_file_ref_text`**, `git status --porcelain backend/`
empty at every gate-stop. Closes backlog **B78**.

**Gate 1 — §R1 over-strict client pre-check fix:**
- `DocumentsTab.jsx` — added `ALLOWED_EXTENSIONS` constant mirroring
  the backend allowlist (`.pdf .jpg .jpeg .png .gif .webp .doc .docx
  .xls .xlsx .csv .txt`) and `fileExtension(name)` helper (lowercase
  last `.`-token, tolerant of `null`/`undefined`/dot-trailing).
  Rewrote `preCheckFile(file)` to accept the file when **either**
  the MIME matches `ALLOWED_MIME_TYPES` **or** the extension
  matches `ALLOWED_EXTENSIONS`. Empty-file and >25 MB checks
  unchanged. Symptom fixed: iOS Safari + Windows Chromium/Edge
  picks where browsers supply an empty / `application/octet-stream`
  MIME no longer hard-reject valid documents.
- `DocumentsTab.test.jsx` — added §R1 regression tests #1–#5 plus
  helper edge-cases. Gate 1 full-suite Jest: **80 suites / 624 tests**.

**Gate 2 — §R2 dialog file-attach + §R3 desktop drag-drop + §R5 hints:**
- §R2 dialog attach (`DocumentsTab.jsx`). New `document-form-attach`
  block in the Add/Edit dialog. Staged file lives in a SEPARATE
  `useState` (`pendingFile`) — never in the create/patch JSON
  payload (`file_ref` stays system-owned). Upload mutation fires
  **after** save settles: new id from `create.mutateAsync` is
  forwarded into `upload.mutateAsync({id, file})`; for edit the
  existing `editing` id is reused. Toast / dialog-close gated on
  the full sequence; explicit "Document saved but upload failed"
  copy when the post-save upload fails (doc left in place).
- §R3 desktop drag-drop (`DocumentsTab.jsx`). New `DropZone`
  sub-component wraps (a) the row Upload cell (testid
  `document-row-dropzone-{id}`) and (b) the dialog attach area
  (`document-form-dropzone`). `onDragOver` toggles a `data-dragover`
  attribute; `onDrop` reads `e.dataTransfer?.files?.[0]` and routes
  through the SAME `preCheckFile` + `onPickFile` /
  `onStageDialogFile` paths the click flow uses — single source
  of truth for validation + toast mapping.
- §R5 hints (scope-creep, confirmed). `<input accept>` appends the
  `.ext` list to the MIME list (Windows + older Chromium pickers
  honour extensions more reliably). "or drag a file here" copy
  under both Upload positions.
- §R6 tests — added #6, #6b, #7, #8, #9, #10, #11, #12, #13, #14
  to `DocumentsTab.test.jsx`. Covers: create+upload chain,
  edit+upload chain, no-file → create-only, payload purity on both
  create and patch (no `file`, no `file_ref` keys), pre-check on
  staged `.exe`, dialog state reset on Cancel-then-reopen, row drop
  → upload, dialog drop → stage, pre-check on drop, and the §R5
  mobile-baseline invariant rendering in BOTH positions with the
  extension list in `accept`. `DocumentsTab.test.jsx` grew 30 → **46
  tests**. Gate 2 full-suite Jest: **80 suites / 634 tests**.

**Gate 2 follow-up — multipart Content-Type bug + wire-level test:**

After Gate 2 landed on `main`, the operator's first live upload
from the row Upload control returned 422 `{type:"missing",
loc:["body","file"]}`. Root cause: `frontend/src/lib/api.js`
declares the shared axios `api` instance with
`headers: { 'Content-Type': 'application/json' }`; axios 1.x's
FormData auto-detection requires the merged Content-Type to be
absent so the browser can fill in `multipart/form-data; boundary=…`,
and the instance-level JSON default short-circuited that — request
shipped as JSON with an unserialised FormData body, server saw no
`file` field. The Chat-43 suite missed it because all component +
hook tests `jest.mock('@/lib/api')` entirely; nothing exercised the
real axios instance with its real defaults.

- `frontend/src/lib/api/supplierDocuments.js` — `uploadDocumentFile`
  now passes `{ headers: { 'Content-Type': undefined } }` as the
  third arg to `api.post`. axios 1.x interprets undefined at the
  per-request layer as "remove from merged headers", unblocking
  FormData auto-detection. `undefined` — NOT the bare string
  `'multipart/form-data'`, which would omit the boundary and 422
  identically. **`lib/api.js` itself was NOT touched** — the shared
  default stays `application/json` for every other caller (zero
  blast radius).
- `frontend/src/lib/api/__tests__/supplierDocuments.upload-multipart.test.js`
  (NEW, 5 tests) — does NOT `jest.mock('@/lib/api')`. Imports the
  REAL `api` instance, installs a request interceptor (post-merge /
  pre-`transformRequest`) AND a custom adapter (post-transform),
  then calls `uploadDocumentFile('D1', file)`. Pins: (1) merged
  `Content-Type` at interceptor time is **undefined** — proves the
  override stripped the JSON default during `mergeConfig`; this is
  the smoking-gun assertion that would have caught the bug. (2)
  Merged `Content-Type` at adapter time is NOT `application/json`
  under any casing / bucket. (3) FormData body carries the File on
  field `file`. (4) POST + `/v1/supplier-documents/D1/file` +
  `baseURL` + `withCredentials: true` all intact. (5) Shared
  `api.defaults.headers['Content-Type']` still `application/json`
  after the call (no-blast-radius regression guard). (6)
  `axios.VERSION` major ≥ 1 (surfaces header-merge regressions).
- `frontend/src/lib/api/__tests__/supplierDocuments.test.js` — the
  §R3.1 assertion that had pinned the (now-buggy) `expect(opts).
  toBeUndefined()` shape was updated to pin the new contract
  `opts.headers['Content-Type'] === undefined`; misleading comment
  rewritten.

After Save-to-GitHub of the multipart fix, the operator repeated the
exact 422-repro upload with a PDF — **200, has_file=true, filename +
size returned, download round-trip works.** Dialog attach + row
drag-drop + dialog drag-drop all re-tested live in the same session.

**VERIFY (canonical, double-run):**
- Gate 2 follow-up full Jest: **81 suites / 639 tests passed**
  (delta vs Gate 2: +1 suite, +5 tests; delta vs B76 close:
  +2 suites / +21 tests). Double-run identical.
- Greps (Gate 2 follow-up): `file_ref` in `DocumentsTab.jsx` → 3
  hits, **all `//` / `/*` comments** documenting the system-owned
  invariant pinned by §R6 test #8 (zero runtime references); single
  shared `<input type="file">` in `<FilePicker>` survives drag-drop
  layering (re-pinned by #14); `sharepoint | graph.microsoft |
  https?://` in `DocumentsTab.jsx` → comments-only (per §R8
  allowance); `lib/api.js` shared instance default still
  `headers: { "Content-Type": "application/json" }` (re-pinned by
  the regression-guard test in the new wire-level file).
- Backend frozen: `git status --porcelain backend/` empty at every
  gate-stop AND at push time; alembic head `0042_file_ref_text`;
  perms **132**; roles 10.

**Files landed (frontend only):**
- `frontend/src/components/suppliers/DocumentsTab.jsx` (modified —
  Gate 1 + Gate 2)
- `frontend/src/components/suppliers/__tests__/DocumentsTab.test.jsx`
  (modified — +5 §R1 tests at Gate 1; +10 §R6 tests at Gate 2)
- `frontend/src/lib/api/supplierDocuments.js` (modified — Gate-2
  follow-up only)
- `frontend/src/lib/api/__tests__/supplierDocuments.test.js`
  (modified — Gate-2 follow-up only)
- `frontend/src/lib/api/__tests__/supplierDocuments.upload-multipart.test.js`
  (added — Gate-2 follow-up; 5 wire-level tests closing the
  mocked-hook blind spot)
- `CHANGELOG.md` (entry prepended for this pack)
- `docs/chat-summaries/chat-44-closing.md` (new — first close for
  chat 44)
- `memory/PRD.md` (this entry)

Backlog **B78 — Supplier-document upload bugfix + dialog attach +
drag-drop** delivered. Operator hand-marks
`docs/SY_Hub_Phase2_Backlog.md` (operator-owned — NOT touched here).

---

### Chat 43 — Build Pack 2.7-FE-docupload · Supplier-document file upload/download (Frontend only) (2026-02)

**Wires the rev-B `POST/GET /v1/supplier-documents/{id}/file`
endpoints (Chat 41 Build Pack 2.7-BE-rev-B) onto `DocumentsTab.jsx`.**
Two-gate run, both verified on `origin/main` via raw-fetch before
advancing. Backend FROZEN — zero changes; permissions stay **132**,
alembic head stays **`0042_file_ref_text`**, `git status --porcelain
backend/` empty at both gate-stop points. Closes backlog **B76**.

**Gate 1 — API layer + hooks + their tests:**
- `lib/api/supplierDocuments.js` — `uploadDocumentFile(id, file)`
  (multipart POST through the shared axios `api`, field name `"file"`);
  `downloadDocumentFile(id)` (cookie-aware blob via `authedFetch`
  against `${API_BASE}/v1/supplier-documents/{id}/file`, returns
  `{blob, filename}`, throws structured `{status, detail}` on
  non-2xx); `parseContentDispositionFilename(header)` (RFC-5987
  `filename*=UTF-8''…` preferred over plain `filename="…"`).
- `hooks/supplierDocuments.js` — `useUploadDocumentFile(supplierId)`:
  `useMutation({id, file})` invalidating `docsKeys.all(supplierId)`
  on success. Download stays imperative.
- Tests added: `lib/api/__tests__/supplierDocuments.test.js` (17),
  `hooks/__tests__/supplierDocuments.test.jsx` (11). Gate 1 full-suite
  Jest: 80 suites / 598 tests.

**Gate 2 — Cleanup + File column + DocumentsTab tests:**
- §R1 destructive cleanup: dialog `<Input>` `document-form-file-ref`
  removed; `file_ref` purged from `emptyForm()`, `rowToForm()` and
  the `onSubmit` payload builder; "File ref" `<SensitiveValue/>`
  column replaced with the new "File" column. Repo-wide grep for
  `document-form-file-ref` and `file_ref` in `DocumentsTab.jsx` →
  zero hits.
- §R2 File column (new `DocumentFileCell` + `FilePicker`
  sub-components in the same file):
  - `has_file && canViewSensitiveDocs` → file_name + human size
    (via `formatFileSize`) + Download button; Replace control when
    editable + not archived.
  - `has_file && !canViewSensitiveDocs` → neutral "File attached"
    indicator only.
  - `!has_file && canEditDocs && !is_archived` → Upload control +
    helper hint text ("PDF, image, Office docs · 25 MB max").
  - Otherwise → `—` placeholder.
  - Archived rows: NO Upload/Replace; Download still permitted on
    existing files for sensitive viewers (§R2.4).
- §R2.5 mobile-first upload: real `<input type="file">` (not
  drag-drop-only) wrapped in `<label>` for tap-to-pick, `accept`
  set to the EXACT §R0.3 backend allowlist (`ALLOWED_MIME_TYPES`
  frozen at module scope). Client-side pre-check (`preCheckFile`)
  fires BEFORE the request: empty / wrong-type / >25 MB blocked
  with inline error; no toast spam. Toast mapping on server errors:
  413 → "File is too large — 25 MB cap."; 422 → `detail` echoed;
  502 → "Document storage is temporarily unavailable, try again
  shortly." (raw detail NEVER echoed for 502).
- §R2.6 download: blob → in-memory `<a download={filename ||
  row.file_name || 'document'}>` → click → `URL.revokeObjectURL`
  in `finally`. No SharePoint URL touches the DOM.
- §R9 scope-creep (confirmed, not silent):
  - Uploading-state guard (`uploadingId` disables the picker while
    in flight; "Uploading…" copy).
  - Inline file-type / size hint text under the empty-state Upload.
  - Inline per-row pre-check error rendered next to the affordance.

**§R5 component tests:** `DocumentsTab.test.jsx` grew **10 → 30 tests**.
All 13 §R5 acceptance cases covered + §R2.4 archived-row guard +
§R2.5 mobile-first invariant + §R9 uploading-state. Mocks for
`@/hooks/supplierDocuments`, `@/lib/api/supplierDocuments`,
`@/context/AuthContext`, `sonner`. NO real network.

**Gate 2 VERIFY (canonical, 2nd-run):**
- Full Jest: **80 suites / 618 tests passed** (delta vs Gate 1:
  +20 tests; delta vs pack-start: +2 suites / +48 tests).
- Targeted: `--testPathPattern="DocumentsTab"` → **30/30 passed**.
- Greps: `document-form-file-ref` zero · `file_ref` in
  `DocumentsTab.jsx` zero · `sharepoint|graph.microsoft` strict
  (comments stripped) zero · runtime DOM emptiness re-proven by
  §R5 #13.
- Backend frozen: `git status --porcelain backend/` empty; alembic
  head `0042_file_ref_text`; perms **132** (verified by `bootstrap.
  verify.perms`).

**Files landed (frontend only):**
- `frontend/src/lib/api/supplierDocuments.js` (modified)
- `frontend/src/hooks/supplierDocuments.js` (modified)
- `frontend/src/components/suppliers/DocumentsTab.jsx` (modified)
- `frontend/src/components/suppliers/__tests__/DocumentsTab.test.jsx` (modified)
- `frontend/src/lib/api/__tests__/supplierDocuments.test.js` (added, Gate 1)
- `frontend/src/hooks/__tests__/supplierDocuments.test.jsx` (added, Gate 1)
- `CHANGELOG.md` (entry prepended for this pack)
- `docs/chat-summaries/chat-43-closing.md` (new — first close for chat 43)
- `memory/PRD.md` (this entry)

Backlog **B76 — Supplier-document upload UI** delivered. Operator
hand-marks `docs/SY_Hub_Phase2_Backlog.md` (operator-owned — NOT
touched here).

---

### Chat 41 — Build Pack 2.7-BE-rev-B · SharePoint/OneDrive via Microsoft Graph · **Gate 3 / pack close** (2026-02)

Closes rev-B: operator-run smoke-test script + closing docs landed.
The pack is complete; the only remaining step is the operator's
one-time live verification (run `python backend/scripts/sharepoint_smoke_test.py`
after Azure admin consent + `Sites.Selected` grant).

**End-of-pack head:** `0042_file_ref_text` (unchanged).
**Perms:** **132** (unchanged across the entire pack).

Files landed at Gate 3:
- `backend/scripts/sharepoint_smoke_test.py` — operator-run live
  verifier. `--grant` runs the `Sites.Selected` site grant. **Refuses
  to run in stub mode (exit 2). Refuses live mode with any blank
  required env var (exit 2). Never prints the secret value or any
  Graph response body.**
- `CHANGELOG.md` — Gate 3 closing block.
- `docs/chat-summaries/chat-41-closing.md` — appended a
  "Build Pack 2.7-BE-rev-B (Backend) — APPENDED" section (earlier
  rev-A close preserved verbatim).
- `memory/Gate3_VERIFY_2.7-BE-rev-B.md` — full Gate 3 artefact bundle.

**NOT touched:** `docs/SY_Hub_Phase2_Backlog.md` (operator-owned).
Two backlog items logged via the closing doc:
- **B76** — Frontend document upload control (separate FE prompt).
- **B77** — Multi-site document routing (Track 5), reusing the
  rev-B `DocumentStore` engine.

VERIFY artefact: `memory/Gate3_VERIFY_2.7-BE-rev-B.md`.

---

### Chat 41 — Build Pack 2.7-BE-rev-B · SharePoint/OneDrive via Microsoft Graph · **Gate 2** (2026-02)

Wires the Gate 1 stub into the supplier_documents service + router.
`file_ref` is now system-owned (structured `StoredObjectRef` JSON);
clients can no longer hand-write it.

**Gate 2 head:** `0042_file_ref_text` (unchanged from Gate 1).
**Perms:** unchanged at **132** — upload reuses
`supplier_documents.edit`, download reuses
`supplier_documents.view_sensitive`.

Files landed at Gate 2:
- `backend/app/services/supplier_documents.py` — `upload_document_file`,
  `download_document_file`, `_supplier_folder_path`,
  `ALLOWED_DOC_MIME_TYPES`, structured `file_ref`, `has_file` + file
  metadata in `serialise`, client-settable `file_ref` removed at
  service layer.
- `backend/app/routers/supplier_documents.py` (rewrote) — `file_ref`
  dropped from `SupplierDocumentCreateBody`/`UpdateBody`,
  `POST /{id}/file` (multipart, `supplier_documents.edit`),
  `GET /{id}/file` (StreamingResponse,
  `supplier_documents.view_sensitive`), error map
  `ValueError(size)→413`, `ValueError→422`, `LookupError→404`,
  `SharePointError→502 "document storage unavailable"`.
- `backend/tests/test_supplier_documents.py` (12 tests; rev-B reshape).
- `backend/tests/test_supplier_document_files.py` (20 new tests).

Deferred to Gate 3: `backend/scripts/sharepoint_smoke_test.py`,
chat-41-closing.md rev-B section.

VERIFY artefacts: `memory/Gate2_VERIFY_2.7-BE-rev-B.md`.

---

### Chat 41 — Build Pack 2.7-BE-rev-B · SharePoint/OneDrive via Microsoft Graph · **Gate 1** (2026-02)

External-auth integration. Gate 1 lands the test-stub surface, the
Graph client scaffold (no live call made during build), and the
schema migration. Live verification is the operator-run smoke-test
at Gate 3 (§R6).

**Gate 1 head:** `0042_file_ref_text` (rev-A was `0041`; +1 migration).
**Perms:** unchanged at **132** (no new perms in this gate;
upload/download will reuse `supplier_documents.edit` and
`supplier_documents.view_sensitive` at Gate 2).

Files landed:
- `backend/app/config.py` — 8 SharePoint settings + `is_sharepoint_stub`
  property (mirrors AI_CAPTURE_MODEL='test-stub').
- `backend/app/services/sharepoint_client.py` — `DocumentStore`
  Protocol, `StoredObjectRef`, `StubDocumentStore` (in-process),
  `GraphDocumentStore` (live; not exercised in build),
  `get_document_store()` factory, `SharePointError` /
  `SharePointConfigError`, `_safe_filename`.
- `backend/alembic/versions/0042_file_ref_text.py` — widen
  `supplier_documents.file_ref` `String(500)` → `Text`. Round-trip
  verified.
- `backend/tests/test_sharepoint_client.py` — 25 tests, double-run
  green in stub mode, zero Azure dependency.

Deferred to Gate 2: `services/supplier_documents.py` wiring of
upload/download, router endpoints `POST/GET /{id}/file`, removal of
client-settable `file_ref`, `has_file`/file-metadata in serialise.

Deferred to Gate 3: `backend/scripts/sharepoint_smoke_test.py`,
chat-41-closing.md rev-B section.

VERIFY artefacts: `memory/Gate1_VERIFY_2.7-BE-rev-B.md`.

---

### Chat 41 — Build Pack 2.7-FE-revision · Gate 1 + 3 operator-eyeball follow-ons (2026-02)

**Frontend Suppliers Contact-Book rework + 3 follow-on changes the
operator caught at eyeball.** Single Gate-1 sweep covering §R1–§R8,
then CIS placement fix (FE-only), then `suppliers.delete` (BE + FE),
then `vat_registered` removal (DB + BE + FE — migration `0041`), then
Step 2B widening pass (multi-field search, click-to-sort, expanded
seed).

**Pytest double-run on pod (canonical, second-run):**
- **1292 passed, 3 xpassed (1295 total), 0 failed, 0 errors** — 232.67 s.
- Each run on a freshly-bootstrapped DB. One pre-existing test-isolation
  gap surfaced (`test_entities_api` mutates entities that
  `test_projects` module fixtures rely on) — candidate backlog item,
  not in scope for this pack.

**Frontend craco test:** **78 suites / 570 tests passed** (single
deterministic run).

**§R9 VERIFY greps — all zero-hit:**
- `default_vat_rate / cis_subtype / 'Subcontractor'` in
  `SupplierForm.jsx / SupplierDetail.jsx / SupplierList.jsx`
- `labelCisSubtype / CIS_SUBTYPE_LABEL` anywhere in `frontend/src/`

**Permissions count target hit exactly: 132** (was 131; +`suppliers.delete`).

**Alembic head: `0041_drop_vat_registered`** (round-trip
up → down → up clean; downgrade re-adds `vat_registered` BOOLEAN NOT
NULL DEFAULT false for dev safety).

**Highlights:**
- §R1 — `lib/api/trades.js` + `hooks/trades.js` (TanStack Query, exported
  `tradesKeys`, `staleTime: 60_000`).
- §R2 — `<TradePicker/>` (combobox over command + popover; client-side
  filter; canonical-name resolution from backend POST; perm-gated Add).
- §R3 — `SupplierForm.jsx` 4-way type select; CIS sub-block
  Contractor-gated (CIS status, CIS-registered, UTR with 10-digit
  client validation); address block, trading_name + contact_name.
- §R4 — `SupplierDetail.jsx` mirror: subtitle ` · CIS …` Contractor-gated;
  address block hidden when all-null; Documents tab gated; Delete button.
- §R5 — `SupplierList.jsx` 4-way type filter with `?type=` seed and
  stale-bookmark fallback; Trade column default-on; CIS badge + amber
  unverified cue Contractor-gated; dynamic colSpan.
- §R6 — `<ColumnPicker/>` (session-only optional-column visibility;
  per-user persistence is backlog **B-COLS**).
- §R7 — Subcontractors nav + `HardHat` icon removed; `canViewTrades`
  + `canCreateTrades` capabilities added; `labelCisSubtype` +
  `CIS_SUBTYPE_LABEL` deleted from `cisFormat.js`.
- §R8 — 78 suites, +3 brand-new test files (14 new tests), existing
  Form/Detail/List + cisFormat suites reworked method-by-method;
  `setupTests.js` `Element.prototype.scrollIntoView` shim added (cmdk
  on jsdom).
- **Eyeball follow-on 1 (FE-only):** CIS status `<select>` moved INSIDE
  the `isContractor` block on Form; cis_status omitted from non-
  Contractor submits; Detail subtitle ` · CIS …` Contractor-gated;
  paired render-presence tests added (the previous payload-only test
  let stale JSX slip through).
- **Eyeball follow-on 2 (BE + FE):** `suppliers.delete` permission
  added (mirrors `suppliers.archive` distribution); `DELETE
  /api/v1/suppliers/{id}` (204/409/403/404); 5-table linked-record
  gate (purchase_orders/actuals/subcontracts/cis_verifications/
  supplier_documents); audit row recorded before DELETE; FE Delete
  button on Detail with toast for 409 (preserves backend's exact
  detail message) and stays-put on conflict.
- **Eyeball follow-on 3 Step 2A (DB + BE + FE):** `vat_registered`
  dropped entirely — operator decision; "has a VAT number" is the
  de-facto registered signal, Xero owns VAT logic. Migration 0041,
  full purge from model/service/router/seed/Form/Detail/List + tests.
- **Eyeball follow-on 3 Step 2B (BE + FE + seed):**
  - Search widened: single `q` matches across name, trading_name,
    contact_name, notes, and the joined `trades.name`
    (case-insensitive, contains). Composes AND with the
    `supplier_type` filter.
  - Click-to-sort: 7 sortable columns on `SupplierList.jsx` with
    asc/desc/clear cycle, `aria-sort` + arrow indicator.
  - Seed expanded to 11 varied contacts across all 4 types + 8
    trades; idempotent via `_REPAIRABLE_FIELDS` upsert (re-run:
    0 created, 11 repaired).

### Chat 41 — Build Pack 2.7-BE-rev-A · Gate 3 (2026-02)

**§R5 tests + §R6 seed + CHANGELOG + chat-41-closing + PRD update.** Final gate of the rev-A run. STOP at Gate 3 for push readiness.

**Pytest double-run on pod (canonical, second-run):**
- **1281 passed, 3 xpassed (1284 total), 0 failed, 0 errors.**
- First-run noise (60 FAILED + 110 ERROR) was session-state pollution from dev iterations; every failing test passes individually. Second run is clean.

**HARD-BREAK fixes (both green on second run):**
- `test_budget_integrity_committed.py`: **4 / 4** — raw-SQL INSERT `default_vat_rate` removed from column list AND values tuple.
- `test_audit_remediation_p0.py`: **16 / 16** — same.

**New rev-A test files (≥14 functions target → landed 35):**
- `test_trades.py` (12): CRUD, whitespace normalisation, case-insensitive idempotent re-create + audit-row dedupe, archive/unarchive lifecycle, list filters, permission gating, archive-doesn't-clear-supplier-trade_id invariant.
- `test_supplier_contact_book.py` (11): serialised shape (vat_registered + trade keys present; cis_subtype + default_vat_rate absent), vat_registered independence from vat_number, full `_resolve_trade` priority matrix incl. `_UNSET` sentinel.
- `test_migration_0040_contact_book.py` (12): DB-only VERIFY — head, 4-value enum + no temp types, columns added/dropped, indexes, FK `ON DELETE SET NULL`, CHECK constraint gone, permission_resource enum extension.

**Reworked test files:**
- `test_subcontractors.py` (13) — class renames `TestSubcontractor*` → `TestContractor*`, alembic head bumped to 0040, enum assertion to 4-value tuple, cis_subtype paths removed, Consultant/Other coverage added, `?supplier_type=Subcontractor → 422` test added.
- `test_suppliers.py` — dropped `default_vat_rate` payload; added serialised-shape assertions.

**Snapshot/baseline test bumps (head + perm count + role grants):**
- alembic head: 7 test files bumped to `0040_contact_book_rework`.
- permission count: 7 historical snapshot tests bumped from `129 → 131` (test_permissions_2_6/7/8a/8b, test_patch_3, test_retro_wires, test_auth_rbac).
- role grants in test_auth_rbac: super_admin 129→131, director 125→127, read_only 17→18 (all via wildcard / direct grant).
- Behavioural message bumps in test_cis_service + test_subcontracts_service for the relabelled error strings.
- Test helpers (`_subcontracts_common.py`, `test_cis_api.py`, `test_cis_service.py`): default supplier_type literal `Subcontractor → Contractor`.

**Hygiene cleanup:**
- `test_po_approvals_api.py`, `test_purchase_orders_api.py`, `test_po_receipts_api.py` — removed silently-ignored `default_vat_rate` from supplier-create payloads.

**§R6 seed:**
- `scripts/seed_contact_book.py` (new, idempotent). 8 starter trades + 4 sample contacts (one of each `supplier_type`). Verified idempotent: re-run produces `contacts_created=0 contacts_repaired=4`.

**Docs landed:**
- `/app/CHANGELOG.md` — Chat 41 entry prepended (D1–D7 deviation block + §R3/§R4/§R5/§R6 detail).
- `/app/docs/chat-summaries/chat-41-closing.md` — closing summary.
- `/app/memory/Gate3_VERIFY_2.7-BE-rev-A.md` — full Gate 3 VERIFY.

**Untouched (per opener):**
- `docs/SY_Hub_Phase2_Backlog.md` (operator-owned).

**Alembic head**: `0040_contact_book_rework`. Permission count: **131**. Roles: 10.
**Status**: rev-A push-ready.

### Chat 41 — Build Pack 2.7-BE-rev-A · Gate 2 (2026-02)

**§R3 (services) + §R4 (routers) + seed_rbac additions.** Continues from Gate 1's `0040_contact_book_rework` migration + model layer. STOP at Gate 2 with grep VERIFY + new permission count.

- **`services/trades.py`** (new): `list_trades`, `get_trade`, `get_or_create_trade` (concurrency-safe via `begin_nested()` SAVEPOINT + IntegrityError retry — both racers resolve to the same row), `set_archived`, `serialise`. Whitespace-collapse + length validate on name.
- **`services/suppliers.py`** reshaped:
  - Dropped `_validate_cis_subtype` + `_coerce_vat_rate`.
  - Added `_UNSET` sentinel + `_resolve_trade` (priority: `trade_id` → `trade` name (grow-as-you-type) → explicit null clears → absent key leaves untouched).
  - `_AUDIT_COLS` no longer includes `cis_subtype` / `default_vat_rate`; now includes `vat_registered` + `trade_id`.
  - `create_supplier` / `update_supplier`: drop dropped fields; honour `vat_registered`; resolve trade. `current_cis_status` default is `'Unverified'` iff `supplier_type='Contractor'` (was `'Subcontractor'`).
  - `serialise` omits `cis_subtype` + `default_vat_rate`; adds `vat_registered`, `trade_id`, and a null-safe `trade` (the joined relationship name).
- **`services/cis.py`** gate (§R3.3): `supplier_type != "Subcontractor"` → `supplier_type != "Contractor"`; error message updated to "CIS verification only valid for contractors (CIS subcontractors)".
- **`services/subcontracts.py`** LD2 gate (§R3.4): `"Subcontractor"` → `"Contractor"`; cosmetic "Subcontractor not found" messages updated to "Contractor not found".
- **`routers/trades.py`** (new): `GET /trades`, `POST /trades` (idempotent grow-as-you-type, returns 201), `POST /trades/{id}/archive` + `/unarchive` (gated on `trades.create` — `mutate` gate reused per §R4.1 NOTE).
- **`routers/suppliers.py`**: bodies reshaped — dropped `cis_subtype` + `default_vat_rate`; added `vat_registered`, `trade_id`, `trade`. `supplier_type` filter description updated to the 4-value label set.
- **`routers/cis.py`**: 409-detector string updated from "only valid for subcontractors" to "only valid for contractors".
- **`server.py`**: mounts `trades_router` directly after `suppliers_router`.
- **`seed_rbac.py`**: `trades.{view,create}` added to catalogue; role grants — `trades.create` to super_admin/director/finance/PM (mirrors `suppliers.create`); `trades.view` additionally to site_manager + read_only (mirrors `suppliers.view`).

**Gate 2 verification (end-to-end live API + grep):**
- §R3.2 grep on `services/suppliers.py` for `cis_subtype | default_vat_rate | _coerce_vat_rate | _validate_cis_subtype | CIS_SUBTYPES` → 3 hits, ALL docstring/comment notes (zero functional references). ✓
- §R3.4 precise grep for `supplier_type == / != "Subcontractor"` in `app/services/` → **zero hits**. ✓
- CIS verify on a plain `Supplier` → **409** with the new "only valid for contractors (CIS subcontractors)" message.
- `?supplier_type=Subcontractor` filter → **422** (relabel confirmed).
- `?supplier_type=Contractor` filter → 200 with the right total.
- Trade idempotent CI re-create returns the same id (no duplicate row).
- `_UNSET` sentinel verified: trade_id swap → explicit null clear → absent key no-op all behave correctly.
- Bootstrap verify: `permissions=131 actual=131`, `roles=10`, alembic head `0040_contact_book_rework`. ✓

**Alembic head**: `0040_contact_book_rework`. Permission count **129 → 131** (target hit exactly).
**Gate 2 VERIFY artefacts**: `/app/memory/Gate2_VERIFY_2.7-BE-rev-A.md`.

### Chat 41 — Build Pack 2.7-BE-rev-A · Gate 1 (2026-02)

**§R1 (migration) + §R2 (models) only.** Operator opener: "STOP at Gate 1 with the VERIFY query outputs." Services / routers / tests / seed are Gate 2 / Gate 3 work.

- **Migration**: `0040_contact_book_rework` (down_rev `0039_committed_single_writer`). Reversible round-trip verified (up → down → up).
- **Schema**:
  - NEW `trades` table (tenant-scoped, audit cols) + `ux_trades_tenant_name_ci` unique on `(tenant_id, lower(name))`.
  - `suppliers.trade_id` UUID FK → trades.id `ON DELETE SET NULL`, nullable, indexed.
  - `suppliers.vat_registered` BOOL NOT NULL DEFAULT false (independent of `vat_number`).
  - DROP `suppliers.cis_subtype` (per D1) + `suppliers.default_vat_rate` (per D2). Column-scoped CHECK `ck_suppliers_vat_rate_range` auto-dropped (verified).
  - `supplier_type` PG enum recreated to `{Contractor, Supplier, Consultant, Other}` via the standard rename → create → drop default → cast (USING CASE) → re-set default → drop old sequence. Data map: `Subcontractor → Contractor`, `Supplier → Supplier`. New default `'Supplier'`.
  - `permission_resource` enum += `'trades'` (autocommit helper, mirrors 0035).
- **Downgrade**: fully reversible with a documented lossy-cast caveat (`Consultant/Other → Supplier` on collapse) and the `trades` enum value remaining in place (PG limitation).
- **Models**:
  - NEW `app/models/trades.py` — `Trade` ORM (tenant-scoped, standard audit cols), exported via `models/__init__`.
  - `app/models/suppliers.py` reshaped: `SUPPLIER_TYPES` to the new 4-tuple; `CIS_SUBTYPES` and the `cis_subtype` / `default_vat_rate` columns removed; `vat_registered` + `trade_id` added; `trade` `lazy="joined"` one-directional relationship (no back_populates) to avoid N+1 in serialise.
  - `app/models/rbac.py`: `RESOURCES += "trades"`.
- **Gate 1 VERIFY artefacts**: `/app/memory/Gate1_VERIFY_2.7-BE-rev-A.md` (head, enum labels, data-mapping seeded row check, dropped/added columns, CHECK constraint gone, trades table + unique index, permission_resource enum extension).
- **Expected intermediate state**: services/routers still reference `CIS_SUBTYPES` and the dropped columns, so the live backend will not import-clean until Gate 2 lands. This is explicitly per §R7 ("Do not touch services/routers until the operator confirms the schema is clean").

**Alembic head**: `0040_contact_book_rework`. Permission count unchanged at **129** at Gate 1 (will become 131 after `seed_rbac.py` + bootstrap at Gate 2).

### Chat 40 — Build Pack 2.7-FE (2026-02)

Frontend-only. Backend FROZEN at `0039_committed_single_writer`. No
permission/role changes (129/10).

**FIX half (D1–D7):** 2.5 supplier surface drift corrections.
  - D1 SupplierForm CIS enum (lowercase) `(gross, net_20, net_30, not_registered)` + null
  - D2 Bank fields use `bank_account_no` + new `bank_name`, `company_number`
  - D3 `is_archived: bool` everywhere (phantom `s.status` removed)
  - D4 Suppliers restore route `/restore` → `/unarchive`; hook renamed
  - D5 SupplierList params switched to `{q, include_archived, supplier_type}`
  - D6 SupplierDetail reads `bank_account_no` + adds `bank_name`/`company_number`
  - D7 Suppliers + Subcontractors nav entries in AppShell

**ADD half (§R4):**
  - SupplierList: Type filter (All/Supplier/Subcontractor), CIS badge column,
    §R6 unverified cue (amber dot + header count) on subcontractor view,
    `useSearchParams` URL sync.
  - SupplierForm: Type selector + Subcontractor block (cis_subtype,
    cis_registered, UTR 10-digit-validated); explicit
    `cis_subtype: null` on Subcontractor→Supplier transitions.
  - SupplierDetail: tabbed (Overview / CIS / Documents / Contracts
    placeholder); per-permission tab visibility.
  - New `CISTab` (current banner + history + record form), `DocumentsTab`
    (toolbar + table + dialog form + expiry badges + archive/restore),
    `CISStatusBadge`, `DocExpiryBadge` (pure frontend bucketing).
  - New `cisFormat.js` label maps + `formatDate` helper.
  - New `lib/api/cis.js`, `lib/api/supplierDocuments.js` + hooks.
  - 8 new capability helpers in `lib/poCapability.js`.

**Tests:** 9 new files named exactly per §R5 — final **513 passed / 75
suites green** (was 424 / 67 at start of 2.7-FE).

**Deferred to ADD-pack follow-up / future chats:**
- Playwright spec `frontend/e2e/suppliers-subcontractors.spec.ts` —
  repo has no Playwright runner wired at HEAD.

### Chat 39 — Build Pack 2.6-FIX (2026-02)
- Alembic head: `0038_sc_valuations` → `0039_committed_single_writer`
- Permissions count unchanged: **129**. Roles unchanged: **10**.
- Backend integrity (A1/A2/A3/A4):
  - `committed_not_invoiced` is now single-writer (Python).
    Trigger writes `committed_value` only.
  - `recompute_for_line` acquires parent-budget + line FOR UPDATE
    locks (parity with `apply_bcr`).
  - Subcontract-valuation certify requires explicit `budget_line_id`
    (422 on omission); silent first-line guess removed.
- Frontend defects (B-CONTINGENCY / B-DATA / C-UNCAT):
  - `is_contingency` exposed in API + Zod schema.
  - BCR detail resolves cost code via `useCostCodes` map.
  - `useCostCodes` uses `keepPreviousData`; `groupLinesByCategory`
    falls back to a Loading bucket while codes are mid-load.
- 16 new tests (4 backend files + 3 frontend files, exact filenames
  per §R5). Test #5 is a genuine two-connection psycopg-3 lock probe.
- Backend suite double-run: **1228 passed, 3 xpassed** both runs.
- Frontend suite: **421 passed across 66 suites**.
- A6 (CIS-in-rollup): investigated, no code change. Finding: CIS is
  correctly payment-side only; cost ledger tracks gross, Payment
  notice carries `cis_deducted`. See
  `docs/chat-summaries/chat-39-closing.md` §A6.
- Backlog (`docs/SY_Hub_Phase2_Backlog.md`) NOT touched. Out-of-scope
  items (A5, A7, A8, B-DESIGN, B-MONEY, B-SIZE) listed in closing
  summary for operator triage.



### 2026-06-01 — Chat 37 (Prompt 2.6-FE-fix) BCR Workflow Defect Fixes ✓ COMPLETE

Frontend-only defect pass on top of Chat 36 (commit `52a4288`).
Backend FROZEN — alembic head `0038_sc_valuations`, perms 129
(re-verified post-fix). Push-to-main via operator's Save-to-GitHub.

Three operator-reproduced defects fixed:
- **Bug 1 (CRITICAL):** `EditBCRDialog` crashed with `ReferenceError:
  DialogDescription is not defined`. Root cause: missing named
  import in `pages/projects/BudgetChangeDetail.jsx` (line 23).
  Audit confirmed every other budgetChanges dialog already
  imported it correctly. Fix: add the import.
- **Bug 2 (HIGH):** Negative deltas displayed but evaluated to
  positive on submit/net. Root cause: `<Input type="number">` in
  `BCRLineEditor.jsx` — browsers strip a lone leading minus, so
  state never receives the sign. Fix: switch to
  `type="text" inputMode="decimal"` (mirrors actuals' working
  signed-money pattern), apply DELTA_REGEX in `EditBCRDialog.submit`,
  and strip commas in onChange so pasted `-1,234` parses to `-1234`.
- **Bug 3 (MEDIUM):** Picker + detail rows showed every line as
  "Untitled line". Root cause: components read `bl.description`
  (does not exist) and `bl.cost_code` (UUID-only emitted). Backend
  emits `line_description`. Fix (frontend-only per LD1): read
  `line_description` and, when null, fall back to
  `` `Line ${display_order ?? id.slice(0,8)}` `` (operator-confirmed
  option c).

**Testing:** added 11 new tests across `BCRLineEditor.test.jsx` and
`BudgetChangeDetail.test.jsx` (R5 acceptance gates: sign preservation,
Transfer £0 net, lone `-`, pasted `-1,234`, picker labels for all
three fallback branches, detail row labels). **FE suite: 416/416
passing** (was 405). ESLint clean. Backend untouched (alembic head
`0038_sc_valuations`, perms 129).

Files modified:
- `frontend/src/pages/projects/BudgetChangeDetail.jsx`
- `frontend/src/components/budgetChanges/BCRLineEditor.jsx`
- `frontend/src/components/budgetChanges/CreateBudgetChangeDialog.jsx`

Files added:
- `frontend/src/components/budgetChanges/__tests__/BCRLineEditor.test.jsx`
- `frontend/src/pages/projects/__tests__/BudgetChangeDetail.test.jsx`



### 2026-06-01 — Chat 36 (Prompt 2.6-FE) BCR Workflow Frontend ✓ COMPLETE

Frontend slice surfacing the full Budget Change Request workflow.
Backend frozen at alembic head `0038_sc_valuations`, 129 permissions.
Operator-confirmed Option (d) scope — per-budget queue via the
BudgetDetail "Changes" tab + dedicated "Change Log" tab + standalone
BCR detail page at `/budget-changes/:bcrId`. Standalone cross-project
queue deferred (backlog **B51** — backend gap; no `GET
/budget-changes/pending` or `GET /projects/{id}/budget-changes` today).

- **§R0.2 ENDPOINT COVERAGE MAP** — all 10 BCR endpoints + 6
  `budget_changes.*` permissions enumerated and mapped to UI surfaces
  with no "intentionally not surfaced" rows.
- **§R0.2 PIN — endpoint 9 (apply)** — confirmed from
  `services/budget_changes.py:507/580`: `approve_bcr` ONLY stamps
  status (no `budget_lines` write, no `recompute_summary`);
  `apply_bcr` is the ONLY mutator (`approved_changes += delta` with
  `FOR UPDATE` fresh-read + all-or-nothing). Two-step Approve → Apply
  UI is required and correct.
- **Surfaces shipped:**
  - **A** `BudgetChangeQueue` — per-budget queue with 8 filter chips
    (Open / All / 6 statuses) mounted as the "Changes" tab on
    BudgetDetail (`?tab=changes`).
  - **B** `BudgetChangeDetail` at `/budget-changes/:bcrId` —
    workflow page with action bar + embedded EditBCRDialog
    (Draft-only inline edit).
  - **C** `CreateBudgetChangeDialog` — type + title + reason +
    lines with client-side invariant mirrors of the backend
    (Transfer/Contingency net=0; Adjustment net≠0; contingency
    source flag check).
  - **D** `BCRRejectDialog` — required-reason modal.
  - **E** `BudgetChangeLogPanel` — read-only history mounted as
    "Change log" tab on BudgetDetail.
  - **F** `BCRStatusPill` — 6-status colour map (slate/amber/sky/
    emerald/rose/muted-slate).
  - **G** `BCRLineEditor` — shared lines builder used by Create + Edit.
- **Self-approval guard (LD2)** mirrors backend behaviour: gross
  movement basis `sum(abs(delta)) >= threshold` against the per-tenant
  `budget.self_approval_threshold_gbp` (default £10k, fetched via
  `useBudgetSelfApprovalThreshold` against
  `GET /api/v1/system-config/budget.self_approval_threshold_gbp`).
  Sub-threshold self-approve is now permitted (UI matches backend).
- **`useBCRTransition('apply')`** coarse-invalidates `['budgets']` so
  BudgetGridV2 totals refresh after Apply (mirrors PO commitment-verb
  pattern at `hooks/purchaseOrders.js:235`).
- **Test surface:** every interactive element has a `data-testid`
  in `bcr-{component}-{purpose}` kebab-case.
- **Tested:** Playwright iteration_11 — 15/15 review scenarios PASS,
  100% frontend success rate. All 3 P3/P4 follow-ups applied
  (threshold-aware self-approval guard; DialogDescription on all 4
  dialogs; uncontrolled→controlled Select warning resolved).

#### Backlog item raised
- **B51 — BCR cross-project list endpoints.** PO approvals has the
  pattern (`GET /approvals/pending` + `GET /projects/{id}/approvals/pending`);
  BCR list endpoint requires `budget_id`. Add
  `GET /budget-changes/pending` + `GET /projects/{id}/budget-changes`
  mirroring it. Unblocks the standalone director "what's awaiting me"
  queue page (deferred LD1 surface). Half-session backend prompt.


### 2026-05-31 — Chat 35 (Prompt 2.8b) Subcontract Valuations, Payment Notices, Retention ✓ COMPLETE

Backend-only build per Build Pack 2.8b. Push-to-main. All §R5 acceptance
gates green (1234 passed, 0 failed, 0 errors — final-run hard gates met).

- **§R0.2 — `net_amount` basis verdict: PRE-deduction.** Reads
  `services/actuals.create_actual` + `_compute_retention` +
  `_compute_cis_deduction` + `services/budgets_reconciliation.recompute_for_line`
  end-to-end. The actuals service stores `net_amount` as-is from the
  payload (no internal subtraction); `retention_amount` +
  `cis_deduction_amount` are recorded as separate columns; the
  cost-tracker subtracts retention from `actuals_to_date` itself.
  Wired R3.1 step 6 to pass `net_amount=gross_this_cert` with explicit
  deduction columns. Test gate 16 backstops:
  `net_amount − retention − CIS == net_payable_this_cert`.

- **§R0.5 — CIS-status mapping** uses the 4-value `current_cis_status`
  domain (`CURRENT_CIS_STATUSES`) — the cache field, NOT the 3-value
  verification-row enum (`CIS_MATCH_STATUSES`). Final wiring:
  `Gross→0, Net→20, Unmatched→30, Unverified→30 (live default), NULL→30
  (defensive)`. Explicit tests for all 5 cases.

- **§R1 Migration `0038_sc_valuations`.** Idempotent enum extensions:
  `permission_action += 'certify', 'release'`;
  `permission_resource += 'subcontract_valuations', 'payment_notices'`
  (resource extension is a logged CHANGELOG deviation vs Build Pack
  §R1.4 which listed action only). 3 new tables: `subcontract_valuations`,
  `payment_notices`, `retention_releases` (each with check
  constraints + the appropriate unique constraints). Adds the
  deferred FK `actuals.related_subcontract_id → subcontracts.id ON
  DELETE SET NULL` (idempotent guard; column existed since 2.5).
  Inserts 7 permission catalogue rows + role grants. Down/up
  round-trip clean.

- **§R2 Permissions.** +7 (4 subcontract_valuations + 3
  payment_notices). **122 → 129** literal. Role grants:
  - `super_admin` + `director`: all 7.
  - `finance`: view/view_sensitive + certify on valuations and
    view/create/release on notices (the money-authorising surface).
  - `project_manager`: view/view_sensitive/create on valuations +
    view on notices (PM raises and views; no certify or release).
  - `site_manager` + `read_only`: view-only on both surfaces.

- **§R3 Services.** Three new services:
  - `services/subcontract_valuations.py` — Draft → Submitted →
    Certified | Rejected. `certify_valuation` computes cumulative
    `gross_this_cert`, retention movement, CIS on labour only,
    over-claim warn-not-block, posts the actual via the existing
    actuals service with §R0.2 PRE-deduction wiring, commits snapshot
    fields, auto-creates the Payment notice. View_sensitive masks
    CIS rate/retention movement/net payable/previous certified net.
  - `services/payment_notices.py` — `create_payment_notice_internal`
    (auto on certify) + `create_payless_notice` (manual against
    Certified only). `PN-NNNN` numbered per-valuation.
  - `services/retention_releases.py` — PC + DLP releases, each once
    per subcontract (unique constraint). Posts a negative-retention
    actual (`net_amount=0`, `retention_amount=-amount_released`) to
    flow the released bucket into `actuals_to_date`.

- **§R4 Routers.** Two new routers under `/api/v1`:
  - `/subcontract-valuations` (POST create, GET list, GET one, POST
    submit, POST certify, POST reject).
  - `/payment-notices` (GET list, GET one, POST payless) + retention
    sub-routes on `/subcontracts/{sc_id}/retention-release[s]`.

- **§R5 Tests.** 6 new files, **54 new tests** (≥36 required).
  Includes gate 16 §R0.2 backstop, all 5 CIS-status branches, NULL
  defensive case, lifecycle gates, cumulative 2nd-cert math, retention
  movement, over-claim warn-not-block, permission gating (PM 403 on
  certify), audit emission, role mapping count assertions.

- **Legacy guardrail tests rebaselined.** 13 head/perm-count pins
  bumped from `0037_subcontracts`/`122` to `0038_sc_valuations`/`129`
  across the legacy test corpus (auth_rbac, bootstrap, multiple
  migration tests, permissions_2_6/2_7/2_8a, retro_wires,
  subcontractors, subcontracts_migration, patch_3). Director count
  118→125, read_only 15→17.

- **Final pytest result.** Warm-DB RUN1 = RUN2 = **1234 passed,
  2 xfailed, 1 xpassed, 0 failed, 0 errors** in ~223s each. Operator's
  hard gates (failed=0 AND errors=0) green on both runs.



### 2026-05-31 — Chat 34 (Prompt 2.8a) Subcontracts & Variations ✓ COMPLETE

Backend-only build per Build Pack 2.8a. Push-to-main. All 35 acceptance
gates green. 2.8b (valuations / payment notices / retention / CIS
deductions) deliberately deferred — `retention_pct` + `cis_applies`
columns stored but UNUSED until 2.8b.

- **§R1 Migration `0037_subcontracts`.** `permission_action += 'cost'`
  (idempotent — `issue` already exists from PO 2.5 so unchanged).
  `permission_resource += 'subcontracts', 'subcontract_variations'`.
  New tables `subcontracts` (header — LD1 nullable PO link, LD2
  Subcontractor-only enforced at service layer, CHECK constraint on
  `status ∈ {Draft, Active, Completed, Terminated}`, UNIQUE
  `(project_id, reference)`) and `subcontract_variations` (header —
  CHECK constraint on `status ∈ {Raised, Costed, Approved, Issued,
  Rejected, Withdrawn}`, CHECK on `cost_treatment IN
  {WithinContractSum, BudgetChange}`, UNIQUE `(subcontract_id,
  reference)`, FK `generated_bcr_id → budget_changes.id ON DELETE
  SET NULL`). Adds the **deferred FK**
  `budget_changes.source_variation_id → subcontract_variations.id ON
  DELETE SET NULL` (LD3 — the column existed as a 2.6 stub; this
  migration adds the constraint only). Down/up round-trip clean.

- **§R2 Permissions.** +10 (5 subcontracts + 5 variations).
  **112 → 122** literal. Role grants mirror live `seed_rbac.py`:
  - `super_admin` + `director` (via wildcard): all 10.
  - `finance`: `view/view_sensitive + approve` on subcontracts and
    `view + approve + issue` on variations (no create/cost — finance
    is the approval/issue authority).
  - `project_manager`: `view/view_sensitive + create/edit` on
    subcontracts and `view + create + cost` on variations (PM
    raises and costs; does NOT approve or issue — separation of
    duties carries through).
  - `site_manager` + `read_only`: `subcontracts.view` +
    `subcontract_variations.view` only.

- **§R3 Services.** New `services/subcontracts.py` and
  `services/subcontract_variations.py`. Subcontracts: SC-NNNN
  project-scoped sequential (race-safe under project row lock); LD2
  rejects plain suppliers as ValueError → 422; LD1 PO link
  validated for same project + same subcontractor (warn-not-block
  sum mismatch via `po_reconciliation_note`); state machine
  `Draft → Active → Completed` + `Terminated`; activation requires
  `signed_at`. Variations: VAR-NNNN per-subcontract sequential;
  state machine `Raised → Costed → Approved → Issued` +
  `Rejected/Withdrawn`. On approval, `cost_treatment` selects:
  - `WithinContractSum`: bumps `subcontract.current_contract_sum`
    by `agreed_value` (LD4).
  - `BudgetChange`: calls the EXISTING
    `services.budget_changes.create_bcr(..., change_type='Adjustment',
    source_variation_id=variation.id, lines=[{budget_line_id, delta}])`
    (LD3). The returned BCR is a normal Draft BCR with its own
    approve/apply lifecycle — NOT auto-applied. Active-budget
    resolution via `is_current=true AND status='Active'`; missing →
    422. SoD carry-through: the BCR creator = the variation
    approver, so 2.6's self-approval guard prevents that SAME user
    from approving the generated BCR above threshold; a different
    user must. Correct and intended; documented in module docstrings.
  Service-layer audit on all mutations (`record_audit` + `field_diff`).

- **§R4 Routers.** `/api/v1/subcontracts` (POST + GET-list + GET +
  PATCH + POST `/{id}/activate|complete|terminate`) and
  `/api/v1/subcontract-variations` (POST + GET-list + GET + POST
  `/{id}/cost|approve|issue|reject|withdraw`). Approve body takes
  `cost_treatment` + `target_budget_line_id` (required when
  `BudgetChange`). Cross-tenant 404, validation 422, bad transition
  409. `subcontracts.view_sensitive` gates contract-sum fields at the
  serialiser.

- **§R5 Tests — 64 functions across 6 files (EXACT names per Build
  Pack):** `test_subcontracts_migration.py` (8),
  `test_permissions_2_8a.py` (11), `test_subcontracts_service.py`
  (14), `test_subcontracts_api.py` (11),
  `test_subcontract_variations_service.py` (13),
  `test_subcontract_variations_api.py` (7). Shared HTTP fixtures live
  in `tests/_subcontracts_common.py` (underscore-prefixed so pytest
  does NOT collect it — same convention as `_bcr_common.py`).
  Coverage includes end-to-end two-user variation→BCR apply
  (gate 26) and source_variation_id round-trip (gate 27).
  Test files were **NOT consolidated** (the 2.6 split-file miss did
  NOT recur).

- **Regression baselines bumped (chat-15 §3 / chat-22 §2 literal-drift
  convention):** `test_auth_rbac.py` (super_admin 112→122, director
  108→118, read_only 13→15), `test_patch_3.py` (112→122),
  `test_permissions_2_6.py` (112→122), `test_permissions_2_7.py`
  (112→122), `test_retro_wires.py` (112→122),
  `test_budget_changes_migration.py` (head 0036→0037),
  `test_subcontractors.py` (head 0036→0037),
  `test_migration_0025_actuals.py` (head 0036→0037),
  `test_migration_0028_user_preferences.py` (head 0036→0037),
  `test_bootstrap.py` (head sentinel 0036_→0037_, 2 sites).

- **2nd-run pytest:** 1183 collected, 1180 passed, 3 xpassed,
  0 failed, 0 errors. Regression floor held.


### 2026-05-31 — Chat 33 (Prompt 2.6) Budget Change Control (BCRs) & Forecasts ✓ COMPLETE

Backend-only build per Build Pack 2.6. Push-to-main. All 35 acceptance
gates green.

- **§R1 Migration `0036_budget_changes`.** `permission_action +=
  'apply'` (idempotent); `budget_lines.is_contingency` BOOL NOT NULL
  DEFAULT false (clean backfill); new tables `budget_changes` (BCR
  header with state machine, denormalised tenant_id per
  purchase_orders precedent, nullable `source_variation_id` STUB
  with NO FK reserved for 2.8) and `budget_change_lines` (signed
  delta). UNIQUE (budget_id, reference); CHECK constraints on type +
  status. Down/up round-trip clean.
- **§R2 Permissions.** +2 (`budget_changes.submit` + `.apply`).
  **110 → 112** (operator-confirmed additive: Build Pack predicted
  +5/115 but the live seed already carried view/create/edit/approve).
  Role grants: super_admin/director (wildcard); PM (full 6); finance
  (view+approve+apply); apply mapping IDENTICAL to approve mapping.
- **§R3 Services.** New `services/budget_changes.py`.
  Audit pattern: service-layer `record_audit` + `field_diff`
  (suppliers/CIS/PO Track-2 convention) — NOT legacy budgets
  router-layer pattern. Per-type invariants (Transfer/Contingency
  net-zero, Adjustment non-zero), race-safe BCR-NNNN reference via
  parent row lock. State machine: Draft → Submitted → Approved →
  Applied + Rejected/Withdrawn terminal. LD2 self-approval guard
  on GROSS movement basis (`sum(abs(delta))` — not net_impact, so
  a £50k↔£50k net-zero Transfer by the raiser still blocks at the
  £10k threshold); NULL-creator fail-open; super-admin NOT exempt.
  Apply re-asserts parent Active/Locked, FRESH reads under FOR
  UPDATE, ALL-OR-NOTHING write, then reuses the EXISTING
  `_recompute_line` + `recompute_summary` (no duplicated math).
- **§R4 Routers.** New `routers/budget_changes.py` mounted at
  `/api/v1`. 10 endpoints: POST/GET list/GET one/PATCH (Draft only)
  + submit/approve/reject (reason required)/withdraw/apply + GET
  `/budgets/{id}/change-log`. Cross-tenant → 404; validation → 422;
  state → 409; self-approval → 403.
- **§R5 Tests.** **39 new test functions split across 4 files** matching
  Build Pack §R5 naming convention:
  - `tests/test_budget_changes_migration.py` (3 — schema + head sentinel)
  - `tests/test_budget_changes_service.py` (15 — invariants 10 + apply 5)
  - `tests/test_budget_changes_api.py` (17 — workflow 7 + self-approval 5 + API surface 5)
  - `tests/test_permissions_2_6.py` (4 — perms count + role mapping)
  Shared helpers in `tests/_bcr_common.py` (leading-underscore → NOT collected).
  Baseline-drift literals bumped across 8 legacy files (chat-15 §3 pattern):
  test_auth_rbac (super_admin 110→112, director 106→108),
  test_bootstrap (head sentinel 0035→0036), test_migration_0025_actuals,
  test_migration_0028_user_preferences, test_patch_3, test_retro_wires,
  test_permissions_2_7, test_subcontractors (all head/count literals).
  **Pytest 2nd-run WARM-DB: 1110 passed, 3 xpassed, 0 failed,
  0 errors, 189.07s.** Regression floor 1071 honoured (+39 net new).
- **Scope honoured.** No frontend (2.6-FE later split). No 2.8
  variation generation (source_variation_id is stub with NO FK).
  No per-role approval limits (B43). No contingency-remaining
  reporting. No edit/reverse of Applied BCR (corrections = new
  opposing BCR by design).
- **Commits:** R1–R5 + closing docs in working tree. NOT pushed-
  confirmed — operator pushes via Save to GitHub.



### 2026-02-01 — Chat 32 (Prompt 2.7) Subcontractors, CIS Verifications & Supplier Documents ✓ COMPLETE

Backend-only build per Build Pack 2.7. Push-to-main (operator verifies
on GitHub web). All 28 acceptance gates green.

- **§R1 Migration `0035_subcontractors`.** Idempotent enum extensions
  (`permission_action += 'verify'`; `permission_resource += 'cis',
  'supplier_documents'`); new PG enum `supplier_type` (`Supplier`,
  `Subcontractor`); 5 new columns on `suppliers`
  (`supplier_type` NOT NULL default `'Supplier'` — clean backfill;
  `cis_subtype` String(30) nullable, app-constrained;
  `cis_registered` Boolean NOT NULL default false;
  `utr` String(13) nullable, sensitive;
  `current_cis_status` String(20) nullable, service-maintained cache);
  new table `subcontractor_cis_verifications` (append-only,
  match_status CHECK Gross/Net/Unmatched, supplier_id+verified_on DESC
  index); new table `supplier_documents` (lightweight; doc_type CHECK
  vs 7 allowed values; soft-delete via is_archived). Downgrade drops
  new tables, columns, and the supplier_type enum (PG cannot drop
  enum values — documented asymmetry per 0029 pattern). Live
  round-trip down/up verified.
- **§R2 Permissions.** `_perms_for("cis", include=["view",
  "view_sensitive","verify"], sensitive={"view_sensitive","verify"})`
  + `_perms_for("supplier_documents", include=["view",
  "view_sensitive","create","edit","archive"],
  sensitive={"view_sensitive","archive"})`. **102 → 110.** Role
  mapping mirrors suppliers.create role-set (super_admin, director,
  finance, project_manager) for cis.verify + ALL 5 supplier_documents
  perms (test gate 27 literal); cis.view_sensitive mirrors
  suppliers.view_sensitive (3 roles); cis.view extended to
  site_manager + read_only (broader read).
- **§R3 Services.**
  - `services/suppliers` extended: `_validate_supplier_type`,
    `_validate_cis_subtype` (rejects on Plain Supplier),
    `_validate_utr` (whitespace-strip + 10-digit check),
    `list_suppliers(supplier_type=…)` filter, `_AUDIT_COLS` includes
    the 5 new columns. `current_cis_status` defaults `Unverified` for
    new Subcontractors, NULL for plain Suppliers; NOT settable via
    update payload. UTR added to `SENSITIVE_RESPONSE_FIELDS`.
  - `services/cis` new module:
    `record_verification` (rejects on non-Subcontractor →
    `ValueError`, validates match_status ∈ {Gross,Net,Unmatched},
    coerces dates/decimals, **only writer of**
    `supplier.current_cis_status`, emits audit `Create`),
    `list_verifications` (newest first by verified_on),
    `get_current_verification`. NO update/delete helpers exposed
    (append-only contract).
  - `services/supplier_documents` new module: mirrors suppliers
    service patterns 1:1 — `create_document`, `list_documents`
    (excludes archived by default, `include_archived` flag),
    `get_document`, `update_document`, `set_archived` (idempotent;
    audits Archive/Restore). `file_ref` + `notes` gated in
    serialiser via `SENSITIVE_RESPONSE_FIELDS`.
- **§R4 Routers.**
  - `routers/suppliers` extended: `?supplier_type=` query param on
    GET (router→service ValueError→422); 4 new create/update body
    fields (`supplier_type`, `cis_subtype`, `cis_registered`, `utr`
    — `utr` max_length=30 at body layer to accept whitespace-decorated
    input; service strips and validates against 10-digit contract).
    Serialiser surfaces all subcontractor fields; `utr` gated.
  - `routers/cis` new (prefix `/cis`): `POST /verifications` (201,
    gate `cis.verify`, cross-tenant → 404, non-subcontractor → 409,
    other ValueError → 422; 201 response includes
    verification_number regardless of view_sensitive since creator
    just wrote it); `GET /verifications?supplier_id=…` (gate
    `cis.view`; strips `verification_number` without
    `cis.view_sensitive`); `GET /verifications/current`. **No PATCH,
    no DELETE.**
  - `routers/supplier_documents` new (prefix `/supplier-documents`):
    POST (201), GET list, GET one, PATCH, POST archive +
    POST unarchive. Cross-tenant → 404. All routers mounted under
    `/api/v1` in `server.py` alongside existing suppliers router.
- **§R5 Tests.** **42 new test functions** across 5 files
  (`test_subcontractors.py` 13, `test_cis_service.py` 7,
  `test_cis_api.py` 7, `test_supplier_documents.py` 11,
  `test_permissions_2_7.py` 4). All 28 build-pack acceptance gates
  covered. Baseline-drift literals bumped (chat-15 §3 pattern) in
  `test_auth_rbac` (super_admin 102→110, director 98→106, read_only
  12→13), `test_bootstrap` (head sentinel 0034_→0035_),
  `test_migration_0025_actuals`, `test_migration_0028_user_preferences`,
  `test_patch_3` (102→110), `test_retro_wires` (102→110).
  **Pytest 2nd-run WARM-DB: 1071 passed, 3 xpassed, 0 failed,
  0 errors, 196.53s.** Regression floor 1038 honoured.
- **Scope honoured.** No frontend (later split 2.7-FE). No auto-expiry
  flagging (LD2 / backlog **B48**). No payment-blocking on lapsed
  CIS (belongs with 2.8 valuations). Legacy `suppliers.cis_status`
  column left in place — `current_cis_status` is the authoritative
  cache; dropping the legacy column is OUT OF SCOPE (documented
  deviation in migration docstring). `supplier_documents.file_ref` is
  a reference string only; binary upload pipeline migrates to Track 5
  (backlog **B49**). Per-project supplier ratings backlog **B50**.
- **Commit:** `09d5367`. NOT pushed-confirmed (per Build Pack 2.7
  opener — operator verifies push on GitHub web).



### 2026-05-31 — Track 2.4C Budget Approval Controls (SoD) ✓ COMPLETE

Build Pack 2.4C R1–R5. Segregation-of-duties: a budget's creator cannot
self-activate at/above a configurable threshold (default £10,000).

- **R1 — Config.** New `system_config` row
  `budget.self_approval_threshold_gbp` (Decimal, default 10000.00,
  category Budget, super_admin-editable). Typed getter
  `get_budget_self_approval_threshold(db)` with in-code fallback
  `DEFAULT_BUDGET_SELF_APPROVAL_THRESHOLD_GBP = Decimal("10000.00")`.
  Seed reconciliation count 39 → 40.
- **R2 — `activate()` guard.** In `app/services/budgets.py::activate()`:
  side-effect-free local-variable total
  = Σ(`original_budget` + `approved_changes`) across freshly-loaded
  `BudgetLine` rows (no `recompute_summary`, no read of cached
  `total_budget`). Comparison `total >= threshold`. NULL
  `created_by_user_id` fail-open. Super-admin **not** exempt.
- **R2.3 — Exception + mapping.** New `BudgetSelfApprovalError` →
  router maps to **HTTP 403** (authorisation refusal).
  `BudgetStateError` stays 409.
- **R5 — Tests.** `TestBudgetSelfApprovalGuard` (8 tests, all passing):
  boundary `==threshold` blocked, `>threshold` blocked, `<threshold`
  allowed, other-user activation allowed, NULL-creator guard asserted
  by source inspection (column is NOT NULL today), super-admin not
  exempt, service raises `BudgetSelfApprovalError` (not
  `BudgetStateError`), getter reads DB + falls back to default.
- **Test fixtures.** Three legacy modules (`test_budgets.py`,
  `test_actuals_routes.py`, `test_budgets_line_delete.py`) added a
  module-scope `_bump_self_approval_threshold` autouse fixture that
  **only raises** the threshold to £999,999,999 (via PUT
  `/system-config/{key}`, which invalidates the backend cache),
  restoring on teardown.
- **Pytest WARM-DB 2nd run:**
  `1035 passed, 2 xfailed, 1 xpassed, 2 warnings in 165.12s`.
- **Commits:** `199c857` (R1–R5 nine-file change), `9871219`
  (test-hygiene fix). **Push pending** — see CHANGELOG push-hygiene
  flag re: pre-existing auto-commit `352eb08` noise.

Files: `app/routers/budgets.py`, `app/seed_system_config.py`,
`app/services/budget_errors.py`, `app/services/budgets.py`,
`app/services/system_config.py`, `tests/test_actuals_routes.py`,
`tests/test_budgets.py`, `tests/test_budgets_line_delete.py`,
`tests/test_system_config.py`.

Backlog spawned: **B43** Stage 2 per-role / per-user approval limits,
**B44** threshold admin UI, **B45** FE 403 self-approval refusal message.



### 2026-02-27 — R7 Batch 2 follow-on mini-pack (backend) ✓ COMPLETE

Adds the missing `GET /projects/{project_id}/purchase-orders` endpoint
— a latent Chat 24 R5 gap that surfaced visibly with Batch 2's R7.5
approvals dashboard (the frontend `listProjectPOs` always hit this
URL).

- **R0 — Endpoint.** Thin wrapper in `app/routers/purchase_orders.py`
  adjacent to the existing `POST /projects/{project_id}/purchase-orders`
  (lines 360-407). Path-bound `project_id: uuid.UUID`; same query
  params as the un-scoped `GET /purchase-orders` (`supplier_id`,
  `status`, `q`, `limit`, `offset`); same `_perm_dep` + `pos.view`
  gate; same response shape `{items,total,limit,offset}`; delegates
  to `svc.list_pos(...)`. Route inventory docstring updated.
- **R1 — Tests.** 4 new tests in
  `tests/test_purchase_orders_api.py::TestR7Batch2FollowOnListProjectPOs`:
  scoped-results (project A vs B), status-filter, perm-gate
  (unauthenticated → 401), unknown-project → 200 + empty.
- **AC1–AC4 — All green.** Pytest warm-DB: 934 passed
  (before 930 → +4), 3 xpassed, 93 errors (all `test_projects.py`,
  pre-existing). Frontend bundle delta zero (main `4cb90fd2.js`
  hash identical). No migration, no new perm, no role grant, no
  frontend changes.



### 2026-02-27 — R7 Batch 2 (frontend) ✓ COMPLETE

R7 Batch 2 turns the seven Batch-1-deferred PO action testids back on
behind real forms / confirm dialogs / optimistic mutations. ONE STOP
at end per build pack `SY_Hub_R7_Batch2_BuildPack_v2.md`.

- **R7.4 — Receipt form.** New `POReceiptDialog` posts to
  `useCreateReceipt` (line qtys + received_date + delivery_note_ref +
  notes). Wired behind `po-actions-receipt-btn` (issued) and
  `po-actions-receipt-partial-btn` (partial). `useCreateReceipt` now
  coarse-invalidates `['budgets']` on success (AC5 — receipt moves
  committed → actual).
- **R7.5 — Per-project approvals dashboard tab.** New
  `POApprovalsTab` mounted as a tab on `PurchaseOrderList`
  (`?tab=approvals`). Uses `useProjectPOs(projectId, { params: {
  status: 'pending_approval' } })` + client-side filter fallback. Row
  Review affordance deep-links to `/purchase-orders/{id}?tab=approvals`
  (Batch-1 `POApprovalPanel` takes it from there). All-projects view
  parked at §CARRIED FORWARD.
- **R7.6 — Confirm-dialog + Void + optimistic layer.** New
  `POVoidDialog` (required-reason, clones reject-dialog shape) wired
  behind `po-actions-void-btn` (approved) and
  `po-actions-void-issued-btn` (issued/partial). Rebuilt
  `usePoTransition` with `onMutate`/`onError`/`onSettled`: void +
  sendBack apply an optimistic `status` patch (rollback on error);
  void/sendBack/issue/approve/close all coarse-invalidate `['budgets']`
  on settle.
- **Edit + Delete (Option A — header-only).** New `POEditDialog`
  (header-only PATCH; bound to backend `edit_tier` enum: `full` /
  `header_annotation_only` / `read_only` from
  `services/po_authz.py:EditPermission`). New `PODeleteDialog`
  (draft-only, mirrors backend 422 on non-draft). `po-actions-edit-btn`
  gates on `edit_tier === 'full'` + `pos.edit`;
  `po-actions-edit-issued-btn` gates on `edit_tier ===
  'header_annotation_only'` + `pos.edit_issued`;
  `po-actions-delete-btn` mounts only on draft.
- **AC1 — `DEFERRED_TESTIDS` array EMPTY, regression-guard block
  DELETED.** All 7 previously-deferred testids are wired; the
  empty-loop guard would have been vacuously green and was removed
  per the pack. Each re-enabled button has a per-status positive
  render assertion.
- **Tests.** Jest 387/387 green (unchanged from baseline — net of
  the 32 removed deferred-loop iterations vs new R7.4/R7.5/R7.6/Edit/
  Delete assertions). Five new E2E specs (`po-receipt.pm`,
  `po-approvals.pm`, `po-void.pm`, `po-edit.pm`, `po-delete.pm`)
  tagged `@po-batch2` + `@smoke`. New `yarn e2e:po-batch2` script.
- **Bundle.** main 395.24 kB gz (cap 437 kB → 41.76 kB headroom).
  `suppliers-po` chunk 14.57 kB gz.



### 2026-02-13 — Audit Remediation TIER P1 (v1 build pack) ✓ (R5 HALTED)

R0 reconciliation → R1–R6 built. R5 (destructive Alembic downgrade)
HALTED for operator decision per build-pack contract. No schema change.
Permissions 102 / roles 10 unchanged. Alembic head unchanged at
`0034_audit_sendback`. **Warm-DB suite: 928 passed, 3 xpassed, 0 failed,
93 errors (all `test_projects.py`, pre-existing).**

- **R0 — Reconciliation gate.** Pre-P0 tree at `130ccfc`: cold run 999
  passed clean / warm run 906 passed + 93 errors (all
  `test_projects.py` — same 93 as post-P0). Confirms the 93 errors are
  pre-existing, not P0-induced. The 2 audit_log failures I'd flagged
  earlier were transient state pollution — today's runs show 0 failures.
- **R1 — `mfa_pending` blocked from `/mfa/disable` and
  `/mfa/backup-codes/regenerate`.** Both swapped from
  `Depends(get_enrollment_user)` → `Depends(get_current_user)`.
  `verify_password` / `verify_totp` gates stay as defence in depth.
  Live evidence: 401 "Invalid token type" with `mfa_pending`; 204 (or
  400 "MFA not enrolled") with `access` — proving the dep passes the
  legitimate token through.
- **R2 — 3 order-dependent flaky tests quarantined** with
  `@pytest.mark.xfail(strict=False, reason=…)` + entry in
  `Future_Tasks.md` §23.
- **R3 — Source-row lock on `create_new_version`.** Layering: Option A
  (shared service helper). NEW `app/services/appraisal_locks.py` exports
  `lock_appraisal_for_update(db, id)`. The P0.1 router helper now
  delegates to it. `create_new_version` calls it BEFORE
  `source.is_current = False`. `create_scenario` audited — does NOT
  flip source's `is_current`, so no lock added (per build-pack rule).
  Two-session proof: A holds → B `NOWAIT` → `OperationalError`; A
  commits → B acquires.
- **R4 — `deps.py:144` docstring fixed** — no longer lists
  `/password/change` (or any of the now-moved security-critical
  endpoints).
- **R5 — P1.10 destructive Alembic downgrade — Option 1 (NotImplementedError)
  APPLIED (operator decision, 2026-02-13).**
  `0027_default_line_items_backfill.py` downgrade replaced with `raise
  NotImplementedError(...)` + module-docstring note. NO new migration.
  0025 round-trip test retargeted to `0027_default_line_items_backfill`
  so it stops AT (does not execute) 0027's downgrade. Runbook entry at
  `/app/docs/SY_Homes_Future_Tasks.md` §24. The `alembic downgrade --sql`
  CI canary remains backlog.
- **R6 — `CHANGELOG.md` entries spliced** for both Chat 26 (§R7.0b +
  §R7 Batch 1) and Audit Remediation TIER P0 and TIER P1.
- **P0 + P1 test file: 25/25 green.**

### 2026-02-13 — Audit Remediation TIER P0 (v2 build pack) ✓

All four P0 (critical) findings from the Claude-Code audit, re-grounded
to `main`. Working tree only; awaiting operator gate before push. No
schema change. **Warm-DB suite: 920 passed, 2 pre-existing failures
(`test_audit_log.py::TestCsvJsonExport`) + 93 pre-existing errors
(`test_projects.py` FK in `appraisal_scenarios`) — verified pre-existing
by stashing P0 deltas: same 2 failures persist. P0 file itself: 16/16
green in isolation AND inside the full warm-DB run.**

- **P0.1 — Appraisal row lock**: new `_lock_appraisal_for_update`
  helper takes `SELECT ... FOR UPDATE` on the appraisal row + every
  cost line (Pattern-α scope) inside the caller's transaction. Called
  at the top of all 13 mutating handlers. Concurrency proof: session
  A holds the lock → session B's `SELECT FOR UPDATE NOWAIT` raises
  `OperationalError`; A commits → B succeeds.

- **P0.2 — Receipt audit actor + line lock**:
  `_recompute_po_status_after_receipt_change` is now keyword-only on
  `actor_user_id`; both callers pass `user.id`. The audit row no
  longer attributes Status_Change to `po.updated_by` (header's last
  editor) — it attributes to the receipter. The line scan inside the
  helper now `.with_for_update()` so the all-fully-received check
  serialises across concurrent receipts on different lines of one PO.

- **P0.3 — `mfa_pending` typed + locked out of `/password/change`**:
  `tokens.py` `Literal` now enumerates all three token types. The
  `/password/change` dep moved from `get_enrollment_principal`
  (accepts `mfa_pending`) to `get_current_principal` (access-only).
  Live evidence: `/password/change` → 401 with `mfa_pending`;
  `/auth/me` + `/mfa/enroll/start` still 200 with `mfa_pending`.

- **P0.4 — `/mfa/verify` rate limit**: new `mfa_verify_per_user`
  bucket = `(5, 60)` in `rate_limit.LIMITS`. The `enforce(...)` call
  sits **between** the token-type check and the User lookup at
  `auth.py:459`, so malformed / expired tokens 401 first and don't
  consume a slot. 429 carries `Retry-After`. Live evidence: 5 OK →
  6th denied (ok=False, retry > 0).

Carried-forward P1 items (audit-pack §OPERATOR DECISIONS CARRIED
FORWARD) — NOT done in P0:
- `/mfa/disable` + `/mfa/backup-codes/regenerate` still accept
  `mfa_pending` (same shape as the `/password/change` hole pre-P0).
  Same "pre-MFA token shouldn't perform security-critical account
  changes" argument applies.
- Audit P1.10 — destructive Alembic downgrade deletes real user
  data; needs explicit operator decision (patch downgrade vs forward-
  fix) when P1 is scoped.

### 2026-02-12 — Chat 26 §R7 Batch 1 fix-up (live-eyeball gate) ✓

Live operator eyeball found three classes of dead/broken buttons that
the Jest matrix had codified as expected — because both ends of the
matrix were wrong in the same way. Working tree only; awaiting gate.

- **Removed from Batch 1 (now hidden, deferred to Batch 2):**
  `po-actions-edit-btn`, `po-actions-delete-btn`,
  `po-actions-edit-issued-btn`, `po-actions-receipt-btn`,
  `po-actions-receipt-partial-btn`, `po-actions-void-btn`,
  `po-actions-void-issued-btn`. Root causes per ticket:
  * Edit / Delete / Edit-issued / Receipt → target routes don't
    exist; clicks landed on the App.js `*` catch-all `not-found-page`.
  * Void → backend `POVoidBody.reason` is `Field(..., min_length=1)`;
    sending `{}` 422s. The reason dialog ships with R7.6.

- **Slim Batch-1 matrix that DOES ship (verified live via Playwright
  as `test-pm` with spot-check `pos.approve` grant):**
  ```
  draft               → Submit
  pending_approval    → Approve, Reject     (self-approval guard)
  approved            → Issue, Send back    (send-back NOT guarded)
  issued              → Close
  partially_receipted → Close
  receipted           → Close
  closed / voided     → (none)
  ```

- **Regression guard** in `POActionButtons.test.jsx` —
  `deferred-to-Batch-2 buttons must render on NO state × persona`:
  8 states × 4 personas × 7 deferred testids = 32 assertions firing
  every CI run. When Batch 2 wires a button back in, the corresponding
  testid must be removed from `DEFERRED_TESTIDS` in the same commit.

- **Spot-check seed** (`/app/scripts/seed_r7_batch1_pos.py`):
  - Re-run is idempotent: wipes prior POs on the project, restores the
    five-PO matrix (draft / pending×2 / approved×2). PO numbers
    advance (e.g. PO-0006…PO-0010 on second run); IDs change but
    states are restored cleanly.
  - MFA self-heal step disables MFA on every `test-*@example.test`
    user (super-admin enrolment auto-fires on each restart).
  - Spot-check grant: gives `pos.approve` to the Project Manager role
    so `test-pm` can exercise Approve/Reject without an MFA dance.
    Sandbox only — production seeding never invokes this script.

- **Jest**: 57 suites, **387/387 passing** (was 357 → +30 net,
  +32 deferred-button regression assertions − 2 obsolete edit_tier
  assertions). Verified with a fresh `yarn test` post-edit.

### 2026-02-12 — Chat 26 §R7 Batch 1 ✓ Frontend (R7.0b send-back wiring + R7.1 + R7.2 + R7.3)

Frontend-only batch building on R7.0b's already-pushed backend send-back
endpoint. Working tree only — **not** pushed; awaiting operator
consolidated-STOP gate approval.

- **§1 — Send-back wiring (carry-forward from R7.0b)**:
  - `lib/api/purchaseOrders.js` — `sendBackPO(poId, body)` POSTs
    `/v1/purchase-orders/{id}/send-back`; `listPOApprovals(poId)` GETs
    `/v1/purchase-orders/{id}/approvals` (data source for R7.3 panel).
  - `hooks/purchaseOrders.js` — `sendBack` verb in `usePoTransition`
    map. New `usePOApprovals(poId, {enabled})` hook for the panel.
    NB: budget-line cache invalidation on commitment-changing verbs
    (send-back joins approve/issue/void) deferred to R7.6 / Batch 2.

- **R7.1 — Project-Detail Budgets tab-link**:
  - `pages/ProjectDetail.jsx` — `<Link>` to `/projects/{id}/budgets`
    (`data-testid=tab-budgets`), gated by
    `budgets.view || me.is_super_admin`. Routes already resolve to
    `BudgetsList` (not the catch-all). Sidebar `Budgets` entry in
    `AppShell.jsx` **left disabled** per locked decision (a global
    landing page is backlog).

- **R7.2 — `components/po/POActionButtons.jsx`** (new):
  - Refactors the inline action area out of `PurchaseOrderDetail.jsx`
    into a single source of truth.
  - Status × perm matrix incl. **approved** row (Issue / Send back /
    Void). Send-back uses shadcn `Dialog` + `Textarea` with required
    notes; reject also moved to a dialog (was `window.prompt`).
  - Self-approval guard mirrors backend `SelfApprovalForbidden`:
    `po.submitted_by === me.id` hides Approve, shows disabled twin
    with tooltip, hides Reject. **Send-back is NOT subject** — it IS
    the correction path.
  - `edit_tier` (lowercased string from backend) handled
    case-insensitively: `read_only` → no mutating buttons;
    `header_annotation_only` → suppress Edit/Delete only; `full` →
    all per matrix; absent → defensive `read_only` fallback.

- **R7.3 — `components/po/POApprovalPanel.jsx`** (new):
  - Mounts in the PO detail "approvals" tab. Renders iff
    `po.status === 'pending_approval'` AND an open approval row exists
    (resolution === null). The GET endpoint does NOT inline the open
    row, so the panel fetches via `usePOApprovals` (`/approvals` list)
    and picks the open one; the rest become history.
  - Over-budget snapshot table from
    `approval.budget_snapshot` (array of decimal-string overrun lines —
    `Number()` only for display via `fmtGBP`; no arithmetic).
  - Sensitive £ → `SensitiveValue` em-dash for read-only personas.
  - Approve (optional reason) / Reject (required reason). Self-
    approval guard via shared `lib/poSubmitter.js` helper. **Send-back
    is NOT here** — it lives only in `<POActionButtons/>` on the
    `approved` row.

- **Tests** — Jest +44 (**356/356 passing**, was 312):
  - `lib/api/__tests__/purchaseOrders.sendBack.test.js` — api/hook
    wiring URL contract.
  - `pages/__tests__/ProjectDetail.budgetsTab.test.jsx` — tab gating
    (with-perm / without-perm / super-admin / siblings).
  - `components/po/__tests__/POActionButtons.test.jsx` — per-status ×
    per-persona matrix (FULL PM / approver / read-only), approved row,
    self-approval rule, send-back dialog DOM transcript, edit_tier
    handling.
  - `components/po/__tests__/POApprovalPanel.test.jsx` — snapshot
    rendering, panel visibility logic, read-only em-dash, approve /
    reject verbs, creator-cannot-approve, send-back excluded.

- **No backend / migration / RBAC change.** Permissions 102, roles 10,
  alembic head `0034_audit_sendback` (unchanged from R7.0b push).

### 2026-05-22 — Chat 25 R6 v2 ✓ Closing-gap pass (frontend-only)

Second R6 pass to close gaps from the v1 pass that the operator flagged.

- **Expand-All (was missing, now wired end-to-end)**:
  - Toolbar buttons `bg2-expand-all` + `bg2-collapse-all`.
  - Single bulk GET `/v1/budgets/{id}/purchase-orders` hydrates every
    per-line cache via `queryClient.setQueryData(poKeys.budgetLineList(lid), …)`.
  - `useBudgetLinePOs` now has `staleTime: 30s` so seeded data is not
    immediately re-fetched.
  - Jest pin asserts ONE bulk GET → ZERO per-line PO GETs at mount.
- **Sticky cost-code column** on horizontal scroll: leading expand
  cell + cost_code header + cost_code body cell all `position: sticky`
  with backing bg. 6 sticky-attachment hits in
  `BudgetGridV2Desktop.jsx`.
- **Empty / Error+Retry states**: POsSection and ReceiptsSection both
  ship `…-loading`, `…-error`, `…-retry`, `…-empty` testids. Retry
  triggers `refetch()`.
- **A11y**: line expand button has `aria-expanded` + `aria-controls`;
  the expanded panel has `role="region"` + `aria-labelledby`.
  Keyboard Enter/Space work via native `<button>` semantics
  (jest-asserted).
- **Receipt photo thumbnail**: new `ReceiptPhotoThumb` with
  `loading="lazy"`, non-empty `alt` (caption → filename → "Receipt
  photo" fallback), `onError` → swaps to glyph fallback. Future-shaped
  endpoint `/api/v1/receipts/photos/{id}` consumed; backend photo
  router lands later.
- **Warm-expand timing**: cache-hit mount measured at ~6ms (budget
  500ms, headroom 80x).
- **Jest**: 53 suites, **324 tests passing** (was 313; +11 R6 v2 tests).
- **Bundle**: main bundle **385.29 kB gz** (gzip -9) / **395.25 kB gz**
  (CRA) — same headroom as v1.

### 2026-05-22 — Chat 25 R6 ✓ Inline Expandable Budget-Line Grid (frontend)

Phase A0 → 4 complete. R6 ships the Buildertrend-style inline expandable
budget-line drilldown against the R5.5 backend endpoints landed in the
prior session.

- **New components** (`src/components/budgets/grid/PerLineTransactionDrilldown/`):
  - `BudgetLineExpandedRow.jsx` — orchestrates breakdown + POs + Bills
  - `POsSection.jsx` — lazy-fetches `/v1/budget-lines/{id}/purchase-orders` (R5.5)
  - `ReceiptsSection.jsx` — nested per-PO `/v1/purchase-orders/{id}/receipts` (P0.3)
  - `BillsPlaceholder.jsx` — static placeholder (Documents & Compliance later track)
- **URL state**: `?expanded=line-id,line-id` on `BudgetDetail`, toggled via
  `setSearchParams(..., { replace: true })` so deep-links don't pollute
  history. Legacy `?line=` / `?drilldown=` are rewritten on mount.
- **A11y**: dedicated expand button per line with `aria-expanded` +
  `aria-controls`; panel mounts as `role="region"` with `aria-labelledby`.
- **RO gating**: `<SensitiveValue/>` renders `—` when the server returns
  `null` for `gross_total` / receipt amounts (already verified at the
  backend by R5.5 RO tests).
- **Deleted**: `BudgetGridDrilldown.jsx`, `POsSectionStub.jsx`,
  `VariationsSectionStub.jsx`, `BillsSection.jsx`, `BillStatusBadge.jsx`
  and their tests (`Drilldown.test.jsx`, `BillsSection.test.jsx`).
- **Jest**: 52 suites, **313 passing** (was 312; +11 R6 tests, +2 R5.5
  URL-pins, ‑10 stale stubs).
- **Bundle**: main **385.26 kB gz** (gzip ‑9 reported) / **395 kB gz**
  per CRA; ceiling 437 kB → **>40 kB headroom**.
- **Jest mock**: `src/__mocks__/react-router-dom.js` extended with a
  driveable `useSearchParams`/`__setSearchParams` so future URL-state
  tests don't need a real router stack.
- 0 dangling references for `BudgetGridDrilldown` / `POsSectionStub` /
  `VariationsSectionStub` / `BillStatusBadge` / legacy `BillsSection`.

### 2026-05-20 — Chat 24 ✓ CLOSED (R0–R5, Prompt 2.5)

Triage closing artefact filed at `docs/chat-summaries/chat-24-closing.md`. R0–R5 shipped, independently verified against real PostgreSQL 16, pushed to `main`. R6–R9 deferred to Chat 25.

- Alembic head `0033_po_receipts` (was 0028; +5 migrations 0029–0033).
- Permissions 102 (was 86; +16: 11 `pos.*` + 5 `suppliers.*`), roles 10 (unchanged).
- Backend pytest 875 passing (Emergent) / 55 PO+approval+receipt suites green (triage clean-DB).
- Jest 312 passing across 53 suites; 25 URL-contract pins.
- Main bundle 395.26 kB gz (cap 437, ~42 kB headroom); all R5 in lazy `suppliers-po` chunk.
- 6 in-flight defects fixed (D1–D6): numbering concurrency race, bad import, isolation_level→autocommit_block in 0029/0031/0032, notification enum, `read_only.suppliers.view` backfill, legacy guardrail rebaseline.
- 4 Build Pack deviations accepted (E1–E4): inline photos, no documents table, role-code mapping, no `pos.reopen`.
- Future_Tasks added: §16 PO approval amount thresholds, §17 reopen-from-closed, §18 cold-start vs 0018 guard (P1), §19 unified documents table, §20 multipart photo streaming.

**Carried as standing rules** ("Hard lessons"):
1. "Committed to main" ≠ pushed. Always Save-to-GitHub + triage re-pull before sign-off.
2. Backend STOP reports must include a real clean-DB migration run.
3. "Tests passing" can mean the suite never ran — confirm count + collection.
4. Demand printouts, not summaries.
5. Verify-don't-trust caught everything that mattered. Keep it.
6. Recommend a Claude Code phase-checkpoint pass on R1–R7 before Track 2 closes.

**Chat 25 job 1**: E2E lifecycle smoke (suppliers→prefix→PO→submit→approve→issue→partial→full→close, + void) against pushed code on live preview — promotes R5 from provisional to confirmed. Then R6 inline grid, R7 transitions/approvals UI, R8 tests sweep, R9 close-out.

### 2026-02-20 — Chat 24 R5 ✓ PO frontend (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING

- Seven new routes wired under React.lazy + `suppliers-po` webpack chunk: `/suppliers`, `/suppliers/new`, `/suppliers/:id(/edit)`, `/projects/:id/purchase-orders(/new|/:po_id)`, `/projects/:id/settings/numbering`.
- API clients: `lib/api/{suppliers,purchaseOrders,numberPrefixes}.js` — every endpoint under `/v1/...` exactly once.
- Hooks: `hooks/purchaseOrders.js` — TanStack Query with nested keys per Build Pack §5.6.
- Components: `<POStatusPill/>` (brand-token pills — first real brand application), `<SensitiveValue/>` (em-dash fallback, defence-in-depth), `<SupplierSelect/>` (filter combobox + create-new), `<POLineEditor/>` (live qty×rate=net + totals strip).
- Permissions: `lib/poCapability.js` — single source of truth; `nextActionsForStatus()` drives lifecycle button rendering.
- Tailwind: extended `sy-teal/sy-orange/sy-grey` palettes with 100/200/600/700/800 shade ramps.
- **URL-contract pins: 22 (≥ 12 floor)** in `lib/api/__tests__/po-url-contracts.test.js`.
- **Whole Jest suite: 312 passed** (was 251 pre-R5, +61). 53 suites green.
- **`yarn build` clean. Main bundle 395.26 kB gz (cap 437 kB, ~42 kB headroom).** R5 surface in own chunk: 10.43 kB gz.
- Future_Tasks logged: §19 unified documents table (post-Documents track), §20 multipart streaming endpoint nice-to-have.

### 2026-02-20 — Chat 24 R4 ✓ PO Receipts backend (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING

- Migration `0033_po_receipts`: 3 tables + recompute trigger + audit/notification enum extensions (via `autocommit_block` helper, no `isolation_level` regression). Backfills `read_only.suppliers.view` to close a drift hole exposed by the 0025 round-trip guardrail.
- Models: `PurchaseOrderReceipt`, `PurchaseOrderReceiptLine`, `PurchaseOrderReceiptPhoto`.
- Service `po_receipts.py`: status guard (issued|partially_receipted), future-date rejection, 30-day backdate requires `pos.edit_issued`, cumulative≤ordered guard, photo de-dup, auto status transition (issued ↔ partially_receipted ↔ receipted), Receipt audit, optional notifications.
- Endpoints: `GET/POST /purchase-orders/{id}/receipts`, `GET/PATCH/DELETE /receipts/{id}` — all under `/api/v1/`.
- Money invariant: `committed_value` unchanged across receipt create + full + delete (asserted by 2 integration tests).
- Tests: 11 unit + 24 integration = 35 R4 tests, all green. Whole suite: 875 passed, 0 failed, 0 errors (ex pre-existing `test_projects.py`).
- Live perm count: 102 (unchanged — R4 reuses `pos.receipt` from R2).
- Clean-DB bootstrap reaches `0033_po_receipts`; downgrade -1 / upgrade round-trip clean.

### 2026-02-20 — Chat 24 R3 ✓ Live-DB verification PASSED
- Provisioned local Postgres (`/app/backend/.env DATABASE_URL=postgresql+psycopg://syhomes:syhomes_dev@127.0.0.1:5432/syhomes`).
- Ran `alembic downgrade -4` then `alembic upgrade head` (0028 → 0032) — clean, zero errors. 0029, 0031, 0032 already used `op.get_context().autocommit_block()` for `ALTER TYPE ADD VALUE`; verified reversible.
- `SELECT count(*) FROM permissions` → **102** (live DB, not catalogue).
- All R1/R2/R3 integration + unit suites green: **84/84 pass** (test_purchase_orders_api, test_purchase_orders_unit, test_po_approvals_api, test_po_approvals_unit, test_number_prefixes, test_suppliers). Includes TestConcurrentNumbering (8 threads, sequential PO-0001..PO-0008, zero unique-constraint violations).
- Defects fixed during verification:
  * **D1 (race)** `po_numbering.allocate_next_number`: `SELECT FOR UPDATE` acquired row lock but SQLAlchemy identity-map served *cached* `next_sequence`, so concurrent POSTs computed the same PO number and tripped `ux_po_project_number`. Added `.execution_options(populate_existing=True)`.
  * **D2 (import)** `routers/number_prefixes._resolve_project`: wrong import `app.models.entities` → `app.models.entity` (singular). Without this, the v1 prefix endpoints raised `ModuleNotFoundError` under the tenant-scope path.
  * **D3 (test)** `tests/test_number_prefixes._get_primary_entity_id`: dropped reference to non-existent `entities.is_archived` column.
- Future task logged (P1): cold-start bootstrap blocked by 0018 guard (docs/SY_Homes_Future_Tasks.md §18).

### 2026-05-20 — Chat 24 R3 ✓ PO Approvals + commitment recompute (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING
- **Migration `0032_po_approvals.py`:**
  * po_approval_resolution ENUM (approved, rejected)
  * `purchase_order_approvals` table with budget_snapshot jsonb,
    resolution_consistency CHECK, reject-requires-notes CHECK, and
    partial unique idx ux_poa_one_open_per_po (at most one open
    approval row per PO)
  * `fn_budget_line_recompute_commitments(uuid)` — canonical
    commitment-recompute SQL function
  * Trigger `trg_po_status_commitments` AFTER UPDATE OF status on
    purchase_orders → recomputes commitments on every linked line
  * Trigger `trg_pol_commitments_on_change` AFTER INSERT/UPDATE/DELETE
    on purchase_order_lines → handles line reassignment (OLD + NEW)
- **Model `PurchaseOrderApproval`** with PO_APPROVAL_RESOLUTIONS.
- **Services:**
  * `po_commitments.py` — over-budget gate (`evaluate_budget_overrun`),
    snapshot builder (`build_budget_snapshot`). Uses LIVE column names
    confirmed against `BudgetLine` model: current_budget,
    committed_value, actuals_to_date.
  * `po_approvals.py` — submit_po_with_budget_gate (3 branches:
    within-budget+!approval=auto-issue, within-budget+approval=
    auto-approved row, over-budget=pending_approval+row), approve_po,
    reject_po (notes required), unlock_po (approved→draft +
    notify prior approver), list_pending_approvals (with
    self-submitter hide). SELF-APPROVAL GUARD enforced — submitter
    cannot approve OR reject own PO (403 `po/self-approval-forbidden`).
- **Router:** 6 new endpoints under `/api/v1/`:
  * POST /purchase-orders/{id}/approve  → pos.approve
  * POST /purchase-orders/{id}/reject   → pos.approve
  * POST /purchase-orders/{id}/unlock   → pos.edit
  * GET  /purchase-orders/{id}/approvals → pos.view
  * GET  /projects/{id}/approvals/pending → pos.approve
  * GET  /approvals/pending → pos.approve
  * Also: existing POST /purchase-orders/{id}/submit replaced with
    budget-gated implementation. Total PO+approval routes mounted: 15.
- **Notifications:** Approval_Requested broadcast to all tenant
  approvers (except submitter) on over-budget submit;
  Approval_Decision to submitter on approve/reject; to prior approver
  on unlock.
- **Docs:** `docs/engineering-invariants.md` updated with the
  commitment contract (§R3) and self-approval guard rule.
- **Tests (25 total):**
  * `test_po_approvals_unit.py` — 8 unit tests verified PASSING
    in-container (budget gate math + snapshot aggregation + exception
    types).
  * `test_po_approvals_api.py` — 17 integration tests
    OPERATOR-VERIFICATION-PENDING (5 budget gate G3.1-G3.5,
    4 approve/reject/unlock G3.6-G3.9, 2 self-approval,
    5 commitment matrix, 1 pending list visibility).
- **Scope honoured:** Receipts → R4. Frontend → R5/R6. Approval-amount
  thresholds → future tracks (logged §15).
- **Commit:** TBD.

### 2026-05-20 — Chat 24 R2 ✓ Purchase Orders core (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING
- **Migrations:**
  * `0030_purchase_orders.py` — po_status enum (8 states), purchase_orders +
    purchase_order_lines tables, fn_po_recompute_header_totals trigger,
    is_fully_receipted Computed column, partial unique idx on
    (project_id, prefix_id, sequence) for forensic reconstruction.
  * `0031_po_permissions.py` — 12 pos.* permissions, role grants.
- **Models (`app/models/purchase_orders.py`):** PurchaseOrder + PurchaseOrderLine
  with Status constants exported for state machine + edit-tier guard.
- **Services:**
  * `po_numbering.py` — atomic next-sequence allocation with SELECT FOR
    UPDATE on the prefix row.
  * `po_authz.py` — DUAL responsibility per build pack §4.5:
    Pattern α tenant/project scoping AND edit-tier guard
    (EditPermission.FULL / HEADER_ANNOTATION_ONLY / READ_ONLY with
    check_can_edit_fields).
  * `po_transitions.py` — state machine: submit, issue, void, close.
    Approval (R3) and receipt (R4) transitions declared in
    ALLOWED_TRANSITIONS but not yet driven.
  * `purchase_orders.py` — CRUD + transitions; every CUD writes audit_log
    with field-level diff; pricing fields gated by `pos.view_sensitive`.
- **Router (`app/routers/purchase_orders.py`):** 9 endpoints under
  `/api/v1/`:
  GET/POST list+create, GET/PATCH/DELETE detail,
  POST submit/issue/void/close.
- **RBAC:** PERMISSION_CATALOGUE += 12 pos.* perms; role mappings for
  super_admin (all 12), director (all 12), finance (9 incl. approve/void/close),
  project_manager (6 incl. submit/void), site_manager (view + receipt).
- **Tests (47 total):**
  * `test_purchase_orders_unit.py` — 33 unit tests verified PASSING
    in-container (state-machine 16 + edit-tier matrix 17).
  * `test_purchase_orders_api.py` — 14 integration tests
    OPERATOR-VERIFICATION-PENDING (require live PG): 6 numbering +
    4 CRUD + 4 transitions.
- **Scope honoured:** Approval flow → R3. Receipt flow → R4.
  Bills entity, PO templates, multi-currency, approval thresholds → future
  tracks. No frontend changes (R5/R6 scope).
- **Commit:** `1012e18 Chat 24 R2: Purchase Orders core (Prompt 2.5)`.

### 2026-05-19 — Chat 24 R1 ✓ Suppliers + Project Number Prefixes (Prompt 2.5)
- Migration 0029_suppliers_prefixes, models `suppliers.py` +
  `number_prefixes.py`, services + routers, 9 tests, all under /api/v1/.
- Commit `357a939`.

### 2026-05-19 — Chat 24 R0 ✓ Pre-flight cleanup
- `LineItemsPanel.jsx` → `LineItemsBreakdown` swap in `LineDrawer.jsx`.
- Supervisor `[program:backend]` template re-applied for self-healing.
- Commit `9070a80`.

### 2026-05-19 — Chat 23 Build Pack A CLOSED ✓ (R1–R10 complete · 38/39 acceptance gates · 1 documented partial)
- **R9/R10 closure:** All R-sections shipped, full test suites green at close (backend **843**, Jest **250**), bundle main **395.1 kB** (cap 437 kB, headroom 41.9 kB), permissions=86, roles=10, alembic head `0028_user_preferences_table`.
- **G38 partial:** v1 `BudgetLinesGrid.jsx` + `SortableLineRow.jsx` deleted; `LineItemsPanel.jsx` survives because it's still mounted by `LineDrawer.jsx` for the items-tab focus contract. Refactor deferred to Future_Tasks §13 (P2).
- **G39:** `/app/docs/chat-summaries/chat-23-closing.md` written — full gate-by-gate accounting + deferral list.
- **Operational debt picked up:** missing `/root/.emergent/on-restart.sh` reinstalled with Step-8 re-seed extension (eliminated the recycle-data-loss class of issue). MFA role-level enforcement documented in `test_credentials.md`. R7 seed pollution workflow documented.
- **Deferred (out of Build Pack A):** Playwright E2E adaptation (Build Pack A-followup), mobile shell rework (Future_Tasks §12, P1), `LineItemsPanel.jsx` deletion (§13, P2), `/api` vs `/api/v1` audit closure (§11, P1).
- **Currently:** Build Pack A is mergeable on operator signal.

### 2026-05-19 — Chat 23 Build Pack A §R8 Mobile read-only card list ✓ (STOP gate #9 partial: functional ✓, shell-UX inadequate → Future_Tasks §12)
- **R8.1 `BudgetGridMobileReadOnly`** (full replacement of R3 stub): stacked header tiles (new `stacked` prop on `BudgetGridHeaderTiles`) + search input (only mobile filter) + card list rendering code + description + current budget + variance badge. Empty-state for zero matches.
- **R8.2 `MobileLineDetailDrawer`**: bottom-anchored `Sheet`, full-viewport. All line fields READ-ONLY (Original/Current/Approved changes/Actuals/Committed/FFC/FTC/Variance/Variance %), sensitive fields gated by `budgets.view_sensitive`. **Notes EDITABLE on mobile** (NotesCell reused with `canEdit = budgets.edit perm`). Per-line transaction drilldown reused (POs stub + Variations stub + Bills live).
- **Explicit NON-features pinned by tests:** NO bulk actions on mobile · NO toolbar (column-visibility/saved-views/presets absent) · NO drilldown row-expand in the list (transactions only inside the drawer).
- **Tests:** Jest 235 → **250** (+15: routing, structure, search, drawer flow, Notes editability gates, sensitive-field gating).
- **Bundle:** main unchanged 395.1 kB · budgets chunk 22.54 → **23.89 kB gz** (+1.35 kB). 41.9 kB headroom.
- **STOP gate #9 outcome:** functionally complete, but operator flagged the surrounding shell (sidebar dominates, no dismiss, content cramped) — logged as Future_Tasks §12, dedicated build pack sized after R10.

### 2026-05-19 — Chat 23 Build Pack A §R7.5 Path-prefix drift audit ✓
- **Fixed three silent-404 callers** that the §R7 spot-check exposed: `useCostCodes` (was `/v1/projects/.../cost-codes`), `useEntities` in `PromoteForm.jsx`, `useProjects` in `ProjectPicker.jsx`. All three correctly route to `/api/...` (no `/v1/`) — confirmed against backend mount table in `server.py:138-160`.
- **`buildCostCodeMap` keyed by `cost_code_id`** (not `id`) so the FK in `budget_lines.cost_code_id` matches the lookup. Backward-compatible fallback to `id` for minimal test fixtures.
- **CSV cost-code resolution** (regression caught by operator spot-check): `buildCsvText` takes `costCodeMap` and special-cases `cost_code` column (TanStack `accessorFn` form ≠ `accessorKey`, so the previous fall-through emitted blanks).
- **Regression pins:** URL contract per fixed hook (positive + hard negative on `/v1/`), buildCostCodeMap key contract, CSV cost-code FK→code resolution, on-screen cell rendering pin (`BudgetGridV2-CostCodeRender.test.jsx`).
- **Future_Tasks §11** logged with full audit survey (P1 — silent 404 with empty-fallback is highest-risk bug class).

### 2026-05-19 — Chat 23 Build Pack A §R7 Bulk delete + CSV export ✓ (STOP gate #8)
- **R7.1 — Row selection** already line-only (groups + items not selectable) per the R3 `enableRowSelection` predicate. Confirmed no group/item rows render the select checkbox.
- **R7.2 — `BulkActionsBar.jsx`** new file. Renders between header tiles and toolbar when ≥1 line selected. Shows count + Export CSV + Delete selected + Clear. Auto-hides Delete when `canEdit=false` OR `editable=false` (Locked/Closed/Superseded). Over-cap warning + disabled Delete when >100 selected.
- **R7.3 — Bulk delete fan-out.** New backend endpoint `DELETE /api/v1/budget-lines/{line_id}` (singular; NO bulk endpoint per locked decision). Frontend loops sequential `deleteBudgetLine(id)` calls capped at 100; **live progress bar** swaps in while running showing "Deleted X of N…" (and "(K failed)" suffix on errors). One audit row per delete (metadata.kind=`line_delete`). Cache invalidation fires ONCE at the end. Partial-failure toast distinguishes total-fail vs partial-fail vs success.
- **R7.3 confirm dialog** — controlled `BulkDeleteConfirmDialog.jsx` wrapping shadcn `AlertDialog` directly (existing `ConfirmDialog` is uncontrolled — wrong shape for imperative open). sy-orange destructive class preserved.
- **R7.4 — Inline RFC-4180 CSV** at `lib/csv.js`: exactly the 5-line `toCsv` from the Build Pack + a `downloadCsv(text, name)` helper using Blob + ephemeral object URL. **NO papaparse**. The export-button reads `table.getVisibleLeafColumns()` and drops `select`/`expand`/`actions` columns. Display columns (variance_to_forecast, forecast_profit, forecast_margin_pct) compute their numeric value inline so the CSV captures the signal instead of JSX.
- **Sensitive-field gating in CSV** verified by Jest: `forecast_profit` + `forecast_margin_pct` columns are not even created for users without `budgets.view_sensitive` (R3.2 contract), so they cannot land in the CSV even if a future bug forced them visible. Pinned by `BulkActionsBar.test.jsx::"non-sensitive user CSV excludes forecast_profit and forecast_margin_pct"`.
- **Backend tests:** 837 → **843** (+6: 204/404/403/409/audit/total-recompute).
- **Frontend tests:** 204 → **223** (+19: 10 RFC-4180 csv unit + 9 BulkActionsBar render/gating/fan-out).
- **Bundle:** main 395.07 → **395.09 kB gz** (+22 B); budgets chunk 20.95 → **22.54 kB gz** (+1.58 kB). Headroom against 437 kB cap: **41.91 kB**.
- **Currently at:** STOP gate #8 — awaiting operator review before R8 (mobile card list + Notes-editable).

### 2026-05-19 — Chat 23 Build Pack A §R6 Saved Views + autosave ✓ (STOP gate #7)
- **R6.1 hooks** (`hooks/userPreferences.js`) — 5 hooks against `/api/v1/me/preferences/{surface}`:
  - `useUserPreferences` — GET snapshot, no refetch-on-focus, `staleTime=Infinity` so initial column-resize drafts aren't clobbered.
  - `useSetCurrentPreference` — PUT autosave, NO cache write (C2 audit fix preserved; signature is `(_data, _variables)`, NOT `arguments[0]`).
  - `useCreateSavedView` — POST + prepend to cached views.
  - `useUpdateSavedView` — PUT + replace in cached views.
  - `useDeleteSavedView` — DELETE + filter from cached views.
- **R6.2 autosave** — 500ms debounced `useEffect` in `BudgetGridV2Desktop` that fires `setCurrentMut` on any change to `{columnVisibility, columnOrder, sorting, filters}`. Initial hydration gated by `hydratedRef` so it does NOT trigger autosave (load-storm guard).
- **R6.3 `SaveViewDialog`** — name validated 1-128 chars; 409 conflict → "Name already in use" toast (dialog stays open); success → success toast + dialog closes.
- **R6.4 `ManageViewsDialog`** — list + rename + delete. Rename = delete-then-create with rollback recreate on half-failure (recovery toast if recreate ALSO fails). Delete fires directly because the dialog is itself a confirmation surface.
- **R6.5 hydration** — first snapshot fetch applies `current.payload.{columnVisibility,columnOrder,sorting,filters}` if non-empty; otherwise keeps `INITIAL_COLUMN_VISIBILITY`. Re-runs gated by `hydratedRef.current` so a refetch never clobbers in-flight user edits.
- **`ViewPresetsDropdown`** extended: 4 starter presets (Profit hidden when `!canViewSensitive`) → divider → saved views (one item per `prefs.views[i].name`) → divider → "Save current view…" + "Manage saved views…" footer.
- **API client** new file `lib/api/userPreferences.js` — 6 typed wrappers (getSnapshot / putCurrent / create / update / delete).
- **Scoped deviations log** — new `docs/chat-summaries/chat-23-closing.md` tracking 3 documented deviations: R3.9b source field (gdv_total ↔ "sale_price"), R5.1 textarea↔input, R6.2 debounce 500ms confirmed as per-Build-Pack.
- **Tests:** Jest 196 → **204** (+8). Hook contracts 6 + grid R6 wiring 2.
- **Bundle:** main 395.07 kB (+22 B); budgets chunk 20.95 kB (+2.18 kB). Headroom 41.93 kB.
- **Currently at:** STOP gate #7 — awaiting operator review before R7 (Bulk delete + CSV export).

### 2026-05-19 — Chat 23 Build Pack A §R5 NotesCell upgrade ✓ (STOP gate #6)
- **`NotesCell.jsx` rewrite**: 600ms debounce; rapid typing coalesces to a single PATCH; **Enter** commits immediately, **Shift+Enter** = newline, **Escape** reverts + cancels pending debounce, **Blur** commits immediately; same-value no-op guard; empty string → `notes: null`; **maxLength=500** enforced via textarea attribute; soft counter appears at ≥450 chars.
- **Optimistic + rollback**: leverages existing `usePatchBudgetLine.onMutate/onError`; NotesCell additionally restores its own `committedRef` so the next entry into edit mode shows the pre-failed value. **`sonner.toast.error`** fires on network failure with the server message.
- **Grid wiring**: `BudgetGridColumns.makeColumns` no longer takes `onUpdateNotes` — it forwards `lineId + budgetId` so the cell owns its own mutation. `BudgetGridV2Desktop` dropped the wrapper closure + the redundant `usePatchBudgetLine` import.
- **Tests:** Jest 184 → **196** (+12 NotesCell cases pinning the entire R5 contract — keystroke debounce, Enter/Shift+Enter/Escape/Blur, null-on-empty, no-op guard, counter, maxLength attr, network-failure rollback + toast).
- **Bundle**: main 395.05 kB unchanged; budgets chunk 18.58 → 18.77 kB (+194 B). Cap 437. Headroom **41.76 kB**.
- **Mobile note**: NotesCell IS mobile-editable per Build Pack §R5; the current mobile stub doesn't yet surface it. Reusing this same NotesCell unchanged in the R8 mobile card list.
- **Currently at:** STOP gate #6 — awaiting operator review before R6 (Saved Views CRUD UI + autosave wiring against the R1.4 backend).

### 2026-05-19 — Chat 23 Build Pack A §R4 BudgetGridDrilldown ✓ (STOP gate #5)
- **R4.1 LineItemsBreakdown** (editable 4-type item editor; description/amount/notes inline + `+ Add item` + delete-with-confirmation using `bg-sy-orange` for the destructive confirm).
- **R4.2 / R4.3** PO + Variations empty-state stubs pointing to Prompts 2.5 / 2.6.
- **R4.4 BillsSection LIVE** (6-col table fed by `useActualsForBudgetLine`). Confirmed param name `budget_line_id` (NOT `line_id`) against `routers/actuals.py:65` before wiring. New `BillStatusBadge` with 5-state semantic colour map (Draft/Posted/Paid/Disputed/Void → slate/sky/emerald/rose/zinc).
- **R4.5 BudgetGridDrilldown** wrapper. Mounted via colspan row directly under each expanded line in `BudgetGridV2Desktop` (items no longer attached as flat TanStack sub-rows).
- **3 confirms answered (operator R4 questions)**:
  1. `appraisal.gdv_total` IS the aggregate development revenue (Σ unit.qty × price_per_unit per `app/services/appraisal_calc.py:144-148`). Not per-unit. ✓
  2. `LineDrawer.jsx` retained (482 lines, unchanged). Actions menu still routes non-Notes edits to it. ✓
  3. Test rename: `PM_EMAIL` → `NON_SENSITIVE_EMAIL = test-readonly@example.test`. PM has `view_sensitive`; only `test-readonly` does not. No production rename, just fixture targeting. ✓
- **Future_Tasks §10** logged: MFA-on-test-users runbook is operational debt (P2). Need a `--test-fixture` middleware bypass for `*@example.test` in non-prod envs.
- **Tests:** Jest 172 → **184** (+12: BillsSection 3, Drilldown stubs + BillStatusBadge 7, budgetCategoryGroup regression-guard updated). Backend unchanged (no backend changes in R4).
- **Bundle:** main 395.05 kB gz (+0.08 from R3), budgets chunk 18.58 kB gz (+1.61). Cap 437. Headroom 41.95 kB.
- **Currently at:** STOP gate #5 — awaiting operator review before R5 (Notes inline-edit upgrade: debounce + audit).

### 2026-05-19 — Chat 23 Build Pack A §R3 BudgetGridV2 ✓ (STOP gate #4)
- **R3.9b backend** (`app/routers/budgets.py`): `_attach_provisional_allocation(db, budget, include_sensitive)` computes per-line `appraisal.gdv_total / len(lines)` 2dp; emitted as `_allocated_sale_price_provisional` on every line ONLY when `budgets.view_sensitive`. Underscore-prefix = "computed, not stored". Source field = `gdv_total` (no literal `sale_price` column exists). 4 new tests passing.
- **R3.1 component tree** — 12 new files under `frontend/src/components/budgets/grid/`:
  - `BudgetGridV2.jsx` — top-level (mobile/desktop chooser).
  - `BudgetGridV2Desktop.jsx` — TanStack Table + filter→group→sort pipeline + drag-reorder (sort-gated).
  - `BudgetGridMobileReadOnly.jsx` — R8 stub (card list).
  - `BudgetGridToolbar.jsx` — 5 filters (search, categories, variance band, only-actuals, only-variance) + views menu + column toggle.
  - `BudgetGridHeaderTiles.jsx` — 5 totals (3 hide for non-sensitive).
  - `BudgetGridColumns.jsx` — 12 cols, 6 default-visible; Profit/Margin conditional on `view_sensitive`.
  - `VarianceCell.jsx`, `MoneyCell.jsx`, `NotesCell.jsx`.
  - `ViewPresetsDropdown.jsx` — Quick/Standard/Full/Profit (Profit hidden if not sensitive).
  - `ColumnVisibilityMenu.jsx`.
  - `SORT_KEY_MAP.js` — id→backend translation + `computedLineValue` for 3 synthetic columns. Dev-mode `console.warn` on miss.
- **R3.5 grouping** — new `lib/budgetCategoryGroup.js` with 9-prefix `CATEGORY_BY_PREFIX`.
- **R3.6 default expansion** — categories open on first render; items closed.
- **R3.4 heat-map** — emerald/amber/rose semantic colours; brand `sy-teal`/`sy-orange` NOT used for variance (operator brand-convention check ✓).
- **R3.8 sort + drag-reorder** — TanStack sort applied via `SORT_KEY_MAP`; drag-reorder kept from v1 and disabled when `sorting.length > 0`.
- **R3.9 gating** — `_allocated_sale_price_provisional` stripped from non-sensitive responses; Profit/Margin columns aren't even created for those users.
- **Inline edit** — Notes ONLY (Q7). All other field edits route through the kept-from-v1 `LineDrawer`.
- **Wiring** — `pages/projects/BudgetDetail.jsx` swaps `BudgetLinesGrid` → `BudgetGridV2`.
- **Bundle:** main 394.97 kB gz (+0.17 over R2), budgets chunk 16.97 kB gz (+4.68). Cap 437 kB. Headroom **42 kB** preserved.
- **Tests:**
  - Backend 833 → **837** (+4 R3.9b cases).
  - Frontend Jest 151 → **172** (+21: VarianceCell 5 / budgetCategoryGroup 7 / SORT_KEY_MAP 8 + the original 1).
- **Currently at:** STOP gate #4 — awaiting operator review before R4 (per-line drilldown: BillsSection live, POs/Variations stubs).

### 2026-05-19 — Chat 23 Build Pack A §R2 frontend code-split ✓ (STOP gate #3)
- **Pre-flight verified:**
  - Full backend pytest run: **833 passed / 0 failed / 0 errors / 122.86s** (post fresh bootstrap; the prior session's ~93 errors were stale-state artifacts from a broken prior bootstrap, not real regressions).
  - G33 permissions=86 ✓ (unchanged); G34 roles=10 ✓ (unchanged).
  - `git status` clean — no auto-URL changes to ride along.
- **R0.3 / R2.1** — `@tanstack/react-table@^8.20.0` already present in `frontend/package.json`. No install needed.
- **R2.2** — `frontend/src/App.js`: `BudgetsList` + `BudgetDetail` converted from eager imports to `React.lazy` with the shared `webpackChunkName: "budgets"` magic comment; route elements wrapped in `<React.Suspense fallback={…Loading…}>` mirroring the existing AICapture pattern. (commit `c8acbb4`)
- **Bundle deltas after R2.2:**
  - `main.js`: **424.17 → 394.80 kB gz** (-29.37 kB — 3× the G11 ≥10 kB target)
  - New chunks: `budgets.a76cfc20.chunk.js` 12.29 kB + `981.chunk.js` 18.20 kB
  - Headroom against the 437 kB cap: **42.20 kB** before §R3 ships Grid v2.
- **Jest:** 151/151 passing (33 suites, 23.8s) — no test changes needed.
- **Fix-ups landed alongside (commit `f0c14a0`):**
  - `test_bootstrap.py::test_alembic_heads_helper_returns_single_head` — sentinel `0027_` → `0028_` per the chat-15 §3 convention now that R1.4 advanced the head.
  - `test_migration_0025_actuals.py::test_alembic_head_is_0025_actuals` — same one-character-class head bump.
  - `test_budgets_default_items.py::test_new_version_copies_items_verbatim_no_autocreate` — explicit `db_session.rollback()` before raw-SQL cleanup so the LIFO-order fixture finaliser doesn't deadlock on the FOR-UPDATE lock the test acquired via `new_version`.

### 2026-05-18 — Chat 23 Build Pack A §R1 backend ✓ (STOP gate #2)
- **R1.1 — Variance band update (commit `98ac673`).** `VARIANCE_AMBER_PCT` 5→0; `VARIANCE_RED_PCT` 15→10. `_classify_variance` operator flipped to use `>=` for Red. 6 new fence-post tests in `test_budgets_variance_bands.py` (-5/0/0.001/9.999/10/25 → Green/Green/Amber/Amber/Red/Red).
- **R1.2 — Auto-create 4 default `budget_line_items` on every new `budget_line` (commit `d990bb3` initial + `ba25b65` fix).** `DEFAULT_LINE_ITEMS = ("Materials","Labour","Equipment","Subcontractor")` at `display_order` 0-3, `amount=0`. `_create_default_items` is idempotent (skips when line already has items). Wired into `create_line` (services/budget_lines.py) and `create_from_appraisal` (services/budgets.py). `new_version` intentionally does NOT call the helper — copies source items verbatim. 5 new tests in `test_budgets_default_items.py` covering constant, service-level create, idempotency, and new_version copy semantics.
- **R1.3 — Migration `0027_default_line_items_backfill` (commit `2725bf1`).** Idempotent backfill: SELECT zero-item lines via LEFT JOIN; INSERT 4 defaults at amount=0. Emits a single `Seed_Run` audit row with `metadata.kind='data_backfill'` + row/item counters. Downgrade removes items matching the exact 4-label + amount=0 + display_order 0-3 shape. 4 tests in `test_migration_0027_backfill.py`. Build Pack §R1.3 spec slug was `0027_budget_line_items_backfill`; operator confirmed canonical name stays `0027_default_line_items_backfill` (one-char-class drift, no rename).
- **R1.4 — `user_preferences` table + 6 endpoints (commit `09d3911`).** Migration `0028_user_preferences_table`: id/user_id/surface_key/name/payload JSONB/created_at/updated_at; FK users.id CASCADE; two partial unique indexes (`name IS NULL` slot = 1 current per user/surface; `name IS NOT NULL` slot = 1 named view per user/surface/name); `set_updated_at` trigger. Service `app/services/user_preferences.py` exposes get_current/set_current/list_views/get_view/create_view/update_view/delete_view with ConflictError/NotFoundError. Router `app/routers/user_preferences.py` mounts under `/api/v1/me/preferences/{surface_key}` with 6 endpoints: GET snapshot, PUT autosave (NOT audited), GET/POST/PUT/DELETE named views (audited Create/Update/Delete). 16 API tests + 3 migration smoke tests = 19 new passing.
- **Test counts after R1 (sample):**
  - `test_budgets.py` 76/76 passing
  - `test_budgets_default_items.py` 5/5
  - `test_budgets_variance_bands.py` 6/6
  - `test_migration_0027_backfill.py` 4/4
  - `test_migration_0028_user_preferences.py` 3/3
  - `test_user_preferences_api.py` 16/16
- **Alembic head:** `0028_user_preferences_table`.
- **Currently at:** Build Pack STOP gate #2 — awaiting operator review before R2 (frontend code-split + TanStack Table install + Grid v2 build).

### 2026-05-18 — Chat 22 CI pipeline hardening ✓ CLOSED
- **Anchor (Future_Tasks §3, open since Chat 14):** GitHub Actions CI pipeline (`.github/workflows/ci.yml`) iteratively hardened across 5 red runs to reach a 799/799 green state without depending on `backend/.env` or sandbox-specific absolute paths.
- **Shipped fixes (cumulative):**
  - `backend/requirements-ci.txt` excludes the private `emergentintegrations` package.
  - `frontend/yarn.lock` regenerated + explicitly staged.
  - 7 pre-existing test-drift assertions patched across 5 test files.
  - CI env: `DATABASE_URL` → `postgresql+psycopg://` (psycopg3 driver), `CORS_ORIGINS`, `MFA_ENCRYPTION_KEY` inline (CI-only Fernet key).
  - CI postgres service: `POSTGRES_INITDB_ARGS=--lc-collate=C.UTF-8 --lc-ctype=C.UTF-8 --encoding=UTF8` (Pattern A — pins CI sort order to match sandbox + Python codepoint oracle).
  - `tests/test_bootstrap.py` + `tests/test_migration_0025_actuals.py`: replaced `/app/backend` hardcodes with `str(Path(__file__).resolve().parents[1])` (Pattern B).
- **Final validation:** Full backend suite (`python -m pytest --ignore=tests/test_c3_governance_smoke.py`) runs **799 passed / 0 failed** (108.72s) under `env -i` with the exact 14-var ci.yml block and no `backend/.env`. The handoff's "3 failing tests" report was a misdiagnosis (non-policy-compliant password in prior agent's local replica). See `CHANGELOG.md` Follow-up 5.
- **Backlog (P3, deferred to Future_Tasks polish):**
  - Refactor 19 cosmetic `load_dotenv("/app/backend/.env")` hardcodes across test suite.
  - Decide explicit `COLLATE` for entity `ORDER BY name` for production deployment.
  - Rename 5 test functions still carrying stale literal numbers from drift patches.

### 2026-02-17 — Prompt 2.5C AI Capture Review Surface ✓
- **Frontend + minimal backend chat.** Surface shipped: AI Capture inbox
  list page (`/ai-capture`) + capture-job detail page (`/ai-capture/:jobId`)
  with side-by-side attachment preview / extracted-fields / promote form.
  PromoteForm re-uses 19B's `BudgetLinePicker` (D37); navigates to the
  created Draft actual on success (D44). One new backend endpoint:
  `GET /api/v1/ai-capture-jobs/:id/attachment` (file bytes, auth-gated).
- **B36 outcome: NOT REPRODUCIBLE AT HEAD.** Zero LOC backend change.
  Hypothesised silent fix in chat-19B's `freshActual` factory rework.
  Regression test `tests/test_actuals_attachments.py::TestB36AttachmentRead
  AfterWrite` pins the read-after-write contract; chat-19B's skipped E2E
  delete case un-skipped (E14). See `chat-19c-closing.md` §"B36 RCA".
- **Bundle headroom remaining post-build: 13.01 kB** (423.99 kB vs +17
  hard-cap of 437.00 kB). Jest 88 → **118**; pytest 782 → **790**;
  smoke unchanged 11/11. 6 new Playwright spec files (operator-run).
- Reference: `docs/chat-summaries/chat-19c-closing.md`. 5 implementation
  deviations (E11–E15) captured. 6 new backlog items B37–B42 appended
  verbatim from Build Pack to Phase 2 backlog.

### 2026-02-15 — Prompt 2.5B Actuals Frontend + Payment View + E2E ✓
- **Frontend + E2E chat** following 19A backend. Bundle 387.10 kB →
  **419.72 kB** (+32.62 kB gz, target ≤+35 / hard cap +50).
- **Surfaces shipped:** ActualsList (per-project table + filters + create
  Sheet), ActualNew (mobile create route), ActualDetail (header / state
  actions / attachments / collapsible history), PaymentsView (Louise's
  global cross-project list with bulk Mark-Paid), AttachmentUploader
  (`react-dropzone@^14` + React synthetic onPaste for clipboard).
- **15 actuals endpoints wired** via `lib/api/actuals.js`; Zod schemas in
  `lib/schemas/actuals.js`; React Query hooks in `hooks/actuals.js`;
  capability helpers in `lib/actualCapability.js`.
- **State machine UI** matches the live router. `canPostDraft` correctly
  uses `actuals.edit` (verified — router docstring's "actuals.post" label
  is documentation-only). All non-trivial actions open a Radix Dialog
  with reason capture; field state resets on action change.
- **BulkPayDialog (Louise)** uses D30 N-call loop with snapshot pattern,
  shared `paid_date`, per-row auto-generated `BACS-YYYYMMDD-{id6}` refs
  (editable), per-row pending/success/error pills, full
  `actualsKeys.all`+`['budgets']` cache invalidation on completion.
- **Sensitive-field gating (D26):** Zod schemas declare sensitive fields as
  `.nullable().optional()`; backend strips at serialiser layer; UI renders
  "—" for `null|undefined` via `fmtGBP`. `ActualHistory` payload tile is
  client-gated on `actuals.view_sensitive`.
- **Pre-prompt backend patch (D32 + D33):** `ActualsListFilters.status`
  now accepts comma-separated values; ValidationError wrapped to 422 in
  both routes. **pytest 780 → 782 passed.**
- **Test deltas:** Jest 47 → **88** (+41 across 7 spec files); Playwright
  32 → **66** (+34 across 9 spec files); smoke 6 → **11**. Coverage:
  `actualCapability.js` 95.16% / `lib/schemas/actuals.js` 100%.
- **Routes are FLAT siblings in App.js** (not nested under ProjectDetail).
  `/payments` is top-level; project routes are `/projects/:id/actuals[/new|/:actualId]`.
- **8 new backlog items (B28–B35)** appended to Phase 2 backlog. Headline:
  B28 — AI capture review surface for Chat 19C.
- Reference: `docs/chat-summaries/chat-19b-closing.md`. **10 implementation
  deviations (E1–E10)** captured. Notably E8 fixed a shipped-code bug in
  `CreateActualSheet` (missing `project_id` in form defaults caused Zod to
  silently reject every submit); E7 patched the `freshActual.ts` factory to
  dynamically resolve the current Active/Locked budget.

### 2026-02-15 — Prompt 2.5A Actuals Backend ✓
- **Backend only — bundle delta 0.** Migration `0025_actuals` applied; 21 new
  endpoints across 3 routers (`actuals`, `inbound`, `ai_capture`); AI capture
  pipeline (Postmark inbound + APScheduler dispatcher + Anthropic stub/live).
- 5 new services: `actuals`, `actual_attachments`, `ai_capture`,
  `postmark_webhook`, `budgets_reconciliation`. 11 domain exceptions in
  `actual_errors`.
- 5 new tables: `actuals` (51 cols), `actual_attachments`,
  `inbound_email_messages`, `ai_capture_jobs`, `actuals_change_log`. 13 plain
  + 2 partial-unique indexes; 6 user triggers; 3 functions. Round-trip
  downgrade/upgrade verified.
- 9 new `audit_action` enum values (`Post`, `Mark_Paid`, `Void`, `Dispute`,
  `Undispute`, `Release_Retention`, `Add_Attachment`, `Remove_Attachment`,
  `Promote_From_Capture`).
- RBAC: `actuals.admin` (sensitive) added. Catalogue exposes 6 actuals perms
  (view/view_sensitive/create/edit/approve/admin). Finance role inherits admin;
  PM gets view/create/edit only.
- 107 new tests across 5 files. **Total backend: 780 passed / 0 failed / 0
  errors.** Baseline gate Jest 47 / pytest 673 / bundle 387.10 kB → after Jest
  47 / **pytest 780** / bundle 387.10 kB (Δ 0).
- Reference: `docs/chat-summaries/chat-19a-closing.md`. 5 implementation
  deviations (E1–E5) captured in chat summary and CHANGELOG. E5 patched
  in-scope (B27 — post-time budget-terminal re-check) per operator request.
  ⚠️ E4 sandbox env change: `POSTMARK_INBOUND_ENABLED=true` for tests;
  production MUST override to `false` until B23 cutover.

### 2026-05-14 — Prompt 2.4B-ii Playwright E2E ✓
- **Test infrastructure only** — zero changes under `backend/app/` or `frontend/src/`.
- Playwright `@playwright/test@1.60.0` + `otplib@12.0.1` (devDependencies).
- 32 physical Playwright tests in 12 spec files across 8 groups (31 active + 1 quarantined LineDrawer #6 per Build Pack v4 §15 known risk + operator policy 3a).
- Smoke subset (`yarn e2e:smoke`): **6/6 passing in 19.3s**.
- `frontend/playwright.config.ts` — single worker, headless, 5 named projects (chromium-pm/admin/readonly/site/anon) with per-role `storageState`.
- `frontend/e2e/global-setup.ts` re-seeds users + extended demo data, primes `storageState` files. `frontend/e2e/global-teardown.ts` exclusion-list sweep.
- 6 helpers in `frontend/e2e/helpers/`: `login.ts`, `seed.ts`, `asserts.ts`, `api.ts`, `factory.ts`, `freshBudget.ts`. No POM per locked decision #9.
- `scripts/seed_demo_budget.sh` extended with `E2E_PROJECT_ID` env override + 3 flags (`--with-v2-lineage`, `--empty-project`, `--extra-appraisal`). All idempotent.
- Baseline gate BEFORE + AFTER: Jest 47 ✓, pytest 673 ✓, bundle 387.09→387.10 kB (delta 0).
- D13 (new): `AppraisalCostLine` schema drift — Build Pack v4 §R2.2b listed 5 phantom columns; corrected to live 10-column schema. Annotation: `docs/chat-summaries/chat-18-build-pack-annotations.md`.
- D14: LineDrawer #6 quarantined (`test.skip`) — covered by Chat 17 Jest unit test.
- Reference: `docs/chat-summaries/chat-18-closing.md`.

### 2026-05-12 — Prompt 2.4B-i §R8 component tests ✓
- 10 test suites, 46 tests, 0 failures, ~3.4s runtime (`yarn test --watchAll=false`).
- Coverage: lib/ 96%, schemas 86%, BudgetsList 92%; component coverage
  46% (5 of 14 components 0% — relied on smoke-tested e2e paths).
- Files: `__tests__/budgetCapability.test.js` (8 tests),
  `__tests__/budgets-schemas.test.js` (5), `BudgetLinesGrid.pure.test.js`
  (5), `VarianceBadge.test.jsx` (6), `StatusBadge.test.jsx` (1),
  `SensitiveBanner.test.jsx` (2), `BudgetLineage.test.jsx` (4),
  `LifecycleActions.test.jsx` (5), `BudgetsList.test.jsx` (4),
  `LineDrawer.test.jsx` (5).
- Test infra: `setupTests.js` + `test/mockMatchMedia.js`
  + `test/renderWithProviders.jsx` + `test/mocks/fixtures.js`
  + `__mocks__/react-router-dom.js` + `jest.resolver.cjs`
  + craco.config.js jest section.
- Required tests all present: `buildReorderedIds` pure-fn (H8),
  lineage breadcrumb (E10), E9 conflict-banner, status×perm matrix,
  sensitive-stripped schema parse, mobile-floor gates, dirtyFields-only
  PATCH body.
- §R6.3 H8 follow-up: extracted `buildReorderedIds` to
  `lib/buildReorderedIds.js` so the pure-fn test doesn't drag dnd-kit /
  zod / shadcn into its require graph.
- §R7 follow-up: corrected FTC method enum values
  (`BudgetRemaining` → `Budget_Remaining` etc.) after schema test
  caught the divergence from backend.

### 2026-05-12 — Prompt 2.4B-i §R7 LineDrawer + LineItemsPanel + CostCodePicker ✓
- `components/budgets/LineDrawer.jsx` — full rhf + Zod form (line_description,
  notes, ftc_method, forecast_to_complete, percentage_complete, cost_code_id);
  dirtyFields-only PATCH body; defensive cost_code_id only sent when status
  permits; sensitive-field gates (notes + FTC fields hidden unless
  `budgets.view_sensitive`); E9 conflict-detect via `updated_at` watermark
  (loadedAt + justSavedRef) with non-blocking "Reload" amber banner;
  close-with-dirty AlertDialog confirm with sy-orange Discard; Cmd/Ctrl+S
  save + Esc close keyboard shortcuts (operator addition).
- `components/budgets/LineItemsPanel.jsx` — inline-CRUD on items table
  (description / qty / unit / rate, computed amount column); add-row
  builder beneath table; per-row Delete via existing ConfirmDialog
  (sy-orange destructive variant); mobile read-only floor. Field rename
  `unit_cost` → `rate` documented as **errata E11**.
- `components/budgets/CostCodePicker.jsx` — shadcn Select wrapping
  `useCostCodes(projectId)`; filters to `enabled` codes but always keeps
  currently-selected even if disabled; loading + missing-label fallback.
- Build: `main.js` 387.08 kB (+4 kB; rhf was already in the bundle).
- Smoke (test-pm on Draft v1): drawer opens, all 6 form fields render,
  dirty tracking flips on type, Cmd+S triggers PATCH + "Line saved"
  toast + dirty resets, Esc with dirty shows discard dialog (Keep
  editing / Discard sy-orange), discard closes drawer, items panel
  shows existing rows + add flow appends new row with computed £500.00.

### 2026-05-11 — Prompt 2.4B-i §R6 Budget Lines Grid ✓
- `components/budgets/SortableLineRow.jsx` — dnd-kit sortable row with
  setActivatorNodeRef-wired drag handle (C8/C9 a11y), inline edit on
  `line_description` and `percentage_complete` (E7 names), optimistic
  update + rollback via `usePatchBudgetLine` (extended in `hooks/budgets.js`),
  client-side cost-code label join (D13/E7), sensitive-field renders via
  `formatMoney(undefined) → "—"`.
- `components/budgets/BudgetLinesGrid.jsx` — DndContext + KeyboardSensor
  for keyboard a11y, `useReorderBudgetLines` with cache-rollback,
  memoised lines/itemIds, mobile read-only banner, reorder-error toast,
  exports pure `buildReorderedIds()` for §R8 unit test.
- `components/budgets/LineDrawer.jsx` — shadcn Sheet placeholder for §R7
  (line JSON dump + "coming next" checklist).
- `lib/budgetCapability.js` — added `isBudgetEditable`, `isLineCreatable`,
  `isCostCodeMutable` status-only helpers.
- Wired into `BudgetDetail.jsx` (replaced §R6 placeholder).
- Build: `main.js` 382.72 kB (+20 kB).
- Smoke (test-pm on v3 Draft): 3 rows render with drag handles, inline
  edit description + %-complete saved and re-rendered, drawer placeholder
  opens via row overflow menu.

### 2026-05-11 — Sandbox provisioning + lineage breadcrumb follow-up
- Recovery: pod-rebuild wiped Postgres install + `postgres` system user
  mid-session. Reinstalled PG16, restored role/DB, re-seeded demo project
  + v1+v2 budgets. Documented as Track 8 / pre-launch hardening item in
  `/app/docs/SY_Hub_Phase2_Backlog.md` (Sandbox / pod-runtime stability).
- New: `components/budgets/BudgetLineage.jsx` — slate-500 inline prev/next
  links computed client-side from cached `useProjectBudgets`. Errata E10
  added to Build Pack (backend has no lineage pointer).
- Verified: v1 (Superseded) → "Next version (v2) →", v2 (Draft, current)
  → "← Previous version (v1)". Cross-navigation confirmed.

### 2026-05-10 — Prompt 2.4B-i Budgets Frontend §R0–§R5 ✓
- §R0–R3: stack installed (TanStack Query v5 + Table v8 + dnd-kit + MSW),
  routes wired, Zod schemas + API clients + 14 React-Query hooks against
  the flat backend paths. Erratas E1–E9 (Jest/CRA, flat paths, baseURL,
  hooks D12/D13, perm rename, schema rename, sensitive optional, refetch-
  on-save conflict UX) baked in.
- §R4: BudgetsList (TanStack Table v8) with status + variance badges,
  CreateFromAppraisal dialog (lazy fetch, exclude existing source
  appraisals), refresh-attention button. `budgets.view` perm gate.
- §R5: BudgetHeader (5 tiles + variance row), LifecycleActions
  (Activate / Lock / Unlock / Close / New Version) gated by status +
  backend-verified perms (`budgets.edit`, `budgets.admin`) and
  `useIsDesktop()`, SensitiveBanner for users without
  `budgets.view_sensitive`, ConfirmDialog with reason capture +
  brand-fixed sy-teal/sy-orange.
- New: `lib/budgetCapability.js`, `components/budgets/{StatusBadge,
  VarianceBadge, BudgetsTable, CreateFromAppraisalDialog, ConfirmDialog,
  SensitiveBanner, BudgetHeader, LifecycleActions}.jsx`.
- Build smoke OK: `main.js` 362.82 kB. Lint clean. Verified end-to-end:
  Draft → Active transition via `POST /api/v1/budgets/:id/activate`.
- **NEXT (next session):** §R6 BudgetLinesGrid (dnd-kit + inline edit),
  §R7 LineDrawer + LineItemsPanel + CostCodePicker (refetch-on-save +
  `updated_at` banner per E9), §R8 component tests (Jest/CRA), §R9/R10.

### 2026-05-09 — Prompt 2.4A Budgets Core (Backend) ✓
- Migration 0024_budgets (3 tables, 3 enums, 7 indexes incl. 2 partial unique).
- ORM models, services (`budgets`, `budget_lines`, `budget_errors`).
- 14 REST endpoints under `/api/v1`.
- New permission `budgets.admin`; PM gains `budgets.create`. Total perms 84.
- 44 new tests; full suite 641/641 passing (was 597 baseline).
- See `/app/CHANGELOG.md` §2.4A and `/app/docs/SY_Hub_Phase2_Backlog.md`.

### Earlier (carried in from previous chats)
- 1.x: tenants, entities, users, RBAC, sessions, audit log, MFA, system_config.
- 2.1: SDLT bands, appraisal default settings (reference data).
- 2.2: Appraisals Core (header, units, cost lines, finance facilities,
  RLV solver, 8-step recompute pipeline, state machine, view_financials gating).
- 2.3 retrofit: Submitted/Approved/Rejected/Reopened toggles + scenarios.
- pre-2.4 cleanup: 0023 cascade fix on `appraisal_scenarios`.

## P0 / P1 / P2 backlog (next prompts)

### P0 — current prompt (Chat 17, Prompt 2.4B-i Frontend) — **CLOSED**
- R0–R10 ✓ shipped. See `docs/chat-summaries/chat-17-closing.md`.

### P0 — next prompt (Chat 18)
- **BudgetLinesGrid v2 (BT-style)** — dedicated Build Pack, full audit
  cycle. Replace flat R6 grid with cost-code grouping, 11+ columns,
  heat-mapped variance, sticky column, bulk-select, filtering. See
  `docs/SY_Hub_Phase2_Backlog.md` HIGH-PRIORITY section.
- **Track 8 P0** — wire `provision_postgres.sh` into `on-restart.sh`
  step 0 (retires the recurring operator interruption pattern observed
  6× in Chat 17). 1-2h fix.

### P0 — Chat 19
- Budgets E2E (Playwright) — pushed from Chat 18 to make room for v2.

### P0 — successor prompt (Chat 18, Prompt 2.4B-ii)
- Budgets E2E (Playwright).

### P1 — Phase 2 backlog (12 items, see SY_Hub_Phase2_Backlog.md)
1. AppraisalUnit aggregation in `create_from_appraisal` (post-Prompt 3.x)
2. Per-line `entity_id` sourcing (multi-entity projects)
3. Actuals service (Prompt 2.5)
4. Commitments service (Prompt 2.5)
5. Budget changes / approval flow (Prompt 2.6)
6. Cash-flow `budget_line_periods` (separate prompt)
7. `linked_programme_task_id` FK to `programme_tasks` (Prompt 3.2)
8. Xero hooks (Track 6)
9. `requires_attention` scheduler infra + clauses 2/3
10. `SystemConfig` variance-threshold columns
11. Idempotency keys on `/from-appraisal`, `/new-version`
12. SOX-style author-cannot-activate review (MD/Louise call)

### P0 — Batch 2 (Chat 26, next prompt)
- **R7.4 — Receipt form.** New routes `/projects/:id/purchase-orders/:po_id/receipts/new` and `/.../receipts/:receipt_id/edit`. Will re-mount `po-actions-receipt-btn` and `po-actions-receipt-partial-btn` in `<POActionButtons/>` (currently hidden; regression test in `POActionButtons.test.jsx` will flip).
- **R7.5 — Approvals dashboard.** Global landing page for all PO approvals awaiting current user. Pulls from `/api/v1/purchase-orders?status=pending_approval&assigned_to=me` (or equivalent — confirm endpoint shape during R7.5 preflight).
- **R7.6 — Confirm-dialog system + optimistic mutations.**
  - Generic `<ConfirmDialog/>` (reason textarea + confirm/cancel). Re-mounts:
    - **Void** button (`po-actions-void-btn`, `po-actions-void-issued-btn`) — backend `POVoidBody.reason` is `Field(..., min_length=1)` so dialog must collect a non-empty reason before firing.
    - Optionally: surface the existing Send-back / Reject dialogs through the same primitive.
  - Optimistic cache updates: turn the current "mutate → invalidate → refetch → render" three-hop into a single render flip with rollback-on-error. Same change un-breaks the "click Approve → page lag → click Approve again → double-mutation" trap.
  - Budget-line cache invalidation on commitment-changing verbs (send-back joins approve/issue/void in that set).
- **PO Edit / Delete forms (draft state, edit_tier=full).** New routes
  `/projects/:id/purchase-orders/:po_id/edit` and `/.../delete`. Will re-mount
  `po-actions-edit-btn` + `po-actions-delete-btn`. **Edit-issued** form
  (`/edit` reused with status=`issued`) re-mounts `po-actions-edit-issued-btn`.
  Whichever batch ships first, the `DEFERRED_TESTIDS` regression guard in
  `POActionButtons.test.jsx` should be trimmed at the same commit so the
  newly-wired button doesn't fail the matrix.

### P2 — debt / future-proofing
- **Batch 2 / R7.6 polish — `useProjectBudgets` UUID guard.** Add a
  one-line client-side guard before firing GET `/v1/projects/:id/budgets`
  so a bad-URL `:projectId` (e.g. `undefined`, `null`, copy-paste
  fragment) renders the empty-state instead of 422-toasting the user:
  `enabled: canView && /^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/.test(projectId)`.
  Same pattern likely useful on the sister hooks (`useBudget`,
  `useProjectActuals`, `useProjectPOs`). Diagnosed during the Batch 1
  gate eyeball; root cause was an empty seed DB + a non-UUID URL
  hitting Pydantic's `uuid_parsing` path validator. Not a code bug;
  filed as P2 hardening only.
- `Project.tenant_id` column (will retire the `hasattr` no-op in services).
- Remaining `ON DELETE RESTRICT` FKs on `appraisal_scenarios`.

## Architecture notes
```
/app/backend/
├── alembic/versions/      # migrations (head: 0024_budgets)
├── app/
│   ├── auth/              # JWT + RBAC + permissions
│   ├── jobs/              # APScheduler-managed background jobs
│   ├── models/            # SQLAlchemy ORM
│   ├── routers/           # FastAPI routers (mounted via server.py)
│   ├── schemas/           # Pydantic request shapes (extra="forbid")
│   ├── services/          # business logic
│   ├── bootstrap.py       # `python -m app.bootstrap` (idempotent pod-start)
│   └── seed_*.py          # reference-data seeds
├── tests/                 # pytest suite (641 tests passing)
├── scripts/seed_test_users.py
└── server.py              # FastAPI app entry (NB: not main.py)
```

## How to run locally
```bash
sudo supervisorctl status               # mongodb, postgres, frontend already up
cd /app/backend && python -m app.bootstrap   # idempotent; bootstraps DB + seeds
sudo supervisorctl start backend
cd /app/backend && pytest tests/ --ignore=tests/test_c3_governance_smoke.py
```
