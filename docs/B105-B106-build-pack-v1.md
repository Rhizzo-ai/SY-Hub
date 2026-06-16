# BUILD PACK — B105 / B106: Cost-Code-First Commercial Line Model

**Chat:** 59 · **Track:** 2 (Commercial Engine) · **Type:** Money-path redesign
**Drafted against:** `origin/main` @ alembic head `0049_unbudgeted_order_lines`
(re-read line-by-line at draft time; main unchanged since Chat 58).
**Design source (LOCKED):** `B105-B106-cost-code-first-design-v2-LOCKED.md` (Chat 58).
**Operator decision carried into this pack (Chat 59):** **Gate B is NOT built.**
See §0.1.

---

## 0. READ THIS FIRST — scope correction vs the locked design

The locked design (Chat 58) was written before a full re-read of the live submit
path. A line-by-line read at draft time surfaced one material fact that changes
scope. The operator has made the call. This section is binding and overrides the
design doc wherever they differ.

### 0.1 An over-budget approval gate ALREADY EXISTS at PO submit — do not duplicate it

`po_approvals.submit_po_with_budget_gate` (the function the `/submit` endpoint
actually calls — NOT the bare `purchase_orders.submit_po`) already evaluates
`po_commitments.evaluate_budget_overrun(db, po)` and routes any PO whose projected
total exceeds a budget line's `current_budget` into a director **approval
workflow** (creates a `PurchaseOrderApproval` row, snapshots the budget, notifies
approvers). This is live, tested, and is the behaviour the operator wants.

**Therefore the design's "Gate B" (a second, 10%-threshold, 409-blocking
commitment-ack on budgeted lines) is CANCELLED.** Consequences, all binding:

- **DO NOT** add `commitment_ack_required`, `commitment_ack_cleared_by`,
  `commitment_ack_cleared_at` to `budget_lines`. **No DDL migration at all** in
  this pack (see §0.2).
- **DO NOT** add an `acknowledge_commitment` service action or router endpoint.
- **DO NOT** modify `submit_po_with_budget_gate`'s over-budget branch, the
  `evaluate_budget_overrun` threshold, or the approval-workflow behaviour.
- The variance constant `VARIANCE_RED_PCT` is **not** reused for any gate here.
- "Gate B" is formally closed as "already satisfied by the Prompt 2.5 over-budget
  approval gate." Record this in the CHANGELOG deviations block.

This pack therefore builds **only**: the cost-code-first line model, resolve-or-mint,
**Gate A** (the unbudgeted £-floor), the PO completeness-at-submit check, and the
mint-no-longer-forces-Red behaviour change. That is the whole of B105/B106.

### 0.2 No DDL required — every column already exists

Confirmed against `backend/app/models/budgets.py` at head 0049:
`is_unbudgeted`, `unbudgeted_reason`, `unbudgeted_source`, `unbudgeted_created_by`,
`unbudgeted_cleared_by`, `unbudgeted_cleared_at`, `requires_attention`,
`variance_status`, `original_budget`, `current_budget`, `committed_value`,
`committed_not_invoiced` all exist. **This build ships ZERO alembic DDL
migrations.** The only data change is one new `system_config` seed row, added to
`seed_system_config.py` (NOT an alembic data migration — see §3.2).

### 0.3 "One line per cost code" is ALREADY enforced by the database

`budget_lines` carries `UniqueConstraint("budget_id", "cost_code_id",
"cost_code_subcategory_id", name="uq_budget_lines_budget_cost_subcat")`. D2 is a DB
invariant already. **Do not add a second uniqueness mechanism.** Two precise
consequences the build MUST respect:

1. Uniqueness is on the **triple** `(budget_id, cost_code_id,
   cost_code_subcategory_id)`, i.e. "one line per cost-code **+ subcategory**".
   The resolve-or-mint match key (§3.4) MUST be that exact triple, so the resolve
   step and the constraint agree and a mint can never violate the constraint.
2. `cost_code_subcategory_id` is part of the key and may be `NULL`. Postgres treats
   `NULL` as distinct in unique constraints, BUT the resolve lookup must treat
   "no subcategory" as a single matchable value (use `IS NULL` in the query, not
   `= NULL`). See §3.4 for the exact predicate.

### 0.4 RESOLVED (Chat 59, operator) — option (ii): floor exempts the existing gate

A minted unbudgeted line has `current_budget = 0`, so the EXISTING over-budget gate
would otherwise route ANY unbudgeted line (any positive amount) into director
approval at submit — making the £1,000 floor meaningless. **Operator decision:
option (ii).** The existing over-budget gate is made to IGNORE an unbudgeted line
whose committed spend is BELOW the floor, so:

- Unbudgeted spend **below** the floor → does NOT trip the existing over-budget
  gate on account of being unbudgeted, and does NOT hard-block (Gate A silent). It
  auto-approves like any within-budget line (flagged, non-blocking).
- Unbudgeted spend **at/above** the floor → Gate A hard-blocks at submit (409) until
  a director clears it.
- A **budgeted** line going over its budget → unchanged; the existing over-budget
  approval workflow still applies exactly as today.

The floor is a `system_config` value (default £1,000, director-editable) — §3.2.

**Backlog (folded into B43/B44 — per-role/per-user approval limits + settings UI):**
operator raised tiered approval — different unbudgeted thresholds requiring
different approver levels (e.g. PM may clear up to £X, finance up to £Y, director
above). Captured against B43/B44; NOT built here. This build ships the single global
editable floor only.

