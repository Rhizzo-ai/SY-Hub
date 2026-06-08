# Chat 47 — Build Pack 2.8-FE-i — Closing Summary

**Pack:** Build Pack 2.8-FE-i · Subcontracts surface (Frontend, scope-fenced) · First of the subcontract/commercial screens
**Scope:** Frontend only. Subcontracts lifecycle (Draft → Active → Completed/Terminated) inside the existing supplier **Contracts** tab. NO valuations, payment notices, retention, or variations — those are 2.8-FE-ii / 2.8-FE-iii.
**Status:** Committed; full FE suite green 2nd-run; ready for operator to Save to GitHub + live eyeball test.

## What shipped

The supplier Contracts tab — previously a `"Subcontracts arrive in 2.8-FE"` placeholder — is now a full inline master-detail surface:

- **List (left).** Reference, title, status pill, current/original contract sum (sensitive-gated). Status filter on top. Rows for other suppliers are never shown (client-side scope fence on `subcontractor_id`).
- **Detail (right).** Reference, title, status pill, original + current contract sum (sensitive-gated), retention, CIS-applies, start/end, signed-at, project + linked PO ids, scope description, lifecycle action buttons.
- **Create.** New-subcontract button (perm-gated) opens a dialog. Required: project + title. Optional: scope, PO link, contract sum, retention %, CIS-applies (default on), start/end dates. NO `reference` (backend generates SC-NNNN) and NO `status` (defaults to Draft).
- **Edit.** Same dialog, mode="edit". Project + subcontractor immutable. All other Pydantic `SubcontractUpdateBody` fields editable, including `signed_at` + `signed_by` (the **FLAG 2a** signature block — Create doesn't get them). PATCH body is built from a diff vs original and trimmed to `UPDATE_ALLOWED` (defence-in-depth against accidental forbidden-key injection).
- **Lifecycle actions.** Valid-transition-only buttons + confirm dialogs:
  - Draft → [Activate, Terminate]
  - Active → [Complete, Terminate]
  - Completed/Terminated → no buttons (terminal line shown).
- **409 vs 422 handling.** Distinct toast paths. Lifecycle hooks use `onSettled` (not `onSuccess`) so a 409 still resyncs the displayed status badge (the build-pack refetch-to-resync contract). The Activate 409 against an unsigned subcontract is rewritten into a human-readable hint per **FLAG 2a**.

Pinned operator decisions honoured verbatim:
- **§R0.1 scope fence.** Subcontracts only. No valuations / notices / retention / variations stubs.
- **§R4.1 layout.** Inline master-detail, same pattern as `CISTab` / `DocumentFolderView`. No route change.
- **§R4.3 valid-transition-only.** Only the per-status valid transitions render as buttons.
- **§R4.5 409 distinct from 422.** Server detail surfaced; hook `onSettled` invalidation keeps the status badge truthful.
- **§R3.1 reuse-don't-reinvent.** Reuses `SensitiveValue`, `ProjectPicker`, shadcn `Dialog`, `Textarea`, `Button`, `fmtGBP`.
- **§R7 STOP gates.** Three gates with 2nd-run counts printed at each.

## Surfaced deviations (Chat-47 flags — agreed with operator BEFORE Gate 1)

Both deviations were flagged before any code was written and confirmed by the operator. Neither is a silent change; both are test-pinned.

### FLAG 1b — `complete` permission gate split

Build Pack §R0.3 documents `POST /v1/subcontracts/{id}/complete → subcontracts.approve`. The actual backend router on origin/main (`backend/app/routers/subcontracts.py:222`) uses `subcontracts.edit`. The §R2.0 single `canTransitionSubcontract` helper would hide the Complete button from a user with `edit` but not `approve` — even though the backend would accept their call.

**Resolution:** split into three helpers — `canActivateSubcontract` / `canTerminateSubcontract` → `subcontracts.approve`, **`canCompleteSubcontract` → `subcontracts.edit OR subcontracts.approve`** (matches backend ground truth; UI never hides a button the backend would accept). The Build Pack docs §R0.3 are wrong here; backend code is right. **Backlog item: correct the Build Pack docs.**

Test pin: `SubcontractsTab.test.jsx::FLAG 1b — user with subcontracts.edit but NOT .approve still sees Complete on Active`.

### FLAG 2a — `signed_at` lives on Edit only; Activate-409 friendly message

Backend `activate_subcontract` (`services/subcontracts.py:524-526`) returns 409 if `signed_at IS NULL`. Build Pack §R4.4 doesn't list `signed_at` / `signed_by` as Create fields, so the workflow is: create Draft → edit to set signed_at → Activate.

**Resolution:** signature block (`signed_at` + a "I signed this contract" checkbox that wires `signed_by = me.id`) renders **edit-only**. The Activate 409 with `/unsigned/i` body is rewritten by `SubcontractActionButtons.jsx::friendlyActivateError` to **"A signed date is required before this subcontract can be activated. Edit the subcontract to set it."** — dead-end avoided.

Test pin: `SubcontractsTab.test.jsx::FLAG 2a — Activate against unsigned subcontract: 409 is mapped to friendly "signed date required" message`.

## Gate evidence (printed)

| Gate | File | 1st run | **2nd run** | Time (2nd) |
|---|---|---|---|---|
| 1 | `lib/api/__tests__/subcontracts.test.js` | 20 / 20 | **20 / 20** | 0.533 s |
| 2 | `components/suppliers/__tests__/SubcontractsTab.test.jsx` | 23 / 23 | **23 / 23** | 1.559 s |
| 3 | `pages/__tests__/SupplierDetail.test.jsx` (updated) | 28 / 28 | **28 / 28** | 1.34 s |
| 3 | Full FE suite | 85 / 710 | **85 / 710** | 16.727 s |

**Delta vs the 83 / 667 baseline:** **+2 suites, +43 tests.**
- `subcontracts.test.js` — 20 wire-level tests (Gate 1).
- `SubcontractsTab.test.jsx` — 23 integration tests (Gate 2).
- `SupplierDetail.test.jsx` — net +0 tests; the former "shows placeholder" test was replaced 1-for-1 by "mounts SubcontractsTab with this supplier's id" (placeholder MUST be absent, mounted-stub MUST receive the correct supplier id).

## Files

API + hooks + capability:
- `frontend/src/lib/api/subcontracts.js` (new)
- `frontend/src/hooks/subcontracts.js` (new)
- `frontend/src/lib/poCapability.js` (additive)

Components:
- `frontend/src/components/suppliers/SubcontractStatusPill.jsx` (new)
- `frontend/src/components/suppliers/SubcontractActionButtons.jsx` (new)
- `frontend/src/components/suppliers/SubcontractFormDialog.jsx` (new)
- `frontend/src/components/suppliers/SubcontractDetail.jsx` (new)
- `frontend/src/components/suppliers/SubcontractsTab.jsx` (new)

Mount:
- `frontend/src/pages/SupplierDetail.jsx` (placeholder removed, SubcontractsTab mounted)

Tests:
- `frontend/src/lib/api/__tests__/subcontracts.test.js` (new)
- `frontend/src/components/suppliers/__tests__/SubcontractsTab.test.jsx` (new)
- `frontend/src/pages/__tests__/SupplierDetail.test.jsx` (modified — placeholder-test replaced)

Docs:
- `CHANGELOG.md` — §2.8-FE-i entry prepended.
- `docs/chat-summaries/chat-47-closing.md` (this file).
- `memory/PRD.md` — Chat 47 section prepended.

## What's explicitly NOT in this pack (scope fence)

- **Valuations** (interim valuations, valuation lines) — 2.8-FE-ii.
- **Payment notices** (PN, PNN) — later.
- **Retention movements** (release schedules, retention release on completion) — later.
- **Variations / change orders** — 2.8-FE-iii.
- **Subcontract documents** (signed PDF upload, etc.) — would slot into the existing `DocumentFolderView` flow in a later pack.

No placeholders, no stubs, no half-built UI surfaces for any of the above. Per §R0.1 lockdown.

## §R9 backlog (surfaced, not built)

1. **Backend:** add `subcontractor_id` query param to `GET /v1/subcontracts` so the supplier Contracts tab can server-side filter. Currently filtered client-side; fine at present scale.
2. **Build Pack docs §R0.3:** the `complete` row should read `subcontracts.edit`, not `subcontracts.approve` (FLAG 1b ground truth from the actual router).
3. **Future packs:** Valuations (2.8-FE-ii), Variations (2.8-FE-iii), Payment notices, Retention movements, Subcontract documents.

## Next chat opener

Live-eyeball this on a Contractor-type supplier with at least one project visible. Verify:
- Create a Draft subcontract → row appears, badge = Draft, Activate visible, Complete hidden.
- Click Activate → 409 toast says "A signed date is required…" (assumes no signed_at set yet).
- Open Edit → set `signed_at` to today → Save.
- Activate → success toast → badge flips to Active without a manual refresh.
- Complete → success toast → badge flips to Completed → action buttons disappear and the terminal line shows.
- As an editor-only user (no `subcontracts.approve`), Complete is still visible on an Active subcontract; Terminate is not (FLAG 1b).
- As a non-sensitive user, both list-column sum and detail original/current sum show "—" (defence-in-depth).
