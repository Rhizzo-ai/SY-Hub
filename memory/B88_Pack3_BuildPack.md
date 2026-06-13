# Build Pack — B88 Pack 3: Packages (Tendering Spine)

**Repo:** `Rhizzo-ai/SY-Hub` · **Target branch:** `main`
**Alembic baseline:** head `0046_rbac_operator_overrides` (down `0045`).
**Drafted:** Chat 53. **Status:** ready for Emergent execution through STOP gates.
**Path truth:** routers carry NO internal prefix; they mount on `v1_router`
(`prefix="/v1"`) which mounts on `api_router` (`prefix="/api"`). External
surface for everything in this pack is therefore **`/api/v1/...`**. Treat live
OpenAPI as authoritative.

---

## 0. PURPOSE & SCOPE

Packages are the **tendering spine**: bundle existing budget lines (with their
quantity/unit/rate detail) into a procurement package, send to multiple
bidders, capture priced bids, and **award** — to one winner or split across
several — where each award **creates a Purchase Order (materials) or a
Subcontract (labour)** using the EXISTING, proven services. No new
money-rollup machinery is built; awards feed the existing
`committed_value` (PG trigger) + `committed_not_invoiced`
(`budgets_reconciliation.recompute_for_*`) chain unchanged.

### In scope (this pack)
- New tables: `packages`, `package_lines`, `package_bids`, `package_bid_lines`,
  `package_awards`, `package_award_lines`.
- New permission resource `packages` (added to `seed_rbac.py`).
- New router `backend/app/routers/packages.py` mounted on `v1_router`.
- New service `backend/app/services/packages.py`.
- Award orchestration calling EXISTING `services.purchase_orders.create_*`
  and `services.subcontracts.create_subcontract`.
- Admin/management frontend at `/admin/packages` (list + detail + bid entry +
  award flow). Mobile-responsive per platform constraint.
- Alembic migration `0047_packages`.

### Explicitly OUT of scope (deferred — DO NOT BUILD)
- Nesting package/commitment rows under budget lines on the Pack 2
  job-costing grid → **Pack 4**.
- Side-by-side bid-levelling comparison grid, multi-package dashboards,
  tender-document attachments, bid scoring → **Pack 3.5** (logged to backlog
  by operator, not by you).
- Subcontract **variation** API endpoints (B80) — separate item.
- Any change to PO / subcontract / budget / reconciliation internals beyond
  calling their existing public service functions.

### Locked design decisions (operator-confirmed, Chat 53)
- **LD-P1** A package groups existing `budget_lines` (by reference, NOT
  containment — budget lines are never moved or owned by a package).
- **LD-P2** Package `kind` ∈ {`labour`, `materials`}. `labour` awards →
  Subcontracts; `materials` awards → Purchase Orders. A package is
  single-kind (no mixed package in v1).
- **LD-P3** **Split awards permitted** — one package may be awarded across
  multiple winners. The hard guard: **Σ(award net) ≤ package total net**.
  Enforced server-side, transactionally, under row locks. This is the
  money-integrity crux of the pack.
- **LD-P4** Bid line quantities/units are **inherited from the package line
  (which inherits from the budget line item detail)** and are NOT editable by
  the bidder-entry form — bidders compete on **rate**, not measurement. The
  package line carries `quantity`, `unit`, and a `budgeted_unit_rate` /
  `budgeted_net_amount`; the bid line carries `quoted_unit_rate` /
  `quoted_net_amount` for the same quantity.
- **LD-P5** "Usual" fast-track: a package may be awarded **directly without a
  competitive bid round** (`award_without_tender`), which internally
  synthesises a single winning bid from entered figures. No separate code
  path for the award itself — same award engine.
- **LD-P6** Add-bidder-on-the-fly = the EXISTING `POST /api/v1/suppliers`
  (`suppliers.create`). The package UI links to it; no new supplier-create
  code in this pack.
- **LD-P7** Permissions reuse the established tier semantics:
  - `packages.view` / `packages.view_sensitive` (sensitive = bid pricing)
  - `packages.create` / `packages.edit`
  - `packages.award` (**sensitive**, money-authorising — mirrors
    `pos.approve` / `subcontracts.approve` distribution; held by
    super_admin/director/finance)
  - `packages.delete` (**sensitive**, super_admin only)
  The award authority bar is `packages.award` alone. The downstream PO/SC is
  created service-side on the system's behalf; we do NOT additionally require
  the caller to hold `pos.create`/`subcontracts.create` (finance — the
  intended awarder — deliberately lacks create; see §6).

---

## 1. DATA MODEL

New file `backend/app/models/packages.py`. Pattern α tenant scoping:
`packages` carries denormalised `tenant_id` (mirrors `purchase_orders` /
`subcontracts`); child tables do not (resolved via parent). All money
`Numeric(14, 2)`; quantities `Numeric(14, 4)`; rates `Numeric(14, 4)`.

