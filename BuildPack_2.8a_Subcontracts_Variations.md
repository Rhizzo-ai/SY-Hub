# Build Pack 2.8a — Subcontracts & Variations

**Prompt:** 2.8a (Track 2 — Commercial Engine; split from 2.8 per brief's
explicit split-candidate flag). 2.8b (Valuations + Payment Notices +
Retention) is a SEPARATE later pack.
**Type:** Backend-only. NO frontend, NO Playwright.
**Branch strategy:** push-to-main (phase-boundary audits only).
**Depends on:** 2.5 (actuals), 2.6 (budget changes — shipped), 2.7
(subcontractors — shipped), purchase_orders (shipped).
**Alembic head at draft time:** `0036_budget_changes`. New migration chains
off HEAD at execution — VERIFY in §R0.

---

## What this builds (plain summary)

Formal **subcontract** records (the signed agreement layer that wraps a
subcontractor PO), plus the **variation** workflow (raise → cost → approve →
issue). An approved variation either folds into the contract sum or generates
a BCR via the 2.6 machinery (`budget_changes.create_bcr` already accepts
`source_variation_id` — this pack populates it and adds the deferred FK).
2.8b (valuations, payment notices, retention, CIS deductions) is OUT of scope.

---

## Locked decisions (do not re-litigate)

- **LD1 — Subcontract↔PO link is nullable + guarded.** `purchase_order_id`
  nullable. A subcontract may stand alone (small jobs; contract sum on the
  subcontract) OR link a PO (large jobs; PO raised first, subcontract wraps
  it). When linked, the PO MUST be same `project_id` AND same
  `supplier_id`/subcontractor; contract sum reconciles to PO `total_amount`
  (WARN-not-block on mismatch — store a flag/note, do not reject).
- **LD2 — Subcontractor only.** A subcontract's counterparty must be a
  `suppliers` row with `supplier_type='Subcontractor'`. Reject plain suppliers
  → `ValueError`.
- **LD3 — Variation→BCR hook is live.** Add the deferred FK
  `budget_changes.source_variation_id → subcontract_variations.id` in this
  pack's migration. On variation approval where `cost_treatment='BudgetChange'`,
  call the EXISTING `create_bcr(..., change_type='Adjustment',
  source_variation_id=<variation.id>)`. Do NOT reimplement BCR logic.
- **LD4 — Contract sum maintenance.** `subcontract.current_contract_sum =
  original_contract_sum + sum(approved variations folded into sum)`. Variations
  treated as BCRs do NOT alter the contract sum (they hit the budget, not the
  contract). Maintained by the service.

---

## §R0 — Pre-flight verification (STOP gate — do not skip)

Confirm against main BEFORE writing code; report deltas.

1. **Alembic HEAD.** `alembic heads`; new migration `down_revision` = literal
   HEAD. Name ≤32 chars. Proposed: `0037_subcontracts` (17 chars).
2. **PO model.** Confirm `purchase_orders` has `project_id`, `supplier_id`,
   `budget_id`, `status` (enum `po_status`, terminal {closed, voided}),
   `total_amount`. Confirm `purchase_order_lines` keyed to `budget_lines`.
3. **budget_changes.create_bcr.** Confirm signature accepts
   `change_type` + `source_variation_id` kwargs and that
   `source_variation_id` column exists on `budget_changes` with NO FK yet
   (2.6 stub). This pack adds the FK.
4. **Subcontractor type.** Confirm `suppliers.supplier_type` enum has
   `Subcontractor` (2.7). Confirm how to query it.
5. **Audit + numbering conventions.** Confirm `services/audit.py` exposes
   `record_audit` + `field_diff` (PO/suppliers service-layer pattern — 2.8a
   uses service-layer audit). Confirm the PO numbering helper
   (`services/po_numbering.py` or similar) pattern for generating
   project-scoped sequential refs; mirror it for subcontract + variation refs.
6. **Router/permission conventions.** Confirm `routers/purchase_orders.py`
   auth pattern (`require_permission` / `_check_perm`), `/api/v1` mount.
7. **Permissions baseline + enum.** Confirm count (expected 112 post-2.6).
   New resources `subcontracts` + `subcontract_variations` → add to
   `RESOURCES` enum (`models/rbac.py`). New actions needed: `issue` (variation
   issue step) — likely NEW `permission_action` value; `cost`/`approve` may
   reuse existing. REPORT which actions are new.
8. **Baseline tests.** pytest twice (WARM-DB; trust 2nd). Record literal
   2nd-run count (expected ~1110). Regression floor = that number.

