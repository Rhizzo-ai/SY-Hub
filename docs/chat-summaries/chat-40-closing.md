# Chat 40 — Build Pack 2.7-FE closing summary

**Pack:** Build Pack 2.7-FE — Suppliers / Subcontractors / CIS / Supplier Documents (frontend)
**Branch base:** main @ `0039_committed_single_writer`, 129 permissions, 10 roles
**Head after this pack:** unchanged (frontend-only; backend FROZEN per §R0)
**Permissions:** 129 (unchanged — no permission CRUD this chat)
**Roles:** 10 (unchanged)
**Backlog file (`docs/SY_Hub_Phase2_Backlog.md`):** NOT touched per §R8.
**Auth flows touched:** none.
**Test count:** **513 tests / 75 suites green** (was 424 / 67 at start of 2.7-FE — +89 tests / +8 suites).

---

## What landed (Chat 40 §R2–§R6 scope, both halves)

### §R2 FIX half (D1–D7) — 2.5 drift corrections to the shipped supplier surface

These were objectively broken against the current backend; every change
is mandatory for 2.7-FE to function. No behaviour changed beyond
aligning the UI to the frozen backend contract.

| # | File | Defect | Fix |
|---|---|---|---|
| D1 | `pages/SupplierForm.jsx` | CIS dropdown offered `(None, Gross, Net_20, Net_30)` — wrong casing + missing `not_registered` | Verbatim backend enum `('', gross, net_20, net_30, not_registered)`; blank → null; human labels |
| D2 | `pages/SupplierForm.jsx` + `lib/api/suppliers.js` | Wrote `bank_account_number`; missed `bank_name` + `company_number` | Renamed to `bank_account_no`; added the two missing sensitive inputs |
| D3 | `pages/SupplierList.jsx` + `SupplierDetail.jsx` | Read phantom `s.status === 'Archived'` | Replaced everywhere with `s.is_archived: bool` |
| D4 | `lib/api/suppliers.js` + `hooks/purchaseOrders.js` | `restoreSupplier` posted to `/restore` — 404 (backend mounts `/unarchive`) | Renamed `restoreSupplier`→`unarchiveSupplier`, route `/restore`→`/unarchive`, hook `useUnarchiveSupplier` |
| D5 | `pages/SupplierList.jsx` | Sent `{status, search}` (ignored by router) | Send `{q, include_archived, supplier_type}` |
| D6 | `pages/SupplierDetail.jsx` | Read `s.bank_account_number` (always undefined) | Read `s.bank_account_no`; added `bank_name` + `company_number` rows |
| D7 | `components/AppShell.jsx` | No nav entries; URL-only access | Suppliers + Subcontractors nav (gated `suppliers.view`); Subcontractors → `/suppliers?type=Subcontractor` |

### §R3 / §R4 ADD half — new surfaces

- **SupplierList enriched** (§R4.1): Type filter (All/Supplier/Subcontractor)
  drives `supplier_type`; CIS column with `<CISStatusBadge/>` on
  subcontractor rows; §R6b unverified cue (amber dot + tooltip on rows
  with `current_cis_status ∈ {null, 'Unverified', 'Unmatched'}` when
  Type=Subcontractor) + header summary. `useSearchParams` seeds and
  syncs the Type filter so the nav "Subcontractors" link lands
  pre-filtered and URLs are shareable.
- **SupplierForm subcontractor block** (§R4.2): Type selector at top;
  subcontractor-only block (`cis_subtype`, `cis_registered`, sensitive
  `utr`); UTR client-validated as 10 digits or empty; non-subcontractor
  payloads omit `cis_subtype`/`cis_registered`/`utr`; explicit
  `cis_subtype: null` on Subcontractor→Supplier edit transitions so
  the backend clears the stored value.
- **SupplierDetail tabbed** (§R4.3): shadcn `Tabs` — Overview / CIS /
  Documents / Contracts. Tabs render per visibility (CIS only for
  subcontractors with `cis.view`; Documents only with
  `supplier_documents.view`; Contracts only for subcontractors).
  Archive/Restore live in the header.
- **`CISTab`** (§R4.4): current-status banner, append-only history
  table, gated record-verification form. Mutation invalidation is
  exact per §R4.4: `['cis','verifications',id]`,
  `['cis','current',id]`, `['supplier', id]`, `['suppliers']`. 409
  defended defensively.
- **`DocumentsTab`** (§R4.5): toolbar + table + shadcn `Dialog` for
  add/edit; archive/restore confirm + toast; `file_ref` + `notes` gated
  on `supplier_documents.view_sensitive`; archived rows
  de-emphasised + chip.
- **`CISStatusBadge`** (§R4.6): 4 statuses + null → Badge variants
  (default/secondary/destructive/outline).
- **`DocExpiryBadge`** (§R4.6 / §R6a): pure frontend bucketing
  (Expired / Expiring soon (≤30d) / no badge); backend stores
  `expires_on` but never flags.
- **`lib/cisFormat.js`**: label maps + `formatDate` via
  `Intl.DateTimeFormat('en-GB')`.
- **`lib/api/cis.js` + `hooks/cis.js`**: verifications API + hooks.
- **`lib/api/supplierDocuments.js` + `hooks/supplierDocuments.js`**:
  documents API + hooks.
- **`lib/poCapability.js`**: 8 new helpers
  (`canViewCIS`, `canViewSensitiveCIS`, `canVerifyCIS`, `canViewDocs`,
  `canViewSensitiveDocs`, `canCreateDocs`, `canEditDocs`,
  `canArchiveDocs`).

### §R6 — Operator-approved enhancements

- (a) Document expiry badges (frontend computation).
- (b) CIS unverified cue on the list + first-class
  `<CISStatusBadge/>`.

