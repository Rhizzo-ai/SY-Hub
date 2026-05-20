# Chat 24 / Prompt 2.5 — Purchase Orders, Suppliers & Numbering (R0–R5)

**Closed:** 2026-05-20
**Status:** R0–R5 complete. Backend (R1–R4) independently verified against a real PostgreSQL 16 by the triage chat. R5 (frontend) verified structurally (files present + committed), NOT functionally (private Emergent dep blocks triage-side build) — provisional pending the E2E smoke.
**Predecessor anchor:** Chat 23 close — BudgetLinesGrid v2. main @ `7b04338`, alembic head `0028_user_preferences_table`, 86 permissions, 10 roles, backend 843, Jest 250, bundle 395.10 kB gz.
**Scope this chat:** Build Pack `SY_Hub_Chat_24_Build_Pack_v1.md`, R-sections R0 (cleanup) → R5 (PO frontend). R6 (inline grid) → R9 (close-out) deferred to Chat 25.

---

## Repo state at close (all pushed to `main`)

```
Branch:            main (push-direct via "Save to GitHub"; NOT auto-pushed — see Lessons)
Alembic head:      0033_po_receipts  (was 0028; +5 migrations 0029–0033)
Permissions:       102  (was 86; +16: 11 pos.* + 5 suppliers.*) — confirmed in live table
Roles:             10   (unchanged)
Backend pytest:    875 passing (per Emergent); triage independently ran PO/approval/receipt
                   logic suites = 55 green on a clean DB
Frontend Jest:     312 passing (was 250; +62), 53 suites; 25 URL-contract pins
Bundle gz:         main 395.26 kB (cap 437, headroom ~42 kB); all R5 in lazy suppliers-po chunk
```

---

## What shipped per R-section

**R0 — Pre-flight & cleanup.** Deleted `LineItemsPanel.jsx` (LineDrawer now mounts LineItemsBreakdown); `/api/v1` prefix audit clean; `on-restart.sh` confirmed. (Container has no Postgres — same as Chat 20; all backend verification ran operator/triage-side.)

**R1 — Suppliers + number prefixes.** `suppliers` (tenant-scoped, shared across projects, portal-stub fields for Track 7) + `project_number_prefixes` (per-project per-entity-type, single-default trigger, shape CHECK). Models, services, routers under `/api/v1/`, project-creation auto-seed of null-middle default prefixes. Migration `0029_suppliers_prefixes` (+ pg_trgm).

**R2 — PO core + status machine + permissions.** `purchase_orders` + `purchase_order_lines`, 8-state machine (`draft → pending_approval → approved → issued → partially_receipted → receipted → closed`, + `voided`; closed/voided terminal). Services: `po_numbering` (atomic FOR UPDATE + populate_existing), `po_authz` (Pattern α scoping + edit-tier guard FULL/HEADER_ANNOTATION_ONLY/READ_ONLY), `po_transitions`, `purchase_orders`. Migrations `0030_purchase_orders` + `0031_po_permissions` (16 perms, full 10-role grant matrix). Required 4 amendment rounds to reconcile grants to spec §9.2 (see Lessons).

**R3 — Approvals + commitment.** `purchase_order_approvals` (+ budget_snapshot jsonb). Commitment functions/triggers: `fn_budget_line_recompute_commitments`, status-change + line-change triggers. submit/approve/reject/unlock endpoints, self-approval guard. Migration `0032_po_approvals`.

**R4 — Receipts.** `purchase_order_receipts` + `_receipt_lines` + `_receipt_photos`, `fn_pol_recompute_receipted_qty` trigger, partial-qty receipting, inline photo metadata, auto status-flip on full receipt, director-tier edit/delete. Migration `0033_po_receipts`.

**R5 — Frontend.** SupplierList/Detail/Form, PurchaseOrderList/Form/Detail, NumberPrefixManager; `<POStatusPill/>` (first brand-token application), `<SensitiveValue/>` (em-dash gating), `<SupplierSelect/>`, `<POLineEditor/>`. 25 URL-contract Jest pins. Lazy `suppliers-po` chunk; main bundle unchanged.

---

## Engineering invariants pinned this chat

