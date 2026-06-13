You are resuming work on SY-Hub (`Rhizzo-ai/SY-Hub`, branch `main`). This is
**B88 Pack 3 — Packages (the tendering spine)**. A complete Build Pack follows
this message; treat it as authoritative and execute it through its STOP gates.
Do not auto-advance past a gate.

## Before you write a single line
1. **Confirm pod health + ground truth** (a 500 after any break = wiped DB
   until proven otherwise):
   - `/api/health` → 200; if not: `bash /app/scripts/provision_postgres.sh`
     → `/root/.venv/bin/python -m app.bootstrap` → reseed.
   - Confirm alembic head `0046_rbac_operator_overrides`, 130 cost_codes,
     136 permissions, 10 roles. Report all four.
2. **Read these files line-by-line and confirm their CURRENT signatures match
   what the Build Pack assumes — if ANY differs, STOP and report the
   discrepancy before building** (do not guess or adapt silently):
   - `backend/app/services/purchase_orders.py` — esp. `create_po(...)` and how
     `_compute_line_totals` derives net/vat/gross (the award engine calls
     `create_po`; note the function is `create_po`, NOT
     `create_purchase_order`).
   - `backend/app/services/subcontracts.py` — esp. `create_subcontract(...)`
     and the `Draft`→`Active` activate guard (`signed_at` requirement).
   - `backend/app/services/budgets_reconciliation.py` — the
     `committed_value`/`committed_not_invoiced` chain you must NOT replicate.
   - `backend/app/services/budgets.py` + the budgets model — `BudgetLine` /
     `BudgetLineItem` shape (you inherit qty/unit/rate from line item detail).
   - `backend/app/seed_rbac.py` — the EXACT `pos` / `subcontracts` permission
     blocks AND their per-role grants (director uses all-minus-exclusions —
     mind the `packages.delete` exclusion trap; PM creates/edits, finance
     awards). `backend/app/models/rbac.py` for `RESOURCES`/`ACTIONS` enums.
   - `backend/app/routers/subcontracts.py` — copy its exception→HTTP mapping,
     `require_permission` gating, and scope-check pattern verbatim in intent.
   - `backend/server.py` — confirm routers mount on `v1_router` (`/api/v1/...`)
     and add the packages router there.

## How to work
- Build STRICTLY to the Build Pack's §1–§8. The award engine (§3.3) is the
  money-integrity crux: one DB transaction, all-or-nothing, package row locked
  FOR UPDATE, the Σ(award net) ≤ package total guard and the per-line quantity
  guard both enforced server-side. Server computes every net (qty × rate);
  never trust a client-supplied net.
- The award authority gate is `packages.award` ALONE (the downstream PO/SC is
  created service-side; do NOT additionally require `pos.create`/
  `subcontracts.create` — finance, the intended awarder, lacks create by
  design). The Build Pack §6 explains this; follow it exactly.
- Test files named EXACTLY `backend/tests/test_packages.py` and
  `backend/tests/test_packages_service.py`. No single-file consolidation.
  ≥55 backend test functions; run pytest TWICE (cold + WARM-DB); WARM is
  authoritative.
- Mutation handlers (frontend) must surface errors visibly — no silent
  onError. The live eyeball is the real acceptance test, not the suite count.
- **GATE 1 (backend) is a HARD STOP** — money/permission/data. Report exactly
  what §8 GATE 1 demands, INCLUDING the live-API request/response proofs
  (create → tender → bid → split award → over-total rejection → PO-issue
  rolls commitment onto the budget line). Then STOP. Do not start the
  frontend until cleared.
- **GATE 2 (frontend + docs)** — docs batch in here (no money risk). Live
  eyeball of `/admin/packages`, full flow walked in the UI. CHANGELOG +
  `docs/chat-summaries/chat-53-closing.md` committed in the same push.
  **NEVER write to `docs/SY_Hub_Phase2_Backlog.md`** (operator-only).
- Committed ≠ pushed. After each gate's "Save to GitHub", expect two commits
  (code+tests, then docs). No Force Push — conflicts go Branch → PR →
  merge → verify.

Confirm pod health + the seven file reads first, flag any signature
discrepancy, then begin Gate 1. The full Build Pack follows.
