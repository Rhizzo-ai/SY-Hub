# Chat 26 / Prompt 2.5 cont. — R7.0b backend send-back + R7 Batch 1 frontend

**Closed:** 2026-02-12 (per CHANGELOG date — note: dates in CHANGELOG entries from this period are inconsistent with the May-2026 working date; the canonical sequence is the chat number, not the date string)
**Status:** Backfilled summary. Authoritative record is `CHANGELOG.md` "Chat 26" entry (lines 15–41). Closing summary not committed at chat-end (procedural miss; backfilled in Chat 28).
**Predecessor anchor:** Chat 25 close — R6 inline grid + R7.0a scaffolding. main @ alembic head `0033_po_receipts`, Jest 357, permissions 102, roles 10.
**Scope this chat:** R7.0b backend send-back path + R7 Batch 1 frontend (slim action buttons + approval panel). Deliberately split from a larger R7 mega-pack into Batch 1 (this chat) / Batch 2 (Chat 28).

---

## Repo state at close

```
Branch:            main
Alembic head:      0034_audit_sendback (was 0033; +1 migration)
Permissions:       102 (unchanged)
Roles:             10 (unchanged)
Frontend Jest:     387 passing (was 357; +30)
Backend pytest:    unchanged from Chat 25 baseline
```

---

## What shipped (per CHANGELOG verbatim)

**R7.0b — `approved → draft` send-back (backend).** Migration `0034_audit_sendback` adds `SendBack` to the audit_action enum. Money invariant: send-back drops `committed_value` via the existing `trg_po_status_commitments` (no new trigger). Permissions/roles unchanged — uses existing `pos.edit` + status-machine perm tier.

**R7 Batch 1 (frontend, no backend deltas).**

- **Project-Detail Budgets tab-link** — `tab-budgets` testid; gated by `budgets.view || is_super_admin`.
- **`<POActionButtons/>`** — slim per-status × per-persona action matrix. Renders today: `submit-btn` (draft), `approve-btn` / `approve-self-disabled` / `reject-btn` (pending_approval), `issue-btn` / `send-back-btn` (approved), `close-issued-btn` / `close-partial-btn` / `close-btn` (issued/partial/receipted). **Edit / Delete / Receipt / Void deferred to Batch 2**; their testids asserted ABSENT on every state × persona by `DEFERRED_TESTIDS` regression guard (8 × 4 × 7 = 32 assertions per CI run). Contract: when a deferred button is wired in Batch 2, the testid must be removed from `DEFERRED_TESTIDS` in the same commit.
- **`<POApprovalPanel/>`** — over-budget snapshot table; approve / reject with optional / required reason; self-approval guard mirrors `SelfApprovalForbidden`; send-back lives only on `<POActionButtons/>` (the `approved` row), NOT in this panel.
- **Send-back API/hook wiring** — `lib/api/purchaseOrders.js` + `hooks/purchaseOrders.js`. **Budget-line cache invalidation on commitment-changing verbs deferred to R7.6** (Chat 28 Batch 2). The R6 grid's committed column will lag a send-back until refetch — acceptable at the batch boundary, called out explicitly in the hook comment.

---

## Engineering invariants pinned this chat

1. **`DEFERRED_TESTIDS` regression-guard pattern.** New ship discipline: any button intentionally deferred to a later batch is asserted absent on every state × persona. Prevents accidental partial-wires and makes the "did Batch 2 actually re-enable this?" check mechanical (just diff `DEFERRED_TESTIDS`).
2. **Send-back release contract.** A successful `approved → draft` send-back releases committed_value via the existing status-commitments trigger — no separate release path. Confirmed by audit-trail SendBack enum entries.
3. **`POApprovalPanel` does NOT own send-back.** Send-back is a button on the approved-status row of the action-buttons matrix, not an option on the approval-decision panel. The approval panel is approve/reject only.

---

## Open / deferred to Chat 27 (audit remediation) and Chat 28 (Batch 2)

- **Claude Code independent audit** of the R7.0b + Batch 1 work — Chat 27 ran this and surfaced 8 findings across two tiers (P0 + P1). All remediated and pushed in Chat 27.
- **R7 Batch 2** — the 7 deferred PO buttons (`po-actions-edit-btn`, `po-actions-delete-btn`, `po-actions-edit-issued-btn`, `po-actions-receipt-btn`, `po-actions-receipt-partial-btn`, `po-actions-void-btn`, `po-actions-void-issued-btn`). → Chat 28.
- **R7.6 budget-line cache invalidation** for commitment-changing verbs (void, send-back, receipt). → Chat 28 (Batch 2 R7.6).
- **R7.5 approvals dashboard** — per-project pending-approvals list. → Chat 28.

---

## Backfill note

Written in Chat 28 (2026-05-27) from the well-detailed CHANGELOG Chat 26 entry. No information loss anticipated vs a same-day write — the CHANGELOG entry is unusually thorough.