1. **Commitment contract.** `committed_value` = SUM(net) for POs in {approved, issued, partially_receipted, receipted}; `pending_value` = {draft, pending_approval}; closed + voided contribute zero. Receipts do NOT alter committed_value (money moves to actuals via Bills later) — proven by explicit test across receipt create/full/delete.
2. **Numbering.** `PO-{middle?}-{NNNN}`; `PO-` fixed; middle optional, configurable per project per entity-type (uppercase alnum+dash, ≤8 chars), auto-sequential per (project, entity, middle), overridable. Same model for Bills. Concurrency-safe via FOR UPDATE + `populate_existing=True`.
3. **Edit tiers.** Draft/Approved → `pos.edit` (full); Issued+ → `pos.edit_issued` (director-tier, header annotations only — lines/totals require void+reissue); Closed/Voided read-only.
4. **PM grant set (project_manager = contracts_manager persona):** 8 pos.* perms — view, view_sensitive, create, edit, issue, receipt, close, delete. NOT edit_issued, approve, void.
5. **Migration enum-extension helper MUST use `op.get_context().autocommit_block()`** (per migration 0020), never `bind.execution_options(isolation_level="AUTOCOMMIT")` — the latter fails inside the open migration transaction.

---

## Defects fixed in-flight

| # | Defect | Fix |
|---|---|---|
| D1 | PO numbering concurrency race — FOR UPDATE took the lock but SQLAlchemy identity map served a cached `next_sequence`; all concurrent requests computed the same number | `.execution_options(populate_existing=True)` on the locked-row query |
| D2 | `ModuleNotFoundError: app.models.entities` in number_prefixes router (singular `entity`) — caused the integration suite to error at collection, so earlier "passing" was unit-only | corrected import; grepped all R1–R5 files, no other bad imports |
| D3 | Broken enum helper in 0029/0031/0032 (`isolation_level="AUTOCOMMIT"`) — `alembic upgrade head` failed at 0028→0029 | replaced with `autocommit_block` in all three |
| D4 | notification_type enum missing `po.partial_receipt`/`po.fully_receipted` — 500 on notify | added via autocommit_block |
| D5 | `read_only.suppliers.view` missing from migration chain — caught by the 0025 round-trip guardrail | backfilled in 0033 (idempotent ON CONFLICT DO NOTHING) |
| D6 | 8 legacy guardrail tests held stale baselines (perm counts 81/86/87, alembic head pins) | rebaselined to 102 / `0033_po_receipts` |

---

## Build Pack deviations (Emergent reported, accepted)

- **E1 — Photos via direct metadata.** Build Pack §4.4 assumed a global `documents` table; repo has none (only `actual_attachments`). Photos stored as file metadata on `purchase_order_receipt_photos`, unique on `(receipt_id, file_path)`. `receipt_proof` tagging dropped. Decision: keep this pattern; unified documents table deferred to Documents & Compliance track (Future_Tasks §19).
- **E2 — Inline photo posting.** No standalone multipart endpoint; photos posted inline with the receipt body. Standalone streaming endpoint deferred (Future_Tasks §20).
- **E3 — Role-code mapping.** Build Pack §9.2 used aspirational role names (admin/finance_director/contracts_manager/designer). Repo has super_admin/director/project_manager/finance/site_manager/sales/read_only/investor_read_only/subcontractor_portal/consultant_portal. Mapped: finance_director→finance, contracts_manager→project_manager. No admin/designer equivalent — consultant_portal left zero-grant (external-facing; correct).
- **E4 — `pos.reopen` removed.** Reopen-from-closed not in 2.5 scope; closed is terminal. Deferred (Future_Tasks §17).

---

## Verification record (what triage confirmed independently)

| Check | Method | Result |
|---|---|---|
| Work actually on GitHub | triage re-pulled `main` after each Save-to-GitHub | confirmed (caught one round where nothing had been pushed) |
| Migrations 0029–0033 apply | clean empty PG 16, `alembic upgrade head` | reached `0033_po_receipts`, zero errors |
| Migrations reversible | downgrade -4 / -1 then upgrade | clean both directions |
| 16 new perms in live table | `SELECT code FROM permissions WHERE ...` | all 16 present, correct names |
| PO/approval/receipt logic | ran the unit suites on clean DB | 55 green |
| autocommit_block fix on remote | grep all 3 migrations on GitHub | confirmed, no isolation_level form remains |
| R5 frontend | files present + committed on GitHub | structural ✓; functional NOT runnable triage-side (private Emergent dep `emergentbase-visual-edits` on assets.emergent.sh) |

