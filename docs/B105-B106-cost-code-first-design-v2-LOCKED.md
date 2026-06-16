# B105 / B106 — Cost-Code-First Commercial Line Model — DESIGN v2 (LOCKED)

**Type:** Design document — LOCKED. This is the agreed model the Build Pack is
drafted against. No Emergent prompt is produced from this session.

**Supersedes:** design v1 (this session, Chat 58). All four open questions resolved.

**Author:** Claude. **Read against:** live `origin/main`, re-verified at session
close. Alembic head `0049_unbudgeted_order_lines` (down_revision
`0048_package_kind_3value_links`). Main confirmed unchanged across the session.

---

## 0. Decisions locked this session (D1–D4)

| # | Question | LOCKED ANSWER |
|---|---|---|
| **D1** | When does the sign-off / threshold gate fire? | **At PO submit**, not at draft create. Flow: quote in → create PO (button or drag-file) → AI extracts + fills, or manual entry → DRAFT → review → **submit** → committed money flows + gates evaluate. A draft is uncommitted and reversible, so it never gates. |
| **D2** | One budget line per cost code, or many? | **One line per cost code.** Codes are added deliberately (manual, allocation, or template) — NOT pre-loaded into every group on every project (that would bog the budget down). A code can exist on a budget **only once**. POs/invoices/payment-apps allocate *into* that one line (they are not extra lines). A PO hitting a code with **no** line → mints the line (the unbudgeted path). No back-compat `budget_line_id` picker is needed for disambiguation because a code is unique per budget. |
| **D3** | Mandatory "reason" field on every line? | **No reason field.** Replaced with a **PO completeness check**: a PO cannot be **submitted** unless every line carries cost_code + quantity + unit_rate + vat_rate + description. **Drafts may be incomplete** (this is what lets AI/manual fill happen progressively). Submit is the gate. (Reason still retained where B102 already stores it on the *minted unbudgeted line* for audit — see §3.4 — but it is NOT a new required field on ordinary budgeted lines.) |
| **D4** | How to mark a budgeted line that has overrun and needs sign-off? | **One dedicated marker on the budget line** (Option 1): `commitment_ack_required` boolean + `commitment_ack_cleared_by` + `commitment_ack_cleared_at`. Kept **entirely separate** from the variance scan's `requires_attention` flag to avoid the B102 collision bug (scan re-flipping a human-acknowledged flag). Historical / repeat-overrun analysis comes from the **audit log** (and a future reporting table), NOT from this operational marker. |

**Standing principle adopted (platform-wide):** *operational state lives on the
record for speed; historical / analytical views are built from the audit trail (or
purpose-built reporting tables) in the reporting track.* Apply this whenever the
"where does this state live" question recurs.

**Standing build habit adopted:** on every build from here, note which
**notification triggers** the feature should eventually fire, so the notifications
mini-track is not a retrofit.

---

## 1. The finding that anchors the whole design (re-confirmed at close)

**Committed money does not reach the budget line at PO create/draft time — only at
submit/issue.** Verified in `purchase_orders.py` + `budgets_reconciliation.py`:

- `create_po` mints the auto-line at `original_budget = 0` but writes **nothing**
  to `committed_value` / `committed_not_invoiced`.
- Committed flows only on `submit_po` / `issue_po` / `void_po`, each of which calls
  `recompute_for_po(db, po.id)` — the **sole writer** of `committed_not_invoiced`
  (formula `retention_pending + po_committed_not_invoiced`; counts PO statuses
  approved / issued / partially_receipted / receipted). A PG trigger maintains
  `committed_value`; Python owns `committed_not_invoiced`.
- A **draft** PO line contributes £0 committed. The line reads its real variance
  colour until submit.

**Therefore the gate fires at submit** (D1), immediately after `recompute_for_po`,
under the parent-budget `FOR UPDATE` lock `recompute_for_line` already holds. One
well-locked, money-safe choke point. No new lock.

---

## 2. The model (locked)

### 2.1 Budget structure (confirmed against operator's worked example + BT screenshot)

```
Facilitating Works (GROUP)..................... £500k   ← group total, holds steady
   ├─ Fac-02  Demolition Works................. £100k   ← ONE line per code
   ├─ Fac-03  Site Clearance................... £150k
   ├─ Fac-04  Specialist Ground................ £100k
   ├─ Fac-01  Hazardous........................ (blank — no detail yet)
   ├─ Fac-05  Diversions....................... £50k
   └─ Unallocated / buffer..................... £100k   ← non-cost-code holding line (FUTURE, backlog)
                                                ──────
                                                £500k
```

