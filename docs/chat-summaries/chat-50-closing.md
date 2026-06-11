# Chat 50 — Build Pack B88 Pack 1 — Closing Summary

**Pack:** Build Pack B88 Pack 1 · Cost-Code Group Hierarchy + Cost-Code Admin · Backend + frontend
**Scope:** New two-tier cost-code hierarchy (parent groups + Construction subgroups), master-table CRUD with complete delete guard, retire/reactivate, granular RBAC permissions, canonical reseed against the operator's corrected master, and a new permission-gated admin screen.
**Status:** COMPLETE. All 5 gates raw-fetch verified on `origin/main`. Live eyeball passed (tree renders, super_admin/director delete-gate differs, in-use delete shows inline block-reasons + Retire-instead). An in-pack 500 was caught during eyeball and fixed before final acceptance.

## What shipped

### Gate 1 — DB schema
- Alembic migration `0044_cost_code_groups`.
- `cost_code_sections` gains `parent_section_id` (uuid, FK self-ref, RESTRICT) + `allows_subgroups` (bool, default false).
- Two-tier hierarchy: parents at tier 1, Construction-only subgroups at tier 2. A third tier is forbidden in code + seed (Build Pack §2.2 rule 3).

### Gate 2 — RBAC
- `cost_codes.{create,edit,delete}` added to the catalogue. Granular re-point of the legacy `cost_codes.admin` per §4.3.
- super_admin holds all 3. director + finance get create+edit. **Delete is super_admin-ONLY** — director explicitly excluded via the role-grants exclusion set in `seed_rbac.py`. Backend defence-in-depth at `routers/cost_codes.py:767`.
- Permission count: **133 → 136**. super_admin role: **133 → 136**. director role: **129 → 131**.

### Gate 3 — Service + endpoints
- Section CRUD: `POST/PATCH/DELETE /api/cost-code-sections`, `GET /api/cost-code-sections?tree=true`.
- Complete delete guard on `DELETE /api/cost-codes/{id}` AND `DELETE /api/cost-code-sections/{id}` — checks budget_lines, appraisal_cost_lines, PO lines (transitively), project_cost_codes, cost_code_subcategories, cost_code_entity_mapping, replaced_by_code_id self-ref. Returns structured `409 {detail: {message, blockers[]}}`, NEVER a bare 500.
- Reactivate (un-retire) endpoint: `POST /api/cost-codes/{id}/reactivate` clears `retired_at` / `retired_reason` / `replaced_by_code_id`.

### Gate 3 (partial-acceptance follow-ups, accepted before clearing)
- Un-skipped 2 delete-guard tests by giving the fixture a self-seeding probe Appraisal + Active Budget (with module-teardown cleanup) so G2 + G3 actually exercise the 409 block path in CI.
- Fixed 25 stale baseline tests (alembic head bumps `0043 → 0044`, permission count bumps `133 → 136` and `129 → 131`, the orphan-perm list trimmed, `test_no_delete_endpoint…` inverted to `test_delete_endpoint_wired…`, function rename `test_permission_catalogue_count_in_python_is_129 → test_total_permissions_matches_catalogue`).
- Full warm-DB suite **1421 passed · 0 failed** both runs.

### Gate 4 — Canonical reseed (against corrected master)
- **Rejected first submission** built against a stale 129-code list with 5 "ACC extras" preserved + an invented SAL-10 "Reservation Fees". Operator provided `BTCostCodes_20260609 (1) (3).xlsx` as the authoritative master.
- Re-built against the master: **130 codes · 9 parent groups · 10 Construction subgroups (4.00–4.09)**.
- Reconciling (NOT additive) seed: hard-deletes non-canonical rows when unreferenced; retires (`status='Retired'`) when blocked by RESTRICT FKs.
- Corrections vs prior 0013 seed:
  - ACC → **3** codes (ACC-04..08 hard-deleted on this pod, no FK refs).
  - SAL-09 = "Post-completion holding & maintenance"; SAL-10 = "Other sales & disposal costs".
  - **OHD-09** newly seeded ("HR, recruitment & employee welfare").
  - **SER-10 un-retired** from legacy migration `0016_audit_remediation_patch_3`.