---

## Open / deferred to Chat 25

1. **E2E lifecycle smoke (job 1)** — suppliers→prefix→PO→submit→approve→issue→partial receipt→full receipt→close, + void. Deferred twice in Chat 24. Run against pushed code on live preview. Promotes R5 from provisional to confirmed.
2. **R6 — inline expandable grid sub-rows** (Buildertrend-style; replaces BudgetGridDrilldown side panel). The big UI shift. §5.3 / G6.1–G6.7.
3. **R7 — status-transition UI + approval panel + receipt form + MyApprovalsDashboard.** §R7 / G7.1–G7.6.
4. **R8/R9 — tests sweep + close-out** (engineering-invariants commitment formula, backlog, chat-25-closing).

## Future_Tasks added this chat
- §16 PO approval amount thresholds (deferred)
- §17 PO reopen-from-closed (deferred)
- §18 cold-start bootstrap blocked by 0018 guard (P1, vs hard-constraint #5)
- §19 unified documents table (Documents & Compliance track)
- §20 PO photo multipart streaming endpoint (nice-to-have)

---

## Hard lessons (carry as standing rules)

1. **"Committed to main" ≠ pushed.** Emergent does not auto-push. 10 commits sat local-only until triage caught it by pulling the repo. Always Save-to-GitHub + triage re-pull before sign-off.
2. **Backend STOP reports must include a real clean-DB migration run.** Biggest token-sink: discovering after 4 amendment rounds that migrations didn't apply. Lint-clean + "tests passing" looked green while the backend wouldn't start.
3. **"Tests passing" can mean the suite never ran** (D2 collection error → unit-only). Confirm count + collection, not just green.
4. **Assertions ≠ evidence.** Every time triage demanded the printed artefact (10×16 grant matrix, live perm count), a real defect surfaced. Demand printouts, not summaries.
5. **Verify-don't-trust is the method and it works.** Caught the missing push, 3 migration defects, the concurrency race, the silent collection failure, and multiple grant errors. Keep it.
6. **Recommend a Claude Code phase-checkpoint pass on R1–R7 before Track 2 closes.**

---

## Appendix — file manifest

### Backend (new)
```
app/models/suppliers.py, number_prefixes.py, purchase_orders.py, po_approvals.py, po_receipts.py
app/services/suppliers.py, number_prefixes.py, po_numbering.py, po_authz.py, po_transitions.py,
             purchase_orders.py, po_commitments.py, po_approvals.py, po_receipts.py
app/routers/suppliers.py, number_prefixes.py, purchase_orders.py
alembic/versions/0029_suppliers_prefixes.py, 0030_purchase_orders.py, 0031_po_permissions.py,
             0032_po_approvals.py, 0033_po_receipts.py
tests/test_suppliers.py, test_number_prefixes.py, test_purchase_orders_unit.py,
             test_purchase_orders_api.py, test_po_approvals_unit.py, test_po_approvals_api.py,
             test_po_receipts_unit.py, test_po_receipts_api.py
```

### Frontend (new)
```
src/lib/api/suppliers.js, numberPrefixes.js, purchaseOrders.js
src/lib/api/__tests__/po-url-contracts.test.js   (25 pins)
src/hooks/purchaseOrders.js
src/components/po/POStatusPill.jsx, SensitiveValue.jsx, SupplierSelect.jsx, POLineEditor.jsx
src/components/po/__tests__/POStatusPill.test.jsx, SensitiveValue.test.jsx, POLineEditor.test.jsx
src/pages/SupplierList.jsx, SupplierDetail.jsx, SupplierForm.jsx
src/pages/projects/PurchaseOrderList.jsx, PurchaseOrderForm.jsx, PurchaseOrderDetail.jsx,
             NumberPrefixManager.jsx
```

### Modified
```
frontend/src/components/budgets/LineDrawer.jsx        (LineItemsPanel → LineItemsBreakdown)
frontend/src/components/budgets/LineItemsPanel.jsx    DELETED
backend/app/seed_rbac.py                              (16 perms + 10-role grants)
8 legacy guardrail test files                         (rebaselined to 102 / 0033)
docs/SY_Homes_Future_Tasks.md                         (+§16–§20)
```
