# Chat 28 — R7 Batch 2 frontend + Batch 2 follow-on backend endpoint

**Closed:** 2026-05-27
**Status:** Closing summary committed at chat-end (per project instructions — back on track after the 25/26/27 backfill earlier this chat).
**Predecessor anchor:** Chat 27 close — TIER P0 + P1 audit remediation. main @ `412fe5c`, alembic `0034_audit_sendback`, permissions 102, roles 10, pytest 930/3/0/93, Jest 387.
**Scope this chat:**
1. Backfill chat-25/26/27 closing summaries (procedural miss, three chats deep).
2. R7 Batch 2 frontend — re-enable the 7 deferred PO action buttons + R7.4 receipt form + R7.5 approvals dashboard + R7.6 optimistic layer + Edit (header-only, Option A) + Delete (draft-only).
3. R7 Batch 2 follow-on — add missing `GET /projects/{project_id}/purchase-orders` backend endpoint surfaced by Claude Code review.

---

## Repo state at close

```
Branch:            main (HEAD 45a9265)
Alembic head:      0034_audit_sendback (unchanged through Batch 2 + follow-on)
Permissions:       102 (unchanged)
Roles:             10 (unchanged)
Backend pytest:    934 passed, 3 xpassed, 0 failed, 93 errors
                   (the 93 = test_projects.py appraisal_scenarios FK, pre-existing,
                   chat-24 carry-forward — unchanged)
Frontend Jest:     387 reported (Emergent's literal output; Claude Code's
                   source-level delta calc was +25, suggesting Emergent's
                   number may be stale — flagged for re-verification in Chat 29)
Frontend bundle:   395.24 kB gz main (cap 437 kB; 41.76 kB headroom)
```

---

## What shipped

### Chat-25/26/27 backfill (procedural cleanup)
Three closing summaries committed to `docs/chat-summaries/` (commit `0dbde4b`).
chat-25 reconstructed from CHANGELOG cross-refs (lowest confidence, flagged
honestly); chat-26 + chat-27 high-confidence from their well-documented
CHANGELOG entries.

### R7 Batch 2 — `0eb116d`
- All 7 previously-deferred testids wired (`DEFERRED_TESTIDS = []`, regression
  guard block deleted, replaced with 25+ positive matrix assertions).
- **R7.4 receipt form** — `POReceiptDialog`, eligible-lines filter (>0
  remaining), quantity map, date + optional notes, `['budgets']` invalidation
  via `useCreateReceipt`.
- **R7.5 per-project approvals dashboard** — `POApprovalsTab` new tab on
  `/projects/{id}/purchase-orders?tab=approvals`, reuses
  `useProjectPOs(projectId, { params: { status: 'pending_approval' } })`,
  client-side filter fallback.