**STOP.** Material delta in 1–7 → HALT and report.

---

## §R1 — Schema (migration `0037_subcontracts`)

### R1.1 — New table `subcontracts`
- `id` UUID PK.
- `tenant_id` UUID NOT NULL FK → tenants ON DELETE RESTRICT.
- `project_id` UUID NOT NULL FK → projects ON DELETE RESTRICT.
- `subcontractor_id` UUID NOT NULL FK → suppliers.id ON DELETE RESTRICT
  (validated `supplier_type='Subcontractor'` at service layer — LD2).
- `purchase_order_id` UUID **nullable** FK → purchase_orders.id ON DELETE
  SET NULL (LD1).
- `reference` String(30) NOT NULL — `SC-NNNN` project-scoped sequence,
  service-generated, unique within project.
- `title` String(200) NOT NULL.
- `scope_description` Text, nullable.
- `status` String(20) NOT NULL default `Draft` — state machine:
  `Draft → Active → Completed` + `Terminated` (terminal). `Active` = signed
  and live; valuations (2.8b) only apply to Active/Completed.
- `original_contract_sum` Numeric(14,2) NOT NULL default 0.
- `current_contract_sum` Numeric(14,2) NOT NULL default 0 — maintained by
  service (LD4).
- `retention_pct` Numeric(5,2) NOT NULL default 0 — stored now, USED by 2.8b.
- `cis_applies` Boolean NOT NULL default true — stored now, USED by 2.8b.
- `start_on` Date nullable, `end_on` Date nullable.
- `signed_at` DateTime nullable, `signed_by` FK users SET NULL.
- `po_reconciliation_note` Text nullable (LD1 warn-not-block record).
- Standard audit cols (created_at/by, updated_at).
- Index `(project_id, status)`. Unique `(project_id, reference)`.

### R1.2 — New table `subcontract_variations`
- `id` UUID PK.
- `tenant_id` UUID NOT NULL FK → tenants RESTRICT.
- `subcontract_id` UUID NOT NULL FK → subcontracts.id ON DELETE CASCADE.
- `reference` String(30) NOT NULL — `VAR-NNNN` per subcontract sequence.
- `title` String(200) NOT NULL.
- `description` Text nullable.
- `status` String(20) NOT NULL default `Raised` — state machine:
  `Raised → Costed → Approved → Issued` + `Rejected`/`Withdrawn` (terminal).
- `estimated_value` Numeric(14,2) nullable (at raise).
- `agreed_value` Numeric(14,2) nullable (set at cost step).
- `cost_treatment` String(20) nullable — set at approval: `WithinContractSum`
  (folds into `current_contract_sum`) | `BudgetChange` (generates a BCR via
  2.6). App-validated.
- `generated_bcr_id` UUID nullable FK → budget_changes.id ON DELETE SET NULL
  (populated when cost_treatment=BudgetChange).
- Workflow stamps: `costed_at`/`by`, `approved_at`/`by`, `issued_at`/`by`,
  `rejected_at`/`by`, `rejection_reason` Text nullable.
- Standard audit cols. Index `(subcontract_id, status)`. Unique
  `(subcontract_id, reference)`.

### R1.3 — Deferred FK from 2.6 (LD3)
- Add FK constraint: `budget_changes.source_variation_id` →
  `subcontract_variations.id` ON DELETE SET NULL. The column already exists
  (2.6 stub); this adds the constraint only. Idempotent guard.

### R1.4 — Migration hygiene
- `issue` enum value → `ALTER TYPE permission_action ADD VALUE 'issue'` if new
  (idempotent). New RESOURCES values are in-code only.
- `downgrade()` drops the source_variation_id FK first, then both new tables.
  Round-trip clean on scratch DB.

---

## §R2 — Permissions (seed_rbac.py)

```python
# Chat 34 §R2 (Prompt 2.8a) — subcontracts.
PERMISSION_CATALOGUE += _perms_for(
    "subcontracts",
    include=["view", "view_sensitive", "create", "edit", "approve"],
    sensitive={"view_sensitive", "approve"},
)
# Chat 34 §R2 (Prompt 2.8a) — subcontract variations.
PERMISSION_CATALOGUE += _perms_for(
    "subcontract_variations",
    include=["view", "create", "cost", "approve", "issue"],
    sensitive={"approve", "issue"},
)
```
- VERIFY which of `cost`/`issue` are new `permission_action` values; handle in
  migration. REPORT.