### 1.1 `packages`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` server default |
| `tenant_id` | UUID FK tenants ON DELETE RESTRICT, NOT NULL | denormalised, indexed |
| `project_id` | UUID FK projects ON DELETE RESTRICT, NOT NULL | |
| `budget_id` | UUID FK budgets ON DELETE RESTRICT, NOT NULL | the budget whose lines are referenced |
| `reference` | String(30) NOT NULL | `PKG-NNNN`, per-project sequence (lock project row, same pattern as `_next_reference` in subcontracts service) |
| `title` | String(200) NOT NULL | |
| `kind` | PG enum `package_kind` (`labour`,`materials`) NOT NULL | LD-P2 |
| `status` | PG enum `package_status` NOT NULL default `draft` | see §2 state machine |
| `description` | Text NULL | |
| `total_net` | Numeric(14,2) NOT NULL default 0 | cached Σ package_lines.budgeted_net_amount; single-writer = service |
| `awarded_net` | Numeric(14,2) NOT NULL default 0 | cached Σ active award_lines.awarded_net |
| `out_to_tender_at` / `_by` | timestamptz / UUID FK users NULL | |
| `awarded_at` / `_by` | timestamptz / UUID FK users NULL | |
| `cancelled_at` / `_by` / `_reason` | timestamptz / UUID / Text NULL | |
| `created_at`/`created_by`/`updated_at`/`updated_by` | standard | created_by/updated_by FK users NOT NULL |

Constraints: `UniqueConstraint(project_id, reference)`;
`CheckConstraint` mirroring the enum value sets (belt-and-braces, named);
indexes `ix_packages_tenant_id`, `ix_packages_project_status`.

### 1.2 `package_lines`
A reference to a budget line, plus the carried-through measurement detail.
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `package_id` | UUID FK packages ON DELETE CASCADE NOT NULL | |
| `budget_line_id` | UUID FK budget_lines ON DELETE RESTRICT NOT NULL | the referenced line — RESTRICT so a referenced line can't be hard-deleted out from under a package |
| `cost_code` | String(20) NOT NULL | snapshot for display/PO line (mirror PO line pattern) |
| `line_number` | Integer NOT NULL | 1-based within package |
| `description` | Text NOT NULL | defaults from budget_line.line_description, editable |
| `quantity` | Numeric(14,4) NOT NULL default 1 | LD-P4 carried through; the competed-on measurement |
| `unit` | String(20) NULL | |
| `budgeted_unit_rate` | Numeric(14,4) NOT NULL | from budget line item detail or derived (net/qty) |
| `budgeted_net_amount` | Numeric(14,2) NOT NULL | your budget figure for this line |
| `notes` | Text NULL | |
| standard stamps | | |

Constraints: `UniqueConstraint(package_id, budget_line_id)` (a budget line
appears at most once per package); `UniqueConstraint(package_id, line_number)`;
index `ix_package_lines_package_id`, `ix_package_lines_budget_line_id`.

### 1.3 `package_bids`
One row per invited bidder.
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `package_id` | UUID FK packages ON DELETE CASCADE NOT NULL | |
| `supplier_id` | UUID FK suppliers ON DELETE RESTRICT NOT NULL | the bidder (existing or freshly created via suppliers.create) |
| `status` | PG enum `package_bid_status` (`invited`,`received`,`declined`,`withdrawn`) NOT NULL default `invited` | |
| `total_net` | Numeric(14,2) NOT NULL default 0 | cached Σ bid_lines.quoted_net_amount |
| `received_at` | timestamptz NULL | set when bid figures entered |
| `notes` | Text NULL | |
| standard stamps | | |

Constraints: `UniqueConstraint(package_id, supplier_id)` (a supplier invited
once per package); index `ix_package_bids_package_id`,
`ix_package_bids_supplier_id`.

### 1.4 `package_bid_lines`
The bidder's priced line. Quantity/unit are NOT stored here — they are the
package line's (LD-P4). Only the rate + derived net are the bid's.
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `package_bid_id` | UUID FK package_bids ON DELETE CASCADE NOT NULL | |
| `package_line_id` | UUID FK package_lines ON DELETE CASCADE NOT NULL | |
| `quoted_unit_rate` | Numeric(14,4) NOT NULL | the bidder's rate for the package line's fixed quantity |
| `quoted_net_amount` | Numeric(14,2) NOT NULL | service-computed = round(quantity × quoted_unit_rate, 2); validated server-side, never trusted from client |
| `notes` | Text NULL | |
| standard stamps | | |

Constraints: `UniqueConstraint(package_bid_id, package_line_id)`;
index `ix_package_bid_lines_bid_id`.

### 1.5 `package_awards`
One row per winner. A package may have several active awards (LD-P3).
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `package_id` | UUID FK packages ON DELETE CASCADE NOT NULL | |
| `supplier_id` | UUID FK suppliers ON DELETE RESTRICT NOT NULL | the winner |
| `source_bid_id` | UUID FK package_bids ON DELETE SET NULL NULL | the bid this award was struck from; NULL for fast-track (LD-P5) |
| `status` | PG enum `package_award_status` (`active`,`cancelled`) NOT NULL default `active` | |
| `awarded_net` | Numeric(14,2) NOT NULL | Σ award_lines.awarded_net; participates in the Σ-guard |
| `created_purchase_order_id` | UUID FK purchase_orders ON DELETE SET NULL NULL | set for materials awards |
| `created_subcontract_id` | UUID FK subcontracts ON DELETE SET NULL NULL | set for labour awards |
| `cancelled_at`/`_by`/`_reason` | | |
| standard stamps | | |