---

## Tests (named **EXACTLY** per §R5)

| # | File | Status |
|---|---|---|
| §R5 #1 | `frontend/src/pages/__tests__/SupplierList.test.jsx` | ✅ 11/11 |
| §R5 #2 | `frontend/src/pages/__tests__/SupplierForm.test.jsx` | ✅ 12/12 |
| §R5 #3 | `frontend/src/pages/__tests__/SupplierDetail.test.jsx` | ✅ 8/8 |
| §R5 #4 | `frontend/src/components/suppliers/__tests__/CISTab.test.jsx` | ✅ 7/7 |
| §R5 #5 | `frontend/src/components/suppliers/__tests__/DocumentsTab.test.jsx` | ✅ 10/10 |
| §R5 #6 | `frontend/src/components/suppliers/__tests__/CISStatusBadge.test.jsx` | ✅ 7/7 |
| §R5 #7 | `frontend/src/components/suppliers/__tests__/DocExpiryBadge.test.jsx` | ✅ 10/10 |
| §R5 #8 | `frontend/src/lib/__tests__/cisFormat.test.js` | ✅ 12/12 |
| §R5 #9 | `frontend/src/lib/api/__tests__/suppliers.test.js` | ✅ 3/3 (D4 regression pin) |

URL-contract pin in `frontend/src/lib/api/__tests__/po-url-contracts.test.js`
updated to assert the new `/unarchive` route.

Playwright E2E spec (`frontend/e2e/suppliers-subcontractors.spec.ts`)
deferred — the repo has no Playwright runner wired up at HEAD; raising
this as an out-of-scope item for the next operator-led test-runner
setup chat.

Full Jest run: **513 passed / 0 failed / 75 suites / ~15s**.

---

## §R7 STOP gates honoured

1. §R0 coverage map confirmed by operator at chat open. ✅
2. After FIX half (D1–D7) — explicit Gate 2 stop, operator inspected
   the defect-fix diff and replied `proceed`. ✅
3. After ADD half + all §R5 tests green — this closing summary. ✅
4. Before push — operator triggers "Save to GitHub"; then verify on
   `origin/main` via raw fetch. (Operator action; not Emergent's.)

---

## §R8 housekeeping

- Bundle: new components import into the existing `suppliers-po`
  webpack chunk (already lazy-loaded); no new top-level route.
  Webpack hot-reload reports `Compiled successfully!` after the
  changes. Gzip-cap delta cannot be measured without a production
  build run — operator can confirm post-Save-to-GitHub.
- Routes: `/suppliers`, `/suppliers/new`, `/suppliers/:id`,
  `/suppliers/:id/edit` unchanged. Subcontractors are the list with a
  filter, not a new route — nav "Subcontractors" links to
  `/suppliers?type=Subcontractor`.
- `CHANGELOG.md` written (Chat 40 entry above the Chat 39 block).
- This file: `docs/chat-summaries/chat-40-closing.md`.
- Backlog: **NOT touched** (operator hand-edits only).
- All test files named **exactly** per §R5.

---

## §R9 out of scope (intentionally not built)

- Subcontracts / variations / valuations UI → 2.8-FE.
- Supplier portal → 2.9.
- Backend changes (frozen — no gaps surfaced).
- PO surface (untouched except shared `SensitiveValue` import).
- Playwright runner wiring (next operator chat).

---

## File list (created / edited)

### Edited
1. `frontend/src/lib/api/suppliers.js` — D4 + sensitive list reshape
2. `frontend/src/hooks/purchaseOrders.js` — `useUnarchiveSupplier`
3. `frontend/src/lib/poCapability.js` — 8 new CIS/docs helpers
4. `frontend/src/pages/SupplierList.jsx` — D3/D5 + Type filter + cue
5. `frontend/src/pages/SupplierForm.jsx` — D1/D2 + Subcontractor block
6. `frontend/src/pages/SupplierDetail.jsx` — D3/D6 + Tabs
7. `frontend/src/components/AppShell.jsx` — D7 (Suppliers + Subcontractors nav)
8. `frontend/src/lib/api/__tests__/po-url-contracts.test.js` — D4 URL pin

### Created
9. `frontend/src/lib/api/cis.js`
10. `frontend/src/lib/api/supplierDocuments.js`
11. `frontend/src/hooks/cis.js`
12. `frontend/src/hooks/supplierDocuments.js`
13. `frontend/src/components/suppliers/CISTab.jsx`
14. `frontend/src/components/suppliers/DocumentsTab.jsx`
15. `frontend/src/components/suppliers/CISStatusBadge.jsx`
16. `frontend/src/components/suppliers/DocExpiryBadge.jsx`
17. `frontend/src/lib/cisFormat.js`
18. `frontend/src/pages/__tests__/SupplierList.test.jsx` (§R5 #1)
19. `frontend/src/pages/__tests__/SupplierForm.test.jsx` (§R5 #2)
20. `frontend/src/pages/__tests__/SupplierDetail.test.jsx` (§R5 #3)
21. `frontend/src/components/suppliers/__tests__/CISTab.test.jsx` (§R5 #4)
22. `frontend/src/components/suppliers/__tests__/DocumentsTab.test.jsx` (§R5 #5)
23. `frontend/src/components/suppliers/__tests__/CISStatusBadge.test.jsx` (§R5 #6)
24. `frontend/src/components/suppliers/__tests__/DocExpiryBadge.test.jsx` (§R5 #7)
25. `frontend/src/lib/__tests__/cisFormat.test.js` (§R5 #8)
26. `frontend/src/lib/api/__tests__/suppliers.test.js` (§R5 #9)