- Parent codes recoded `slug → numeric` ("acquisition" → "1", "construction" → "4", etc.). Group names canonicalised: 1 = Land & Acquisition; 3 = Professional Fees; 5 = Sales & Marketing; 8 = Accounting.
- Spreadsheet's duplicate-4.08 collision resolved per operator: 4.06 = Prefab/MMC, 4.07 = Existing Buildings, 4.08 = External Works.
- Idempotency proven: run-2 = 0 changes, row counts identical.
- Migration round-trip safety: `test_migration_0025_actuals.py`'s downgrade-then-upgrade now finalises with `scripts.seed_cost_code_structure.run()` so the dropped `parent_section_id` / `allows_subgroups` columns are re-populated for downstream test modules.

### Gate 5 — Frontend admin screen
- New `frontend/src/pages/CostCodeAdmin.jsx` at route `/cost-codes/admin`.
- Tree view (parent → subgroup → code) with the master's display convention ("4 Construction", "4.01 Substructure", "FAC-01 …").
- Permission gates read off **live `me.permissions`** via `useAuth().hasPerm(code)` — no hardcoded role-name checks. A debug badge row prints the live `create / edit / delete` evaluations for eyeball confirmation.
- 409 block-reasons surfaced **inline** within the delete modal (orange-accent panel, bulleted blockers), with a **"Retire instead"** button that closes the delete modal and opens the retire modal pre-targeted at the same code. Toasts only fire for non-409 errors.
- Brand colours locked per Build Pack §6: teal `#0F6A7A` primary, orange `#FC7827` accent, grey `#CECECE` neutral.
- Anti-recursion refactor: first build used a self-referencing `<SectionNode>` which crashed CRA's babel-loader chain with "Maximum call stack size exceeded". Refactored to two non-recursive components (`<ParentSectionNode>` + `<SubgroupNode>`) — tree depth is fixed at 2 by design.
- Legacy `CostCodesList.jsx` + `ProjectCostCodes.jsx` kept alive (different surfaces: read-only browse and per-project enrolment toggle); list page now headlines a teal "Open Cost-Code Admin →" link.

## The seed-correction saga (129 → 130)

Gate 4 was originally submitted against a 129-code canonical list (sourced from the Build Pack §5.3 mapping in the markdown). Operator REJECTED it: the actual authoritative source is `BTCostCodes_20260609 (1) (3).xlsx`, not the build-pack markdown. Key corrections supplied by operator:

| | Rejected (129) | Corrected (130) |
|---|---|---|
| Total | 129 + 5 ACC "extras" | **130 canonical, no extras** |
| ACC | 8 (5 preserved as extras) | **3** (ACC-04..08 hard-deleted) |
| SAL-09 | "Other sales & disposal costs" | "Post-completion holding & maintenance" |
| SAL-10 | invented as "Reservation Fees" | **"Other sales & disposal costs"** |
| OHD | 8 codes | **9 codes** (OHD-09 added) |
| SER-10 | Retired → SER-06 | **Active** (un-retired) |
| Group 1 | "Acquisition" | "Land & Acquisition" |
| Group 3 | "Design & Professional Fees" | "Professional Fees" |
| Group 5 | "Sales, Marketing & Disposal" | "Sales & Marketing" |
| Group 8 | "Accounting & Financial Services" | "Accounting" |

The discard-and-rebuild was clean — the seed script was made authoritatively reconciling (not additive) so the corrected master OVERRIDES whatever was in the DB, including any legacy retire metadata. Operator diffed the seed's full code→name map against the xlsx cell-by-cell before clearing Gate 4.