Constraints: `CheckConstraint` that **exactly one** of
`created_purchase_order_id` / `created_subcontract_id` is non-null when
`status='active'` (named `ck_package_awards_one_downstream`); index
`ix_package_awards_package_id`.

### 1.6 `package_award_lines`
Which package lines (and how much of each) this award covers. Supports the
split: different award_lines for the same `package_line_id` across different
awards must sum ≤ that line's budgeted_net (per-line guard) AND total awards ≤
package total (header guard).
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `package_award_id` | UUID FK package_awards ON DELETE CASCADE NOT NULL | |
| `package_line_id` | UUID FK package_lines ON DELETE RESTRICT NOT NULL | |
| `quantity` | Numeric(14,4) NOT NULL | the slice of the line's quantity awarded to this winner (default = full line qty for a non-split award) |
| `awarded_unit_rate` | Numeric(14,4) NOT NULL | the winning rate (from bid line, or fast-track entry) |
| `awarded_net` | Numeric(14,2) NOT NULL | service-computed = round(quantity × awarded_unit_rate, 2) |
| standard stamps | | |

Constraints: `UniqueConstraint(package_award_id, package_line_id)`;
index `ix_package_award_lines_award_id`,
`ix_package_award_lines_package_line_id`.

> **Split semantics note for the service author:** v1 split is **by line and
> by quantity within a line**. A package line of qty 100 may be awarded
> 60 units to winner A and 40 to winner B. The per-line guard is
> Σ(award_line.quantity for that package_line across active awards) ≤
> package_line.quantity (NOT the net — quantity is the physical measure and
> must not be over-committed). The header guard is the net-money guard
> (LD-P3). BOTH are enforced.

---

## 2. STATE MACHINES

### Package status
```
draft ──(send_to_tender)──▶ out_to_tender ──(award*)──▶ partially_awarded ──(award*)──▶ awarded
  │                              │                            │
  │ (award_without_tender, LD-P5)│                            │
  └──────────────────────────────┴────────────────────────────┘
  draft / out_to_tender / partially_awarded ──(cancel)──▶ cancelled  (terminal)
```
- `package_status` enum values: `draft`, `out_to_tender`, `partially_awarded`,
  `awarded`, `cancelled`.
- A package becomes `awarded` when `awarded_net == total_net` (fully awarded,
  within a £0.01 tolerance) OR operator explicitly closes it; becomes
  `partially_awarded` when `0 < awarded_net < total_net`.
- `cancelled` is terminal. Cancelling a package with active awards is
  **blocked** (must cancel awards first — see §3 cancel award).
- Editing package **lines** is allowed only in `draft`. In `out_to_tender`,
  lines are frozen (bids are against them). Header annotations
  (`title`, `description`, `notes`) editable until terminal.

### Package bid status
`invited` → `received` (figures entered) → may go `declined` / `withdrawn`
(terminal-ish; a withdrawn/declined bid cannot be the source of a new award).
Entering figures sets `received` + `received_at`.

### Package award status
`active` → `cancelled`. Cancelling an award **must** also handle the
downstream PO/SC — see §3.

---

## 3. SERVICE LAYER — `backend/app/services/packages.py`

Audit pattern: service-layer `record_audit` + `field_diff` (import from
`app.services.audit`), identical to `services/subcontracts.py`. Every
create / mutate / state-transition / award / cancel records an audit row.
`_snapshot()` + `field_diff()` for updates; explicit action strings for
transitions (e.g. `package.send_to_tender`, `package.award`,
`package.award_cancelled`).

Scope: replicate `_visible_project_ids` / `_scope_check_project` from
`services/subcontracts.py` verbatim in intent (cross-tenant load returns
"not found", never 403-leak of existence).

### 3.1 Core CRUD
- `create_package(db, *, project_id, budget_id, title, kind, user, perms,
  description=None, request=None) -> Package`
  - Validate project visible + budget belongs to project + budget not in a
    terminal status (`Superseded`/`Closed` → reject: cannot tender against a
    dead budget).
  - Lock project row, allocate `PKG-NNNN`.
  - `total_net = 0`, status `draft`.
- `add_package_line(db, *, package_id, budget_line_id, user, perms,
  description=None, quantity=None, unit=None, budgeted_unit_rate=None,
  request=None)`
  - Only when package `draft`.
  - Validate `budget_line_id` belongs to `package.budget_id` (reuse the exact
    membership check from `services/purchase_orders._validate_budget_lines`).
  - Inherit `cost_code` (derive via budget line FK, mirror
    `_budget_line_cost_code`), `description` (← `line_description`),
    `quantity`/`unit`/rate from the budget line's **item detail** where
    present; if the line has multiple items, default `quantity=1`,
    `budgeted_unit_rate=current_budget`, `budgeted_net_amount=current_budget`
    and flag in `notes` that detail should be confirmed (NEVER silently
    fabricate quantities). Service computes `budgeted_net_amount =
    round(quantity × budgeted_unit_rate, 2)`.
  - Recompute `package.total_net`.
