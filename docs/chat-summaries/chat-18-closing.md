# Chat 18 closing — Prompt 2.4B-ii Budgets Playwright E2E

**Closed:** 2026-05-14
**Predecessor anchors:**
- Chat 17 (2.4B-i) closed 2026-05-12 (Jest 47, errata E1–E13)
- Track 8 P0 closed 2026-05-13 (commit `b5ebdf3` — pod-recycle auto-recovery wired)
**Final commit:** see git log (`chore(2.4B-ii): chat-18 close — Playwright E2E baseline + 31 tests`)

## Self-report (§R6 contents)

| Item | Value |
|---|---|
| Test count (physical) | 32 |
| Test count (active)   | 31 (1 quarantined — LineDrawer #6) |
| Test count (smoke)    | 6 |
| Suite runtime (smoke) | **19.3 s** end-to-end (incl. globalSetup ~10 s, teardown <1 s) |
| Suite runtime (full)  | NOT EXECUTED this session — Rhys runs full suite locally on clean state per operator policy 2 |
| Browser matrix        | chromium 1.60.0 (Playwright pinned `^1.51.0`, yarn resolved 1.60.0 — caret-minor) |
| Trace storage path    | `frontend/test-results/` (gitignored) |
| HTML report path      | `frontend/playwright-report/` (gitignored) |

### Smoke run output (yarn e2e:smoke)
```
Running 6 tests using 1 worker
  ✓ 1 [chromium-pm]    › budget-detail.pm.spec.ts:5:5    › @smoke header tiles render … (1.6s)
  ✓ 2 [chromium-pm]    › budgets-list.pm.spec.ts:12:5    › @smoke populated state … (1.3s)
  ✓ 3 [chromium-pm]    › line-drawer.pm.spec.ts:25:5     › @smoke edit + save … (3.0s)
  ✓ 4 [chromium-pm]    › lines-grid.pm.spec.ts:6:5       › @smoke drag-reorder … (5.1s)
  ✓ 5 [chromium-admin] › lifecycle.admin.spec.ts:19:1    › @smoke full lifecycle … (3.0s)
  ✓ 6 [chromium-anon]  › auth.anon.spec.ts:6:5           › @smoke login success … (1.6s)
6 passed (19.3s)
```

### Skipped / quarantined
- `line-drawer.pm.spec.ts` — **LineDrawer #6 "E9 conflict banner"** marked `test.skip` per Build Pack v4 §15 known risk + operator policy 3a. The deterministic refetch path requires `window.queryClient = queryClient` exposure in `App.jsx`, which would be a `frontend/src/` source change outside §1's hard constraint. Equivalent coverage exists in Chat 17 `LineDrawer.test.jsx` Jest harness.

### Deviations from Build Pack v4
- **D13 (new)** — `AppraisalCostLine` schema drift. Build Pack §R2.2b clone-list contained 5 phantom columns (`subcategory_id`, `input_basis`, `input_rate`, `input_quantity`, `manual_override_value`) that do not exist in the live model (`backend/app/models/appraisals.py` lines 164–186). The live schema is 10 columns: `appraisal_id, display_order, cost_code_id, label, category, auto_source, percentage, amount, is_locked, notes` (+ id/created_at/updated_at defaulted). Git history: model was created in `0f47ef8` (2026-05-02) with one adjustment in `b1e6712` (2026-05-03) — both predate Prompt 2.4A. The phantom columns appear to be a Prompt-2.2-era earlier draft that never landed on `main`. **Resolution per operator option (a)**: seeder uses the 10-column live list; Build Pack v4 annotated inline.
- **D14 (operational quarantine)** — LineDrawer #6 demoted to `test.skip` per known risk (above).

Other D1–D12 unchanged from v4.

### Baseline gate (§R0.5)
| Gate | Jest | pytest | Bundle |
|---|---|---|---|
| BEFORE | 47/47 ✓ | 673 ✓ | 387.09 kB |
| AFTER  | 47/47 ✓ | 673 ✓ | 387.10 kB |
| Δ      | 0 | 0 | +10 bytes (gzip rounding; Playwright is devDep) |

### Open items / learnings for next chat

1. **LineDrawer #6 stabilisation (P1)** — Decide whether to:
   (a) add `window.queryClient = queryClient` to `App.jsx` in dev mode only (2-line source change, unlocks the conflict-banner E2E test), or
   (b) keep relying on the Jest unit-test coverage and remove the skip placeholder.
   Either way is acceptable; current state is "covered but only in Jest harness".

2. **FTC method + Manual FTC selectors (P3)** — LineDrawer #5 uses `getByRole('combobox', {name:/ftc method/i})` and `getByRole('spinbutton', {name:/forecast.*complete|manual/i})`. Held active in this session (not flaky in smoke run). If full-suite run flakes on these, the fix is two testids in `LineDrawer.jsx`.

3. **MFA_ENCRYPTION_KEY (P0 — env doc gap)** — Discovered missing during pod recovery: `app/auth/mfa.py::_get_fernet` reads this from `.env` and raises on missing/invalid. Should be added to the canonical `.env` template documented in the bootstrap-fix-p0 build pack (currently lists DATABASE_URL + BOOTSTRAP_ADMIN_* + JWT_SECRET but not MFA_ENCRYPTION_KEY). Generate with: `python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'`.

4. **APP_ENV + SYHOMES_RATE_LIMIT_DISABLED (P1 — env doc gap)** — pytest assumes both are set (`conftest.py::_reset_rate_limiter` is in-process only and does not affect the live backend's rate limiter). Without these two env flags, ~232 tests error with 429. Add to the canonical `.env` template alongside the MFA key.

5. **Schema-drift surveillance (P2)** — D13 surfaced via the §R2.2b caveat. Suggest a future audit pass that diff-checks Build Pack heredocs against the live SQLAlchemy models before paste-ready handoff.

6. **dnd-kit KeyboardSensor cadence (P3)** — Lines grid #1 needed inter-keystroke `waitFor(200–300 ms)` because back-to-back ArrowDown presses raced the optimistic-update render. Documented as a deviation from the Build Pack v4 test code (Build Pack omitted the waits). If a future refactor swaps sensors, this assumption breaks.

## Pod-recovery preamble — Track 8 P0 #7

This is the **7th** consecutive pod-recycle requiring `provision_postgres.sh` + `.env` recovery (Chat 17 saw 6 such interruptions). The runbook is now stable:

1. Read `bootstrap.py` module docstring (lines 1–106) for env var requirements.
2. Reconstruct `/app/backend/.env` with:
   - `DATABASE_URL=postgresql+psycopg://syhomes:syhomes_dev@127.0.0.1:5432/syhomes`
   - `BOOTSTRAP_ADMIN_EMAIL=rhys@syhomes.co.uk`
   - `BOOTSTRAP_ADMIN_PASSWORD=<the actual password>`
   - `TEST_USER_PASSWORD=TestUser-Dev-2026!`
   - `JWT_SECRET=<random 256-bit>`
   - `MFA_ENCRYPTION_KEY=<Fernet.generate_key()>` ← **add to runbook**
   - `APP_ENV=test` ← **add to runbook**
   - `SYHOMES_RATE_LIMIT_DISABLED=1` ← **add to runbook**
   - `CORS_ORIGINS=<preview URL origin>`
3. Reconstruct `/app/frontend/.env` with:
   - `REACT_APP_BACKEND_URL=<preview URL>`
   - `REACT_APP_PREVIEW_URL=<same>`
4. `bash /app/scripts/provision_postgres.sh` — installs PG16 + bootstraps DB + starts backend.
5. `sudo supervisorctl restart frontend` so CRA's webpack-dev-server picks up the new `.env` (otherwise `process.env.REACT_APP_BACKEND_URL` is undefined in the bundle → frontend calls `/undefined/api/...`).
6. Verify Jest 47, pytest 673, bundle ≤390 kB.

The preview URL is captured via Emergent sandbox `preview_endpoint` env var (was `https://po-suppliers-phase2.preview.emergentagent.com` this session).
