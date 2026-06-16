# EMERGENT BUILD OPENER — B105 / B106: Cost-Code-First Commercial Line Model

You are continuing the SY-Hub build on `Rhizzo-ai/SY-Hub`, branch `main`, alembic
head `0049_unbudgeted_order_lines`. This is a **money-path redesign** in Track 2
(Commercial Engine). Work to the attached Build Pack `B105-B106-build-pack-v1.md`
**exactly**. It is authoritative; this opener is orientation + guardrails.

## Fresh-pod provisioning (if needed)
If the pod is cold (preview 502 / supervisor socket missing / no `postgres` user),
run the provisioning runbook first:
`bash /app/scripts/provision_postgres.sh` → `python -m app.bootstrap` → confirm
`/health` 200. Do NOT proceed until the backend is up and the existing suite
collects.

## What you are building (and explicitly NOT building)

BUILD (full detail in the Build Pack §3):
1. **Cost-code-first line schema** on PO + package lines: a line names `cost_code_id`
   (+ optional `cost_code_subcategory_id`); the old `unbudgeted` XOR is collapsed.
   `budget_line_id` stays as a validated back-compat alias. The `unbudgeted_*`
   fields stay as deprecated, accepted-but-ignored fallbacks (§3.1, §3.10).
2. **Resolve-or-mint** (§3.3, §3.4): new `find_line_for_code` helper; in `create_po`
   AND `add_package_line`, resolve the line for the code on the budget, or mint one.
   Replaces the B102 unbudgeted pre-pass. "Unbudgeted" is now a server outcome (no
   existing line), not a caller flag.
3. **Neutral mint** (§3.5): `create_unbudgeted_line` gains `force_flag=False` and, by
   default, NO LONGER forces `variance_status='Red'` / `requires_attention=True` at
   mint. The Red/attention decision moves to Gate A at submit.
4. **Gate A — unbudgeted £-floor** (§3.6, §3.7): new `evaluate_unbudgeted_floor_gate`
   wired into `submit_po_with_budget_gate` and `issue_po`, AFTER `recompute_for_po`,
   under the existing budget lock. At/above the floor (default £1,000, config-backed)
   → 409 block (`UnbudgetedAckRequiredError`), PO stays Draft. Below floor →
   flagged, non-blocking.
5. **Option (ii) separation** (§3.7a): make `evaluate_budget_overrun` skip un-cleared
   unbudgeted lines, so the EXISTING over-budget approval gate governs BUDGETED
   overruns only and Gate A owns unbudgeted lines. This is the operator-locked
   reconciliation — build it exactly as §3.7a specifies.
6. **PO completeness at submit** (§3.8): a PO cannot be SUBMITTED unless every line
   has cost_code + quantity>0 + unit_rate>=0 + vat_rate + non-empty description.
   DRAFTS may be incomplete (so `create_po` totals must tolerate incomplete lines —
   persist net=0, do not raise; §3.4 step 5). Incomplete submit → 422.
7. **Config** (§3.2): `get_unbudgeted_ack_floor` in `system_config.py` + a new seed
   row `budget.unbudgeted_ack_floor_gbp` ("1000.00", Decimal, Budget, director) added
   to `seed_system_config.py` (NOT an alembic migration).

DO NOT BUILD (hard boundaries):
- **NO** `commitment_ack_required` / `commitment_ack_cleared_by/at` columns. **NO
  DDL migration at all.** Every column already exists; alembic head stays `0049`.
- **NO** second over-budget gate, **NO** `acknowledge_commitment` action/endpoint,
  **NO** change to the existing over-budget approval workflow beyond the single
  §3.7a skip.
- **NO** new permission and **NO** new role grant. Unbudgeted sign-off reuses the
  existing `budgets.clear_unbudgeted` permission and the existing
  `/budget-lines/{id}/clear-unbudgeted` endpoint.
- **NO** frontend (B107), no notifications wiring (unless separately instructed),
  no templates/buffer/staged-maturity.

## Critical engineering constraints (money path)
- Gate A reads `committed_not_invoiced` (the Python-owned single-writer column),
  AFTER `recompute_for_po`, under the parent-budget `FOR UPDATE` lock that
  `recompute_for_line` already holds in the same transaction. Do not add a new lock.
- Raising `UnbudgetedAckRequiredError` must roll back the transition so the PO stays
  Draft — the router commits only after the service returns; verify nothing commits
  before the raise.
- Mint cannot duplicate: the DB constraint `uq_budget_lines_budget_cost_subcat`
  guarantees one line per `(budget, cost_code, subcategory)`. Resolve finds an
  existing line first; a concurrent double-mint that hits the constraint must be
  caught and surfaced as 409, not 500 (§3.9 race note).
- Match key for resolve is the FULL triple `(budget_id, cost_code_id,
  cost_code_subcategory_id)`, with `IS NULL` handling for a null subcategory.

## Tests — non-negotiable
- Create the exact test files named in §6 (no single-file consolidation):
  `test_cost_code_first_resolve.py`, `test_unbudgeted_floor_gate.py`,
  `test_po_completeness_submit.py`; re-baseline the mint-forced-Red assertions in
  `test_unbudgeted_orders.py` (convert to `force_flag=True` legacy + add
  `force_flag=False` neutral).
- Cover every numbered case in §6 (resolve/mint/alias/D2/boundaries/separation/
  completeness/re-baseline/award).
- **Warm-DB double-run:** a fresh pod throws ~90 IntegrityErrors on the first
  pytest run. Run the suite TWICE and report BOTH counts; the second is accurate.

## Stop conditions / gate report
After building, STOP and produce the gate report in Build Pack §7:
1. `alembic heads` = `0049_unbudgeted_order_lines` (no new revision).
2. grep proof NO `commitment_ack_*` columns exist anywhere.
3. RBAC permission count UNCHANGED (paste both runs).
4. `get_unbudgeted_ack_floor` returns Decimal("1000.00"); seed row present (SELECT).
5. Full pytest output, BOTH runs, new files broken out + re-baselined file.
6. 409 body sample (Gate A) + 422 body sample (completeness).
7. `scan_requires_attention` production code unchanged.
8. Option (ii) separation proof: `is_within_budget` True for a below-floor
   unbudgeted-only "overrun"; `evaluate_budget_overrun` unbudgeted-skip exercised.

Commit in two commits as usual (1: code + tests; 2: CHANGELOG + chat-59-closing),
but DO NOT consider the build accepted until the operator's reviewer (Claude) has
verified the gate report against `origin/main`. Record in CHANGELOG that B105/B106
ships no alembic revision by design (all columns pre-exist; config seeding is
lifespan-owned) and that "Gate B" from the original design is closed as already
satisfied by the Prompt 2.5 over-budget approval gate.

Begin. Read the Build Pack end to end before writing any code.