See §3.7a for the exact, surgical change to `evaluate_budget_overrun` that
implements option (ii) under money-path discipline.

---

## 1. Why this build exists (one paragraph)

Today a PO/package line is EITHER budgeted (`budget_line_id` supplied) OR unbudgeted
(`unbudgeted=true` + cost code + reason), enforced by an XOR validator. The operator
wants the commercial document to be **cost-code-first**: a line names a cost code,
and the server decides whether that code already has a budget line (allocate into
it) or not (mint one). "Unbudgeted" becomes a server-determined outcome, not a
caller assertion. Plus: an unbudgeted line should only demand director sign-off when
the committed spend on it crosses a configurable floor (default £1,000); below that
it is flagged but non-blocking. And a PO must be **complete** before it can be
submitted (every line: cost code + qty + rate + vat + description), while **drafts
may be incomplete** so AI capture / manual entry can fill them progressively.

---

## 2. The shape of the change (map before you build)

| Area | File | Change |
|---|---|---|
| Schema | `routers/purchase_orders.py` `POLineCreate` | Collapse XOR → cost-code-first (§3.1) |
| Schema | `routers/packages.py` package-line body | Same cost-code-first collapse (§3.1) |
| Resolve | `services/budget_lines.py` | NEW `find_line_for_code` helper (§3.3) |
| Resolve | `services/purchase_orders.py` `create_po` | Replace B102 pre-pass with resolve-or-mint (§3.4) |
| Resolve | `services/packages.py` `add_package_line` | Replace B102 unbudgeted branch with resolve-or-mint (§3.4) |
| Mint | `services/budget_lines.py` `create_unbudgeted_line` | Stop forcing Red/attention at mint; add `force_flag=False` (§3.5) |
| Gate A | `services/budget_lines.py` | NEW `evaluate_unbudgeted_floor_gate` (§3.6) |
| Gate A wire | `services/po_approvals.py` `submit_po_with_budget_gate` | Invoke Gate A after `recompute_for_po`, before the existing over-budget branch (§3.7) |
| Option (ii) | `services/po_commitments.py` `evaluate_budget_overrun` | Skip un-cleared unbudgeted lines so the existing gate owns budgeted overruns only (§3.7a) |
| Gate A wire | `services/purchase_orders.py` `issue_po` | Invoke Gate A after `recompute_for_po` (§3.7) |
| Completeness | `services/purchase_orders.py` submit path | NEW completeness check at submit (§3.8) |
| Config | `services/system_config.py` | NEW `get_unbudgeted_ack_floor` (§3.2) |
| Config | `seed_system_config.py` | NEW seed row `budget.unbudgeted_ack_floor_gbp` (§3.2) |
| Errors | `services/budget_errors.py` (or PO errors) | NEW `UnbudgetedAckRequiredError`, `POLineIncompleteError` (§3.9) |
| Router | `routers/purchase_orders.py` submit/issue | Map new errors → 409 / 422 (§3.9) |

Nothing else is in scope. No DDL. No new permission. No new RBAC role grant.

---

## 3. Detailed specification

### 3.1 Schema — cost-code-first line body

**`POLineCreate` (in `routers/purchase_orders.py`)** — new shape. Keep
`model_config = ConfigDict(extra="forbid")`.

```
cost_code_id:               uuid            # NEW, optional at schema level*
cost_code_subcategory_id:   uuid | None     # NEW, optional
budget_line_id:             uuid | None     # back-compat alias (validated, §3.4)
description:                str   | None    # optional at CREATE (draft may be blank)
quantity:                   float | None    # optional at CREATE; > 0 if present
unit_rate:                  float | None    # optional at CREATE; >= 0 if present
vat_rate:                   float          = 20.00   # 0..100
cost_code:                  str   | None    # display string, max 20 (unchanged)
unit:                       str   | None
line_number:                int   | None    # >= 1
notes:                      str   | None
# --- DEPRECATED, accepted-but-ignored for one release (§3.10) ---
unbudgeted:                 bool            = False
unbudgeted_cost_code_id:    uuid | None
unbudgeted_subcategory_id:  uuid | None
unbudgeted_reason:          str  | None     # max 2000
```

\* **Validator rule** (replaces the XOR `_xor_budget_line`):
- A line MUST resolve to a cost code. Acceptable inputs, in priority order:
  1. `cost_code_id` present → use it.
  2. `cost_code_id` absent but `budget_line_id` present → server derives the cost
     code from the budget line (back-compat; §3.4).
  3. `cost_code_id` absent but deprecated `unbudgeted_cost_code_id` present →
     treat as `cost_code_id` (back-compat; §3.10) and log a deprecation warning.
  4. None of the above → `ValueError("cost_code_id is required")`.
- `quantity`, `unit_rate`, `vat_rate`, `description` are **optional at create**
  (drafts may be incomplete — D3). Completeness is enforced at **submit** (§3.8),
  NOT here. If `quantity` is present it must be `> 0`; if `unit_rate` present, `>= 0`;
  `vat_rate` 0..100. These bound-checks stay at the schema for present values.
- If BOTH `cost_code_id` and `budget_line_id` are present, they are NOT rejected at
  the schema — the service validates agreement and 422s on mismatch (§3.4). This
  keeps the "alias must agree" logic in one place (the service, under the lock).

