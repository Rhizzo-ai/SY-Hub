# SY Homes Operations — Prompt 1.5 Audit Report

**Date**: 2026-04-23  
**Scope**: Pre-handoff audit before Claude Code reads `Rhizzo-ai/SY-Hub` at the
1.5 tag. Targets the seven concerns Rhys raised in the handoff brief:
append-only enforcement, audit coverage completeness, sensitive-field
redaction correctness, stage-machine bypass paths, retroactive FK cascade
behaviour, `projects.view_sensitive` gate completeness, and the
`has_project_dependents` extension list.

**Severity legend** (matches the 1.3 remediation audit format):
- **C** — Critical (security or data-integrity bug; ship before merge)
- **I** — Important (security-relevant or correctness gap; ship soon)
- **M** — Minor (hygiene / DX / documentation; defer to Polish Pass)

**Headline**: 0 Critical · 3 Important · 7 Minor.  
The Prompt 1.5 implementation is **safe to merge to main** as-is — the three
Important findings are pre-existing gaps from Prompts 1.2 and 1.4, not
introduced by 1.5. They should land as a small follow-up patch ("Audit
remediation #2") before Prompt 1.6.

---

## Critical findings

None.

---

## Important findings

### I1 — `POST /api/users` (invite) writes no `audit_log` row
**File**: `app/routers/users.py`, line 332–334.

The invite endpoint creates a new user row with status `Pending_Invitation`,
generates an invitation token hash, and `db.commit()`s — without calling
`record_audit`. Every other write path on `users` (Edit / Unlock / Role
Assign / Role Revoke) records audit. This is a forensic blind spot: invited
users appear in the system with no record of who invited them beyond the
`invited_by_user_id` foreign key on the row itself, and no IP/UA capture.

**Fix**: insert a `record_audit(action="Create", resource_type="users",
resource_id=u.id, actor_user_id=current.id, …)` call after the `db.flush()`
that lands the new row, before `db.commit()`. Stamp metadata with
`{"kind": "invitation", "invitee_email": email}` (email is fine in
metadata; it's not in SENSITIVE_FIELDS and it identifies the resource).

**Pre-existing**: yes. Bug landed in Prompt 1.2; survived 1.4's audit pass.

### I2 — `POST /api/users/{id}/scrub_pii` writes no `audit_log` row
**File**: `app/routers/users.py`, line 489–518.

This endpoint nukes first/last name, display name, email, phone, avatar,
job title, password hash, password history, MFA secrets and backup codes,
sets status to `Archived`, stamps `archived_at`. It is the single most
destructive write path in the whole codebase — and there is no audit row.

The action is gated on `users.admin`, but the audit gap means we cannot
forensically reconstruct who scrubbed whom from inside the audit log. The
existing breadcrumb (`admin_notes` text suffix on line 510) is not a
substitute — it is mutable, isn't queryable, and is itself wiped if a
second scrub is attempted. **Must be audited**.

**Fix**:
```python
record_audit(
    db, action="Update", resource_type="users", resource_id=u.id,
    actor_user_id=current.id,
    field_changes=[
        {"field": "password_hash", "old": "[REDACTED]", "new": "[REDACTED]"},
        {"field": "mfa_secret_encrypted", "old": "[REDACTED]", "new": "[REDACTED]"},
        {"field": "mfa_backup_codes_encrypted", "old": "[REDACTED]", "new": "[REDACTED]"},
        # email/name/phone changes will be picked up by SENSITIVE_FIELDS-aware
        # diff if you build one; otherwise stamp into metadata.
    ],
    metadata={"kind": "pii_scrub", "scrubbed_at": datetime.now(timezone.utc).isoformat()},
    request=request,
)
```
Also: this endpoint takes no `request: Request` parameter today — add one
so the audit row captures IP/UA.

**Pre-existing**: yes. Same vintage as I1.

### I3 — `bank_name` and `bank_account_name` are missing from `SENSITIVE_FIELDS`
**Files**: `app/services/audit.py` line 56–70 (definition);  
`app/routers/entities.py` line 56–58 (snapshot includes them).

`_entity_snapshot()` includes `bank_name` and `bank_account_name`
verbatim. On entity update, `field_diff(before, after)` produces
`{"field": "bank_account_name", "old": "Smith Holdings Ltd", "new": "Smith
Holdings (UK) Ltd"}` and that goes into `audit_log.field_changes` in
**cleartext**. `bank_account_number_masked` is already masked at write
time (`****1234`) so leaking it via audit is benign — but the **account
holder name** and **bank** are PII that an audit-log reader without bank
detail access would otherwise be denied.

The existing redaction set covers credentials and tokens (good) but
overlooks PII columns added in Prompt 1.1 specifically because the spec
called bank fields out as sensitive (entities.view_sensitive gates them
on read).

**Fix**: extend `SENSITIVE_FIELDS` in `app/services/audit.py`:
```python
SENSITIVE_FIELDS: frozenset[str] = frozenset({
    # …existing entries…
    "bank_account_name",
    "bank_name",
    "bank_account_number_masked",  # already masked but consistent to redact
})
```
Add a regression test that creates an entity, edits a bank field, and
asserts the audit row's `field_changes` carries `[REDACTED]` not the
literal value.

**Pre-existing**: yes. Landed with the audit module in Prompt 1.4.

---

## Minor findings

### M1 — Append-only trigger carve-out: document the bypass surface
**File**: `alembic/versions/0007_audit_trigger_cascade.py`.

The `pg_trigger_depth() > 1` carve-out is **safe today** because the only
way `audit_log` mutates inside a nested trigger context is via FK
referential actions on its own outgoing FKs (`actor_user_id`,
`impersonator_user_id`, `entity_id`, `project_id`, `session_id` — all
`ON DELETE SET NULL`). I traced every trigger in the live schema:

```sql
SELECT tgname, tgrelid::regclass FROM pg_trigger WHERE NOT tgisinternal;
```
Returns only the per-table `set_updated_at` triggers (none of which touch
`audit_log`) plus the `audit_log_no_modify` trigger itself. **No code
path in the current schema can chain to depth > 1 while writing to
`audit_log` other than via referential actions.**

The risk surfaces if someone later adds a trigger on (e.g.) `users` that
performs `UPDATE audit_log SET …` for any reason — that would hit
depth = 2 and bypass the guard silently.

**Fix**: add a comment block at the top of `audit_log_no_modify` (and a
note in `0007_audit_trigger_cascade.py`'s docstring) stating: *"No
trigger on any other table may perform UPDATE/DELETE on audit_log. The
only legitimate depth>1 callers are FK referential actions. Adding a
trigger that violates this assumption silently bypasses the append-only
guard."* Belt-and-braces option: add an `event_trigger` on `CREATE
TRIGGER` that rejects any new trigger naming `audit_log` in its body —
overkill for now, parked.

### M2 — `password-reset/request` writes a token hash without an audit row
**File**: `app/routers/auth.py`, line 829–847.

When a known active user requests a reset, `password_reset_token_hash`
and `password_reset_expires_at` are written. Today this is captured only
in `user_login_history` as `Password_Reset_Requested`. The spec arguably
covers it via the auth history table — and double-logging adds noise to
the audit page — but a reader scanning `audit_log` for "what happened to
this account?" will miss the trail. Document as design choice or extend
`record_audit` to it.

**Recommendation**: leave as-is, but call out in the audit module docstring
that auth-side state changes (login attempts, reset requests, MFA fails)
live in `user_login_history`, with `audit_log` reserved for top-level
business writes. Already partially documented.

### M3 — `has_project_dependents` TODO is missing Phase 5 sales tables
**File**: `app/services/projects.py`, line 86–101.

The TODO block enumerates appraisals, budgets, actuals, commitments,
budget_changes, cash_flow_entries, programmes, programme_tasks, documents,
compliance_registers, certificates, xero_*. It omits the Phase 5 sales
side (plots, buyer_reservations, sale_completions, etc.). Once Phase 5
lands, deleting a project that has plots sold against it would silently
succeed today.

**Fix**: append to the TODO comment:
```
- plots, plot_buyers, reservations, sale_completions (Phase 5 sales)
```
Optional belt-and-braces: add a single integration test in 1.5 that
asserts the function returns False when no dependents exist (already
covered indirectly by `test_delete_no_dependents_succeeds`) and a
TODO-marked failing test that documents the expected behaviour once 2.5
lands.

### M4 — `access_token_jti` in `SENSITIVE_FIELDS` is a category error
**File**: `app/services/audit.py`, line 56–70.

`access_token_jti` is a UUID identifier used to bind an access token to a
session row. It is not a secret — exposing it in audit diffs reveals
nothing exploitable. Including it in the redaction set is semantically
sloppy (suggests "this is sensitive when it isn't"). Currently no code
path writes `access_token_jti` into a field diff, so the bug is dormant.

**Fix**: remove `access_token_jti` from the set, or add a one-line comment
explaining the conservative choice.

### M5 — Pre-emptive entries in `SENSITIVE_FIELDS` for absent tables
**File**: `app/services/audit.py`, line 56–70.

`key_hash` (api_keys), `access_token_encrypted` and
`refresh_token_encrypted` (SSO tokens) reference tables that don't exist
yet — both deferred to Prompt 1.3 stage 2. Harmless but confusing for a
new reader. Either gate them behind a `# Reserved for 1.3 stage 2`
comment or remove until those modules land.

### M6 — Audit scope is entity-rooted; project-scoped users see partial trails
**File**: `app/routers/audit.py`, line 140–159 (`_apply_scope`).

The scope filter applies `audit.view`'s **entity** scope only. A user
whose `user_role.project_scope='Specific'` includes project P but whose
`entity_scope` excludes P's `primary_entity_id` will see project P in
`/api/projects` but get an empty `/api/audit?project_id=P`.

This is consistent with the "entity is the security boundary" model — the
project-scope is treated as a refinement *within* an entity scope — but
isn't called out in the audit router's docstring. Document, don't fix.

### M7 — `pytest tests/` (without `python -m`) fails collection
**Files**: `/app/backend/tests/`, no `__init__.py`; no `pyproject.toml`
or `pytest.ini`.

Bare `pytest tests/` fails with `ModuleNotFoundError: No module named
'tests'` because `from tests.conftest import login_with_auto_enroll,
plain_login` (used by every test module) requires `/app/backend` on
`sys.path`. `python -m pytest tests/` works because `-m` adds cwd.

**Fix**: add at `/app/backend/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```
3-line addition. Removes a sharp edge for any auditor / new contributor
running the suite. Logged as a Polish Pass item.

---

## Verifications passed (no findings)

- **Stage machine bypass paths** — Only two writes to
  `Project.current_stage` exist in the codebase, both in
  `app/routers/projects.py` (`advance_stage` line 492 and `override_stage`
  line 534). `ProjectUpdate` schema deliberately omits `current_stage`,
  `status`, `stage_entered_at`. PUT cannot mutate stage. ✓
- **0009 retroactive FKs** verified against the live database:
  - `fk_user_role_projects_project_id`: `ON DELETE CASCADE` ✓
  - `fk_audit_log_project_id`: `ON DELETE SET NULL` ✓
  Both match the CHANGELOG draft.
- **`projects.view_sensitive` gate completeness** — `_serialise()` in
  `app/routers/projects.py` line 162–195 omits all six FIN_FIELDS
  (`gdv_actual`, `build_cost_actual`, `all_in_cost_actual`,
  `profit_actual`, `margin_actual_pct`, `financials_refreshed_at`)
  unless `can_fin` is True. The list endpoint, detail endpoint, advance
  response, override response, team add response, and financials-refresh
  response all flow through the same serialiser. ✓
- **Audit coverage on `projects` writes** — every commit in
  `app/routers/projects.py` is preceded by a `record_audit` call:
  create / update / delete / stage advance / stage override / team add /
  team remove. ✓
- **Audit coverage on `entities` writes** — create / update / delete all
  audited. (Sensitive-field redaction gap is I3, not a coverage gap.) ✓
- **Audit coverage on `sessions` writes** — self-revoke, revoke-others,
  admin-revoke-all all audited (one row per session revoked, correctly).
  ✓
- **Audit coverage on `auth` writes** — login (success), MFA verify,
  MFA enrol/disable/regen, password change, password reset complete,
  logout — all audited. The unaudited write paths in this router are
  intentionally so (rate-limit log_event, login-failed log_event,
  refresh-token rotation): they belong in `user_login_history`, not
  `audit_log`. ✓
- **Test suite** — 314 passed / 1 skipped / 0 failed when invoked via
  `python -m pytest tests/` against current main, after running
  `python scripts/seed_test_users.py` to refresh fixtures.

---

## Suggested follow-up patch

Bundle I1 + I2 + I3 + M1 + M3 + M4 + M5 + M7 into "Audit remediation
patch #2" before Prompt 1.6. Estimated size:

- 5 lines in `audit.py` (SENSITIVE_FIELDS additions / category-error
  removal / comment).
- ~25 lines across `routers/users.py` (two `record_audit` blocks +
  `request: Request` plumbing).
- 1 docstring update in `services/projects.py`.
- 1 docstring/comment in `0007_audit_trigger_cascade.py`.
- 3 lines in a new `pyproject.toml`.
- 2 new pytest cases (one for each of I1, I2; I3 is covered by extending
  an existing entity-update test).

Total: ~60 LOC + 2 tests. Keeps the suite green at 316 passing.

M2 and M6 are documentation-only; can land in the same patch or
separately.

---

*Generated locally — not committed. Build chat to verify against
commit-time reality before tagging.*
