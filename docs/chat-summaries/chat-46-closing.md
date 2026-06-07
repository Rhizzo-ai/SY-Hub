# Chat 46 — Build Pack 2.7-DOCS-FE — Closing Summary

**Pack:** Build Pack 2.7-DOCS-FE · Document Folder Tree UI (Frontend) · B79 Part 2 of 2
**Scope:** Frontend only. **Closes B79** (paired with Chat 45's B79-BE).
**Status:** Committed; ready for operator to Save to GitHub + live eyeball test.

## What shipped

The two-pane document folder browser. Replaces the flat
`<DocumentsTab/>` table with a tree on the left + file list on the
right. Folders nest to any depth; docs move between folders by
drag-and-drop AND by a "Move to…" button (button = canonical
testable path; drag = polish). All upload / replace / download
behaviour is reused verbatim from a new `documentFileShared` module
extracted from the old DocumentsTab — zero duplication, zero
regression of B76/B78.

Pinned operator decisions honoured verbatim:
- **F1 desktop-target.** Two-pane on ≥768px; on narrow screens a
  graceful single-column fallback + "best on desktop" notice. NOT a
  mobile UX — mobile is a separate future build with its own review.
- **F2 move paths.** Drag is primary polish, button is canonical.
- **F3 reuse file primitives** (FilePicker / DropZone / DocumentFileCell
  / preCheckFile / ACCEPT_ATTR / error mappers) verbatim.
- **F4 optional fields.** `doc_type` + `title` both optional (Chat 45
  D4/D5). The dialog keeps both inputs; both default-empty; the
  title placeholder explains it auto-fills from the filename.

## Gate evidence (printed)

- **Gate 1.** Shared module `documentFileShared.jsx` extracted; the
  retiring `DocumentsTab.jsx` re-imports from it and **its existing
  46-test suite ran green unchanged** (refactor-safety proven). New
  `documentFileShared.test.jsx` ports the relevant coverage — **37
  tests** passing.
- **Gate 2.** New `lib/api/documentFolders.js` + `hooks/documentFolders.js`
  + new `moveDocument` / `useMoveDocument` in the supplier-docs
  module. New `lib/api/__tests__/documentFolders.test.js` —
  **16 wire-level tests** (URL + body + params) passing.
  `lib/poCapability.js` gains `canCreateFolder` / `canEditFolder` /
  `canMoveDocs`.
- **Gate 3.** `DocumentFolderView.jsx` + `FolderNode.jsx` +
  `FolderPicker.jsx` built. The drag handlers are wired AND the
  button path is fully tested. New `DocumentFolderView.test.jsx` —
  **21 tests** (R6 #1-#21) passing.
- **Gate 4.** `SupplierDetail.jsx` swapped to `<DocumentFolderView/>`;
  the page test's mock retargeted. **`DocumentsTab.jsx` + its test
  deleted** AFTER coverage proven ported. Grep confirms zero
  remaining `DocumentsTab` runtime imports.

**Final 2nd-run FE suite:** 83 suites passed, **667 tests passed**,
0 failures, 0 errors. Baseline (Chat 44 close): 81 / 639.
Net: **+2 suites, +28 tests** (+74 from 3 new files − 46 from the
deleted DocumentsTab suite). Direction up, accounting balances.

**Backend invariants intact:** zero `backend/` touches, alembic head
stays `0043_document_folders`, permissions stay 133, roles stay 10.
`docs/SY_Hub_Phase2_Backlog.md` not touched.

## Design notes

- **Component structure.** The view splits across
  `DocumentFolderView` (top-level state + composition), `FolderNode`
  (recursive tree + per-node action menu), `FolderPicker` (flat
  indented radio list for the move dialogs), plus three Dialog
  subcomponents and a small set of presentational helpers
  (`NarrowNotice`, `Header`, `TreePane`, `FilesPane`,
  `FilesPaneHeader`, `BreadcrumbTrail`, `FilesTable`, `FileRow`,
  `FileRowActions`, `DocFormFields`, `DocAttachField`). Each file
  stays well under 700 lines and each component is dumb (state lives
  in the view) — easy to scan, easy to test in isolation.
- **State design.** A pure `useMemo` overlay computes effective
  expanded folders from `overrides ∪ (every root open by default)`
  — no `useEffect`-set-state, no re-entrant render path when the
  tree query refetches.
- **Drag invariants.** `dataTransfer` payload carries
  `application/x-sy-doc-id`; the in-memory `dragDocId` is a fallback
  for jsdom. Drop targets glow only when (a) the user can move
  AND (b) the folder is not archived.
- **Direct contents only.** The right pane shows
  `docs.filter(d => d.folder_id === selectedFolderId)` — NOT
  recursive. Matches the backend's `file_count` which is a DIRECT
  per-folder count. Keeping the badge and the visible list on the
  same definition prevents them from disagreeing.
- **Error mapping** centralised in a `mapMoveError` helper so every
  folder/doc mutation surfaces a 422 server detail verbatim (loop
  guard, not-empty, duplicate name), a 403 as "You don't have
  permission to do that.", and a 404 as "That item no longer exists."

## Deviations flagged for review (none silent)

1. **`craco.config.js` `isDevServer` excludes `NODE_ENV=test`.**
   The `@emergentbase/visual-edits/craco` plugin was being loaded
   under `craco test`, which broke babel-traverse on
   `<FolderNode/>`'s self-recursive render with a stack-overflow.
   That plugin is semantically dev-only — loading it under Jest
   was a misconfiguration irrespective of this pack. One-line
   guard added; `start`/`develop` paths untouched.
2. **Component split into 3 sibling files** (`DocumentFolderView.jsx`
   + `FolderNode.jsx` + `FolderPicker.jsx`). The Build Pack §R4.1
   describes a single component; the split is a structural
   refinement to keep per-file complexity down AND to dodge the
   babel-stack issue above. Semantics unchanged: parent owns state,
   children are dumb.
3. **`docs/chat-summaries/chat-46-closing.md` is written by Emergent**,
   per the §R8 instruction. Flagged for visibility.

## Live eyeball test items (operator)

Green tests don't prove drag UX or live integration (Chat 44 lesson).
After Save to GitHub:
1. Create a new root folder.
2. Create a subfolder inside it from the per-node "+".
3. Drag a doc from the files list onto the subfolder — confirm it
   moves (file_count updates, doc disappears from the source pane).
4. Use the "Move to…" button on a doc — pick Unfiled — confirm the
   doc moves to the All view's Unfiled.
5. Upload a file into the currently-selected folder via the row
   Upload control AND via the Add document dialog's attach area.
6. Rename a folder.
7. Try to archive a non-empty folder — confirm the 422 detail
   "folder is not empty: move or archive its contents first" toasts.
8. Move a folder to itself / a descendant — confirm the 422 detail
   "cannot move a folder into itself or one of its descendants"
   toasts.
9. Confirm narrow-viewport notice appears at <768px width and the
   layout stacks gracefully.

## Files landed

See `CHANGELOG.md` §Chat-46 for the canonical list. 9 new files,
6 modified, 2 deleted (all confined to `frontend/`).