- `update_package` (header annotations + `update_package_line` for draft-only
  line edits) — both recompute `total_net` where money changes; `field_diff`
  audit.
- `remove_package_line` (draft only); recompute.
- `delete_package` (`packages.delete`) — only `draft` or `cancelled`, only
  when zero active awards. Hard delete cascades children. Audit
  `package.deleted`.

### 3.2 Tender round
- `send_to_tender(db, *, package_id, user, perms, request=None)`
  - `draft` → `out_to_tender`; requires ≥1 package line; stamps
    `out_to_tender_at/_by`. Freezes lines.
- `invite_bidder(db, *, package_id, supplier_id, user, perms, request=None)`
  - Package must be `out_to_tender`. Validate supplier exists + tenant scope.
  - **Kind/type coherence guard:** for `kind='labour'`, supplier
    `supplier_type` must be `Contractor` (mirror the subcontract LD2 guard);
    for `kind='materials'`, supplier_type must be `Supplier` OR `Contractor`
    (materials can come from either — warn-not-block if `Contractor`).
    Reject `Consultant`/`Other` for both with a clear 422.
  - Creates `package_bids` row (`invited`). Idempotent on
    `(package_id, supplier_id)` → 409 if already invited.
- `enter_bid(db, *, package_bid_id, lines, user, perms, request=None)`
  - `lines` = list of `{package_line_id, quoted_unit_rate}`. Service computes
    `quoted_net_amount = round(package_line.quantity × quoted_unit_rate, 2)`.
    NEVER trust a client-supplied net.
  - Upserts `package_bid_lines`; sets bid `received` + `received_at`;
    recomputes bid `total_net`. Validate every `package_line_id` belongs to
    the bid's package; reject unknown/foreign lines (422).
- `decline_bid` / `withdraw_bid` — status transitions, audit.

### 3.3 Award engine (THE CRITICAL PATH)
`award_package(db, *, package_id, awards, user, perms, request=None)`

`awards` = list of award specs, each:
```
{
  "supplier_id": UUID,
  "source_bid_id": UUID | null,          # null = fast-track (LD-P5)
  "lines": [ { "package_line_id": UUID,
               "quantity": Decimal,       # slice; default = full line qty
               "awarded_unit_rate": Decimal } ],
  # materials-only PO header hints (optional): required_by_date, delivery_address
  # labour-only SC header hints (optional): retention_pct, cis_applies, scope_description
}
```

**Permission gate:** caller holds `packages.award`. (No additional
`pos.create`/`subcontracts.create` requirement — see §6 defence-in-depth
resolution; the downstream is created service-side.) Missing
`packages.award` → 403.

**Transaction & locking (single DB transaction, all-or-nothing):**
1. Load + **lock the package row FOR UPDATE** (serialises concurrent awards —
   prevents two awards each individually passing the Σ-guard but jointly
   breaching it; this is the classic lost-update hazard and MUST be covered by
   a test, see §5 T-AW-9).
2. Package status must be `out_to_tender` or `partially_awarded`
   (or `draft` only when ALL specs are fast-track, LD-P5 — in which case
   transition draft→… directly).
3. Validate each award spec:
   - supplier scope + kind/type coherence (as §3.2 invite guard).
   - if `source_bid_id` given: bid belongs to package, is `received`, supplier
     matches, and each awarded line's `awarded_unit_rate` equals the bid line's
     `quoted_unit_rate` (award must reflect the bid struck — no silent
     re-pricing; if operator wants a different rate that's a fast-track award,
     `source_bid_id=null`).
   - every `package_line_id` belongs to the package.
   - `quantity` per line > 0 and ≤ remaining un-awarded quantity for that
     package line (**per-line quantity guard**, across existing active awards).
   - `awarded_net` computed server-side = round(quantity × awarded_unit_rate, 2).
4. **Header money guard (LD-P3):** Σ(new awarded_net) + existing active
   `package.awarded_net` ≤ `package.total_net` + £0.01 tolerance. Breach →
   422 with a precise message naming the overage. **No partial application** —
   reject the whole call.
