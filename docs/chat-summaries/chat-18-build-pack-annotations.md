# Build Pack 2.4B-ii v4 — on-disk annotation

This file documents inline annotations to Build Pack v4 (the paste-ready
master at `https://customer-assets.emergentagent.com/job_418fe444-56cf-402f-b402-d8ecae94dddd/artifacts/l558ce6p_SY_Hub_Prompt_2_4B_ii_Budgets_E2E_Build_Pack_v4.md`).

When the next session reads the Build Pack, apply these corrections.

---

## §R2.2b — `--extra-appraisal` cost-line clone — REPLACE

### Build Pack v4 text (incorrect — 14 phantom columns)
```sql
INSERT INTO appraisal_cost_lines (
  appraisal_id, cost_code_id, subcategory_id, label, category,
  auto_source, input_basis, input_rate, input_quantity, percentage,
  manual_override_value, amount, notes, display_order
)
SELECT
  v_new_appraisal_id, cost_code_id, subcategory_id, label, category,
  auto_source, input_basis, input_rate, input_quantity, percentage,
  manual_override_value, amount, notes, display_order
FROM appraisal_cost_lines WHERE appraisal_id = v_src_appraisal_id;
```

### What actually shipped (D13 — live 10-column schema)
```sql
-- Verified against backend/app/models/appraisals.py lines 164-186 on
-- 2026-05-14. AppraisalCostLine columns: id (default), appraisal_id,
-- display_order, cost_code_id, label, category, auto_source, percentage,
-- amount, is_locked, notes, created_at (default), updated_at (default).
INSERT INTO appraisal_cost_lines (
  appraisal_id, display_order, cost_code_id, label, category,
  auto_source, percentage, amount, is_locked, notes
)
SELECT
  v_new_appraisal_id, display_order, cost_code_id, label, category,
  auto_source, percentage, amount, is_locked, notes
FROM appraisal_cost_lines WHERE appraisal_id = v_src_appraisal_id;
```

Phantom columns removed (do not exist on `main` and never have):
- `subcategory_id`
- `input_basis`
- `input_rate`
- `input_quantity`
- `manual_override_value`

Live column added (was missing from v4 clone list):
- `is_locked` (boolean, default false) — preserved in the clone.

Git history of `backend/app/models/appraisals.py`:
- `0f47ef8` 2026-05-02 — initial 206-line model
- `b1e6712` 2026-05-03 — one adjustment, 25/8 +/-

Both commits predate Prompt 2.4A. The phantom column list in v4 traces
back to a Prompt-2.2-era earlier draft that never merged.

---

## §R3.6 LineDrawer — quarantine #6 — APPEND

### LineDrawer #6 "E9 conflict banner" — `test.skip` per operator policy 3a

The conflict-banner E2E test requires deterministic refetch of the
budget line query while the drawer is open. The Build Pack v4 fallback
("page.evaluate using window.queryClient.invalidateQueries") assumes
the React app exposes the QueryClient on `window`. Chat 17's source
does not do this.

Operator policy 3a (recorded in session opener): surface the flake,
quarantine, do NOT add `window.queryClient = queryClient` to `App.jsx`.
Equivalent coverage already exists in `LineDrawer.test.jsx` Jest unit
test ("E9 conflict banner").

If the operator approves the 2-line source change in a future session,
the skip can be flipped back on without further edit to the spec.

---

## §R1.2 globalSetup — `psql` path — REPLACE

### Build Pack v4 text
```typescript
execSync(
  `PGPASSWORD=syhomes_dev psql -h 127.0.0.1 -U syhomes ...`,
```

### What actually shipped
On a freshly-provisioned Emergent pod the `psql` binary lives at
`/usr/lib/postgresql/16/bin/psql` and is NOT on `PATH`. Both globalSetup
and globalTeardown use the absolute path.

---

## §R3.4 Lifecycle #1 — ConfirmDialog wiring — REPLACE

