# Chat 27 — Audit Remediation TIER P0 + TIER P1 (8 findings, all green)

**Closed:** 2026-02-13 (per CHANGELOG dates — same date-vs-real-date caveat as Chat 26)
**Status:** Backfilled summary. Authoritative record is `CHANGELOG.md` "Audit Remediation TIER P0" (lines 44–81) and "Audit Remediation TIER P1" (lines 83–142). Closing summary not committed at chat-end (procedural miss; backfilled in Chat 28).
**Predecessor anchor:** Chat 26 close — R7.0b + R7 Batch 1. main @ `0034_audit_sendback`, Jest 387, permissions 102, roles 10.
**Scope this chat:** Claude Code independent audit of Chat 26 surfaced 8 findings across two tiers. Chat 27 remediated all 8 (TIER P0 = 4 critical; TIER P1 = 6 high — R1–R6, of which R6 was the CHANGELOG-entry write-up itself). No schema change; no new functional surfaces.

---

## Repo state at close

```
Branch:            main (HEAD 412fe5c at chat-end)
Alembic head:      0034_audit_sendback (unchanged through P0 + P1)
Permissions:       102 (unchanged)
Roles:             10 (unchanged)
Backend pytest:    930 passed, 3 xpassed, 0 failed, 93 errors
                   (the 93 = test_projects.py appraisal_scenarios FK,
                   chat-24 carry-forward, proven pre-existing in R0)
Frontend Jest:     387 (unchanged — no frontend deltas this chat)
```

---

## What shipped — TIER P0 (4 critical)

**P0.1 — Per-appraisal row lock at 13 mutating recompute sites** (`app/routers/appraisals.py`). New `_lock_appraisal_for_update` helper takes `SELECT … FOR UPDATE` on the appraisal row + its cost lines inside the caller's transaction. Called at the top of every handler that runs `appraisal_calc.recompute`. Concurrency proof: two-session test (session A holds, session B `SELECT FOR UPDATE NOWAIT` raises `OperationalError`; A commits → B acquires).

**P0.2 — Receipt audit actor = receipting user; all PO lines locked before status flip** (`app/services/po_receipts.py`). `_recompute_po_status_after_receipt_change` signature now requires keyword-only `actor_user_id`; both callers pass `user.id`. Audit row's `actor_user_id` is the receipter, not `po.updated_by` (header's last editor). The all-fully-received check `.with_for_update()`s every PO line so concurrent receipts on different lines of one PO serialise the status flip.

**P0.3 — `mfa_pending` typed + locked out of `/password/change`** (`app/auth/tokens.py` + `app/routers/auth.py`). Token-type Literal now enumerates `access | mfa_challenge | mfa_pending`. `/password/change` moved from `get_enrollment_principal` (accepts `mfa_pending`) to `get_current_principal` (access-only). Live evidence: `/password/change` → 401 with `mfa_pending`; `/auth/me` + `/mfa/enroll/start` still 200/4xx-but-not-401.

**P0.4 — `/mfa/verify` rate-limit** (`app/services/rate_limit.py` + `app/routers/auth.py`). New bucket `mfa_verify_per_user = (5, 60)`. `enforce(…)` sits BETWEEN the token-type check and the User lookup, so malformed/expired tokens 401 first and don't consume a slot. 429 carries `Retry-After`. Real HTTP proof: 5 OK → 6th HTTP 429.

---

## What shipped — TIER P1 (6 high — R1–R6)

**R1 — Two `mfa_pending` holes closed** (`app/routers/auth.py`). `/mfa/disable` + `/mfa/backup-codes/regenerate` moved from `get_enrollment_user` to `get_current_user`. Same hole class as P0.3 on `/password/change`. `verify_password` + `verify_totp` gates left in place as defence in depth.

**R2 — 3 order-dependent flaky tests quarantined.** Marked `@pytest.mark.xfail(strict=False)` with named-debt reason. Tracked in `/app/docs/SY_Homes_Future_Tasks.md` §23: `test_audit_log.py::test_csv_export_shape`, `…::test_json_export_shape`, `test_sessions_history_reset.py::test_login_success_creates_row`. De-quarantining contract: isolate the underlying coupling first; remove xfail decorator AND Future_Tasks §23 entry in the same commit.