5. For each validated award spec, create the `package_awards` +
   `package_award_lines` rows, then **call the existing downstream service**:
   - **materials** → `services.purchase_orders.create_po(...)`. **Exact live
     signature (verified Chat 53):**
     `create_po(db, *, user, perms, project_id, payload, request=None)
     -> PurchaseOrder`, where `payload` is a dict carrying `supplier_id`,
     `budget_id`, and `lines` (plus optional `required_by_date`,
     `delivery_address`, `delivery_notes`, `notes`, `approval_required`,
     `approval_reason`). Each line dict requires
     `budget_line_id`, `cost_code`, `description`, `quantity`, `unit_rate`
     (the service computes `vat_amount`/`gross_amount`/`net_amount` itself —
     supply `unit_rate=awarded_unit_rate`, `quantity`, and let the service
     derive net; pass `vat_rate` only if non-default 20.00). Store the
     returned `PurchaseOrder.id` in `created_purchase_order_id`. The PO is
     created in its native initial status (`draft`) — awarding does NOT
     auto-issue; the PO then follows its own approve/issue lifecycle, at which
     point the EXISTING trigger + `recompute_for_po` flow commitments onto the
     budget line. **Do not replicate any commitment math.**
     > NB: confirm against live OpenAPI/source whether `create_po` derives
     > `net_amount` internally or expects it on the line dict — the docstring
     > lists `unit_rate`+`quantity` as required but not `net_amount`. Match
     > the live behaviour exactly; if it expects `net_amount`, pass
     > `awarded_net`. STOP and report if ambiguous.
   - **labour** → `services.subcontracts.create_subcontract(...)`. **Exact
     live signature (verified Chat 53):** `create_subcontract(db, *,
     project_id, subcontractor_id, title, user, perms,
     purchase_order_id=None, scope_description=None, original_contract_sum=0,
     retention_pct=0, cis_applies=True, start_on=None, end_on=None,
     request=None)`. Pass `subcontractor_id=supplier_id`,
     `original_contract_sum=awarded_net`, `title` derived from package,
     retention/cis hints from the award spec. The subcontractor's
     `supplier_type` MUST be `Contractor` (the service enforces LD2 and will
     raise otherwise — the package invite guard should already have prevented
     a non-Contractor labour bidder). Store returned `Subcontract.id` in
     `created_subcontract_id`. **The subcontract is created `Draft` and is NOT
     auto-activated** — activation requires `signed_at` to be set and is done
     by the operator in the subcontracts module (the service raises
     `SubcontractStateError` on activate if unsigned). Awarding therefore
     records the commitment intent; the subcontract's own lifecycle governs
     when it becomes Active. Commitment rollup onto the budget line happens via
     any linked PO + the existing reconciliation — a Draft subcontract alone
     does not move `committed_value` (that is correct and expected).
6. Recompute `package.awarded_net`; set package status
   (`partially_awarded` / `awarded`); stamp `awarded_at/_by` on first award.
7. Single `record_audit` per award (`package.award`) capturing
   supplier, source_bid_id, awarded_net, and the created downstream id.
8. Commit. Any failure at any step → full rollback (no orphan PO/SC, no
   half-applied award). Because the downstream create services run in the SAME
   session/transaction, a raise after a PO create rolls the PO back too —
   **verify this is true in test T-AW-10** (no autocommit inside the create
   services).

`cancel_award(db, *, package_award_id, reason, user, perms, request=None)`
- `packages.award` required.
- Only when the **downstream PO/SC is still safely reversible**: PO must be in
  `draft`/`pending_approval` (not yet `issued` or receipted); subcontract must
  be `Draft` (not `Active`). If the downstream has progressed, **block** with a
  clear 409 ("award's purchase order has been issued; void it there first").
  Do NOT auto-void/auto-terminate the downstream from here in v1 (keeps
  authority where it belongs). 
- On allowed cancel: mark award `cancelled`, recompute `package.awarded_net`,
  re-open package status (`awarded`→`partially_awarded`, or
  `partially_awarded`→`out_to_tender` if awarded_net returns to 0), audit
  `package.award_cancelled`. The downstream draft PO/SC is left for the
  operator to delete in its own module (or optionally delete it here ONLY if
  trivially in `draft` — operator decision; default = leave it, document in
  CHANGELOG).
- `cancel_package(db, ...)` — blocked if any active awards; else
  `→ cancelled`.

### 3.4 Read/serialise
- `serialise_package(p, *, with_sensitive)` — `with_sensitive` gates bid
  pricing (`packages.view_sensitive`). Without it: bidder names + statuses
  visible, but `total_net`, bid `total_net`, all rates/nets **redacted**
  (return `null` or omit), mirroring the suppliers/subcontracts sensitive
  pattern.
- `get_package`, `list_packages(project_id=..., status=..., kind=...)`.
- `list_bids(package_id)`, `get_bid(bid_id)`.

---

## 4. ROUTER — `backend/app/routers/packages.py`

`router = APIRouter(tags=["packages"])` — NO prefix. Mount on `v1_router` in
`backend/server.py` (add `v1_router.include_router(packages_router)` adjacent
to subcontracts). External paths below are the live surface.

Gate every route with `Depends(require_permission("packages.<x>"))` exactly as
`routers/subcontracts.py` does. `view_sensitive` is checked inside the handler
(`perms.has("packages.view_sensitive")`) and passed to `serialise_*`.