> **IMPORTANT — `_compute_line_totals` interaction.** Today
> `_compute_line_totals` (services/purchase_orders.py) raises `ValueError` if
> `quantity <= 0` or rate `< 0`, and reads `quantity`/`unit_rate` unconditionally.
> Under the new "draft may be incomplete" rule a draft line may have
> `quantity=None`. The Build Pack MUST make `create_po`'s totals computation
> **tolerant of incomplete draft lines**: when a line is incomplete, persist it
> with `net=vat=gross=0` and DO NOT raise. The completeness gate at submit (§3.8)
> is what enforces real numbers before money moves. Spell this out — see §3.4
> step 5.

**Package line body (in `routers/packages.py`)** — apply the identical collapse:
add `cost_code_id` / `cost_code_subcategory_id`, keep `budget_line_id` as a
validated alias, retain `unbudgeted*` as deprecated accepted-but-ignored. The
package path has its own completeness story (packages are pre-tender estimates, not
committed money) — see §3.4 note and §3.8: **the completeness-at-submit gate
applies to PO submit only**, not to package-line creation.

### 3.2 Config — the unbudgeted ack floor

**`system_config.py`** — mirror `get_budget_self_approval_threshold` exactly:

```python
UNBUDGETED_ACK_FLOOR_KEY = "budget.unbudgeted_ack_floor_gbp"
DEFAULT_UNBUDGETED_ACK_FLOOR_GBP = Decimal("1000.00")

def get_unbudgeted_ack_floor(db: Optional[Session] = None) -> Decimal:
    """GBP floor at/above which an unbudgeted line's committed spend
    requires director sign-off before the PO can be issued. Below the
    floor the line is flagged but non-blocking. Mirrors the self-approval
    threshold pattern (config-backed, in-code default fallback)."""
    value = get_or_default(
        UNBUDGETED_ACK_FLOOR_KEY, DEFAULT_UNBUDGETED_ACK_FLOOR_GBP, db=db
    )
    return value if isinstance(value, Decimal) else Decimal(str(value))
```

**Seed row — add to `seed_system_config.py` `SEEDS` list (NOT an alembic
migration).** The module docstring is explicit: config seeding runs at lifespan
AFTER `seed_rbac` because `minimum_role_to_edit` needs `roles.id`; an alembic data
migration cannot resolve the role FK on first boot. Add, in the `# Budget` block:

```python
("budget.unbudgeted_ack_floor_gbp", "1000.00", "Decimal", "Budget",
 "director", "GBP floor at/above which an unbudgeted order line's committed "
 "spend requires director sign-off before the PO can be issued"),
```

`seed_system_config` is idempotent (skips existing keys), so this seeds on the next
boot of every existing pod and on fresh forks. **Comparison semantics: `>=`** — at
exactly the floor, sign-off IS required (matches the self-approval `>=` convention).

> **No downgrade needed** for a seed row — seeding is idempotent and additive. If a
> formal "removable" story is wanted later it is a separate task; do not write an
> alembic data migration here.

### 3.3 NEW helper — `find_line_for_code`

In `services/budget_lines.py`:

```python
def find_line_for_code(
    db: Session, *, budget_id: uuid.UUID,
    cost_code_id: uuid.UUID,
    cost_code_subcategory_id: Optional[uuid.UUID],
) -> Optional[BudgetLine]:
    """Return the single existing budget line for this
    (budget, cost_code, subcategory) triple, or None. The triple matches
    uq_budget_lines_budget_cost_subcat exactly, so at most one row can
    match. NULL subcategory is matched with IS NULL (not = NULL)."""
    stmt = select(BudgetLine).where(
        BudgetLine.budget_id == budget_id,
        BudgetLine.cost_code_id == cost_code_id,
    )
    if cost_code_subcategory_id is None:
        stmt = stmt.where(BudgetLine.cost_code_subcategory_id.is_(None))
    else:
        stmt = stmt.where(
            BudgetLine.cost_code_subcategory_id == cost_code_subcategory_id
        )
    return db.scalar(stmt)
```

This is called inside `create_po` / `add_package_line` AFTER the parent budget has
been validated and (in the PO path) while the caller-owned transaction holds the
budget lock chain established by `_validate_budget`/subsequent operations. It is a
read; the mint that may follow re-acquires `FOR UPDATE` via `create_line`. (Lock
re-entrancy within one transaction is already relied upon by the existing B102
path — preserved.)

### 3.4 Resolve-or-mint (replaces the B102 unbudgeted pre-pass)

**In `create_po` (services/purchase_orders.py)** — replace the existing
`for lp in line_payloads: if lp.get("unbudgeted"): ...` block (current lines
~327–352) with the resolve-or-mint pass below. Everything after it
(`budget_line_ids = [...]`, `_validate_budget_lines`, totals, insert, audit) stays,
with the one totals-tolerance change noted in step 5.

Pseudocode (translate to real Python against live signatures):