## The `?status=All` 500 bug (caught during Gate-5 eyeball)

The screen calls `GET /api/cost-codes?status=All` on mount. The legacy route passed `status` straight into `WHERE status = :s` against the `cost_code_status` Postgres enum `{Active, Retired}`. `'All'` is not a member → `InvalidTextRepresentation` → bare 500.

Fix in `routers/cost_codes.py::list_cost_codes` (10 lines):

```python
if status:
    if status.lower() == "all":
        pass
    elif status in ("Active", "Retired"):
        query = query.where(CostCode.status == status)
    else:
        raise HTTPException(422, f"invalid status filter: {status!r}")
```

Regression suite `tests/test_cost_codes_status_filter.py` (7 tests): `All`/`all` case-insensitive, `Active` / `Retired` exact, 6 bogus values → **422 not 500**, omitted-param parity with `All`, composition with `section_id`.

## Verification method

Each gate raw-fetch verified on `origin/main` by the operator before clearing. Final live eyeball at `/cost-codes/admin`:

1. As `test-admin@example.test` (super_admin) — header badges read `create:yes · edit:yes · delete:yes`; trash icons visible; deliberately-attempted delete on an in-use code (e.g. ACQ-01) showed the inline 409 panel with bulleted blocker reasons + Retire-instead button; Retire-instead opened the retire modal pre-targeted at the same code.
2. As `test-director@example.test` (director) — header badges read `create:yes · edit:yes · delete:no (super_admin only)`; trash icons NOT visible; replaced by the faded `ShieldOff` icon with tooltip "Delete requires super_admin (cost_codes.delete)".

## Final state

- **Alembic head:** `0044_cost_code_groups`
- **Permissions:** 136 (super_admin 136 · director 131)
- **Cost codes:** 130 · 9 parent groups · 10 Construction subgroups
- **Full pytest suite (warm DB):** **1449 passed · 3 xpassed · 0 failed**, both 2nd-run consecutive runs

## What's next

**B88 Pack 2 — Job-Costing grid + two budget screens.** Builds on top of the now-clean cost-code structure: per-project job-costing grid (commitments / actuals / variance against budget by cost code) and two budget UI surfaces (original vs current variance view, plus the cost-plan import). Backend has the data already (`budgets`, `budget_lines`, `actuals` from prior packs); B88 Pack 2 is mostly frontend with thin backend additions for aggregations.

## Files touched (summary)

Backend:
- `app/models/cost_codes.py` — `parent_section_id` + `allows_subgroups` on `CostCodeSection`.
- `app/routers/cost_codes.py` — section CRUD, complete delete guard, reactivate, status-filter fix.
- `app/services/cost_codes.py` — delete-guard block-reason builders.
- `app/seed_rbac.py` — `cost_codes.{create,edit,delete}` catalogue + role grants (director exclusion of delete).
- `alembic/versions/0044_cost_code_groups.py` — schema migration.
- `scripts/seed_cost_code_structure.py` — canonical reconciling seed (NEW).
- `tests/test_cost_code_sections.py`, `tests/test_cost_code_delete_guard.py`, `tests/test_cost_code_reactivate.py`, `tests/test_cost_code_seed_structure.py`, `tests/test_cost_codes_status_filter.py` — NEW.
- 25 stale baseline tests updated for the new alembic head + permission counts.

Frontend:
- `pages/CostCodeAdmin.jsx` — NEW.
- `App.js` — route added.
- `pages/CostCodesList.jsx`, `pages/ProjectCostCodes.jsx` — recoded for numeric parent codes + subgroup roll-up; list page got the "Open Cost-Code Admin" link.

Docs:
- `CHANGELOG.md` — Chat-50 entry.
- `docs/chat-summaries/chat-50-closing.md` — this file.
- `docs/SY_Hub_Phase2_Backlog.md` — operator-hand-edited only; not touched.