- New perms = 5 + 5 = **10**. Expected 112 → **122** (confirm vs §R0.8
  baseline; if ≠112, baseline + 10).
- Role mapping: `subcontracts` + variations create/edit/cost to the
  budget-edit / contracts set (incl. project_manager); `approve`/`issue` to the
  approval-authorised roles (director, finance, super_admin per the LIVE map —
  VERIFY and mirror as prior packs did). REPORT resolved map.

---

## §R3 — Service layer

### R3.1 — `services/subcontracts.py` (new)
- `create_subcontract(...)`: validates subcontractor type (LD2); if
  `purchase_order_id` set, validate same project + same subcontractor and
  reconcile sum (warn-not-block → `po_reconciliation_note`); generate `SC-NNNN`
  (race-safe, mirror PO numbering); status `Draft`;
  `current_contract_sum = original_contract_sum`. Gate `subcontracts.create`.
- `update_subcontract` (Draft/Active per field — scope changes Draft-only;
  dates/signed editable on Active). `activate` (`Draft→Active`, requires
  signed), `complete` (`Active→Completed`), `terminate` (→Terminated).
  State guards via `ValueError`/state-error pattern.
- Service-layer audit (`record_audit`+`field_diff`) on all mutations.

### R3.2 — `services/subcontract_variations.py` (new)
- `raise_variation(...)` → `Raised`, `VAR-NNNN`, optional estimated_value.
  Parent subcontract must be Active. Gate `.create`.
- `cost_variation(agreed_value)` → `Raised→Costed`. Gate `.cost`.
- `approve_variation(cost_treatment)` → `Costed→Approved`. Gate `.approve`.
  - `WithinContractSum`: add `agreed_value` to subcontract
    `current_contract_sum` (LD4).
  - `BudgetChange`: call EXISTING `create_bcr(db, budget_id=<subcontract's
    project budget — resolve the current/active budget for the project>,
    change_type='Adjustment', source_variation_id=variation.id, ...)`; store
    returned BCR id in `generated_bcr_id`. The BCR's `created_by` is the
    variation-approving user. The BCR then follows its OWN approve/apply
    lifecycle (2.6) — approving the variation does NOT auto-apply the BCR.
    NOTE the SoD interaction: because the BCR creator = the variation
    approver, 2.6's self-approval guard means that SAME user cannot approve
    the generated BCR if its gross movement ≥ threshold — a second user must.
    This is correct and intended (separation of duties carries through).
    Document this two-step + the SoD carry-through clearly.
- `issue_variation` → `Approved→Issued` (Issued is TERMINAL — the formal
  instruction to the subcontractor has been sent; no further transitions).
  Gate `.issue`.
- `reject_variation(reason)` / `withdraw_variation` → terminal.
- Resolve "which budget" for BCR generation: the project's current Active
  budget (`is_current=true`). If none, `ValueError` (can't raise a budget-
  change variation against a project with no live budget).

---

## §R4 — Routers (`/api/v1`)

### R4.1 — `routers/subcontracts.py` (prefix `/subcontracts`)
- POST (create, `.create`, 201), GET list `?project_id=&status=` (`.view`),
  GET `/{id}` (`.view`), PATCH (`.edit`),
  POST `/{id}/activate` `/complete` `/terminate` (`.edit`/`.approve` as
  appropriate). Gate sensitive sum fields behind `subcontracts.view_sensitive`.
### R4.2 — `routers/subcontract_variations.py` (prefix `/subcontract-variations`)
- POST (raise, `.create`), GET list `?subcontract_id=&status=` (`.view`),
  GET `/{id}` (`.view`),
  POST `/{id}/cost` (`.cost`), `/{id}/approve` (`.approve`, body:
  cost_treatment), `/{id}/issue` (`.issue`), `/{id}/reject` (`.approve`),
  `/{id}/withdraw` (`.create`).
- Cross-tenant → 404, validation → 422, bad transition → 409.
- Register both in `server.py`.

---

## §R5 — Acceptance gates (≥ 34 new test functions)

Files: `test_subcontracts_service.py`, `test_subcontracts_api.py`,
`test_subcontract_variations_service.py`, `test_subcontract_variations_api.py`,
`test_subcontracts_migration.py`, `test_permissions_2_8a.py`.

**Migration**
1. upgrade clean; both tables + the source_variation_id FK exist.
2. down→up round-trip clean.

**Subcontracts**
3. Create against a Subcontractor → Draft, `SC-0001`,
   `current_contract_sum=original`.
