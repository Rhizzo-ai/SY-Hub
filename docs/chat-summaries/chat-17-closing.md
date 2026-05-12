# Chat 17 — Prompt 2.4B-i Budgets Frontend (Build Pack v2)

**Dates:** 2026-05-10 → 2026-05-12 (3 calendar days, six pod-recycle interruptions)
**Build Pack:** `/app/docs/SY_Hub_Prompt_2_4B_i_Frontend_Build_Pack_v2.md`
**Shipped:** §R0 through §R10 — all phases ✓

---

## Self-report (§R9)

Did the chat execute the §R0-§R8 implementation faithfully? **Mostly yes**, with 11 documented erratas (E1-E11) where the spec diverged from the running backend / build tooling. Every divergence was surfaced to the operator before code committed; nothing was silently re-interpreted.

Did every spec rule survive? **One open question:** §R6.3 H8 "extract `buildReorderedIds` to its own file" was deferred until §R8 broke the pure-fn test — fixing it forced the extraction at that point. No user-visible impact, but the fix landed late.

Did the brand-token rules hold? **Yes** — every Save / Activate / Lock / primary CTA uses `bg-sy-teal text-white hover:brightness-110`; every destructive Unlock / Close / NewVersion / Discard uses `bg-sy-orange text-white hover:brightness-110`. No `-hover` suffixes anywhere. No purple gradients. Verified by inspection across BudgetsList, LifecycleActions, ConfirmDialog, LineDrawer.

Did mobile-floor hold? **Yes** — `useIsDesktop()` gates every mutation surface (lifecycle, inline edit, drag handles, items add/edit/delete, drawer Save). Mobile users see a read-only banner and no edit affordances.

Did sensitive-field gates hold? **Yes** — `notes` + FTC method/value are hidden in the LineDrawer when user lacks `budgets.view_sensitive`. Money tiles render "—" via `formatMoney(undefined)` when stripped by backend. Schema `.nullable().optional()` round-trip verified by `budgets-schemas.test.js`.

Did Rules of Hooks hold? **Yes** — every hook called unconditionally above every early return across all 14 new components / pages.

Where did I add things not in spec? Two operator-confirmed additions:
1. **v1↔v2 lineage breadcrumb** in BudgetHeader (operator request after §R5 review; landed as `components/budgets/BudgetLineage.jsx`, documented E10).
2. **Cmd/Ctrl+S + Esc keyboard shortcuts** in LineDrawer (operator request before §R7).

---

## Bundle delta

| Stage | `main.js` gzipped | Delta from prior |
|---|---:|---:|
| Chat-17 start (post-R3 baseline) | 336.95 kB | — |
| After §R5 (header + lifecycle) | 362.82 kB | +25.87 |
| After §R6 (BudgetLinesGrid + dnd-kit) | 382.72 kB | +19.90 |
| After §R7 (LineDrawer + items + picker) | 387.08 kB | +4.36 |
| After §R8 (tests, no app bundle impact) | 387.08 kB | 0.00 |
| **Total chat-17 delta** | **387.08 kB** | **+50.13 kB gzipped** |

The +50 kB covers: TanStack Table v8, dnd-kit Sortable + Modifiers, shadcn Sheet, react-hook-form + zodResolver, zod runtime, 14 new components, 11 new hooks, 6 new lib helpers. The biggest single contributor is TanStack Table (~12 kB) + dnd-kit (~9 kB).

---

## Test summary

| Metric | Value |
|---|---|
| Test suites | 10 |
| Tests | 46 |
| Failed | 0 |
| Runtime | 3.4 s |
| Coverage (lib/) | **96 %** |
| Coverage (lib/schemas/) | 86 % |
| Coverage (pages/projects/BudgetsList) | 92 % |
| Coverage (components/budgets — tested files) | 100 % on Status/Variance/Sensitive/BudgetsTable/BudgetLineage; 66-86 % on LifecycleActions/LineDrawer/CostCodePicker/ConfirmDialog |
| Coverage gap | 5 of 14 components have 0% (BudgetHeader, BudgetLinesGrid, SortableLineRow, BudgetDetail page, LineItemsPanel) — relied on smoke-tested end-to-end paths rather than unit tests |

**Required tests by §R8 — all present:**
- `buildReorderedIds` pure-fn unit (H8) ✓
- `test_lineage_breadcrumb_renders_when_sibling_present` (E10) ✓
- E9 conflict-banner unit (updated_at mismatch surfaces banner) ✓
- Status × perm matrix (8 capability tests) ✓
- Sensitive-stripped schema parse ✓
- Mobile-floor gate (lifecycle, BudgetsList) ✓
- dirtyFields-only PATCH body ✓

---

## Errata captured (E1-E11)

