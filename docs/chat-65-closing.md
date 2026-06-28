# CHAT 65 — CLOSING SUMMARY

**Project:** SY-Hub · `Rhizzo-ai/SY-Hub` · branch `main`
**Session:** C4 (RLV solver) + C4-tail (scenario comparator) — the LAST critical.
**Outcome:** Both shipped, gated, merged, and verified on `origin/main`. The
entire critical-fix backlog is now cleared.

---

## What shipped

### C4 — RLV solver: secant → bracketed bisection
- `backend/app/services/rlv_solver.py` fully rewritten. Unbracketed secant
  replaced with bracketed bisection over `[0, 2 × GDV]`.
- Guaranteed convergence (monotonic `profit_gap` proven); three honest outcomes
  (converged / unreachable-with-best-achievable / degenerate-no-GDV);
  iterations bounded at 60 (safety cap), typically ~25 evaluations.
- Signature, `RlvResult` (7 fields), `_penny`/`_achieved_pct` preserved — no
  router or downstream change. No mutation of `land_purchase_price`.
- Proven offline (named cases + 500 random, worst margin gap £1.01 < £1.50 test
  bound) BEFORE build. On-platform: 10 RLV tests green, appraisals suite 52
  passed, independent live-API verification.

### C4-tail — scenario comparator display honesty
- `backend/app/services/appraisal_scenarios.py::get_group_comparator`:
  `residual_land_value` now nulled unless `rlv_converged is True`; new
  `rlv_converged` key added. Two-key edit only.
- 3 new tests in `backend/tests/test_appraisal_scenarios_comparator.py`; 16
  scenario tests green; verified live end-to-end.

### Verified on origin/main (codeload tarball, not self-report)
- Bisection present, secant gone; 6 + 3 new tests present; alembic head still
  `0050`; both scaffolding scratch files (`backend_test.py`,
  `recovery_verification_test.py`) absent.

---

## Process notes (for continuity)

- **Two conflict-merges this session.** Both pushed as `conflict_*` branches
  (Emergent auto-commits the whole working tree; cannot push only changed
  files), merged via PR. Never force-pushed. Branches:
  `conflict_260626_2255` (C4) and `conflict_280626_2056` (C4-tail, PR #29).
  Both can be deleted now.
- **The C4-tail push carried 45 files**, only 4 of which were this session's
  work. The rest: C1-front files already on main (harmless re-touch), a
  platform preview-host rewrite (`sy-production-qa → prod-property-hub`,
  27 files, hostname-only, no logic — consciously let through; reverting risks
  breaking this container's preview/CI), and 2 scaffolding files (removed before
  save). Full delta was eyeballed before merge.
- Sandbox required Postgres re-provision at session start (the usual wipe).
  C4 demo data lost again on the test-suite teardown — irrelevant to C4 (proven
  via test suite, not preview clicking).

---

## State at close

- **Critical-fix backlog: CLEARED.** C3 · NEW-CRIT-1+H1 · C2 · C1-back ·
  C1-front · C4 · C4-tail all on main.
- Alembic head `0050_backfill_invoiced_against_commitment`, **143 permissions**,
  10 roles.
- Test baseline: the long-standing 19-failure baseline persists; two are the
  known stale permission-count assertions (136 vs live 143) in
  `test_auth_rbac.py` / `test_permissions_2_6.py` — still owed a quiet
  hardening pass.

---

## Next session (Chat 66): H4/H5 — appraisal land/finance double-count

**DESIGN-FIRST. Money-engine change — highest blast radius in the appraisal
system.** Full design read already done this session — see the chat-66 opener
for the complete findings. Headline:

- **Root cause is a design gap, not a typo.** There is **no `Land` auto-source
  and no land flag** on `AppraisalCostLine`. Land lives only in the header
  field `land_purchase_price`; a "land line" exists only if a user manually adds
  an Acquisition line. The engine then guesses "is there a land line?" by
  matching an Acquisition line whose amount **exactly equals** `land_price` AND
  whose label **starts with 'land'** (`appraisal_calc.py:147-151`), and folds
  `land_price` into acquisition only if that guess returns False
  (`appraisal_calc.py:232-233`). The guess fails on "Site purchase" labels,
  split land lines, or rounding mismatches → land counted twice → **profit
  understated**. A coincidental match drops real land cost.
- **Finance (H5):** `finance_tot = max(cat_tot["Finance"], total_finance)`
  (`appraisal_calc.py:240`) is a blunt anti-double-count guard; mixed
  manual+engine finance can be silently under- or over-counted.
- **Likely fix:** make `land_purchase_price` the single source of truth for
  land (or add a real `Land` auto-source / explicit flag). Reconcile finance
  properly rather than `max()`. **Needs a migration (new enum value) AND a
  frontend touch** (how the screen creates/handles land lines) — NOT a clean
  backend-only gate. Prove the new summation offline (named + random cases)
  before any Build Pack, same as C4.

Read-before-Build-Pack: `appraisal_calc.py` recompute lines 126-266; the
default-line seeder `routers/appraisals.py:470-516`; the manual line-create
endpoint `routers/appraisals.py:1132`; `AppraisalCostLine` /
`AppraisalFinanceFacility` models; existing appraisal tests.
