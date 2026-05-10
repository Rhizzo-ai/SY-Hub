# Chat 16.5 — Closing Summary

**Type:** Triage chat — coverage debt patch + brand tokens (Pre-2.4B-i housekeeping)
**Date closed:** 2026-05-10
**Final test status:** **664/664 passing** (641 baseline + 23 coverage-debt tests)
**Push target:** main (audit happens at phase boundaries, not per-prompt)

---

## 1. What shipped

### 1a. Coverage debt — 23 tests
Build Pack §R5 numbered: #6, #10, #14, #30, #31, #33, #34, #39, #41, #45, #46, #49, #53, #64, #65, #66, #70, #72, #74, #78, #81, #85, #89.

All landed in `backend/tests/test_budgets.py` across 11 existing classes (no new classes, no fixture refactors). Module-scoped `site_manager` fixture added (mirrors `pm`), backed by `test-site@example.test`.

### 1b. Brand tokens registered
- `design_guidelines.json` (root, NOT under `frontend/` — flagged at execution time): `colors.brand.description` clarified slate-baseline + teal-CTA split. `brand_palette` extended with `usage_rules` array (5 prescriptive rules), `*_foreground` keys, `reconciliation_status: "Provisional — Track 8 designer engagement"`.
- `frontend/tailwind.config.js`: `sy-teal` / `sy-orange` / `sy-grey` registered via `var(--…)` form (NOT `hsl(var(--…))` — full sRGB hex, not HSL triplets).
- `frontend/src/index.css`: 7 CSS vars on `:root` (`--sy-teal`, `--sy-teal-hover`, `--sy-teal-foreground`, `--sy-orange`, `--sy-orange-hover`, `--sy-orange-foreground`, `--sy-grey`).
- **Tokens registered, NOT applied.** No component touches. Application deferred to Chat 17 (2.4B-i).

### 1c. CHANGELOG entry
Single Chat 16.5 entry inserted between `## Entries` and `## 2.4A`, dated 2026-05-10.

### 1d. chat-16-closing.md updates (this turn)
§1b: 23 rows flipped ❌→✅ with test-location pointers. §1c: tally updated (Direct ✅: 50; 🟡: 21; ❌: 0 for Bucket C). §1d: Bucket B14 prose rewritten as discharged. §4 + header: 641 → 664.

---

## 2. STOP #31 — resolved (B11 service canonical)

**Conflict:** chat-16-closing §R5 #31 spec said "items NOT cloned on new-version." Service implementation (`services/budgets.py:572–583`, B11) clones items.

**Resolution:** Service is canonical. Spec corrected.
- Test renamed: `test_create_new_version_does_not_carry_items` → `test_create_new_version_clones_items_with_lines`
- Assertion flipped to verify item-count parity by `cost_code_id` matching (2-item seed proves cloning, not 1:1 coincidence)
- chat-16-closing row #31 ❌→✅; B11 marked canonical.

**Rationale:** Property development convention — version-bumping a budget = scope refinement, not clean restart. Items (felt, tiles, labour) carry meaning across versions; forcing manual re-entry adds friction without product value.

---

## 3. Triage chat workflow learnings

- **Multi-pass audit caught 4 critical errors before paste** (PM/lock perm, `is_locked` vs `frozen_at`, `metadata_json` column name, `/internal/` vs `/admin/` path). Some genuine prompt errors; some were "build-state audits Claude Code should own."
- **Separation enforced:** triage chat audits prompt-internal consistency only. Build-state verification (does the column exist, is the perm wired) goes to Claude Code via the audit checklist at `docs/SY_Hub_Chat_16_5_Claude_Code_Audit_Checklist.md`.
- **Branching strategy reset:** prompt-level branches add friction without value. Audits run at phase boundaries (end of track), not per-prompt. All 16.5 work pushed to main; `chore/chat-16.5-coverage-and-brand` branch deprecated.
- **Save to GitHub** auto-commits and lets you target a remote branch from the UI regardless of local branch name. Custom multi-line commit messages NOT supported via this path — acceptable when content matters more than message.

---

## 4. Locked decisions for Chat 17 (2.4B-i Frontend Build Pack v1)

1. **Build Pack length:** 2,000–2,400 lines.
2. **Audit cycles:** iterate until bulletproof (no fixed cap).
3. **Optimistic update split:**
   - Optimistic for: description, notes, % complete, drag-reorder
   - Server-confirmed for: FTC method change, lock/close state, line create/delete, threshold-cross writes, cost code reassignment
4. **Concurrent editing protection:**
   - Line drawer = explicit Save (not instant)
   - Line-level version stamps; conflict toast on stale write
   - Budget-level `locked` / `closed` for immutable snapshots
5. **Mobile = read-only floor.** Site users don't manage budgets; office staff do. Desktop-primary.
6. **Stack confirmed:** TanStack Query + TanStack Table NOT yet installed — Build Pack v1 includes `yarn add @tanstack/react-query @tanstack/react-table` as a step. react-hook-form + Zod already present (verified in package.json). axios cookie-only via `lib/api.js`.
7. **No Playwright.** That's Chat 18 (2.4B-ii E2E).
8. **Brand tokens applied in 2.4B-i:** Save / Create / Lock buttons → `bg-sy-teal`. Force-unlock / destructive confirmations → `bg-sy-orange`. Slate-900 baseline elsewhere.

---

## 5. Final state

- All 16.5 work pushed to `main`
- Audit checklist on main: `docs/SY_Hub_Chat_16_5_Claude_Code_Audit_Checklist.md`
- Test count: 664 passing (was 641)
- Permission count: 84 (unchanged)
- Alembic head: 0024_budgets (unchanged)
- Bootstrap: rc=0
- Frontend build: clean

**Awaiting:** Claude Code audit (Monday) → if clean, Chat 17 begins. If issues found, doc-only or test-only follow-up before Chat 17.

**Chat 16.5 closed.**