4. Create against a plain Supplier → `ValueError`/422 (LD2).
5. Create with PO same project+subcontractor → linked OK.
6. Create with PO different project → rejected.
7. Create with PO whose total ≠ contract sum → linked + `po_reconciliation_note`
   set (warn-not-block, LD1).
8. Second subcontract same project → `SC-0002`.
9. `activate` without signed → rejected; with signed → Active.
10. `complete` from Active → Completed; from Draft → rejected.
11. `terminate` → Terminated.
12. Cross-tenant fetch → 404.
13. Sum fields hidden without `subcontracts.view_sensitive`.

**Variations — workflow**
14. Raise on Active subcontract → Raised, `VAR-0001`.
15. Raise on Draft subcontract → rejected.
16. `cost` sets agreed_value, Raised→Costed.
17. Approve from Raised (skip cost) → 409.
18. `issue` from Approved → Issued; from Costed → 409.
19. reject (reason required) / withdraw → terminal; missing reason → 422.
20. Second variation → `VAR-0002`.

**Variations — cost treatment (the core)**
21. Approve `WithinContractSum` → `current_contract_sum += agreed_value`;
    no BCR created.
22. Approve `BudgetChange` → calls create_bcr(Adjustment,
    source_variation_id set); `generated_bcr_id` populated; contract sum
    UNCHANGED.
23. The generated BCR is a normal Draft BCR (NOT auto-applied) — assert its
    status is Draft and the budget line `approved_changes` is unchanged until
    the BCR is separately applied.
24. `BudgetChange` variation on a project with no Active budget → `ValueError`.
25. Approving with invalid `cost_treatment` → 422.

**Variation→BCR integration**
26. End-to-end: user A raises→costs→approves(BudgetChange) the variation
    (generating the Draft BCR); a DIFFERENT user B approves+applies the
    generated BCR via 2.6 (B ≠ the BCR creator, so the self-approval guard
    permits it) → budget line `approved_changes` reflects the variation
    value; budget header FFC recomputed.
27. The applied BCR's `source_variation_id` round-trips to the variation.

**Permissions / regression**
28. Permission count = baseline + 10 (literal; expected 122 if baseline 112).
29. `subcontracts.approve` / `subcontract_variations.approve`+`issue` mapped to
    the approval roles; create/cost to the contracts set (assert vs live map).
30. `subcontracts.create` absent → 403; `subcontract_variations.issue` absent
    → 403 on issue.
31. Subcontract status transitions rejected from wrong states (service-level).
32. Variation status transitions rejected from wrong states (service-level).
33. Numbering is race-safe (SC/VAR refs unique + sequential under contention).
34. Audit row written on create/approve/issue (service-layer record_audit).
35. Full suite 2nd-run: baseline + new, **zero regressions**, 0 failed.

---

## Out of scope (explicit)

- 2.8b: valuations, payment notices, retention release, CIS deductions →
  separate pack. `retention_pct` + `cis_applies` are STORED now, UNUSED until
  2.8b.
- Any frontend / Playwright (2.8-FE later).
- Auto-applying the generated BCR (variation approval generates a Draft BCR;
  applying it is a separate 2.6 action — by design).
- 2.9 portal (subcontractor-submitted variations) → later.
- Multi-budget variation splitting → not in scope (single Active budget).

---

## Self-report format (REQUIRED)

```
## 2.8a Self-Report
- §R0 deltas: <list or "none material">
- Alembic: HEAD was <X>; migration 0037_subcontracts; round-trip <pass/fail>;
  source_variation_id FK added: <yes/no>
- permission_action enum: new values <cost/issue — which>
- Permission count: <before> → <after> (expected baseline + 10 = 122)
- Tables added: subcontracts, subcontract_variations
- Variation→BCR hook: create_bcr called with source_variation_id <verified>
- Routers registered: subcontracts, subcontract_variations
- Tests: <N> new. pytest 2nd-run: <P passed / F failed / X xfailed>.
  Regression floor <baseline>: <held/broke>
- Deviations: <list>
- Files changed: <count + list>
- Commits: <sha(s)>; closing docs (CHANGELOG + chat-34-closing.md) committed;
  NOT pushed-confirmed — operator pushes via Save to GitHub.
- IMPORTANT: name test files EXACTLY per §R5 (no single-file consolidation —
  the 2.6 split-file miss must not recur).
```

**STOP gates real. No auto-advance past §R0. No scope additions — log ideas to
backlog. Name test files exactly as §R5 specifies.**