- One budget line per cost code. POs / invoices / payment applications allocate
  **into** the line (BT screenshot: SUB-02 is one line with many MKM/SMC/etc.
  allocations beneath). They are commercial documents on the line, not extra lines.
- Only the codes actually needed on a project appear. Added via manual entry,
  allocation, or template (both template kinds — see backlog).
- Blank codes are allowed (budgeted later or never).
- The buffer/unallocated line is a **future** first-class concept (backlog) — for
  now it is just an ordinary line.

### 2.2 The three line states the grid must show

| State | How it's recorded | Grid render | Blocks submit? |
|---|---|---|---|
| **Ack-required — unbudgeted over floor** | `is_unbudgeted=True` AND `unbudgeted_cleared_at IS NULL` AND `requires_attention=True` (forced Red, B102 columns) | Red, "Director sign-off required" pill | **Yes** |
| **Ack-required — budgeted overrun** | `commitment_ack_required=True` AND `commitment_ack_cleared_at IS NULL` (NEW dedicated columns, D4) | Red, "Director sign-off required" pill | **Yes** |
| **Flagged non-blocking — unbudgeted under floor** | `is_unbudgeted=True` AND `unbudgeted_cleared_at IS NULL` AND `requires_attention=False` | Amber/info "Unbudgeted — below sign-off floor" pill | No |
| **Normal** | none of the above | Standard variance colour from real maths | No |

---

## 3. Request shape + server-side resolve

### 3.1 Today (B102, on main)

`POLineCreate` is an XOR: a line carries EITHER `budget_line_id` (budgeted) OR
`unbudgeted=true` + `unbudgeted_cost_code_id` + `unbudgeted_reason` (an after-
validator enforces the XOR). `add_package_line` mirrors this with the same kwargs.
The service resolves the unbudgeted branch into a real auto-line before
`_validate_budget_lines`.

### 3.2 New cost-code-first line body

| Field | Type | Notes |
|---|---|---|
| `cost_code_id` | uuid, **required** | primary identifier; replaces the XOR |
| `cost_code_subcategory_id` | uuid, optional | validated against the cost code |
| `quantity` | decimal > 0 | required for submit (completeness check) |
| `unit_rate` | decimal ≥ 0 | required for submit |
| `vat_rate` | decimal, default 20.00 | required for submit |
| `description` | text | required for submit |
| `unit`, `notes`, `line_number` | as today | optional |
| `budget_line_id` | uuid, optional **back-compat alias** | if supplied, server validates it resolves to the same `(budget, cost_code)`; mismatch → 422. New frontend stops sending it. |

The `unbudgeted` boolean + `unbudgeted_*` cluster are **removed from the caller's
concern** — "unbudgeted" becomes a **server-determined outcome** of the resolve
step (no existing line for that code), not a caller assertion. (Accept-but-ignore
the old `unbudgeted_*` fields for one release for back-compat, then remove.)

### 3.3 Resolve-or-mint (replaces the B102 unbudgeted pre-pass)

```
for each line payload:
    existing = find_budget_line(budget_id, cost_code_id, subcategory_id)   # exact match
    if existing is not None:
        line = existing                 # budgeted code → committed rises on submit
    else:
        line = create_unbudgeted_line(  # unbudgeted code → mint once
                   budget_id, cost_code_id, subcategory_id, source=<po|package>)
    if payload.budget_line_id is not None and payload.budget_line_id != line.id:
        raise 422   # back-compat alias must agree with the resolved line
    payload.budget_line_id = line.id    # downstream invariant unchanged
```

Because a code is unique per budget (D2), the match is unambiguous — there is never
more than one candidate line, so the platform never guesses. After the pass every
payload carries a real `budget_line_id`, so `_validate_budget_lines` holds
unchanged. Minimal blast radius: this swaps in for the existing unbudgeted pre-pass;
`_compute_line_totals`, PO insert, and audit are untouched.

### 3.4 Mint behaviour change (important)

`create_unbudgeted_line` today **unconditionally** sets `variance_status='Red'` +
`requires_attention=True` at mint. Under the new model the gate can't be evaluated
at mint (committed is still £0 on a draft, §1). So:

- At mint: keep `is_unbudgeted=True`, `unbudgeted_source`, `unbudgeted_created_by`,
  and (retain) `unbudgeted_reason` for audit. **Do NOT force Red / requires_attention
  at mint.** Leave the line in a neutral, not-yet-evaluated state.
- The forced-Red / ack state is decided **at submit**, by the gate (§4), once
  committed is real.

> Build-Pack note: this is a behavioural change to a B102 function. The Build Pack
> must update `create_unbudgeted_line` (or introduce a `force_flag=False` param to
> preserve the old behaviour for any caller that still wants it) and re-baseline the
> B102 tests that assert mint-time forced-Red. Treat under money-gate discipline.

### 3.5 PO completeness check (D3)

A line is "complete" when it has cost_code_id + quantity (>0) + unit_rate (≥0) +
vat_rate + non-empty description. Enforced at **submit** (`submit_po`), not at
create. An incomplete line → submit raises a domain error → router 422 naming the
incomplete line(s). Drafts persist with incomplete lines freely.

---

## 4. The gate at submit (two checks, one evaluation point)

New function `evaluate_commitment_gate(db, budget_line_ids)` invoked inside
`submit_po` / `issue_po` **immediately after** `recompute_for_po`, under the
existing parent-budget `FOR UPDATE` lock. The award path inherits the gate because
it routes through `create_po` then submit.

### 4.1 Gate A — unbudgeted £-floor

For a line `is_unbudgeted=True` AND `unbudgeted_cleared_at IS NULL`:
```
if committed_not_invoiced > unbudgeted_ack_floor_gbp (config, default £1000):
    requires_attention = True; variance_status = 'Red'   # ack-required, BLOCK submit
else:
    requires_attention = False                            # flagged non-blocking, ALLOW
```

### 4.2 Gate B — budgeted committed-over-budget %

For a line `is_unbudgeted=False` AND `original_budget > 0`:
```
overrun_pct = (committed_not_invoiced - original_budget) / original_budget * 100
if overrun_pct >= red_variance_pct (reuse VARIANCE_RED_PCT constant, default 10):
    commitment_ack_required = True                        # ack-required, BLOCK submit
# else: no gate; normal variance colour applies
```
**DECIDED:** trigger on **committed**, not invoiced — early warning before billing.

### 4.3 "BLOCK submit" mechanics

`submit_po` / `issue_po` raise `CommitmentAckRequiredError` (NEW) → router maps to
**409 Conflict** with a body naming the offending line(s) and the reason
(`unbudgeted_over_floor` / `committed_over_budget`). PO stays Draft. Frontend (B107)
surfaces "Director sign-off needed on N lines" with a deep link to the clear action.
After clearance, re-submit succeeds.

### 4.4 Clearing the two ack types — KEEP THEM SEPARATE

- **Unbudgeted ack:** existing `clear_unbudgeted` (perm `budgets.clear_unbudgeted`).
  Guarded by `if not line.is_unbudgeted: raise` — works as-is for Gate A.
- **Budgeted-overrun ack:** NEW `acknowledge_commitment` action clearing
  `commitment_ack_required` (sets `commitment_ack_cleared_by/at`). A budgeted line
  is `is_unbudgeted=False` so it **cannot** reuse `clear_unbudgeted` (by design — no
  overloading). Permission: reuse `budgets.clear_unbudgeted` (same director-level
  authority) OR a sibling perm — **Build-Pack design decision; recommendation: reuse
  `budgets.clear_unbudgeted`** to avoid permission-catalogue churn, since the
  authority required is identical. Confirm in the Build Pack.

---

## 5. Config (mirror the self-approval threshold pattern exactly)

`system_config` is key/value with typed parse + in-code default fallback (no schema
change). Template: `get_budget_self_approval_threshold()`.

```python
UNBUDGETED_ACK_FLOOR_KEY = "budget.unbudgeted_ack_floor_gbp"
DEFAULT_UNBUDGETED_ACK_FLOOR_GBP = Decimal("1000.00")

def get_unbudgeted_ack_floor(db=None) -> Decimal:
    value = get_or_default(UNBUDGETED_ACK_FLOOR_KEY,
                           DEFAULT_UNBUDGETED_ACK_FLOOR_GBP, db=db)
    return value if isinstance(value, Decimal) else Decimal(str(value))
```