| method | path | permission | notes |
|---|---|---|---|
| POST | `/projects/{project_id}/packages` | `packages.create` | body: budget_id, title, kind, description |
| GET | `/projects/{project_id}/packages` | `packages.view` | filters: status, kind |
| GET | `/packages` | `packages.view` | cross-project list (visible scope) |
| GET | `/packages/{package_id}` | `packages.view` | includes lines, bids, awards |
| PATCH | `/packages/{package_id}` | `packages.edit` | header annotations |
| DELETE | `/packages/{package_id}` | `packages.delete` | draft/cancelled, zero active awards → 204 |
| POST | `/packages/{package_id}/lines` | `packages.edit` | draft only |
| PATCH | `/packages/{package_id}/lines/{line_id}` | `packages.edit` | draft only |
| DELETE | `/packages/{package_id}/lines/{line_id}` | `packages.edit` | draft only → 204 |
| POST | `/packages/{package_id}/send-to-tender` | `packages.edit` | draft→out_to_tender |
| POST | `/packages/{package_id}/cancel` | `packages.edit` | → cancelled (guarded) |
| POST | `/packages/{package_id}/bids` | `packages.edit` | invite bidder (supplier_id) |
| GET | `/packages/{package_id}/bids` | `packages.view` | bid list (pricing gated) |
| POST | `/bids/{bid_id}/enter` | `packages.edit` | enter priced lines |
| POST | `/bids/{bid_id}/decline` | `packages.edit` | |
| POST | `/bids/{bid_id}/withdraw` | `packages.edit` | |
| POST | `/packages/{package_id}/award` | `packages.award` | the award engine; body = awards[] |
| POST | `/awards/{award_id}/cancel` | `packages.award` | guarded reversal |

Error contract: validation → 422 (Pydantic + service `ValueError` mapped to
422 with message); not-found / cross-tenant → 404; state-machine breach →
409; permission → 403. Mirror the exact exception-to-HTTP mapping already used
in `routers/subcontracts.py` (reuse its `_err` / exception classes pattern).

Pydantic request/response schemas in
`backend/app/schemas/packages.py` (new). All money/qty fields `Decimal` with
`max_digits`/`decimal_places` matching the columns; reject negative.

---

## 5. TESTS — `backend/tests/test_packages.py` (+ service test file)

**File names EXACTLY:** `backend/tests/test_packages.py` (HTTP-layer) and
`backend/tests/test_packages_service.py` (service-layer). No single-file
consolidation. Target **≥ 55 test functions** total. WARM-DB second run is the
authoritative pass.

Coverage map (each a distinct function):

**Model/migration (service file)**
- T-M-1 migration up creates all 6 tables + 4 enums; down drops cleanly.
- T-M-2 enum value sets exact; check constraints present.
- T-M-3 `ck_package_awards_one_downstream` rejects both-null and both-set on active.

**Package CRUD**
- T-PK-1..6 create (happy), reject terminal budget, reject foreign budget,
  PKG-NNNN sequence + per-project uniqueness, add/remove line draft-only,
  line edit recomputes total_net.
- T-PK-7 add line rejects budget_line from a different budget (422).
- T-PK-8 line inherits cost_code/description/qty/unit/rate from budget line item.
- T-PK-9 delete blocked when active award exists; allowed when draft.

**Tender**
- T-TN-1 send_to_tender requires ≥1 line; draft→out_to_tender.
- T-TN-2 lines frozen after tender (edit → 409).
- T-TN-3 invite bidder; duplicate invite → 409.
- T-TN-4 labour package rejects non-Contractor bidder (422).
- T-TN-5 materials package accepts Supplier; warns on Contractor.
- T-TN-6 enter_bid computes net = qty × rate; ignores client net.
- T-TN-7 enter_bid rejects foreign package_line_id (422).
- T-TN-8 decline/withdraw transitions; declined bid not awardable.

**Award engine (the crux)**
- T-AW-1 single full award (materials) creates a PO in `draft` with correct
  lines (budget_line_id, qty, rate, net) and links created_purchase_order_id.
- T-AW-2 single full award (labour) creates a Subcontract `Draft` with
  original_contract_sum = awarded_net and links created_subcontract_id.
- T-AW-3 **split award** across two suppliers, both within total → both
  succeed; awarded_net = sum; status `partially_awarded` then `awarded`.
- T-AW-4 **header Σ-guard**: award totalling > package total_net → 422,
  NOTHING created (assert zero POs/SCs, awarded_net unchanged).
- T-AW-5 **per-line quantity guard**: awarding more units of a line than
  remain → 422.
- T-AW-6 fast-track award (`source_bid_id=null`) from draft → creates
  downstream; LD-P5.