### Build Pack v4 implied (incorrect)
```typescript
await page.getByTestId('lifecycle-activate').click();
await page.getByTestId('lifecycle-activate-dialog-confirm').click(); // wrong
await expect(page.getByText('Active')).toBeVisible();
```

### What actually shipped
`LifecycleActions.jsx` makes `Activate` and `Lock` **direct mutations**
(no ConfirmDialog wrapper). Only `Unlock`, `Close`, and `NewVersion`
use `ConfirmDialog`. Test corrected to click the button only.

```typescript
await page.getByTestId('lifecycle-activate').click();
await expect(page.getByText('Active')).toBeVisible();
// Lock is the same — immediate mutation.
// Close + NewVersion go through ConfirmDialog (testId-prefixed).
```

---

## §R3.5 Lines-grid #1 drag-reorder — keyboard cadence — APPEND

The dnd-kit KeyboardSensor processes ArrowDown presses one at a time
and the optimistic-update render must settle before the next press can
swap. Add 200–300 ms `waitForTimeout` between presses. Without this
the test produced `[Superstructure, Substructure, Finishes]` (one swap
only) instead of the expected `[Superstructure, Finishes, Substructure]`.

```typescript
await firstDrag.focus();
await page.keyboard.press('Space');
await page.waitForTimeout(200);
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(300);
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(300);
await page.keyboard.press('Space');
await page.waitForTimeout(1_500); // optimistic + server confirm settle
```

---

## §R2 helpers/factory — single-current constraint — APPEND

The `from-appraisal` endpoint rejects when the project already has a
non-terminal current budget (`uq_budgets_one_current_per_project`
allows exactly one `is_current=true` per project). The factory
helper supersedes any non-terminal current via SQL before each POST:

```typescript
function supersedeCurrent(projectId: string): void {
  execSync(
    `${PG_CMD_BASE} -c "UPDATE budgets SET status='Superseded', is_current=false WHERE project_id='${projectId}' AND status IN ('Draft','Active','Locked')"`,
    { stdio: 'pipe' },
  );
}
```

This is invoked at the top of `createFreshBudget` (and by extension
`createActiveBudget` / `createLockedBudget`).

Side effect: BudgetsList tests that run after any fresh-budget-using
test will see additional Superseded rows in the list. Tests are written
defensively (`expect(rows.first()).toBeVisible()` rather than asserting
a specific count).

---

## §R2.2b base seed — `appraisal_cost_lines` seeded on base appraisal — APPEND

The Build Pack v4 base seed creates `Demo Appraisal v1` but does NOT
populate its `appraisal_cost_lines` rows. The `--extra-appraisal` flag
then errors with "no source appraisal with cost lines found" because
the only Approved appraisal has zero cost lines.

The shipped base-seed block additionally inserts 3 `appraisal_cost_lines`
rows on `Demo Appraisal v1` (Substructure / Superstructure / Finishes,
all category `Construction`, auto_source `Manual`). These are the rows
the `--extra-appraisal` clone targets.

```sql
INSERT INTO appraisal_cost_lines
  (appraisal_id, display_order, cost_code_id, label, category, auto_source, amount)
VALUES
  (v_appraisal_id, 0, v_cc_ids[1], 'Substructure works', 'Construction', 'Manual', 400000),
  (v_appraisal_id, 1, v_cc_ids[2], 'Superstructure',     'Construction', 'Manual', 600000),
  (v_appraisal_id, 2, v_cc_ids[3], 'Finishes',           'Construction', 'Manual', 250000);
```

---

## §R2.1 helpers/login — `source_appraisal_id` payload — REPLACE

The `from-appraisal` POST body uses `source_appraisal_id`, not
`appraisal_id`. Schema verified via 422 response surfaced during smoke run:

```json
{"detail":[
  {"type":"missing","loc":["body","source_appraisal_id"],"msg":"Field required",...},
  {"type":"extra_forbidden","loc":["body","appraisal_id"],...}
]}
```

`factory.ts::createFreshBudget` ships with the correct body shape.