```
for lp in line_payloads:
    # 1. Determine the cost code for this line.
    cc_id  = lp.get("cost_code_id") or lp.get("unbudgeted_cost_code_id")   # §3.10
    sub_id = lp.get("cost_code_subcategory_id") or lp.get("unbudgeted_subcategory_id")
    alias  = lp.get("budget_line_id")

    if cc_id is None and alias is not None:
        # Back-compat: derive code from the supplied budget line.
        bl = db.get(BudgetLine, alias)
        if bl is None or bl.budget_id != budget.id:
            raise ValueError(f"budget_line_id {alias} not on budget {budget.id}")
        cc_id, sub_id = bl.cost_code_id, bl.cost_code_subcategory_id

    if cc_id is None:
        raise ValueError("cost_code_id is required")

    cc_id  = uuid.UUID(str(cc_id))
    sub_id = uuid.UUID(str(sub_id)) if sub_id else None

    # 2. Resolve existing line, else mint one (the unbudgeted path).
    existing = bl_svc.find_line_for_code(
        db, budget_id=budget.id, cost_code_id=cc_id,
        cost_code_subcategory_id=sub_id,
    )
    if existing is not None:
        line = existing
    else:
        # Mint. Reason: prefer explicit deprecated reason if present,
        # else a deterministic default (no user-facing reason field now, D3).
        reason = (lp.get("unbudgeted_reason") or "").strip() \
                 or "Auto-created: order raised against an unbudgeted cost code"
        try:
            line = bl_svc.create_unbudgeted_line(
                db, budget_id=budget.id, user=user, perms=perms,
                cost_code_id=cc_id, cost_code_subcategory_id=sub_id,
                entity_id=None, reason=reason, source="purchase_order",
                force_flag=False,          # §3.5 — DO NOT force Red at mint
            )
        except (BudgetStateError, BudgetNotFoundError, BudgetValidationError) as e:
            raise ValueError(str(e)) from e

    # 3. Back-compat alias must agree with the resolved line.
    if alias is not None and uuid.UUID(str(alias)) != line.id:
        raise ValueError(
            "budget_line_id does not match the resolved cost-code line"
        )   # router → 422

    # 4. Stamp the resolved id back so downstream invariant is unchanged.
    lp["budget_line_id"] = line.id
    lp["cost_code_id"]   = cc_id     # keep for totals/labelling

# 5. budget_line_ids = [...]; _validate_budget_lines(...) UNCHANGED.
#    Totals: _compute_line_totals MUST tolerate incomplete draft lines —
#    if quantity is None or unit_rate is None, persist net=vat=gross=0
#    and skip the > 0 / >= 0 raise. Real numbers are enforced at submit (§3.8).
```

**In `add_package_line` (services/packages.py)** — replace the
`if unbudgeted: ... else: bline = db.get(...)` block (current lines ~502–523) with
the same resolve-or-mint logic, `source="package"`, `force_flag=False`. The package
path has no "incomplete draft" totals concern (it inherits from the budget line via
`_inherit_from_budget_line`), so no totals-tolerance change is needed there — but it
DOES gain resolve-or-mint and the alias-agreement check.

> **Why this is safe (state explicitly in the pack so the auditor can verify):**
> after the pass every payload carries a real `budget_line_id` that belongs to
> `budget.id` (either pre-existing or freshly minted on it), so
> `_validate_budget_lines`' "all belong to this budget" invariant holds unchanged.
> The mint re-uses `create_unbudgeted_line` → `create_line`, which re-acquires the
> budget `FOR UPDATE` (re-entrant). The unique constraint guarantees the mint can
> never create a duplicate for a code that already had a line, because resolve
> would have found it first; and if a race minted concurrently, the DB constraint
> raises `IntegrityError` (map to 409 — see §3.9 race note).

### 3.5 Mint behaviour change — stop forcing Red at create

**`create_unbudgeted_line` (services/budget_lines.py)** — add a parameter
`force_flag: bool = False`. Behaviour:

- When `force_flag=False` (the new default, used by resolve-or-mint): create the
  line with `is_unbudgeted=True`, `unbudgeted_reason`, `unbudgeted_source`,
  `unbudgeted_created_by` set as today, BUT **do not** set `variance_status="Red"`
  and **do not** set `requires_attention=True`. Leave them at whatever
  `create_line` → `recompute_summary` produced (a £0 line lands Green / not-flagged
  — a neutral, not-yet-evaluated state). The Red/attention decision now belongs to
  Gate A at submit (§3.6).
- When `force_flag=True`: preserve the exact current behaviour (force Red +
  attention) for any caller that still wants mint-time forcing. (No live caller
  passes True after this build, but keeping it avoids a hard breaking change and
  lets the re-baselined B102 tests assert both behaviours explicitly.)

Update the docstring to describe both modes. This is a money-adjacent function —
treat under full audit discipline; the change is the removal of two unconditional
assignments behind a flag.

> **Interaction with `scan_requires_attention` — verify and preserve.** The scan
> skips any line where `is_unbudgeted AND unbudgeted_cleared_at IS NULL`. Under the
> new model a not-yet-evaluated unbudgeted line (neutral, not cleared) is STILL
> skipped by the scan — which is correct: we do not want the variance scan flipping
> an unbudgeted line's attention state; Gate A owns it until cleared. No change to
> `scan_requires_attention` is required, but the Build Pack MUST include a test
> asserting the scan still ignores a §3.5 neutral unbudgeted line (T-SCAN-1).

### 3.6 NEW — Gate A: the unbudgeted £-floor evaluation

In `services/budget_lines.py`:

```python
def evaluate_unbudgeted_floor_gate(
    db: Session, *, budget_line_ids: list[uuid.UUID],
) -> list[dict]:
    """For each given line that is an un-cleared unbudgeted line, decide
    whether its committed spend has crossed the sign-off floor.

    Sets the operational marker on the line:
      - committed_not_invoiced >= floor  → requires_attention=True,
        variance_status='Red'   (ack-required; BLOCKS issue)
      - committed_not_invoiced <  floor  → requires_attention=False
        (flagged non-blocking; ALLOWS issue)
    Budgeted lines (is_unbudgeted=False) and already-cleared unbudgeted
    lines are skipped untouched.

    Returns a list of blocking lines: [{budget_line_id, cost_code,
    committed_not_invoiced, floor}]. Empty list ⇒ nothing blocks.

    MUST be called only AFTER recompute_for_po has written
    committed_not_invoiced and under the parent-budget FOR UPDATE lock
    that recompute_for_line holds within the same transaction.
    """
```

Implementation notes (binding):
- Load the floor once via `get_unbudgeted_ack_floor(db)`.
- Load each line by id. Skip if `not line.is_unbudgeted` or
  `line.unbudgeted_cleared_at is not None`.
- Read `committed_not_invoiced` (Decimal; coalesce None→0). Compare `>= floor`.
- Set the markers as above. `db.flush()`.
- Build the blocking list from lines that landed `requires_attention=True`.
- Write an audit row per line whose marker state changed (action `Update`,
  resource `budget_lines`, metadata `{"event": "unbudgeted_floor_gate",
  "committed_not_invoiced": ..., "floor": ..., "blocking": bool}`).

> **Why `committed_not_invoiced` and not `committed_value`?** `committed_value` is
> trigger-maintained and includes already-invoiced commitment;
> `committed_not_invoiced` is the Python-owned single-writer column representing
> live outstanding commitment, freshly written by `recompute_for_po` immediately
> before the gate. It is the correct, consistent quantity to gate on and is read
> under the same lock. (If the operator later wants gross PO value instead, that's
> a one-line change — note as a backlog candidate, do not build.)

### 3.7 Wiring Gate A into the submit / issue paths

Gate A must run at the point committed money becomes real and BLOCK the PO from
reaching a state where the supplier is told (issued). Two wire points:

**(a) `po_approvals.submit_po_with_budget_gate`** — after EACH `recompute_for_po`
call, before returning, evaluate Gate A on the PO's touched budget lines:

```
blocking = bl_svc.evaluate_unbudgeted_floor_gate(
    db, budget_line_ids=<distinct budget_line_ids on this PO>
)
if blocking:
    raise UnbudgetedAckRequiredError(blocking)   # → router 409, PO stays draft
```

- Collect the line ids the same way `recompute_for_po` does (distinct
  `PurchaseOrderLine.budget_line_id` for this PO) — or have
  `evaluate_unbudgeted_floor_gate` accept the PO id and do that lookup itself
  (cleaner; pick one and be consistent). The gate runs under the lock chain
  `recompute_for_po`→`recompute_for_line` already established in this transaction.
- Place the check in BOTH branches (the within-budget auto-approve branch AND the
  pending-approval branch) so an unbudgeted-over-floor PO cannot slip through
  either. Simplest: evaluate once immediately after the branch's
  `recompute_for_po`, before the branch's `record_audit`/return. **Raising rolls
  back the transition** (request-scoped session rollback), so the PO stays Draft —
  exactly the desired "blocked" behaviour. Verify the router does NOT commit before
  the raise (it commits only after the service returns — confirmed at HEAD).

**(b) `purchase_orders.issue_po`** — after its `recompute_for_po(db, po.id)`,
evaluate Gate A the same way and raise on blocking. This covers the
approved→issued path (a PO that was auto-approved within budget but carries an
unbudgeted-over-floor line must not issue without sign-off).

> **Ordering vs the existing over-budget gate (option ii, locked §0.4):** Gate A
> and the existing over-budget gate are reconciled by §3.7a, which makes the
> existing gate ignore below-floor unbudgeted lines. With that in place the rule is
> clean: below-floor unbudgeted → neither gate fires (auto-approve, flagged
> non-blocking); at/above-floor unbudgeted → Gate A hard-blocks (409); budgeted
> overrun → existing approval workflow unchanged. Wire Gate A AFTER each
> `recompute_for_po` (so committed is real) and raise `UnbudgetedAckRequiredError`
> on any blocking line, in BOTH the submit wrapper and `issue_po`.

### 3.7a Option (ii) — make the existing over-budget gate ignore below-floor unbudgeted lines

This is a surgical, money-path change to `po_commitments.evaluate_budget_overrun`.
Treat under full audit discipline.

**The timing subtlety (must be respected):** `evaluate_budget_overrun` runs in
`submit_po_with_budget_gate` at line ~159, BEFORE `recompute_for_po`. At that
moment `bline.committed_value` does NOT yet include this PO. The function already
models the PO's contribution explicitly as `po_net` (`_aggregate_po_net_by_budget_line`)
and computes `projected = committed_value + actuals + po_net`. So the committed
spend that the floor must be compared against, for THIS submit, is:

```
unbudgeted_committed_for_floor = committed_value + po_net      # excludes actuals;
                                                              # = outstanding commitment
```

(We compare commitment, not `projected` including actuals, to match Gate A which
reads `committed_not_invoiced`. For a fresh unbudgeted line `committed_value` is 0,
so this equals `po_net` — the new commitment being raised. Consistent.)