Seed row required (category `Budget`, value_type `Decimal`, `minimum_role_to_edit`
= director role, `default_value = "1000.00"`).

**% trigger (Gate B):** REUSE the existing `VARIANCE_RED_PCT` **constant** in
`budgets.py` (currently `Decimal("10.000")`). **Correction to original opener
assumption:** variance thresholds are *in-code module constants*
(`VARIANCE_AMBER_PCT` / `VARIANCE_RED_PCT`), **NOT** `system_config`-backed, and
there is **no** `_load_variance_thresholds` reader. "Reuse the red-variance
threshold" = reuse the constant. Making the % UI-editable later = a separate small
task to promote `VARIANCE_RED_PCT` into `system_config` (backlog candidate, not this
build).

---

## 6. Migration / back-compat

**No DDL strictly required for the core model** — all needed columns exist at head
0049 EXCEPT the D4 marker. Migrations for this build:

1. **DDL:** add `commitment_ack_required` (Boolean, default False, not null),
   `commitment_ack_cleared_by` (uuid FK users, nullable),
   `commitment_ack_cleared_at` (timestamptz, nullable) to `budget_lines`.
2. **Data:** seed `budget.unbudgeted_ack_floor_gbp` row.

**API back-compat (additive + deprecation window):**
- Keep `budget_line_id` accepted as optional, validated alias (§3.3).
- Accept-but-ignore the old `unbudgeted=*` / `unbudgeted_*` cluster for one release;
  log a deprecation warning; remove next release.
- This keeps the B102 test suite green through the transition and lets B107 land
  without lockstep pressure. (The Gate 7 frontend was already shelved as B107.)

---

## 7. Grid rendering (informs B107 frontend pack — NOT built this session)

Three pill styles per §2.2: blocking-red "sign-off required" (both ack types),
amber/info "unbudgeted below floor", and normal variance heat-map. Unbudgeted lines
read Red naturally once committed lands (committed > 0 over original 0). Only new FE
work is the two pills + the gated clear/acknowledge actions (gated on the relevant
permission). `original`-blank / `committed`-filled is the unbudgeted visual.

---

## 8. Notification triggers this feature should eventually fire (for the notifications mini-track)

Logged now per the standing build habit — NOT built in B105/B106 except possibly the
first one as the mini-track's opening thread:

- **PO submitted but blocked — sign-off required** → notify director(s) holding
  `budgets.clear_unbudgeted`. **(Candidate first notification to build.)**
- PO sign-off cleared → notify the PO raiser ("your PO can now be issued").
- Unbudgeted line minted (any size) → optional digest to finance.
- Budgeted line crossed the overrun threshold → notify project director.

---

## 9. What the Build Pack must carry (next session — NOT now)

- Fresh re-read of live code at draft time (main may move).
- Three-pass money-gate audit (correctness/completeness; money-integrity/
  transactional safety; gate logic/permissions). Expect Critical+High+Medium defect
  counts in line with prior money-path packs.
- Test list (warm-DB double-run) covering at minimum:
  - resolve-existing-line vs mint-new-line;
  - code-unique-per-budget enforcement (attempt to add a 2nd line for an existing
    code → blocked);
  - back-compat alias: `budget_line_id` still accepted + validated; mismatch → 422;
  - old `unbudgeted_*` cluster accepted-but-ignored (deprecation);
  - mint no longer forces Red at create (§3.4 re-baseline of B102 tests);
  - PO completeness: incomplete draft persists; submit of incomplete → 422;
  - Gate A floor boundary (£999.99 / £1000.00 / £1000.01);
  - Gate B % boundary (just-under / exactly / just-over red %);
  - draft never gates (committed £0 → no ack);
  - submit-blocked → clear/acknowledge → re-submit succeeds (both ack types);
  - the two ack paths are separate (`clear_unbudgeted` rejects a budgeted line;
    `acknowledge_commitment` rejects an unbudgeted line);
  - idempotent clear/acknowledge;
  - award path inherits the gate via its downstream PO submit;
  - audit rows written for mint, gate-trip, and each ack.
- Migration 1 (DDL) + Migration 2 (seed row), both with downgrade.
- Permission decision for Gate B ack confirmed (recommendation: reuse
  `budgets.clear_unbudgeted`).

---

*End of design v2 (LOCKED). Next session: B105/B106 Build Pack draft against this
document + a fresh live-code re-read, under full money-gate audit discipline.*
