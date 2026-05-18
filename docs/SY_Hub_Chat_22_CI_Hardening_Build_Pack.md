# Build Pack v-final — Chat 22: CI Pipeline Hardening (post-Chat-21 first-run failures)

**Unit of work:** `ci-hardening-v1` (logical label; Emergent's Save-to-GitHub will land as auto-commits to `main`).

**Anchor:** First CI run from Chat 21 (commit `26822fb`, 2026-05-18) red after 27s. Two distinct failures, both at setup-step level — neither reached pytest or yarn build proper.

**Gates:** Green CI badge. First-run-green isn't just cosmetic — it confirms the CI pipeline itself works end-to-end. Until then, we're flying blind on whether Chat 21 even built the right thing.

**Estimated size:** Half a session. Targeted infra fix: one new file (`requirements-ci.txt`), one workflow edit, possibly one regenerated `yarn.lock`, plus the test-drift cleanup we'd already scoped (3 perm-count literals + 1 alembic-head literal). No source code touched.

**Build Pack version:** v-final (post 3-pass audit).

### Audit-pass changelog

**v1 → v-final (Pass 2/3, fresh-reader defect hunt + alignment):**
- **Critical 1 — Hardened `grep -v` pattern in §R2.** Original `'^emergentintegrations=='` would silently miss lines with leading whitespace, extras syntax (`emergentintegrations[foo]==0.1.0`), or `>=`/`<` constraints. Replaced with anchored case-insensitive extended regex matching all PEP 508 dependency line forms. Plus an explicit upfront `grep -nEi` to confirm exactly-one-match before the `grep -v` runs.
- **Medium 3 — Defensive env source in §R0.5.** `psql $DATABASE_URL` assumes the variable is exported. Added `if [ -z "${DATABASE_URL:-}" ]; then source /app/backend/.env; fi` so the baseline step works whether or not the agent's shell already has it. Also wrapped `$DATABASE_URL` in quotes to handle special chars.
- **Medium 4 — Example head string in §R5.3 now clearly illustrative.** The `0026_ai_capture_costs_perm` literal is in an example block, but the surrounding prose now explicitly instructs the agent to use §R0.3's captured value, not the example.
- **Minor 5 — CHANGELOG template placeholders flagged.** Added instruction line before the template that every `<placeholder>` must be filled with the actual captured value.
- **Minor 6 — Schema-flexibility note in §R0.5.** Added inline note that if `role_permissions` table uses different join column names than the example, the agent corrects per actual schema (`\d role_permissions` will show it).

---

## §0 — Pre-flight

Before any other action: `cd /app && git pull origin main`. Resync against Chat 21's auto-commits.

If the container is a fresh fork (no Postgres, no `on-restart.sh`), follow the provisioning runbook in `/app/backend/app/bootstrap.py`'s module docstring before proceeding.

---

## §1 — Background and the two failures

### Failure 1 — Backend job: `emergentintegrations==0.1.0` not on PyPI

CI run #1, backend job, step `Install backend dependencies`:

```
ERROR: Could not find a version that satisfies the requirement
emergentintegrations==0.1.0 (from versions: none)
ERROR: No matching distribution found for emergentintegrations==0.1.0
Error: Process completed with exit code 1.
```

**Cause:** `backend/requirements.txt` pins `emergentintegrations==0.1.0`. This is a private package available only inside Emergent's sandbox (not on public PyPI). GitHub Actions' `pip install -r requirements.txt` therefore fails.

**Why this only surfaced now:** Every chat 1–21 ran pytest inside the Emergent container where the package is pre-installed. CI is the first environment outside that walled garden. The failure is real but pre-existing — Chat 21 just made it visible.

**Resolution (operator decision Q1, option 3):** Split a `requirements-ci.txt` that mirrors `requirements.txt` minus `emergentintegrations`. Workflow uses the new file. Local dev / Emergent sandbox keeps using `requirements.txt` (unchanged). Net effect: CI installs everything the test suite imports; `emergentintegrations` is only imported by sandbox-specific runtime paths that pytest doesn't exercise.

**Verification before drafting:** §R1 below confirms `emergentintegrations` is NOT imported by any module under `backend/app/` or `backend/tests/`. If §R1 finds an import, STOP — option 3 is wrong for that case, and we need option 2 (conditional import). Don't paper over a real import dependency.

### Failure 2 — Frontend job: `yarn.lock` out of sync with `package.json`

CI run #1, frontend job, step `Install frontend dependencies`:

```
yarn install v1.22.22
[1/4] Resolving packages...
error Your lockfile needs to be updated, but yarn was run with `--frozen-lockfile`.
info Visit https://yarnpkg.com/en/docs/cli/install for documentation about this command.
Error: Process completed with exit code 1.
```

**Cause:** Some package in `frontend/package.json` has a version constraint that doesn't match what's resolved in `yarn.lock`. Could be:
- (a) Someone bumped a version in `package.json` without rerunning `yarn install`.
- (b) Emergent's sandbox silently updated the lockfile during a previous build but didn't commit the updated lockfile.
- (c) A semver range in `package.json` widened to a version not in the lockfile.

**Why this only surfaced now:** Emergent's sandbox runs `yarn install` (relaxed mode) which silently updates the lockfile. CI runs `yarn install --frozen-lockfile` (strict mode) which is the correct way to do reproducible CI — and strict mode caught the drift.

**Resolution (operator decision Q2, option 2):** Investigate which package(s) caused the drift FIRST, then regenerate the lockfile. Diagnosis is cheap (`yarn install` dry-run will name the package). The diagnosis tells us whether this is innocent (a forgotten relock — just commit the new lockfile) or sinister (Emergent silently bumping a major version — push back).

### Bonus scope — Pre-existing test drift (carried over from Chat 21 closing)

Chat 21's local pytest run reported 5 failing tests, all literal-mismatch drift:

- `tests/test_auth_rbac.py::TestAuthMe::test_me_super_admin_returns_87_permissions` — name says 87, body asserts `== 85`. Live state: 86 perms. Both the function name AND the assertion are wrong.
- `tests/test_auth_rbac.py::TestPermissions::test_permissions_returns_87_permissions` — similar pattern.
- `tests/test_auth_rbac.py::TestRoles::test_roles_returns_10_seeded_roles` — asserts `super_admin == 85` and `director == 81`. Live state should add `ai_capture.view_costs` from Chat 20, so super_admin should be 86 (or whatever's actually live).
- `tests/test_migration_0025_actuals.py::TestMigration0025Schema::test_alembic_head_is_0025_actuals` — asserts head is `0025_actuals`. Live head is `0026_ai_capture_costs_perm`.
- Possibly one more in `tests/test_bootstrap.py` — historical head sentinel pattern (chat-15-closing §3 documented this as "part of any migration's bookkeeping").

These were caught by Emergent locally during Chat 21 but deliberately not fixed (out of Chat 21 scope per §2). Chat 22 absorbs them.

### Hard constraints (Mandatory carry-forwards)

1. **No source code changes.** Only `tests/`, the new `requirements-ci.txt`, the workflow YAML, and possibly `frontend/yarn.lock`. Production code untouched.
2. **No new migrations.** No alembic revisions added.
3. **No new permissions, roles, or seeds.** Permission count assertions are updated to match current state, but the catalogue itself is not modified.
4. **`emergentintegrations` MUST remain in `requirements.txt`.** Removing it from the canonical file would break sandbox dev. Only `requirements-ci.txt` (new file) excludes it.
5. **I11 bundle hard cap is 437,000 bytes gzipped on `build/static/js/main.<hash>.js`.** Unchanged. Chat 22 doesn't touch frontend source.
6. **pytest invocation in CI stays `python -m pytest --ignore=tests/test_c3_governance_smoke.py`.** Future_Tasks §4 still deferred.

---

## §2 — In scope / Out of scope

### In scope

1. Diagnose `emergentintegrations` import surface (§R1.1). Confirm option 3 is correct.
2. Create `/app/backend/requirements-ci.txt` = `requirements.txt` minus the one `emergentintegrations` line (§R2).
3. Edit `.github/workflows/ci.yml`: change `pip install -r requirements.txt` to `pip install -r requirements-ci.txt` in the backend job (§R3).
4. Diagnose `yarn.lock` drift (§R1.2). Name the offending package(s).
5. Regenerate `yarn.lock` if drift is innocent; STOP and self-report if drift looks like Emergent silently bumped something significant (§R4).
6. Read the actual failing pytest output to capture exact assertion values (§R5.1). Don't trust my §1 paraphrasing — read the live failures.
7. Patch the literal numbers in `tests/test_auth_rbac.py` (3 tests) (§R5.2).
8. Patch the alembic head literal in `tests/test_migration_0025_actuals.py` (1 test) (§R5.3).
9. Patch the head sentinel in `tests/test_bootstrap.py` if present (§R5.4).
10. Run full pytest locally to confirm green (§R6.1).
11. Run yarn build + Jest locally to confirm green (§R6.2).
12. CHANGELOG entry + Future_Tasks annotation (§R7).
13. Spot-check at chat close (§R8).

### Out of scope (DO NOT bundle)

- **Removing `emergentintegrations` from `requirements.txt`.** It stays in canonical. Only CI gets a leaner copy.
- **Investigating WHY `emergentintegrations` is on PyPI as a private package.** Out of band; talk to Emergent support if curious.
- **Adding Playwright to CI.** Future_Tasks; Chat 21 deferred this.
- **Adding lint to CI.** Future_Tasks; Chat 21 deferred this.
- **Removing the `--ignore=tests/test_c3_governance_smoke.py` flag.** Future_Tasks §4 work; still deferred.
- **Any change to backend source, frontend source, models, schemas, routers, services, migrations, seeds, permissions.**
- **Adding NEW tests.** Only patching literal values in existing tests.
- **Updating test FUNCTION NAMES that contain stale numbers** (e.g. `test_me_super_admin_returns_87_permissions` referring to the wrong number). Renaming functions is a wider concern — pytest discovers by file, not by name; the function can stay named "87" while asserting "86". A separate Future_Tasks polish entry will rename them en masse when this matters.
- **Bumping dependency versions beyond what's needed to make the lockfile coherent.** Minimum-surface fix only.

---

## §3 — Build plan (R0–R8)

### §R0 — Baseline (STOP gate)

```bash
# 0.1 — Resync
cd /app
git pull --ff-only origin main
git rev-parse HEAD                          # record SHA
git status                                  # expect clean

# 0.2 — Confirm Chat 21 is on main
test -f /app/.github/workflows/ci.yml && echo "ci.yml present (Chat 21 landed)"
test -f /app/CHANGELOG.md && grep -c "Chat 21" /app/CHANGELOG.md  # expect ≥1

# 0.3 — Confirm bootstrap is healthy
cd /app/backend
python -m app.bootstrap                     # expect rc=0
alembic current                             # record (expected ~0026_ai_capture_costs_perm)

# 0.4 — Capture current test state
python -m pytest --ignore=tests/test_c3_governance_smoke.py 2>&1 | tail -20
# expect: 5-ish failures matching §1 "Bonus scope" list.
# CAPTURE the failure list verbatim — that's the source of truth for §R5.

# 0.5 — Check actual permission and role counts (source of truth)
# Ensure DATABASE_URL is exported (sourced from backend/.env if not already).
if [ -z "${DATABASE_URL:-}" ]; then
  set -a; source /app/backend/.env; set +a
fi
psql "$DATABASE_URL" -tAc "SELECT COUNT(*) FROM permissions;"  # record exact value
psql "$DATABASE_URL" -tAc "SELECT COUNT(*) FROM roles;"        # record exact value
psql "$DATABASE_URL" -tAc "
  SELECT r.code, COUNT(rp.permission_code) as cnt
  FROM roles r
  LEFT JOIN role_permissions rp ON rp.role_code = r.code
  GROUP BY r.code
  ORDER BY r.code;
"
# Record super_admin, director, project_manager, finance counts.
# These are the values to substitute into the assertions in §R5.
# NOTE: if the join column names differ in your schema (e.g.
# role_permissions.role_id vs role_code), the agent corrects per the
# actual schema — \\d role_permissions will show it.
```

**Self-report and STOP if:**
- `/app/.github/workflows/ci.yml` is missing (Chat 21 didn't land).
- Bootstrap rc ≠ 0.
- Pytest failure count is wildly different from "5-ish" (e.g. 50+ failures suggest a deeper issue we haven't scoped).

---

### §R1 — Diagnose the two CI failures

#### R1.1 — `emergentintegrations` import surface

```bash
# Where is the package actually imported?
grep -rn "emergentintegrations\|import emergentintegrations\|from emergentintegrations" \
  /app/backend/app /app/backend/tests /app/backend/scripts 2>/dev/null

# Where is it referenced in requirements?
grep -n "emergentintegrations" /app/backend/requirements.txt
```

**Expected (option 3 valid):** Zero hits inside `app/` and `tests/`. The package is in requirements.txt as a Phase-1 leftover from when Emergent's template assumed you'd use it, but no SY-Hub code actually imports it.

**If hits found:** STOP and self-report. The fix shifts from option 3 (skip in CI) to option 2 (make the import conditional). That's a different scope — propose it but do NOT execute it without operator sign-off.

#### R1.2 — `yarn.lock` drift diagnosis

```bash
cd /app/frontend
# Dry-run frozen-lockfile to confirm the failure repros locally:
yarn install --frozen-lockfile 2>&1 | head -30

# If it fails, run without --frozen-lockfile and capture the DIFF:
yarn install 2>&1 | tee /tmp/yarn_install.log | tail -30

# Now compare lockfile before vs after:
git diff --stat frontend/yarn.lock
git diff frontend/yarn.lock | head -100  # first chunk of changes
```

**Capture in self-report:**
- Output of `git diff --stat frontend/yarn.lock` (one line, shows lines added/removed).
- The names of any packages whose `version "..."` lines changed.
- Whether the diff looks "innocent" (one or two patch-level bumps from a recent install) or "sinister" (major-version bumps, ten+ packages affected).

**Decision tree:**
- **Innocent drift (≤5 packages, patch-level bumps):** Commit the regenerated `yarn.lock` as part of Chat 22. Proceed to R5.
- **Sinister drift (>5 packages OR major-version bumps):** STOP and self-report. Operator decides whether to absorb the changes or push back to Emergent.

---

### §R2 — Create `/app/backend/requirements-ci.txt`

```bash
cd /app/backend
# First, locate the exact line(s) matching emergentintegrations to confirm
# there's exactly one and it's a plain `name==version` form. Catch any
# weird cases (whitespace, extras, multiple lines) BEFORE the grep -v.
grep -nEi '^[[:space:]]*emergentintegrations([[:space:]]|=|>|<|;|$)' requirements.txt
# Expect: exactly 1 line, matching `emergentintegrations==0.1.0` (or close).
# If 0 hits → STOP; the package isn't where we expected.
# If 2+ hits → STOP; the requirements file has duplicates and needs cleanup
# before this Build Pack can proceed cleanly.

# Create requirements-ci.txt = requirements.txt minus that line.
grep -vEi '^[[:space:]]*emergentintegrations([[:space:]]|=|>|<|;|$)' \
  requirements.txt > requirements-ci.txt

# Sanity-check: line count delta should be exactly 1.
EXPECTED=$(($(wc -l < requirements.txt) - 1))
ACTUAL=$(wc -l < requirements-ci.txt)
test "$ACTUAL" -eq "$EXPECTED" && echo "OK: line delta = 1" || \
  echo "STOP: line delta = $((EXPECTED - ACTUAL + 1)) — grep matched multiple lines or none"

# Sanity-check: emergentintegrations NOT in the new file at all.
grep -ciE '^[[:space:]]*emergentintegrations' requirements-ci.txt
# Expect: 0. Any other number → STOP.

# Sanity-check: file installs cleanly in a venv.
python -m venv /tmp/ci-venv-check
/tmp/ci-venv-check/bin/pip install --upgrade pip -q
/tmp/ci-venv-check/bin/pip install -r requirements-ci.txt 2>&1 | tail -5
rm -rf /tmp/ci-venv-check
```

Add a header comment to the new file explaining its purpose (PREPEND
to the file — must not interfere with pip parsing, which treats lines
starting with `#` as comments):

```
# requirements-ci.txt — CI pipeline requirements.
#
# Identical to requirements.txt EXCEPT excludes emergentintegrations==0.1.0,
# which is a private Emergent sandbox package not available on public PyPI.
# Used by .github/workflows/ci.yml in the backend job.
#
# Do NOT use for local dev — use requirements.txt instead.
# Keep in lockstep with requirements.txt: any time a dep is added/bumped there,
# add/bump it here too (or regenerate from `grep -vEi
# '^[[:space:]]*emergentintegrations([[:space:]]|=|>|<|;|$)' requirements.txt
# > requirements-ci.txt`).
```

---

### §R3 — Edit `.github/workflows/ci.yml`

One-line change in the backend job — the `pip install -r requirements.txt` line:

```bash
# Before:
#   pip install -r requirements.txt
# After:
#   pip install -r requirements-ci.txt
```

Find the exact line:

```bash
grep -n "pip install -r requirements" /app/.github/workflows/ci.yml
```

Edit in place. Then add a comment above the new line explaining why:

```yaml
      - name: Install backend dependencies
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          # CI uses requirements-ci.txt (= requirements.txt minus
          # emergentintegrations, which is a private Emergent sandbox
          # package not on public PyPI). See chat-22-closing.md.
          pip install -r requirements-ci.txt
          # psql client used by the pgcrypto step below.
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends postgresql-client
```

Validate YAML still parses:

```bash
python3 -c "import yaml; yaml.safe_load(open('/app/.github/workflows/ci.yml'))" \
  && echo "YAML parse: OK"
```

---

### §R4 — Regenerate `yarn.lock` (only if R1.2 said "innocent")

If R1.2's diagnosis was "sinister drift" → STOP, do not execute R4.

If R1.2's diagnosis was "innocent drift" → the file is already regenerated by the `yarn install` (without `--frozen-lockfile`) you ran during R1.2. Confirm it's clean now:

```bash
cd /app/frontend
yarn install --frozen-lockfile 2>&1 | tail -5
# Expect: "success Already up-to-date." or "Done in Xs."
# If still fails: STOP. The regeneration didn't take.
```

Record in self-report:
- The line-count delta on `yarn.lock` (e.g. "+23 -8 lines").
- The list of packages whose version strings changed.

---

### §R5 — Patch the test drift literals

#### R5.1 — Read the actual failures

The §R0.4 capture is the source of truth. Re-read it now:

```bash
cd /app/backend
python -m pytest --ignore=tests/test_c3_governance_smoke.py -v 2>&1 | grep -E "FAILED|AssertionError" | head -30
```

For each failure, record:
- The test file + function name.
- The assertion line (`grep -A 5 "def test_..." path/to/test.py`).
- The actual value at runtime (from the AssertionError message).
- The expected value at runtime (from the live DB — captured in §R0.5).

Don't proceed to R5.2/R5.3/R5.4 until §R5.1's table is complete.

#### R5.2 — Patch `tests/test_auth_rbac.py` permission-count literals

For each failure that's a "wrong N" in this file:

```bash
# Example pattern — the file as of chat-19A says super_admin == 85, director == 81.
# If live state is super_admin == 86, director == 82, the assertions need updating.
grep -n "== 85\|== 81\|== 87\|len(data\[\"permissions\"\]) ==" /app/backend/tests/test_auth_rbac.py
```

For each line that fails, change the literal to the value captured in §R0.5. **Add a comment line above each assertion documenting the trail:**

```python
# super_admin count history:
#   1.7 baseline: 81
#   + 2.2 (appraisals.submit, appraisals.view_financials): 83
#   + 2.4A (budgets.admin): 84
#   + 2.5A (actuals.admin): 85
#   + 2.5C (ai_capture.view_costs from chat-20): 86  ← current
assert role_perms["super_admin"] == 86
```

This keeps the trail visible so the next person editing it doesn't lose context. **Do NOT rename functions** — keep `test_me_super_admin_returns_87_permissions` as-is. Function-name vs assertion-value drift is recorded but not fixed (out of scope per §2).

#### R5.3 — Patch `tests/test_migration_0025_actuals.py` head literal

```bash
grep -n "0025_actuals\|0025_" /app/backend/tests/test_migration_0025_actuals.py
```

For each occurrence, decide:
- If it's asserting the table SCHEMA from migration 0025 (51 columns, indexes, etc.) → leave alone. The 0025 migration's effects persist past 0026.
- If it's asserting `version_num == '0025_actuals'` → this is now wrong (head is whatever §R0.3's `alembic current` returned).

The likely fix is **one line** in `test_alembic_head_is_0025_actuals`. Use the EXACT head string captured in §R0.3 (`alembic current`), not the example below:

```python
def test_alembic_head_is_0025_actuals(self, engine):
    with engine.connect() as c:
        head = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    # Updated by Chat 22: 0025_actuals → <head from §R0.3>.
    # Keep function name (renaming is out of scope; see chat-22 §2).
    assert head == "<head from §R0.3>", f"expected <head>, got {head!r}"
```

The example shows `0026_ai_capture_costs_perm` because that's the head reported by Chat 21's local run — but the agent uses §R0.3's actual capture in case it's drifted further.

#### R5.4 — Patch `tests/test_bootstrap.py` head sentinel (if present)

```bash
grep -n "0025_\|0026_\|startswith(\"00" /app/backend/tests/test_bootstrap.py
```

If a `head.startswith("0025_")` or similar exists, bump to match live head. This is the same mechanical pattern chat-15-closing §3 logged as "part of any migration's bookkeeping" — Chat 20 didn't catch it.

---

### §R6 — Local validation

```bash
# 6.1 — Run pytest end-to-end. Expect 0 failures now.
cd /app/backend
python -m pytest --ignore=tests/test_c3_governance_smoke.py 2>&1 | tail -10
# Record: N passed, 0 failed.

# 6.2 — Frontend build + Jest.
cd /app/frontend
yarn install --frozen-lockfile 2>&1 | tail -3  # MUST be green after R4
yarn build > /tmp/yarn_build.log 2>&1
tail -10 /tmp/yarn_build.log
MAIN=$(ls build/static/js/main.*.js | head -1)
SIZE_BYTES=$(gzip -c "$MAIN" | wc -c | tr -d ' ')
echo "Bundle: $SIZE_BYTES bytes"
test "$SIZE_BYTES" -le 437000 && echo "OK under cap" || echo "OVER CAP"

CI=true yarn test --watchAll=false 2>&1 | tail -5

# 6.3 — Workflow YAML still parses.
python3 -c "import yaml; yaml.safe_load(open('/app/.github/workflows/ci.yml'))" && echo "YAML: OK"
```

Self-report:
- pytest: N passed, 0 failed.
- yarn install --frozen-lockfile: clean.
- yarn build: clean.
- Bundle: bytes / 437000 cap.
- Jest: N passed, 0 failed.
- YAML parses.

---

### §R7 — CHANGELOG + Future_Tasks

#### R7.1 — CHANGELOG entry (prepend at top of `/app/CHANGELOG.md`)

Fill in every `<placeholder>` with the actual value from R0–R6 self-report
captures. Don't ship the literal `<placeholder>` text.

```markdown
## Chat 22 — CI pipeline hardening (<DATE>)

**Anchor:** First Chat 21 CI run (commit `26822fb`, 2026-05-18) red after 27s. Two setup-step failures, both pre-existing weaknesses surfaced by CI's stricter environment.

- **New file: `/app/backend/requirements-ci.txt`** — `requirements.txt` minus
  `emergentintegrations==0.1.0` (which is a private Emergent sandbox package
  not on public PyPI). Header comment documents the lockstep maintenance rule.
- **Edited `.github/workflows/ci.yml`**: backend job now installs from
  `requirements-ci.txt` instead of `requirements.txt`.
- **Regenerated `frontend/yarn.lock`** — drift diagnosed as <innocent|skipped per R4 sinister-drift STOP>;
  <N> packages updated (<list package names>). `yarn install --frozen-lockfile` now clean.
- **Test drift patches (<N> literals across <N> files):**
  - `tests/test_auth_rbac.py` — super_admin assertion bumped <old> → <new>;
    director assertion bumped <old> → <new>.
    Function names retained as-is (renaming out of scope; see chat-22 §2).
  - `tests/test_migration_0025_actuals.py::test_alembic_head_is_0025_actuals`
    — assertion bumped `0025_actuals` → `<head from §R0.3>`.
  - `tests/test_bootstrap.py` — head sentinel bumped <or "not modified — no sentinel found">.
- No source code, migrations, permissions, or seeds modified by this Build Pack.
```

#### R7.2 — Future_Tasks polish entry

Append a new entry at the bottom of `/app/docs/SY_Homes_Future_Tasks.md`:

```markdown
## N. Test function names with stale literal numbers — polish

**Surfaced in:** Chat 22 (CI hardening, 2026-05-18)
**Severity:** P3 (cosmetic)

`tests/test_auth_rbac.py` has function names like
`test_me_super_admin_returns_87_permissions` whose assertions have drifted
to different values (currently 86). Chat 22 fixed the assertions but kept
function names unchanged because renaming is wider-scope. A follow-up polish
pass should rename them all to a permission-count-agnostic style like
`test_me_super_admin_returns_seeded_permission_count` and assert against
`len(PERMISSION_CATALOGUE)` to make them self-updating.

**Resolution:** Single test-renaming polish prompt. Touches no production code.
```

---

### §R8 — Spot-check

```bash
cd /app
git status --porcelain
# Expected:
#   M  CHANGELOG.md
#   M  docs/SY_Homes_Future_Tasks.md
#   M  .github/workflows/ci.yml
#   M  frontend/yarn.lock     (if R4 ran)
#   M  backend/tests/test_auth_rbac.py
#   M  backend/tests/test_migration_0025_actuals.py
#   M  backend/tests/test_bootstrap.py     (if R5.4 found a sentinel)
#   ?? backend/requirements-ci.txt
#   ?? docs/SY_Hub_Chat_22_CI_Hardening_Build_Pack.md
#   ?? docs/chat-summaries/chat-22-closing.md
```

After Save-to-GitHub, eye-check at `https://github.com/Rhizzo-ai/SY-Hub`:
1. New commit at top of main.
2. All files in the list above show in the diff.
3. CI workflow re-triggers automatically on the new push.
4. Both jobs green within ~10 min.

If CI is still red after this Build Pack lands, paste the new failure logs into the chat and we'll iterate.

---

## §4 — Acceptance criteria

1. `/app/backend/requirements-ci.txt` exists, line count = `requirements.txt` line count − 1.
2. `.github/workflows/ci.yml` references `requirements-ci.txt` in the backend job.
3. `yarn install --frozen-lockfile` exits 0 locally.
4. `python -m pytest --ignore=tests/test_c3_governance_smoke.py` exits 0 locally (zero failures).
5. `yarn build` clean; main bundle under 437,000 bytes gzipped.
6. `yarn test --watchAll=false` exits 0 locally.
7. CHANGELOG Chat 22 entry at top.
8. Future_Tasks polish entry appended.
9. First CI run after Save-to-GitHub: both jobs green within 10 min.

---

## §5 — Self-report template

```
### R0 — Baseline
- repo SHA: <recorded>
- ci.yml present on main: <yes / no>
- bootstrap rc: <0 / N>
- alembic current: <recorded>   ← record exact value
- pytest baseline: <N> passed, <N> failed
- failing tests (verbatim names): <list>
- perms count (R0.5): <recorded>
- roles count (R0.5): <recorded>
- per-role permission counts: <table>

### R1.1 — emergentintegrations import audit
- Hits in app/: <count>  ← expect 0
- Hits in tests/: <count>  ← expect 0
- Hits in scripts/: <count>
- Conclusion: option 3 is <valid / invalid — switch to option 2>

### R1.2 — yarn.lock drift diagnosis
- frozen-lockfile fails locally: <yes / no>
- yarn install (relaxed) line-count delta: <+N -N>
- packages with changed version strings: <list>
- Drift classification: <innocent / sinister>
- Proceed to R4: <yes / STOP>

### R2 — requirements-ci.txt
- Line count of requirements.txt: <N>
- Line count of requirements-ci.txt: <N-1>
- emergentintegrations grep in new file: <empty / FAIL>
- Test install in /tmp venv: <clean / errors>
- Header comment added: <yes / no>

### R3 — workflow YAML edit
- Old line: pip install -r requirements.txt
- New line: pip install -r requirements-ci.txt
- Comment added: <yes / no>
- YAML still parses: <yes / no>

### R4 — yarn.lock regen
- Skipped (sinister drift): <yes — STOP / no — proceeding>
- yarn install --frozen-lockfile after regen: <clean / FAIL>
- Final line-count delta on yarn.lock: <+N -N>

### R5.1 — Failure table (verbatim)
| Test | File | Old literal | New literal |
|---|---|---|---|
| <fill> | <fill> | <fill> | <fill> |

### R5.2/R5.3/R5.4 — Patches applied
- tests/test_auth_rbac.py — <N> lines changed
- tests/test_migration_0025_actuals.py — <N> lines changed
- tests/test_bootstrap.py — <N> lines changed (or "no sentinel found")
- Trail comments added above each changed assertion: <yes / no>
- No function names renamed: <verified / NOT VERIFIED>

### R6 — Local validation
- pytest: <N> passed, <N> failed   ← expect 0 failed
- yarn install --frozen-lockfile: <clean>
- yarn build: <clean>
- Main bundle bytes: <N>   ← expect ≤437,000
- Jest: <N> passed, <N> failed
- Workflow YAML parses: <yes>

### R7 — Docs
- CHANGELOG entry: <yes>
- Future_Tasks polish entry: <yes>

### R8 — Files committed
- .github/workflows/ci.yml: M
- backend/requirements-ci.txt: ??
- backend/tests/test_auth_rbac.py: M
- backend/tests/test_migration_0025_actuals.py: M
- backend/tests/test_bootstrap.py: M (or "not modified — no sentinel")
- frontend/yarn.lock: M (or "not modified — drift was sinister, see R1.2")
- CHANGELOG.md: M
- docs/SY_Homes_Future_Tasks.md: M
- docs/SY_Hub_Chat_22_CI_Hardening_Build_Pack.md: ??
- docs/chat-summaries/chat-22-closing.md: ??
- No source code changes (backend/app/, backend/alembic/, frontend/src/): <verified>

### Final state
- alembic head: <unchanged from R0>
- Permissions: <unchanged from R0>
- Roles: <unchanged from R0>
- Test count: <new total> passing, 0 failing

### Next CI run expectation
- After Save-to-GitHub, CI re-triggers automatically.
- Both jobs (backend, frontend) green within ~10 min.
- README badge turns green.
```

---

## §6 — Chat-end ritual

Before declaring close: open `https://github.com/Rhizzo-ai/SY-Hub` and eye-check that the most recent auto-commits include all of:

1. `backend/requirements-ci.txt` (new)
2. `.github/workflows/ci.yml` (modified — backend pip install line)
3. `frontend/yarn.lock` (modified — only if R4 ran)
4. `backend/tests/test_auth_rbac.py` (modified)
5. `backend/tests/test_migration_0025_actuals.py` (modified)
6. `backend/tests/test_bootstrap.py` (modified — if R5.4 ran)
7. `CHANGELOG.md` (Chat 22 entry at top)
8. `docs/SY_Homes_Future_Tasks.md` (polish entry appended)
9. `docs/SY_Hub_Chat_22_CI_Hardening_Build_Pack.md` (this file)
10. `docs/chat-summaries/chat-22-closing.md` (self-report)

After spot-check, watch CI: `https://github.com/Rhizzo-ai/SY-Hub/actions`. New workflow run should start within ~2 min and both jobs go green.

---

## §7 — Stop-gates

- **R0.4:** Pytest baseline has 50+ failures (way more than expected drift; deeper issue we haven't scoped).
- **R1.1:** `emergentintegrations` is imported by `app/` or `tests/`. Option 3 is wrong — STOP and re-scope with operator.
- **R1.2:** yarn.lock drift looks sinister (>5 packages OR major-version bumps). STOP and self-report; operator decides.
- **R2 line-count check:** New file's line count delta ≠ 1.
- **R4:** `yarn install --frozen-lockfile` still fails after regen.
- **R6.1:** Pytest still has failures after R5 patches.
- **R6.3:** Workflow YAML doesn't parse.
- Scope creep: any temptation to touch source code, models, schemas, migrations, permissions, seeds, frontend src — STOP.

---

_End of Build Pack v1._