**R3 — Source-row lock on `create_new_version`** (`app/services/appraisal_revisions.py` + new `app/services/appraisal_locks.py`). Layering choice: **Option A** (extract shared helper). New `appraisal_locks.lock_appraisal_for_update(db, id)` is the single source of truth for the appraisal-row `SELECT FOR UPDATE`. P0.1 router helper now delegates to it (cost-line lock stays inline). `create_new_version` calls the helper BEFORE `source.is_current = False`, so two concurrent new-version calls on the same Approved source can no longer interleave past the partial unique `uq_appraisals_current_per_project_scenario`. `create_scenario` confirmed NOT to flip `source.is_current` per docstring contract; no lock added per "don't lock for symmetry."

**R4 — Stale `deps.py:144` docstring fix.** `get_enrollment_principal` no longer lists `/password/change` or `/mfa/disable` / `/mfa/backup-codes/regenerate`. Rewritten to call out that security-critical account changes are explicitly NOT in the `mfa_pending` reach (better than the bare removal the build pack asked for).

**R5 — Destructive Alembic downgrade neutered — Option 1 (operator decision).** `alembic/versions/0027_default_line_items_backfill.py` downgrade replaced with `raise NotImplementedError("0027 is a backfill — downgrade would destroy user-edited budget_line_items (hard-constraint #5). Forward-fix instead.")`. NO new migration. The 0025 round-trip test retargeted from `0024_budgets` → `0027_default_line_items_backfill` so it walks back to but does not execute 0027's downgrade. Runbook + tracking in Future_Tasks §24.

**R6 — CHANGELOG entry written.** The long-missing Chat 26 + P0 + P1 CHANGELOG entries written.

---

## Verification record

| Tier | Method | Result |
|---|---|---|
| P0 | Emergent self-report + count reconciliation + Claude Code source-level independent pass (13-handler lock table) + triage read of main | CLEAN |
| P1 | Same — Claude Code source-level read of every touched file, P0.1 13-site lock survival walked explicitly, R3 two-session race shape verified, R5 trapdoor confirmed | CLEAN |
| Counts | 930 passed, 3 xpassed, 0 failed, 93 errors at HEAD 412fe5c | reconciled |

P0.1 lock-survival under R3 refactor was the highest-risk regression candidate; Claude Code verified all 13 `_lock_appraisal_for_update` call sites unchanged and the wrapper still locks both the appraisal row (now via shared helper) AND every cost line (still inline). No regression.

The previous P0 review's `appraisal_scenarios.py:155` recompute-without-lock concern was formally retired by R3's analysis (`create_scenario` reads but does not mutate the source).

---

## Carry-forward (logged in Chat 28 opener as backlog)

- **P2 (Claude Code P1 finding):** verify no governance router defers the commit after `create_new_version` (deferred commit reopens a cross-worker race). Audit governance handlers; wrap in immediate try/commit/except if any defer.
- **Cosmetic:** rename `test_downgrade_upgrade_round_trip_preserves_schema` — no longer round-trips 0025 post-R5 (the function name now lies; test comment + Future_Tasks §24 are honest about the gap).
- **Cosmetic:** clarify `_lock_appraisal_for_update` wrapper docstring — still says "single appraisal row plus every cost line" (accurate for the wrapper, but a reader of the new shared helper alone may not realise the wrapper still adds the cost-line lock).
- **P0.2 metadata enrichment:** `receipt_id` on Status_Change audit row.
- **`alembic downgrade --sql` CI canary** — structural guard against future 0027-shaped destructive downgrades.
- **`test_projects.py` 93-error `appraisal_scenarios` FK carry-forward** — dedicated cleanup pass.

---

## Hard lessons (carry as standing rules — codified in Chat 28 opener)

1. **Eyeball + independent Claude Code pass catches what self-reports miss.** Caught every P0/P1 hole this arc (P0.1 13-site lock, P0.2 receipter-as-actor, P0.3 + R1 mfa_pending typing, P0.4 rate-limit ordering, R3 race).
2. **Assertions ≠ evidence — print the literal artefact.** Re-emphasised across both tiers.
3. **R3 layering decisions deserve a build-pack-up-front line.** "Option A vs Option B" got asked mid-tier; codifying ahead of time would have saved a turn.
4. **Operator-decided trapdoors are legitimate** (R5 Option 1) — don't auto-implement clever destructive downgrades; raise + document instead.
5. **Counts + collection are non-negotiable.** 930/3/0/93 was demanded, not summarised.

---

## Backfill note

Written in Chat 28 (2026-05-27). The CHANGELOG P0 + P1 entries are unusually thorough — no information loss vs a same-day write. The independent verification report Claude Code produced was also retained in chat history and is the primary source for the verification-record table above.
