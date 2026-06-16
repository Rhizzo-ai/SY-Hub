# Chat 57 — Closing summary

**Pack:** B102 — Unbudgeted-order path (Gates 1–6).
**Branch:** `main`.
**Status:** Gates 1–6 CLEARED and verified on `origin/main`. Gate 7 (frontend)
SHELVED in favour of a cost-code-first redesign (design-first next chat).

## What shipped (verified on main this chat)

- Migration `0049_unbudgeted_order_lines` (head; on `0048`). Six columns on
  `budget_lines`: `is_unbudgeted`, `unbudgeted_reason`, `unbudgeted_source`,
  `unbudgeted_created_by`, `unbudgeted_cleared_by`, `unbudgeted_cleared_at`.
- `budgets.clear_unbudgeted` permission (non-sensitive, director default).
  Live permission count **143**.
- Gate 5 — PO line unbudgeted leg (explicit qty+rate, £0 trap closed).
- Gate 6 — package line unbudgeted leg + award inheritance proven; award path
  bit-identical to HEAD (the inheritance is a property of existing code).

## Verification notes (how, not just what)

- Verified file-by-file on `origin/main` via raw fetch + shallow clone, not
  Emergent self-report. **The Gate 6 first push had not landed** — schema still
  had required `budget_line_id`, service had no unbudgeted branch, test file
  404'd. Operator re-pushed; second push landed all four files, test file at the
  correct `backend/tests/` path (the report had written `tests/`).
- Did NOT re-run the pytest suite (no pod access this chat). The warm-run counts
  in the gate report (19 baseline failures unchanged, +6 from T11–T12, 149-green
  regression cohort) are taken on the report's word; the code + structure that
  the money gate hangs on were verified directly.

## Known drift recorded (not fixed — deliberate)

- `tests/test_auth_rbac.py` and `tests/test_permissions_2_6.py` assert a stale
  permission count of **136**; live is **143**. These are part of the
  19-failure baseline that ran unchanged through all B102 gates. Authoritative
  count lives in `tests/test_packages_service.py` (143, B102-updated). Small
  follow-up to true these up — logged, not touched inside a money gate.

## Records drift found at close (flagged to operator)

- CHANGELOG top entry was "Chat 55"; chat-summaries stopped at chat-53 (gaps at
  48, 49). Recent Emergent commits are bare "auto-commit" — the disciplined
  two-commit close-out (build + closing docs) had slipped on recent chats, which
  is why records drifted. This chat (57) closes by hand. Operator confirmed the
  B102 work was previously unclosed and this chat owns the write-up.
- Chat 56 has no CHANGELOG entry on main — separate gap, not covered here.

## Decisions made this chat (the pivot)

1. **Cost-code-first commercial line model.** PO/package lines pick a cost code,
   not a budget line. Unbudgeted code → budget line auto-materialises, original
   column blank, committed carries the PO, reads red naturally. One path.
2. **Director acknowledgement KEPT but threshold-gated** (was binary):
   unbudgeted spend > config floor (default £1000), or committed > original
   budget by config % (DECIDED: committed not invoiced — early warning; lean to
   reuse red-variance threshold). Sub-threshold = logged + flagged, non-blocking.
3. **Decision 2A** — this is a backend redesign of the Gate 5/6 entry point, so
   pause and design it properly as its own pack before any frontend.

## State of play

- Gates 1–6 on main. Foundation for the pivot, not wasted.
- Backlog B105–B108 to be hand-added by operator (Emergent never touches
  backlog). See `backlog-additions-chat-N.md`.
- Next chat = **design-first** for the cost-code-first model. Opener:
  `next-chat-opener-cost-code-first-design.md`.

## Operator actions before next chat

1. Commit this summary to `docs/chat-summaries/chat-57-closing.md`.
2. Insert the Chat 57 CHANGELOG block above the Chat 55 entry.
3. Hand-add B105–B108 to `docs/SY_Hub_Phase2_Backlog.md`.
4. (Optional, recommended) tighten the close-out discipline back up — the
   "auto-commit" drift is what let records slip.