**Change:** inside the per-line loop of `evaluate_budget_overrun`, before appending
an overrun, add a guard:

```python
# Option (ii), B105/B106: an unbudgeted line below the sign-off floor does
# NOT count as an over-budget overrun (its zero original_budget would
# otherwise always trip this gate). At/above the floor it is handled by
# Gate A (a hard 409 block), NOT by this approval-routing gate, so we
# also skip it here to avoid double-routing. Net effect: unbudgeted lines
# are owned entirely by Gate A; this gate governs BUDGETED overruns only.
if bline.is_unbudgeted and bline.unbudgeted_cleared_at is None:
    continue
```

**Rationale for skipping unbudgeted lines from this gate entirely (not just
below-floor):** an at/above-floor unbudgeted line is hard-blocked by Gate A (409,
PO stays draft) — it never reaches the approval-workflow path, so including it here
would be dead logic at best and double-handling at worst. A below-floor unbudgeted
line must auto-approve. Either way, this gate should not act on un-cleared
unbudgeted lines. Once cleared (`unbudgeted_cleared_at` set), the line is a normal
line and rejoins this gate's budgeted logic on any future PO. This keeps a clean
separation: **Gate A owns unbudgeted lines; the existing over-budget gate owns
budgeted overruns.**

> **Audit checkpoint:** confirm no other caller of `evaluate_budget_overrun` /
> `is_within_budget` relies on it flagging unbudgeted lines. Grep both names.
> `build_budget_snapshot` is separate and unchanged (it still snapshots all touched
> lines for the approver's context — fine). Add a test that `is_within_budget`
> returns True for a PO whose only "overrun" is a below-floor unbudgeted line.

### 3.8 PO completeness check at submit (D3)

A PO line is **complete** when it has: a resolved `budget_line_id` (always true
post-resolve), `cost_code` (non-empty), `quantity > 0`, `unit_rate >= 0`,
`vat_rate` present (0..100), and a non-empty `description`.

- Enforce at **submit only**, inside `submit_po_with_budget_gate`, BEFORE the
  transition (`po_transitions.submit`). Load the PO's lines; if any is incomplete,
  raise `POLineIncompleteError(incomplete_line_numbers)` → router **422** naming the
  offending line number(s). The PO stays Draft.
- Drafts persist incomplete freely (no check at `create_po`; the totals-tolerance
  in §3.4 step 5 is what lets a £0/blank line be saved).
- This is PO-scoped. Package-line creation is NOT gated by completeness (packages
  are estimates; their completeness story is the existing award/tender flow).

### 3.9 Errors and router mapping

New exceptions (place in `services/budget_errors.py` or a PO-local errors module —
match the existing convention; `budget_errors.py` already houses budget-domain
errors, prefer it for `UnbudgetedAckRequiredError`, and the PO module for
`POLineIncompleteError` if that's cleaner):

- `UnbudgetedAckRequiredError(blocking: list[dict])` — carries the blocking lines.
  Router maps to **409 Conflict**, body:
  ```json
  {"type": "unbudgeted_ack_required",
   "title": "Director sign-off required on unbudgeted line(s)",
   "lines": [{"budget_line_id": "...", "cost_code": "...",
              "committed_not_invoiced": "...", "floor": "..."}]}
  ```
- `POLineIncompleteError(line_numbers: list[int])` — router maps to **422**, body
  names the incomplete line numbers.

Add `except` arms in the `/submit` and `/issue` endpoints
(`routers/purchase_orders.py`). Keep existing `TransitionError`→409,
`ValueError`→422, `PoNotFound`→404 arms. Order the new `UnbudgetedAckRequiredError`
arm before the generic `ValueError` arm.

> **Concurrency race on mint (map to 409):** if two requests mint the same code
> concurrently, the unique constraint raises `IntegrityError` on the second flush.
> Catch it in `create_po`/`add_package_line` and surface as a 409 ("a line for this
> cost code was just created; retry") rather than a raw 500. Add a test (T-RACE-1)
> that simulates the duplicate by attempting two lines with the same cost code in a
> single PO payload → the second resolve finds the first mint within the same
> transaction (so it allocates, not duplicates) — and a service-level test that a
> direct double-mint raises and is handled.

### 3.10 Deprecation handling of `unbudgeted_*`

- Keep `unbudgeted`, `unbudgeted_cost_code_id`, `unbudgeted_subcategory_id`,
  `unbudgeted_reason` as **named optional fields** on `POLineCreate` / package body
  (so `extra="forbid"` does NOT reject old callers). They are accepted and read
  ONLY as fallbacks in §3.4 step 1, never as authoritative.
- When any `unbudgeted_*` field is present on a request, log one deprecation
  warning (logger `syhomes.deprecation`, message naming the field and pointing to
  `cost_code_id`). Do not warn per-line in a tight loop more than once per request
  — dedupe.
- The `unbudgeted` boolean is ignored entirely for routing (resolve-or-mint decides
  budgeted-vs-unbudgeted by line existence). Document: "next release removes these
  fields" — add a backlog item (B-DEPREC-unbudgeted-fields).

---

## 4. Migrations

**DDL:** none.
**Data:** none as an alembic migration. One seed row added to
`seed_system_config.py` (§3.2), which seeds idempotently at lifespan.

> If the project's migration-gate checklist expects "a migration per build", record
> in the CHANGELOG that B105/B106 intentionally ships no alembic revision because
> all columns pre-exist and config seeding is lifespan-owned, not migration-owned.
> Alembic head remains `0049_unbudgeted_order_lines`.

---

## 5. Permissions

No new permission. No new role grant.
- Unbudgeted sign-off (clearing a Gate-A-blocking line) uses the EXISTING
  `budgets.clear_unbudgeted` permission and the EXISTING
  `POST /budget-lines/{line_id}/clear-unbudgeted` endpoint + `clear_unbudgeted`
  service action. Director and super_admin already hold it
  (all-minus-exclusions baseline; `clear_unbudgeted` is not excluded). Confirm by
  re-running the RBAC count assertion (see §6 warm-DB note) — permission count is
  **unchanged** by this build.

> Verify `clear_unbudgeted` still correctly clears a §3.5 neutral-then-gated line:
> it sets `unbudgeted_cleared_at/by`, `requires_attention=False`, and recomputes
> variance off any forced Red. Since Gate A (not mint) sets the Red, and
> `clear_unbudgeted` already recomputes + sets `requires_attention=False` under the
> lock, it works unchanged. Add a test asserting the full cycle (T-CYCLE-1, §6).

---

## 6. Tests (warm-DB double-run; money-path → three-pass audit)

> **Warm-DB rule:** a fresh pod throws ~90 IntegrityErrors on first pytest run.
> Run the suite TWICE; the second run is the accurate count. State both counts in
> the gate report.

Test file naming — create these exactly (no single-file consolidation):
- `backend/tests/test_cost_code_first_resolve.py` — resolve-or-mint + alias + D2.
- `backend/tests/test_unbudgeted_floor_gate.py` — Gate A + boundaries + wiring.
- `backend/tests/test_po_completeness_submit.py` — completeness at submit.
- Re-baseline existing assertions in `backend/tests/test_unbudgeted_orders.py`
  (the mint-forced-Red tests) — do NOT delete; convert to assert the
  `force_flag=True` legacy behaviour explicitly, and ADD new tests for
  `force_flag=False` neutral mint.

Minimum coverage (each a discrete test function):

**Resolve-or-mint (`test_cost_code_first_resolve.py`)**
1. Line with `cost_code_id` for a code that HAS a budget line → resolves to that
   line (no mint; line count unchanged).
2. Line with `cost_code_id` for a code with NO line → mints exactly one line,
   `is_unbudgeted=True`, neutral (NOT Red, NOT requires_attention) — §3.5.
3. Two PO lines naming the SAME new code in one payload → ONE mint; the second
   resolves to the first (no duplicate; respects D2). 
4. D2 enforcement: attempting state that would create a 2nd line for an existing
   `(budget, code, subcat)` is impossible via resolve (asserts resolve found the
   existing); a direct double-mint raises `IntegrityError` and is surfaced as 409
   (T-RACE-1).
5. Back-compat alias: `budget_line_id` supplied alone (no `cost_code_id`) → server
   derives code, resolves same line, succeeds.
6. Alias mismatch: `cost_code_id` + a `budget_line_id` that points at a DIFFERENT
   line → 422.
7. Deprecated `unbudgeted_cost_code_id` only (no `cost_code_id`) → treated as the
   code, resolves/mints, deprecation warning logged.
8. Neither code nor alias → 422 "cost_code_id is required".
9. Subcategory in the key: a code with subcat A and a line for subcat A resolves;
   the same code with subcat B (no line) mints a SEPARATE line (proves the triple
   key, not code-only).
10. NULL-subcategory matching: a line with NULL subcat resolves via `IS NULL`
    (not accidentally missed).

**Gate A floor (`test_unbudgeted_floor_gate.py`)** — option (ii) locked (§0.4).
11. Floor boundary £999.99 committed → non-blocking (requires_attention False,
    issue allowed).
12. Floor boundary exactly £1000.00 → BLOCKS (>= semantics) — 409 on submit.
13. Floor boundary £1000.01 → BLOCKS.
14. Draft never gates: a draft PO with an unbudgeted line and £0 committed →
    `evaluate_unbudgeted_floor_gate` returns empty; no block. (Committed only flows
    at submit.)
15. Submit of an unbudgeted-over-floor PO → 409, PO stays Draft, line marked Red +
    requires_attention.
16. Clear via existing `clear_unbudgeted` → re-submit succeeds (T-CYCLE-1).
17. Below-floor unbudgeted line: submit succeeds, line flagged
    (is_unbudgeted True, cleared_at NULL) but requires_attention False.
18. Config override: set `budget.unbudgeted_ack_floor_gbp` to "5000.00" via
    `system_config.set_value` → a £1500 committed unbudgeted line no longer blocks.
19. `issue_po` path: an auto-approved (within-budget) PO carrying an
    unbudgeted-over-floor line → `issue` raises 409 until cleared.
20. Scan isolation (T-SCAN-1): `scan_requires_attention` leaves a §3.5 neutral
    unbudgeted line untouched (skipped, counted in `skipped_unbudgeted`).
21. Audit: a gate-trip writes the `unbudgeted_floor_gate` audit row; a clear writes
    the existing `clear_unbudgeted` row.
22. Separation (option ii): a PO whose ONLY over-current_budget line is a
    below-floor unbudgeted line → `is_within_budget` returns True (the existing
    over-budget gate ignores it) AND Gate A does not block → submit auto-approves.
23. Separation (option ii): a PO with a below-floor unbudgeted line AND a genuinely
    over-budget BUDGETED line → the existing over-budget approval workflow fires for
    the budgeted line (pending_approval), Gate A stays silent (unbudgeted under
    floor). Confirms the two gates own their own domains.
24. Separation (option ii): a PO with an at/above-floor unbudgeted line → Gate A
    409-blocks; the existing over-budget gate does NOT also route it (the unbudgeted
    skip in §3.7a means `evaluate_budget_overrun` ignores it). After clear,
    re-submit: the now-cleared line is normal; submit proceeds.

**Completeness at submit (`test_po_completeness_submit.py`)**
25. Draft create with an incomplete line (no qty) → persists, line stored with
    net=0, no error.
26. Submit of a PO with any incomplete line → 422 naming the line number(s); PO
    stays Draft.
27. Submit of a fully complete PO → proceeds (transition happens).
28. Completeness checks each field: missing description, missing qty, qty<=0
    (caught earlier at totals if present), missing/blank cost_code → each 422 at
    submit. (Drive via direct line states.)

**Re-baseline (`test_unbudgeted_orders.py`)**
29. `create_unbudgeted_line(..., force_flag=True)` → still forces Red + attention
    (legacy behaviour pinned).
30. `create_unbudgeted_line(...)` (default `force_flag=False`) → neutral: NOT Red,
    NOT requires_attention. (Replaces the old T1 assertion that mint forces Red.)
31. Existing clear-unbudgeted lifecycle tests still pass against a line that became
    Red via Gate A rather than via mint.

**Award path**
32. `award_package` creates a DRAFT PO (no submit) → no gate fires at award; the
    gate fires when that draft PO is later submitted/issued (assert award succeeds
    with an unbudgeted-over-floor line present, then submit of the created PO 409s).

### 6.1 Three-pass audit (mandatory before this pack ships to Emergent)
- **Pass 1 — correctness/completeness:** every §3 change present; signatures match
  live code; resolve-or-mint replaces (not augments) the B102 pre-pass in both
  paths; no orphaned references to removed XOR.
- **Pass 2 — money-integrity/transactional safety:** Gate A reads
  `committed_not_invoiced` under the existing lock, after `recompute_for_po`;
  raising rolls back the transition (PO stays Draft); no commit-before-raise;
  totals-tolerance does not let real committed money flow on an incomplete line
  (it can't — incomplete blocks at submit before transition); mint cannot duplicate
  (DB constraint + resolve).
- **Pass 3 — gate logic/permissions:** `>=` boundary correct; below-floor allows;
  draft never gates; clear uses existing perm; option (ii) separation correct
  (existing gate ignores un-cleared unbudgeted lines, Gate A owns them);
  deprecation fields never authoritative.

Expect Critical+High+Medium defects in line with prior money-path packs; fix
in-place, re-verify, report counts.

---

## 7. Gate report (paste back to Claude for independent verification)

Report MUST include, copy-paste from the pod:
1. `alembic heads` → still `0049_unbudgeted_order_lines` (no new revision).
2. `grep` proof that `commitment_ack_*` columns were NOT added anywhere.
3. Permission count before/after → UNCHANGED (paste the RBAC count assertion
   result, both pytest runs).
4. `get_unbudgeted_ack_floor` returns Decimal("1000.00") on a seeded pod; the seed
   row present in `system_config` (SELECT proof).
5. Full pytest output, BOTH runs (warm-DB), with the new test files' results
   broken out and the re-baselined `test_unbudgeted_orders.py` results.
6. The new error→status mappings exercised (409 body sample for Gate A; 422 body
   sample for completeness).
7. Confirmation `scan_requires_attention` is byte-for-byte unchanged except (if
   any) the test-only assertions; ideally zero production change to that function.
8. Proof of option (ii) separation: `is_within_budget` returns True for a PO whose
   only over-current_budget line is a below-floor unbudgeted line (paste the test
   result), and the `evaluate_budget_overrun` unbudgeted-skip is exercised.

Then STOP. Do not push closing docs until Claude clears the gate.

---

## 8. Out of scope (do NOT build — on backlog)
- B107 frontend (grid pills, clear/acknowledge actions).
- Gate B / `commitment_ack_*` columns (CANCELLED — §0.1).
- B109 templates, B110 buffer/unallocated line, B111 staged maturity.
- B112 notifications track. (Optional single notification — see §9; default DEFER.)
- Promoting `VARIANCE_RED_PCT` to system_config.
- Quote→PO AI capture.
- Removal of deprecated `unbudgeted_*` fields (next release; B-DEPREC).

---

## 9. Notification trigger (logged per standing habit; DEFER unless operator says otherwise)
- "PO blocked at submit — unbudgeted sign-off required" → notify directors holding
  `budgets.clear_unbudgeted`. Candidate first thread of B112. **Default: do not
  build in this pack.** If the operator wants the single notification now, wire it
  off the `UnbudgetedAckRequiredError` raise in `submit_po_with_budget_gate`
  (reuse `_broadcast_to_approvers`-style helper, audience = clear_unbudgeted
  holders). Confirm before building.

---

*End Build Pack v1. Drafted against live main @ 0049, three-pass audit pending
before Emergent handoff. Money-path discipline throughout.*