| Code | Title | Resolution |
|---|---|---|
| E1 | Test runner — Vitest → Jest/CRA | `craco test` + `@testing-library/jest-dom`; jest.fn() not vi.fn() |
| E2 | App stack — Vite → CRA | `process.env.NODE_ENV !== 'production'` not `import.meta.env.DEV` |
| E3 | Brand token — `bg-sy-teal-hover` doesn't exist | Use `bg-sy-teal text-white hover:brightness-110 active:brightness-95` |
| E4 | localStorage cross-tab auth — not used | Drop the design; auth stays in HttpOnly cookie + context |
| E5 | Cost-code endpoint flat path | `useCostCodes(projectId)` consumes existing Foundation 1.6 hook |
| E6 | Appraisals endpoint flat path | `useApprovedAppraisals` reads `/v1/projects/:id/appraisals`, filters client-side |
| E7 | Line / budget field renames | `description→line_description`, `position→display_order`, `ftc_value→forecast_to_complete`, etc. |
| E7.1 | Appraisals endpoint accepts no query params | Client-side filter via `existingSourceAppraisalIds` |
| E8 | Permission `budgets.create` → `budgets.edit` for line edits | Capability helpers updated; verified against backend deps |
| E9 | Conflict-detect via `updated_at` not `version` | LineDrawer `loadedAt` watermark + amber Reload banner |
| E10 | Backend has no lineage pointer | `BudgetLineage` computes prev/next from cached `useProjectBudgets` |
| E11 | Line items field is `rate` not `unit_cost`; `amount` required not derived | Compute `amount = qty * rate` at add-row submit; allow inline override |

---

## Sandbox recovery — pod-recycle stability

Operator interruption pattern observed across **six** recycles in this chat (recoveries #1-6 documented in `SY_Hub_Phase2_Backlog.md` ⇒ "Sandbox / pod-runtime stability"). Recovery #4 prompted the durable script ship (`/app/scripts/provision_postgres.sh`, commit `2e462f2`); subsequent recoveries 5+6 used the script (80 s cold, 36 s warm).

Sandbox stability is **Track 8 / pre-launch P0**. Recommended chat-18 action is wiring `provision_postgres.sh` into `/root/.emergent/on-restart.sh` step 0 as a precondition check.

---

## Backlog finalisation

### High-priority — Chat 18 dedicated build

- **BudgetLinesGrid v2 (BT-style)** — operator surfaced Buildertrend Job Costing Budget view as the target end-state. Cost-code grouping + expand/collapse + per-group subtotals; 11+ money columns with column visibility toggle; per-line status pills; heat-mapped variance cells (pink overrun / green underrun); indented hierarchy; sticky cost-code column on horizontal scroll; top-level view tabs. Reference: Buildertrend. Data model in 2.4A already supports it (original/current/actuals/CNI/FTC/FFC variance per line + cost_code_id for grouping); UI rework only. **To be specced as a dedicated Build Pack with full audit cycle in Chat 18.** Includes two operator-implied features: (a) bulk select + bulk actions (apply % complete to a cost-code root, bulk reassign codes, bulk delete); (b) filtering (by cost-code root, variance band, status, % complete range).

### Track 8 — Pre-launch hardening

- **Sandbox-stability P0** — wire `/app/scripts/provision_postgres.sh` into `/root/.emergent/on-restart.sh` step 0. Self-heal the missing-postgres-install case the bootstrap-fix-p0 contract didn't cover. Investigation finding documented in `SY_Hub_Phase2_Backlog.md`.
- **Mobile UX pass** — current "Read-only on mobile" floor is sufficient for 2.4B-i ship. Sidebar dominance + layout review deferred. Operator confirmed not to spend cycles here during R7/R8.

### Chat 19 — Budgets E2E

- Playwright smoke covering BudgetsList → CreateFromAppraisal → BudgetDetail → lifecycle (Draft→Active→Lock→Close), inline edit, drawer save + conflict banner, items CRUD. Was originally planned for Chat 18 — pushed back to make room for BudgetLinesGrid v2.

---

## Git status at chat close

Expected: clean working tree on `main` after all chat-17 commits push. The chat-closing commit will include:
- All 14 new components / pages / helpers
- All 10 test files + `setupTests.js` + `jest.resolver.cjs`
- `craco.config.js` jest section
- This chat-summary file
- `SY_Hub_Phase2_Backlog.md` updates (Track 8 + BT-style backlog entry)
- `memory/PRD.md` updates (R4-R8 ship records)

Two pre-existing commits in this chat that aren't reverted:
- `2e462f2` chore(infra): durable pod-recycle recovery script
- `92885b0` docs(infra): on-restart.sh investigation finding + Track 8 P0/P1 tasks

---

## Hand-off for Chat 18

Pick from in priority order:
1. **Track 8 P0** — wire `provision_postgres.sh` into `on-restart.sh` (1-2h fix, retires recurring operator interruption)
2. **BudgetLinesGrid v2 (BT-style)** — dedicated Build Pack required; high-priority operator-flagged surface
3. Chat 19 Playwright E2E once v2 is in
