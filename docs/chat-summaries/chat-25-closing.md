# Chat 25 / Prompt 2.5 cont. — PO Lifecycle UI (R6 inline grid, R7.0a backend, E2E smoke)

**Closed:** ~2026-05-21 (reconstructed at backfill time — Chat 28)
**Status:** Backfilled summary. Authoritative record is `CHANGELOG.md` Chat 26 entry + Chat 24-closing's "deferred to Chat 25" list. Closing summary was not committed at chat-end (procedural miss; backfilled in Chat 28 alongside chats 26 & 27).
**Predecessor anchor:** Chat 24 close — Prompt 2.5 R0–R5 (Suppliers + PO core + approvals + receipts backend; PO/Supplier frontend list/detail/form). main @ post-`0033_po_receipts`, 102 permissions, 10 roles, Jest 312, bundle 395.26 kB gz.
**Scope this chat (per Chat 24-closing §"Open / deferred to Chat 25"):**
1. E2E lifecycle smoke — suppliers → prefix → PO → submit → approve → issue → partial receipt → full receipt → close, + void.
2. R6 — inline expandable PO sub-rows on Budgets grid (Buildertrend-style; replaces BudgetGridDrilldown side panel).
3. R7.0a — initial status-transition UI scaffolding + MyApprovalsDashboard-ready backend hooks (the `approved → draft` send-back path itself was deferred to Chat 26 as R7.0b).
4. R8/R9 — tests sweep + close-out.

> **Backfill caveat:** this summary is reconstructed from CHANGELOG references and the explicit Chat 24-deferral list. Per-R-section line-by-line detail is NOT preserved — refer to CHANGELOG and `git log --oneline` between `7b04338` (Chat 24 head) and the pre-Chat-26 head for the precise commits.

---

## Repo state at close (reconstructed)

```
Branch:            main
Alembic head:      0033_po_receipts (no migration delta this chat; R7.0b's
                   0034_audit_sendback shipped in Chat 26)
Permissions:       102 (unchanged from Chat 24)
Roles:             10 (unchanged)
Frontend Jest:     357 passing (per CHANGELOG Chat 26 entry's "357 → 387"
                   anchor — i.e. 357 was the pre-Chat-26 baseline = Chat 25
                   close state)
Backend pytest:    ≈875+ (unchanged backend or +small from R7.0a wiring)
```

---

## What shipped (per CHANGELOG references)

**E2E lifecycle smoke (carried forward from Chat 24).** Promoted Chat 24's R5 frontend from "structural ✓ / functional ✗" to verified against the live preview. Suppliers → prefix → PO → full status walk + void.

**R6 — Buildertrend-style inline expandable sub-rows.** The PO list moved off a side-panel pattern into inline expandable rows on the Budgets grid surface. The big UI shift Chat 24 explicitly deferred.

**R7.0a — Status-transition UI scaffolding.** Status pills + approval-panel container + per-status × per-persona action affordance plumbing (the data shapes that Batch 1 in Chat 26 then turned into the slim `<POActionButtons/>` and `<POApprovalPanel/>`). The `approved → draft` send-back path itself was held back to Chat 26 / R7.0b (migration `0034_audit_sendback` + the SendBack audit enum value).

**R8/R9 — tests + close-out.** Jest grew to 357 (Chat 26 entry's baseline). Engineering invariants from Chat 24 (commitment formula, numbering, edit tiers, PM grant set) pinned across the R6 surface.

---

## Open / deferred to Chat 26 (per CHANGELOG)

1. **R7.0b — `approved → draft` send-back backend.** Migration + audit enum + commitment-release path. → Shipped Chat 26.
2. **R7 Batch 1 frontend** — slim `<POActionButtons/>`, `<POApprovalPanel/>`, send-back wiring; `DEFERRED_TESTIDS` regression-guard mechanism for the Edit/Delete/Receipt/Void buttons. → Shipped Chat 26.
3. **R7 Batch 2 frontend** — the 7 deferred PO buttons. → In progress Chat 28.

---

## Hard lessons (carried into Chat 26+)

- The `DEFERRED_TESTIDS` regression-guard pattern that Chat 26 introduced was a direct response to Chat 25 R7.0a's "buttons exist as scaffolds but aren't wired" shape — i.e. asserting absent-where-deferred prevented accidental partial-wires from sneaking through.
- The R5/R6/R7 surface-by-surface progression (Chat 24 → 25 → 26) confirmed that PO lifecycle UI benefits from split build packs over one mega-pack; this is the precedent for R7 Batch 1 (Chat 26) / Batch 2 (Chat 28).

---

## Backfill note

This summary was written in Chat 28 (2026-05-27) from CHANGELOG cross-references rather than at chat-end. If a finer-grained reconstruction is ever needed, the source-of-truth is:
- `CHANGELOG.md` Chat 26 entry — anchors Chat 25's close state (Jest 357, alembic 0033) implicitly via deltas.
- Chat 24-closing's "Open / deferred to Chat 25" list — the scope intent.
- `git log --oneline 7b04338..<pre-chat-26-head>` — the actual commits.