- **R7.6 confirm-dialog + Void + optimistic layer** — `POVoidDialog` mirrors
  reject-dialog reason-required pattern; `usePoTransition` rewritten with
  `onMutate`/`onError`/`onSettled` (built fresh, not extended — there was no
  prior pattern despite the pack's claim).
- **Edit (Option A — header-only)** — `POEditDialog` honours `edit_tier` enum
  (full / header_annotation_only / read_only) per backend `po_authz.py`
  contract; FULL fields gated inside `{isFull && ...}`; annotation-only
  payload when `!isFull`; empty-diff short-circuits.
- **Delete (draft-only)** — `PODeleteDialog` mounts only on draft, navigates
  to PO list on success to avoid 404 on detail page.
- **`e2e:po-batch2` script** + 5 new persona-suffixed Playwright specs tagged
  `@po-batch2` / `@smoke`.

### Batch 2 follow-on — `45a9265`
- **`GET /projects/{project_id}/purchase-orders`** — thin wrapper over
  `svc.list_pos(...)`, `project_id` bound from PATH. Mirrors the un-scoped
  `GET /purchase-orders` (line 154) byte-for-byte aside from the path binding.
- 4 new tests in `TestR7Batch2FollowOnListProjectPOs`: scoped results,
  status filter honoured, perm-gated, unknown-project returns empty.
- Closes a latent Chat 24 R5 bug — `PurchaseOrderList` page has been silently
  hitting this URL since Chat 24; the FE's "Failed to load purchase orders"
  error state was masking a 404, not a permission issue.
- Pytest 930 → 934 (+4 exact).
- No frontend changes. Bundle hash unchanged from `0eb116d`.

---

## Verification record

| Layer | Method | Outcome |
|---|---|---|
| Batch 2 self-report | Emergent's 7 artefacts (DEFERRED empty, matrix, optimistic block, bundle) | Reported clean |
| Batch 2 local Playwright | Operator ran in Emergent sandbox | **Skipped** — sandbox kept wiping pip deps between runs; one auth-cache symptom investigated then proved a red herring (the real bug was the missing GET endpoint, fixed in follow-on) |
| Batch 2 Claude Code review | Independent source-level audit | CONCERNS — push valid, one functional gap (the missing endpoint) → became the follow-on |
| Follow-on self-report | 4 artefacts, warm-DB pytest 934 | Clean |
| Follow-on operator verification | git push to origin/main `45a9265` | Live |

---

## Hard lessons (carry as standing rules — codify in Chat 29 opener)

1. **Sandbox recycles cost real time.** Pip deps in `/usr/local/lib/...` do
   NOT survive Emergent container recycles or `supervisorctl restart backend`.
   The provision script handles Postgres but not the Python deps; a fresh
   container can't seed test users without `pip install -r requirements.txt
   --break-system-packages` first. Document in the Chat 29 opener pre-flight.
2. **Local Playwright was skipped this batch and a real bug slipped to push
   because of it.** Jest + Claude Code review caught the bug (R7.5's missing
   endpoint) but only because Claude Code reads source independently. Without
   that pass, Batch 2 would have shipped broken R7.5. Standing rule: never
   skip BOTH local Playwright AND Claude Code; one of the two must run.
3. **Chat 24 R5 ships latent URL bugs.** The `PurchaseOrderList` page has
   been silently failing since Chat 24 because frontend tests mock the
   hook. Future Chat-24-class work needs an integration / e2e check on
   actual URL resolution, not just hook return shape.
4. **Self-report Jest counts can drift.** Emergent reported Jest 387
   unchanged; Claude Code's source-level delta was +25 (expected ~412).
   The "unchanged" claim is suspect — re-run in preview env at Chat 29 open.
5. **AC1 anti-pattern.** `expect([]).toEqual([])` is a vacuous-green
   tautology. Positive regression guards (assert each previously-deferred
   testid renders SOMEWHERE) are the real safety net. Logged backlog.

---

## Carry-forward (Chat 29+ backlog)

**Immediate (Chat 29 candidates):**
- Re-verify Jest count in preview env (expected ~412, not 387 as reported).
- Re-run R7.5 dashboard Playwright in preview env now the endpoint exists.

**Polish backlog (no urgency):**
- Remove `issue` from `COMMITMENT_VERBS` (Claude Code finding — no-op for
  committed_value; harmless extra invalidation today).
- Replace `expect([]).toEqual([])` AC1 tautology with positive
  `EXPECTED_WIRED_TESTIDS` parametric guard.
- `POEditDialog` `if (tier === 'read_only') return null;` defence-in-depth.
- Add `['budgets']`-invalidation pin tests for approve/issue/close.
- Optional R7.5 search filter — endpoint accepts `q`, FE doesn't expose it.

**Track 2 wrap-up (when R7 fully closed):**
- Track 2 wrap-up audit checkpoint (with MD/Louise per the audit-checkpoint
  plan in project instructions).
- All-projects approvals dashboard (§CARRIED FORWARD from Batch 2 — needs
  new global PO-list hook).
- Delivery / collection acceptance note feature (NEW backlog item from
  Chat 28 — proper feature: note generation, assignee, notification
  plumbing).

**From Chat 27 audit remediation (unchanged):**
- **P2:** verify no governance router defers commit after
  `create_new_version` (cross-worker race risk).
- Cosmetic: rename `test_downgrade_upgrade_round_trip_preserves_schema`;
  clarify `_lock_appraisal_for_update` wrapper docstring.
- P0.2 metadata enrichment (`receipt_id` on Status_Change audit row).
- `alembic downgrade --sql` CI canary.
- `test_projects.py` 93-error `appraisal_scenarios` FK cleanup pass.

**Line-item mutation backend mini-pack** (Edit Option B) — deferred from
Batch 2; only build if a real edit-line-items requirement surfaces.

---

## Next session: Chat 29

Scope TBD. Strong candidates: re-verify the two preview-env items (Jest
count + R7.5 e2e), then either fold the small polish backlog into a R7-wrap
prompt, or move to Track-2 wrap-up planning. Operator's call at chat-29 open.