- T-AW-7 award with source_bid_id must match bid rate (mismatch → 422).
- T-AW-8 award requires `packages.award`; a caller holding create/edit but
  NOT award (e.g. project_manager) → 403. A finance caller (award but not
  pos.create) CAN award successfully (proves the downstream is created
  service-side, not gated on the caller's create perm).
- **T-AW-9 concurrency**: two concurrent award calls each individually valid
  but jointly breaching total — second must fail under the FOR UPDATE lock
  (serialised), total never exceeded. (Use the same concurrency test harness
  pattern as the budgets lock tests.)
- **T-AW-10 atomicity**: force a failure AFTER a downstream PO create within a
  multi-award call → assert full rollback (no PO row persists, no award row,
  package.awarded_net unchanged).
- T-AW-11 awarded_net tolerance: award summing to total_net within £0.01 →
  status `awarded`.

**Cancel**
- T-CX-1 cancel award whose PO is still draft → award cancelled, awarded_net
  recomputed, package re-opened.
- T-CX-2 cancel award whose PO is `issued` → 409 (blocked).
- T-CX-3 cancel award whose SC is `Active` → 409.
- T-CX-4 cancel_package blocked with active award; allowed when none.

**Permissions / scope / sensitive**
- T-PM-1 each mutating route 403s without its permission.
- T-PM-2 cross-tenant package load → 404 (not 403).
- T-PM-3 `view` without `view_sensitive` redacts all pricing
  (package total_net, bid totals, rates, nets all null/omitted).
- T-PM-4 `view_sensitive` reveals pricing.

**Audit**
- T-AD-1 create / send_to_tender / award / award_cancelled each write an
  audit row with correct action + actor.
- T-AD-2 award audit row records created downstream id + awarded_net.

**Reconciliation integration (proves the chain, no new math)**
- T-RC-1 after a materials award's PO is moved to `approved`/`issued` via the
  EXISTING PO endpoints, the referenced budget line's `committed_value` /
  `committed_not_invoiced` reflect the award (calls real PO transition +
  asserts the existing reconciliation ran). This is the "every pound
  traceable" end-to-end proof.

**RBAC seed**
- T-RB-1 `packages.*` permissions present, count delta correct, sensitive set
  = {view_sensitive, award, delete}; default custom-role grants exclude
  award/delete (matches B83 default-grant rule).

---

## 6. RBAC SEED CHANGES — `backend/app/seed_rbac.py`

Day-one role grants — **mirror the EXACT live `pos` / `subcontracts`
distribution, which is verified below (Chat 53). Do not invent.**

The live pattern (confirmed in `seed_rbac.py`):
- **director** is granted via `set(ALL_PERMISSION_CODES) - {exclusions}` — i.e.
  director gets EVERYTHING not explicitly excluded. **This is a trap:**
  `packages.award` and `packages.view_sensitive` will be granted to director
  automatically (correct — director should award). But **`packages.delete`
  must be ADDED to the director exclusion set** to keep delete super_admin-only
  (exactly as `cost_codes.delete` is excluded — same counter-intuitive math).
  Add `"packages.delete"` to the `ROLE_PERMISSIONS["director"]` exclusion set.
- **project_manager** — PM *creates and edits* but does NOT hold the
  money-authorising act (PM has `pos.create/edit` but NOT `pos.approve`;
  `subcontracts.create/edit` but NOT `subcontracts.approve`). So PM gets:
  `packages.view, packages.view_sensitive, packages.create, packages.edit`.
  **PM does NOT get `packages.award`.**
- **finance** — finance holds the *authorising* act but NOT create/edit
  (finance has `pos.approve` but NOT `pos.create`; `subcontracts.approve` but
  NOT create). Finance gets: `packages.view, packages.view_sensitive,
  packages.award`.
- **read_only / investor_read_only** — `packages.view` only (NOT
  view_sensitive).
- **site_manager / sales / others** — none (confirm against live; site_manager
  has only `pos.view, pos.receipt` — give site_manager nothing on packages in
  v1 unless operator says otherwise).

> **DEFENCE-IN-DEPTH RESOLUTION (read carefully — this corrects an internal
> tension):** the award engine's secondary gate must NOT require the literal
> `pos.create` / `subcontracts.create` permission, because **finance is the
> intended awarder and finance deliberately lacks create** (create lives with
> PM). Requiring `pos.create` would lock finance out of awarding — wrong.
> **Therefore the award engine's authority gate is simply `packages.award`.**
> The downstream PO/SC is created by the SERVICE acting on the system's
> behalf (service-layer create, not a re-check of the caller's PO/SC create
> perm). `packages.award` is itself a sensitive, money-authorising permission
> held only by super_admin/director/finance — that IS the authority bar.
> **Remove the "+ downstream create perm" requirement everywhere it appears in
> this pack** (§0 LD-P7, §3.3 permission gate, §4 award row, test T-AW-8).
> Replace T-AW-8 with: "award requires `packages.award`; a caller with
> create/edit but not award (e.g. project_manager) gets 403."

Add the permission block adjacent to the `pos` / `subcontracts` blocks:
```python
# Chat 53 §B88 Pack 3 — Packages (tendering spine).
# sensitive: view_sensitive (bid pricing), award (money-authorising),
# delete (destructive).
PERMISSION_CATALOGUE += _perms_for(
    "packages",
    include=["view", "view_sensitive", "create", "edit", "award", "delete"],
    sensitive={"view_sensitive", "award", "delete"},
)
```
And add `"packages.delete"` to the director exclusion set (see trap above).

Permission count: baseline 136 → **142** (6 new). Roles unchanged (10 +
custom). Because B83 shipped, new permissions auto-grant to custom roles per
the default-grant rule (non-sensitive AND action ∉ delete/admin/void) — so
custom roles get view/create/edit by default, NOT award/delete. State the new
count explicitly in the gate report.

---

## 7. FRONTEND — `/admin/packages`

Stack/area mirrors `RolePermissionsAdmin.jsx` conventions; API layer
`frontend/src/lib/api/packages.js`. Brand teal `#0F6A7A`, orange `#FC7827`,
grey `#CECECE`. Mobile-responsive (site users may view).

Screens:
1. **List** (`/admin/packages`): table — reference, title, kind, status pill,
   total_net, awarded_net, progress. Filters status/kind/project. "New
   package" button.
2. **Detail** (`/admin/packages/:id`):
   - Header: reference, title, kind, status, totals (pricing gated on
     `packages.view_sensitive`).
   - **Lines tab**: package lines with budget figures; add/edit/remove in
     draft (line picker pulls budget lines from the package's budget via
     existing budgets API).
   - **Bids tab** (when out_to_tender+): invited bidders, statuses, totals;
     "Invite bidder" (supplier picker + link to create-supplier using existing
     suppliers screen, LD-P6); "Enter bid" form (rate per line; net shown
     live, computed client-side for display but authoritative server-side).
   - **Award panel**: select winner(s); for split, allocate lines/quantities;
     live running total with a **hard visual block + disabled submit when
     Σ award > package total** (mirror the server guard — but server is
     authoritative). "Award without tender" fast-track entry (LD-P5).
   - On award success: show created PO/SC references with links to their
     existing module screens.
   - Cancel award (guarded; surfaces the 409 reason visibly).
3. Mutations: every mutation handler surfaces errors **visibly** (no silent
   onError) — the live-eyeball lesson. A failed award must show the exact
   server message (e.g. the Σ-guard overage).

Frontend tests: component tests for list, line editing, bid entry net
computation, award allocation + over-total block, sensitive redaction.
Target ≥ 25 frontend test functions. **But the gate is the live eyeball**, not
the count.

---

## 8. GATES (STOP — no auto-advance)

### GATE 1 — BACKEND (HARD STOP: money/permission/data)
Build §1–§6. Then STOP and report:
1. `alembic upgrade head` → confirm new head `0047_packages`; `alembic
   downgrade -1` then `upgrade head` clean (idempotent).
2. **Two pytest runs** (cold then WARM-DB); report both counts. WARM is
   authoritative. All `test_packages*.py` green.
3. Permission count printed = **142**; roles = 10 (+ any custom).
4. **Live-API proof (not just suite counts)** — against the running pod, via
   real HTTP with a seeded super_admin session, paste the actual
   request/response for:
   a. create package (materials) + add 2 lines → show total_net.
   b. send-to-tender + invite 2 bidders + enter 2 bids.
   c. **split award** within total → show 2 awards, 2 created PO ids, package
      status `partially_awarded`/`awarded`, awarded_net.
   d. **over-total award attempt** → show the 422 + that no PO was created.
   e. move one created PO to `issued` via the EXISTING PO endpoint → fetch the
      referenced budget line → show `committed_value` /
      `committed_not_invoiced` now reflect the award (the end-to-end pound-
      traceability proof).
5. OpenAPI: list the new `/api/v1/...` package paths as actually served.
Do NOT proceed to frontend until I verify this gate on origin/main per-file.

### GATE 2 — FRONTEND + DOCS (eyeball stop; docs batched in — no money risk)
Build §7. Then STOP and report:
1. Frontend test counts (both runs if applicable).
2. **Live eyeball**: load `/admin/packages` on the running dev server (prove
   the dev-server path compiles — screenshot or explicit confirmation of the
   rendered screen, not just passing tests). Walk the full flow in the UI:
   create → tender → bid → split award → see PO/SC links → attempt over-total
   (must block visibly).
3. CHANGELOG entry (Pack 3) + `docs/chat-summaries/chat-53-closing.md` drafted
   and committed in the same push. **Do NOT touch
   `docs/SY_Hub_Phase2_Backlog.md`** (operator-only).
4. Confirm both commits pushed; list every changed file for per-file
   verification.

---

## 9. NON-NEGOTIABLE BUILD RULES (carried)
- Read the actual live PO + subcontract + budgets-reconciliation service
  signatures before wiring the award engine — call them EXACTLY as they exist;
  do not assume parameter names. If a signature differs from this pack, STOP
  and report the discrepancy rather than guessing.
- Committed ≠ pushed; verify per-file on origin/main.
- No Force Push; conflict → Branch → PR → merge → wait 60s → verify.
- The award engine is one DB transaction, all-or-nothing, package row locked.
- Server computes every net (qty × rate); client nets are display-only and
  never trusted.
- Mutation handlers surface errors visibly.
- Test files named exactly as §5.

---
*End Build Pack — B88 Pack 3.*
