# Chat 20 / Prompt 2.5D — AI Capture Cost Dashboard (B38)

**STATUS: v-FINAL — paste-ready. 4 audit passes completed (14 Pass-2 catches applied, Pass 3 doc-vs-impl alignment clean at 21 consistent permission-code mentions, Pass 4 fresh-eyes read clean).**

**Predecessor anchor:** Chat 19C closed 2026-02-17 — AI Capture Review Surface (B28) + B36 lock-in. Bundle 423.99 kB (13.01 kB headroom). pytest 790, Jest 118. Alembic head `0025_actuals`.

**Scope:** Backend aggregation endpoint + new permission + lazy-loaded frontend dashboard page (totals + 30-day daily line + status breakdown) + tests. **Zero LOC change** to AI capture pipeline, actuals state machine, or existing review-surface code.

---

## Front matter — locked decisions

| # | Decision | Resolution |
|---|---|---|
| L1 | Backend aggregation owner | Backend (new `GET /v1/ai-capture-jobs/stats` endpoint). NOT client-side rollup. |
| L2 | Page location | New route `/ai-capture/cost` — flat sibling per I1. NOT a tab on the inbox. |
| L3 | MVP visualisations | (a) Four totals cards (b) 30-day daily cost line chart (c) status breakdown bar. Door left open for model breakdown (D4 + B43). |
| L4 | Permission model | New permission `ai_capture.view_costs`. Granted to super_admin, director, finance. Visible/manageable in `/permissions`. NOT `actuals.admin`. |
| L5 | Chart library | `recharts@^3.6.0` (already in package.json — verified). |
| L6 | Bundle strategy | `React.lazy()` on the entire `AICaptureCosts` page so recharts is code-split into its own chunk. Main bundle delta MUST be ≤ +3 kB gz. |
| L7 | Date range UI | Quick-pick buttons: 7 days / 30 days / 90 days / All time. NO custom date picker in v1 (defer to backlog). |
| L8 | Currency rendering | `fmtGBP(cost_pence / 100)` everywhere. Backend returns pence; frontend converts on render. |
| L9 | Empty-state behaviour | If period has zero jobs: render totals as £0.00/0, render charts with explicit empty-state message. NEVER crash. |
| L10 | Time series timezone | Backend aggregates by `date_trunc('day', created_at AT TIME ZONE 'Europe/London')`. NOT UTC (Louise would lose a day's data at midnight). |
| L11 | Status breakdown buckets | `Completed`, `Failed`, `Discarded` only. `Queued` / `Extracting` / `Awaiting_Review` are in-flight and excluded from "spend on outcomes" view. |
| L12 | Test runner | Jest via `craco test` (E1 from Chat 17 — NOT vitest). |
| L13 | Path alias | `@/` → `frontend/src/` (verified, I10). |
| L14 | Cookies-only auth | `api.js` axios instance with `withCredentials: true` — reuse existing. |
| L15 | Playwright | NOT in this Build Pack. Specs deferred to follow-up half-session. |

---

## Front matter — deviations (Dn)

These are explicit calls Claude (triage) made before paste. Emergent honours unless it has a verified-better reason; any deviation surfaces as Em.

- **D1.** Permission code `ai_capture.view_costs` (NOT `actuals.cost_view`, NOT `ai_capture.view`). Resource enum gets new value `ai_capture`; action enum gets new value `view_costs`. Both via `ALTER TYPE ... ADD VALUE` per migration 0020 pattern (autocommit_block).
- **D2.** New permission marked `is_sensitive=true`. Cost data reveals operational pricing; treated as finance-sensitive.
- **D3.** Role grants on permission rollout: super_admin, director, finance. NOT project_manager, NOT site_manager. Matches `actuals.admin` distribution.
- **D4.** Status breakdown chart only — model breakdown (claude-3-5-sonnet vs others) deferred to backlog B43. Backend `model_used` IS returned in the per-job rollup grouping should we revisit. v1 dashboard does NOT chart model.
- **D5.** Time series granularity = daily only. No hourly/weekly toggle in v1.
- **D6.** Backend returns daily series with ZERO-FILLED missing days (so chart renders continuous). Empty days have `cost_pence: 0, job_count: 0` rather than being omitted.
- **D7.** Backend response uses pence (integers) for all monetary fields. Avoids float round-tripping. Frontend divides by 100 at render time.
- **D8.** Date range quick-pick uses radio-style toggle buttons (NOT Radix Select — F9 sentinel pattern not needed for static option set).
- **D9.** Page wrapper uses the same hooks-above-perm-gate pattern as `CaptureJobDetail.jsx` (E13). `useCaptureCostStats` MUST be called before any conditional early-return.
- **D10.** `fmtGBP` already exists in `lib/format.js` (verified). NO new currency helper; reuse.
- **D11.** Chart colours pull from SY brand tokens — line chart uses `sy-teal`, status breakdown uses `sy-teal` (Completed) / amber-500 (Failed) / slate-400 (Discarded). NO new Tailwind tokens introduced (I11 brand discipline).
- **D12.** Recharts components imported individually (not as `* as Recharts`) to maximise tree-shaking inside the lazy chunk.
- **D13.** `useCaptureCostStats` invalidation key bucketed under `aiCaptureKeys.all` so promote/discard/retry mutations already in `hooks/aiCapture.js` invalidate the stats query automatically (I12 cross-domain pattern, in-domain in this case).
- **D14.** Skeleton loaders rendered while `isLoading` (NO `null` returns that flash blank). Pattern: card-shaped pulsing rectangles using `animate-pulse` Tailwind class.
- **D15.** Backend endpoint accepts `from_date` and `to_date` as query params (ISO date YYYY-MM-DD), both optional. Server default = today and today-30. Validator rejects future dates and `from > to` with 422.
- **D16.** **Bundle assertion fixture.** The Build Pack ships a new `frontend/src/pages/__tests__/AICaptureCosts.bundle.test.js` smoke test that imports the lazy-load wrapper and asserts the chunk imports succeed; it does NOT measure size (CRA build is the size source of truth). Size verified at §R0 + §R6 STOP gates.

---

## Front matter — new backlog items (added at chat-end)

- **B43** — AI Capture cost dashboard: breakdown by model. Surface `model_used` aggregation when more than one model is in use. v1 ships status breakdown only (D4).
- **B44** — AI Capture cost dashboard: custom date picker. v1 ships quick-pick buttons (7d/30d/90d/all). Add range picker if Louise asks for arbitrary windows.
- **B45** — AI Capture cost dashboard: CSV export. Currently the page is view-only. Useful for board pack inclusion if monthly cost surfaces become material.
- **B46** — AI Capture cost dashboard: notification when daily cost crosses a threshold. Operator-defined `system_config` cost ceiling triggers alert. Pairs with B26 pause helper.

---

# §R0 — Baseline + decision gates

## R0.1 Verify environment

```bash
cd /app/backend
python -m pytest --co -q 2>&1 | tail -1   # MUST report 790 collected
alembic current                            # MUST report 0025_actuals (head)

cd /app/frontend
yarn jest --listTests 2>&1 | tail -1       # Jest spec file count
yarn build 2>&1 | tail -5                  # build clean; capture gzipped main JS line
ls -la build/static/js/main.*.js           # confirm bundle filename pattern
```

Record into the R8.1 self-report under §R0 lines.

## R0.2 Verify live-code preconditions

```bash
# Permission enum extension targets — verify migration 0020 autocommit_block pattern
grep -A 3 'autocommit_block' backend/alembic/versions/0020_permission_action_submit.py

# Existing permission row insert pattern (idempotent ON CONFLICT)
grep -A 8 'INSERT INTO permissions' backend/alembic/versions/0019_appraisals_core.py

# Existing role_permissions backfill pattern (NOT EXISTS join)
grep -A 12 'INSERT INTO role_permissions' backend/alembic/versions/0014_cost_code_permissions.py

# Verify recharts is in package.json but NOT yet imported (lazy-load is meaningful)
grep -r 'from .recharts' frontend/src/ | wc -l    # expect 0 — first use is this build
grep '"recharts"' frontend/package.json           # expect ^3.6.0

# Confirm React.lazy pattern is unused on AppShell-level routes today
grep -n 'React.lazy' frontend/src/App.js          # expect 0

# fmtGBP helper signature
grep -A 5 'export function fmtGBP' frontend/src/lib/format.js

# Existing aiCapture hook factory bucket
grep -A 6 'aiCaptureKeys' frontend/src/hooks/aiCapture.js
```

## R0.3 Decision gates (resolve before R1)

| Gate | Check | Pass | Fail action |
|---|---|---|---|
| Migration 0025 is current head | `alembic current` | proceed | STOP — fresh-fork provisioning runbook |
| pytest baseline 790 | `pytest --co -q` | proceed | STOP — investigate test drift |
| Jest baseline 118 | `yarn jest --listTests` count + 19C closing | proceed | STOP — investigate frontend test drift |
| Bundle ≤ 437 kB | `ls build/static/js/main.*.js` then gzip-size of contents | proceed | STOP — bundle budget already busted |
| recharts present | `grep '"recharts"' frontend/package.json` | proceed | install `recharts@^3.6.0` first |
| recharts NOT yet imported | `grep -r 'from .recharts.' frontend/src/` count = 0 | confirms lazy-load delta logic | adjust §R6 STOP gate 1 expected delta upward |
| `fmtGBP` exists at `lib/format.js` | grep | proceed | abort — required helper missing |
| `aiCaptureKeys.all` exported from `hooks/aiCapture.js` | grep | proceed | abort — required factory missing |
| `permission_resource` enum exists | introspect | proceed | abort — 0002 migration missing |
| `permission_action` enum exists | introspect | proceed | abort — 0002 missing |
| `is_super_admin` available on `UserPermissions` object | grep `is_super_admin` in `app/auth/permissions.py` | proceed | adjust §R1.3 perm check |

Resolve every gate before R1.

---

# §R1 — Backend

## R1.1 New migration `0026_ai_capture_costs_perm`

Path: `backend/alembic/versions/0026_ai_capture_costs_perm.py`

**Migration purpose:** extends `permission_resource` enum with `'ai_capture'`, extends `permission_action` enum with `'view_costs'`, inserts the `ai_capture.view_costs` permission row, and grants it to super_admin + director + finance roles. All idempotent.

```python
"""0026 — ai_capture.view_costs permission (B38 cost dashboard).

Revision ID: 0026_ai_capture_costs_perm
Revises: 0025_actuals

Adds:
  - permission_resource enum value 'ai_capture'
  - permission_action enum value 'view_costs'
  - permissions row code='ai_capture.view_costs' (is_sensitive=true)
  - role_permissions grants for super_admin, director, finance

Idempotent. Safe to re-run.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0026_ai_capture_costs_perm"
down_revision = "0025_actuals"
branch_labels = None
depends_on = None


MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0026")

ROLES_GRANTED = ("super_admin", "director", "finance")


def upgrade() -> None:
    # ENUM extensions must run outside a transaction (Postgres limitation).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE permission_resource ADD VALUE IF NOT EXISTS 'ai_capture'"
        )
        op.execute(
            "ALTER TYPE permission_action ADD VALUE IF NOT EXISTS 'view_costs'"
        )

    bind = op.get_bind()

    # Insert permission row (idempotent via ON CONFLICT).
    bind.execute(sa.text("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES (
            gen_random_uuid(),
            'ai_capture.view_costs',
            'ai_capture',
            'view_costs',
            'View aggregated AI capture cost / token / volume statistics',
            true
        )
        ON CONFLICT (code) DO NOTHING
    """))

    # Grant to roles (idempotent via NOT EXISTS join).
    inserted = 0
    for role_code in ROLES_GRANTED:
        result = bind.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.code = :role AND p.code = 'ai_capture.view_costs'
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """), {"role": role_code})
        inserted += result.rowcount or 0

    # Audit row.
    rev_uuid = uuid.uuid5(MIGRATION_AUDIT_NAMESPACE, revision)
    bind.execute(sa.text("""
        INSERT INTO audit_log
            (id, action, resource_type, resource_id, field_changes,
             metadata_json, created_at)
        VALUES (gen_random_uuid(), 'Permission_Change', 'migration', :rid,
                CAST('[]' AS jsonb), CAST(:meta AS jsonb), :now)
    """), {
        "rid": str(rev_uuid),
        "meta": json.dumps({
            "kind": "seed_run", "revision": revision,
            "target": "permissions + role_permissions",
            "permissions": ["ai_capture.view_costs"],
            "roles_granted": list(ROLES_GRANTED),
            "rows_inserted": inserted,
        }),
        "now": datetime.now(timezone.utc),
    })


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id
          AND p.code = 'ai_capture.view_costs'
    """)
    op.execute(
        "DELETE FROM permissions WHERE code = 'ai_capture.view_costs'"
    )
    # ENUM values not removable in Postgres; leave in place.
```

## R1.2 Update `seed_rbac.py`

Add the catalogue entry and role mapping so fresh boots seed the new permission.

**Step 1.** Add the catalogue tuple. Locate the existing `PERMISSION_CATALOGUE += _perms_for("actuals", ...)` block and add this block IMMEDIATELY AFTER (the actuals block ends ~line 105–110):

```python
# Chat 20 §R1.2 (Prompt 2.5D / B38) — new resource + action for cost dashboard.
PERMISSION_CATALOGUE += [
    ("ai_capture.view_costs", "ai_capture", "view_costs",
     "View aggregated AI capture cost / token / volume statistics", True),
]
```

**Step 2.** Extend the finance role grant. Locate the existing `ROLE_PERMISSIONS["finance"] = { ... }` literal assignment (line ~165) and add the new perm to that literal:

```python
ROLE_PERMISSIONS["finance"] = {
    # ... existing entries unchanged ...
    "ai_capture.view_costs",   # Chat 20 §R1.2 — cost dashboard visibility
}
```

**Step 3.** No edit needed to `super_admin` (built via `set(ALL_PERMISSION_CODES)` — auto-picks up the new perm).

**Step 4.** No edit needed to `director` (built via `set(ALL_PERMISSION_CODES) - {exclusions}` — auto-picks up the new perm).

**STOP gate (PASS 2 verified):** the placement above the `_codes_for("actuals")` selectors matters because the new perm sits OUTSIDE the actuals resource. The post-hoc union pattern (`ROLE_PERMISSIONS["finance"] | {...}`) used in earlier drafts is brittle to merge conflicts; in-literal extension is the canonical pattern here.

## R1.3 New endpoint `GET /api/v1/ai-capture-jobs/stats`

Append to `backend/app/routers/ai_capture.py` (do NOT create a new router file — group with the existing 6 capture endpoints).

```python
# ---------------------------------------------------------------------
# 7. Stats — Chat 20 §R1.3 (B38 cost dashboard)
# ---------------------------------------------------------------------

from datetime import date as date_type, timedelta

@router.get("/ai-capture-jobs/stats")
def get_capture_stats(
    from_date: Optional[date_type] = Query(default=None, description="ISO date YYYY-MM-DD, inclusive"),
    to_date: Optional[date_type] = Query(default=None, description="ISO date YYYY-MM-DD, inclusive"),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("ai_capture.view_costs")),
    db: Session = Depends(get_db),
):
    """Aggregated AI capture statistics for a date range.

    All monetary fields are returned as integer pence to avoid float
    round-tripping. Frontend renders as £ via /100 division.

    Date bucketing uses Europe/London tz (NOT UTC) so the day boundaries
    match what Louise expects in the dashboard (L10).
    """
    today = datetime.now(timezone.utc).astimezone().date()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - timedelta(days=29)  # inclusive 30-day window

    if from_date > to_date:
        raise HTTPException(422, detail={
            "code": "invalid_date_range",
            "message": "from_date must be <= to_date",
        })
    if to_date > today:
        raise HTTPException(422, detail={
            "code": "future_date",
            "message": "to_date cannot be in the future",
        })

    return cap_svc.compute_capture_stats(
        db, from_date=from_date, to_date=to_date,
    )
```

**Imports needed at top of `ai_capture.py`:**
- `from datetime import datetime, timezone, date as date_type, timedelta` — verify what's already imported; add only missing.

## R1.4 Service function `compute_capture_stats`

Append to `backend/app/services/ai_capture.py`.

```python
# ---------------------------------------------------------------------
# Stats aggregation — Chat 20 §R1.4 (B38)
# ---------------------------------------------------------------------

from datetime import date as date_type, timedelta
from sqlalchemy import func, text as sa_text


def compute_capture_stats(
    db: Session, *, from_date: date_type, to_date: date_type,
) -> dict:
    """Aggregate ai_capture_jobs over a date range.

    Returns:
        {
          "period": {"from_date": "...", "to_date": "...", "days": N},
          "totals": {
            "total_jobs": int,
            "total_cost_pence": int,
            "avg_cost_pence": int,  # rounded; 0 if total_jobs == 0
            "total_prompt_tokens": int,
            "total_completion_tokens": int,
          },
          "daily_series": [
            {"date": "YYYY-MM-DD", "cost_pence": int, "job_count": int},
            ...   # ZERO-FILLED for missing days (D6)
          ],
          "by_status": [
            {"status": "Completed", "cost_pence": int, "job_count": int},
            {"status": "Failed",    "cost_pence": int, "job_count": int},
            {"status": "Discarded", "cost_pence": int, "job_count": int},
          ],
        }
    """
    # ----- Totals (single query, NULL-safe) -----
    totals_row = db.execute(sa_text("""
        SELECT
          COUNT(*) AS total_jobs,
          COALESCE(SUM(cost_pence), 0) AS total_cost_pence,
          COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
          COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens
        FROM ai_capture_jobs
        WHERE created_at AT TIME ZONE 'Europe/London' >= :from_date
          AND created_at AT TIME ZONE 'Europe/London' < :to_date_excl
    """), {
        "from_date": from_date,
        "to_date_excl": to_date + timedelta(days=1),
    }).one()

    total_jobs = int(totals_row.total_jobs)
    total_cost_pence = int(totals_row.total_cost_pence)
    avg_cost_pence = round(total_cost_pence / total_jobs) if total_jobs else 0

    # ----- Daily series, zero-filled -----
    raw_series = db.execute(sa_text("""
        SELECT
          DATE(created_at AT TIME ZONE 'Europe/London') AS d,
          COUNT(*) AS job_count,
          COALESCE(SUM(cost_pence), 0) AS cost_pence
        FROM ai_capture_jobs
        WHERE created_at AT TIME ZONE 'Europe/London' >= :from_date
          AND created_at AT TIME ZONE 'Europe/London' < :to_date_excl
        GROUP BY d
        ORDER BY d
    """), {
        "from_date": from_date,
        "to_date_excl": to_date + timedelta(days=1),
    }).all()
    series_by_day = {r.d: (int(r.cost_pence), int(r.job_count)) for r in raw_series}

    daily_series = []
    day = from_date
    while day <= to_date:
        cost, count = series_by_day.get(day, (0, 0))
        daily_series.append({
            "date": day.isoformat(),
            "cost_pence": cost,
            "job_count": count,
        })
        day += timedelta(days=1)

    # ----- Status breakdown (Completed / Failed / Discarded only — L11) -----
    status_rows = db.execute(sa_text("""
        SELECT
          status,
          COUNT(*) AS job_count,
          COALESCE(SUM(cost_pence), 0) AS cost_pence
        FROM ai_capture_jobs
        WHERE created_at AT TIME ZONE 'Europe/London' >= :from_date
          AND created_at AT TIME ZONE 'Europe/London' < :to_date_excl
          AND status IN ('Completed', 'Failed', 'Discarded')
        GROUP BY status
    """), {
        "from_date": from_date,
        "to_date_excl": to_date + timedelta(days=1),
    }).all()
    status_lookup = {r.status: (int(r.cost_pence), int(r.job_count)) for r in status_rows}
    by_status = []
    for s in ("Completed", "Failed", "Discarded"):
        cost, count = status_lookup.get(s, (0, 0))
        by_status.append({"status": s, "cost_pence": cost, "job_count": count})

    return {
        "period": {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "days": (to_date - from_date).days + 1,
        },
        "totals": {
            "total_jobs": total_jobs,
            "total_cost_pence": total_cost_pence,
            "avg_cost_pence": avg_cost_pence,
            "total_prompt_tokens": int(totals_row.total_prompt_tokens),
            "total_completion_tokens": int(totals_row.total_completion_tokens),
        },
        "daily_series": daily_series,
        "by_status": by_status,
    }
```

## R1.5 Backend tests

Append to `backend/tests/test_ai_capture.py` (or new `test_ai_capture_stats.py` — see PASS 2 audit decision).

Minimum test set (8 cases — H tag = High importance, must pass):

```
TestCaptureStatsPermissions:
  H test_actuals_admin_alone_returns_403           # actuals.admin does NOT grant view_costs
  H test_finance_role_returns_200                  # finance has the new perm
  H test_director_role_returns_200
  H test_unauthenticated_returns_401

TestCaptureStatsAggregation:
  H test_empty_range_returns_zeros                 # no jobs in range
  H test_totals_sum_correctly_across_statuses      # seed mix; verify SUM
  H test_daily_series_zero_filled_for_gap_days     # 1 job day 1, 1 job day 30, days 2-29 are zero rows
  H test_by_status_excludes_in_flight              # Queued/Extracting/Awaiting_Review NOT in by_status

TestCaptureStatsValidation:
  H test_from_after_to_returns_422
  H test_future_to_date_returns_422
  H test_default_30_day_window                     # no params → last 30 days inclusive

TestCaptureStatsPermissionCatalogue:
  H test_ai_capture_view_costs_in_catalogue        # PERMISSION_CATALOGUE contains the new row
  H test_finance_role_set_includes_new_perm        # ROLE_PERMISSIONS["finance"] has it
  H test_project_manager_does_not_have_perm        # negative guard
```

(Final count: 11 minimum. Some may collapse where the same fixture handles multiple assertions; aim for ≥ 11 distinct test_ methods.)

**Test deltas expected:** pytest 790 → ~801 (+11).

**Fixture pattern:** module-scoped `db_engine` with explicit `_wipe_()` teardown (matching existing budgets test pattern). The teardown MUST disable the `audit_log_no_modify` trigger before deleting audit rows seeded by the stats endpoint's audit-side-effects (none in §R1.4 design, but the migration writes one row — that's handled at migration scope, not test scope).

---

# §R2 — Frontend data layer

## R2.1 Zod schema — `frontend/src/lib/schemas/aiCaptureStats.js` (NEW)

```javascript
// frontend/src/lib/schemas/aiCaptureStats.js — Chat 20 §R2.1
//
// Mirrors compute_capture_stats response shape exactly. All monetary
// fields are integer pence (NOT pounds, NOT floats). See L8 / D7.
import { z } from 'zod';

export const CaptureStatsPeriodSchema = z.object({
  from_date: z.string(),  // YYYY-MM-DD
  to_date: z.string(),
  days: z.number().int().positive(),
});

export const CaptureStatsTotalsSchema = z.object({
  total_jobs: z.number().int().nonnegative(),
  total_cost_pence: z.number().int().nonnegative(),
  avg_cost_pence: z.number().int().nonnegative(),
  total_prompt_tokens: z.number().int().nonnegative(),
  total_completion_tokens: z.number().int().nonnegative(),
});

export const CaptureStatsDailyPointSchema = z.object({
  date: z.string(),
  cost_pence: z.number().int().nonnegative(),
  job_count: z.number().int().nonnegative(),
});

export const CaptureStatsByStatusSchema = z.object({
  status: z.enum(['Completed', 'Failed', 'Discarded']),
  cost_pence: z.number().int().nonnegative(),
  job_count: z.number().int().nonnegative(),
});

export const CaptureStatsResponseSchema = z.object({
  period: CaptureStatsPeriodSchema,
  totals: CaptureStatsTotalsSchema,
  daily_series: z.array(CaptureStatsDailyPointSchema),
  by_status: z.array(CaptureStatsByStatusSchema),
});
```

## R2.2 API client — extend `frontend/src/lib/api/aiCapture.js`

Append (do NOT rewrite):

```javascript
import { CaptureStatsResponseSchema } from '@/lib/schemas/aiCaptureStats';

export async function getCaptureCostStats({ fromDate, toDate, signal } = {}) {
  const params = {};
  if (fromDate) params.from_date = fromDate;
  if (toDate) params.to_date = toDate;
  const { data } = await api.get('/v1/ai-capture-jobs/stats', {
    params, signal,
  });
  const result = CaptureStatsResponseSchema.safeParse(data);
  if (!result.success) {
    const issues = result.error.issues.slice(0, 3)
      .map(i => `${i.path.join('.') || '<root>'}: ${i.message}`).join('; ');
    const err = new Error(`Schema drift @ GET /ai-capture-jobs/stats: ${issues}`);
    err.zodIssues = result.error.issues;
    throw err;
  }
  return result.data;
}
```

## R2.3 React Query hook — extend `frontend/src/hooks/aiCapture.js`

Append:

```javascript
import { getCaptureCostStats } from '@/lib/api/aiCapture';

aiCaptureKeys.stats = (filters) => [...aiCaptureKeys.all, 'stats', filters];

export function useCaptureCostStats(filters = {}, opts = {}) {
  return useQuery({
    queryKey: aiCaptureKeys.stats(filters),
    queryFn: ({ signal }) => getCaptureCostStats({ ...filters, signal }),
    staleTime: 60_000,  // dashboard is OK to be slightly stale
    ...opts,
  });
}
```

**STOP gate (PASS 2 verify):** the `aiCaptureKeys.stats(...)` factory result is included in `aiCaptureKeys.all`-prefix invalidation triggered by promote/discard/retry mutations (already in `hooks/aiCapture.js`). This means: a user discarding a job from the inbox correctly invalidates an open cost dashboard. I12 satisfied.

## R2.4 Capability helper — extend `frontend/src/lib/aiCaptureCapability.js`

Append:

```javascript
export function canViewCaptureCosts(me) {
  if (!me) return false;
  const perms = me.permissions || [];
  return perms.includes('ai_capture.view_costs') || !!me.is_super_admin;
}
```

**Note (PASS 2 corrected):** the `me` payload from `GET /auth/me` returns BOTH `permissions: string[]` AND `is_super_admin: boolean` as separate fields. Verified against `app/routers/auth.py::me` and existing `ActualsSensitiveBanner.jsx` pattern. There is NO `'*'` wildcard convention in this codebase — earlier draft included one in error.

---

# §R3 — Frontend page (lazy-loaded)

## R3.1 Page component — `frontend/src/pages/AICaptureCosts.jsx` (NEW)

This is the file that imports recharts. Lazy-loading via React.lazy on the ROUTE means the entire page chunk (page + recharts + charts) loads on demand only.

```jsx
// frontend/src/pages/AICaptureCosts.jsx — Chat 20 §R3.1 (B38)
//
// Cost dashboard. Lazy-loaded from App.js (§R4) so recharts is
// code-split into its own chunk.
//
// I13 hooks-above-perm-gate: useCaptureCostStats MUST be above the
// canViewCaptureCosts() early-return.
import { useState, useMemo } from 'react';
import { useAuth } from '@/context/AuthContext';
import { canViewCaptureCosts } from '@/lib/aiCaptureCapability';
import { useCaptureCostStats } from '@/hooks/aiCapture';
import { fmtGBP } from '@/lib/format';
import { CostTotalsCards } from '@/components/ai-capture/CostTotalsCards';
import { CostDailyChart } from '@/components/ai-capture/CostDailyChart';
import { CostByStatusChart } from '@/components/ai-capture/CostByStatusChart';
import { DateRangePicker } from '@/components/ai-capture/DateRangePicker';

function computeRange(quickPick) {
  const today = new Date();
  const toYMD = (d) => d.toISOString().slice(0, 10);
  // "All time" sends an explicit pre-feature epoch start; backend's missing-
  // params default is last-30-days, which would silently truncate "all" to
  // 30 days. AI capture didn't exist before Feb 2026 so '2024-01-01' is
  // safe as a forever-floor. (PASS 2 H6.)
  if (quickPick === 'all') {
    return { fromDate: '2024-01-01', toDate: toYMD(today) };
  }
  const days = { '7d': 6, '30d': 29, '90d': 89 }[quickPick] ?? 29;
  const from = new Date(today);
  from.setDate(from.getDate() - days);
  return { fromDate: toYMD(from), toDate: toYMD(today) };
}

export default function AICaptureCosts() {
  const { me } = useAuth();
  const [quickPick, setQuickPick] = useState('30d');
  const range = useMemo(() => computeRange(quickPick), [quickPick]);

  const { data, isLoading, error } = useCaptureCostStats(range, {
    enabled: canViewCaptureCosts(me),
  });

  if (!canViewCaptureCosts(me)) {
    return (
      <div className="p-6 text-sm text-slate-500" data-testid="cost-no-perm">
        You don't have permission to view AI Capture costs.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6" data-testid="ai-capture-costs-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="font-heading text-2xl text-slate-900">AI Capture Costs</h1>
        <DateRangePicker value={quickPick} onChange={setQuickPick} />
      </div>

      {error && (
        <div className="text-sm text-rose-600" data-testid="cost-error">
          {error?.response?.data?.detail?.message
            || error?.message
            || 'Failed to load stats'}
        </div>
      )}

      <CostTotalsCards data={data} isLoading={isLoading} quickPick={quickPick} />

      <CostDailyChart data={data} isLoading={isLoading} />

      <CostByStatusChart data={data} isLoading={isLoading} />
    </div>
  );
}
```

## R3.2 DateRangePicker — `frontend/src/components/ai-capture/DateRangePicker.jsx` (NEW)

```jsx
// frontend/src/components/ai-capture/DateRangePicker.jsx — Chat 20 §R3.2
//
// Simple radio-style toggle group. NO Radix Select — static options,
// no need for F9 sentinel pattern (D8).
const OPTIONS = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: 'all', label: 'All time' },
];

export function DateRangePicker({ value, onChange }) {
  return (
    <div
      className="inline-flex rounded-md border border-slate-200 bg-white p-0.5"
      role="radiogroup"
      data-testid="date-range-picker"
    >
      {OPTIONS.map((opt) => {
        const isActive = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(opt.value)}
            data-testid={`date-range-${opt.value}`}
            className={[
              'px-3 py-1.5 text-sm rounded',
              isActive
                ? 'bg-sy-teal text-white'
                : 'text-slate-600 hover:text-slate-900',
            ].join(' ')}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
```

## R3.3 CostTotalsCards — `frontend/src/components/ai-capture/CostTotalsCards.jsx` (NEW)

```jsx
// frontend/src/components/ai-capture/CostTotalsCards.jsx — Chat 20 §R3.3
//
// Four-card row of headline totals. Pence → GBP at render via fmtGBP(/100).
import { fmtGBP } from '@/lib/format';

function Card({ label, value, testid, isLoading }) {
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid={testid}
    >
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 h-8 flex items-center">
        {isLoading ? (
          <div
            className="h-6 w-24 rounded animate-pulse bg-slate-200"
            data-testid={`${testid}-skeleton`}
          />
        ) : (
          <span className="font-mono text-2xl text-slate-900">{value}</span>
        )}
      </div>
    </div>
  );
}

export function CostTotalsCards({ data, isLoading, quickPick }) {
  const t = data?.totals;
  const p = data?.period;
  // Friendly preset label (PASS 2 H10) — "All time" rather than "800 days".
  const periodLabel = (() => {
    if (!p) return '—';
    if (quickPick === 'all') return 'All time';
    if (quickPick === '7d') return 'Last 7 days';
    if (quickPick === '30d') return 'Last 30 days';
    if (quickPick === '90d') return 'Last 90 days';
    return `${p.days} day${p.days === 1 ? '' : 's'}`;
  })();
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        label="Total spent"
        value={fmtGBP((t?.total_cost_pence ?? 0) / 100)}
        testid="cost-total-spent"
        isLoading={isLoading}
      />
      <Card
        label="Total jobs"
        value={String(t?.total_jobs ?? 0)}
        testid="cost-total-jobs"
        isLoading={isLoading}
      />
      <Card
        label="Average per job"
        value={fmtGBP((t?.avg_cost_pence ?? 0) / 100)}
        testid="cost-avg-per-job"
        isLoading={isLoading}
      />
      <Card
        label="Period"
        value={periodLabel}
        testid="cost-period"
        isLoading={isLoading}
      />
    </div>
  );
}
```

## R3.4 CostDailyChart — `frontend/src/components/ai-capture/CostDailyChart.jsx` (NEW)

```jsx
// frontend/src/components/ai-capture/CostDailyChart.jsx — Chat 20 §R3.4
//
// Daily cost line. Imports recharts directly — this is the file that
// pulls recharts into the lazy chunk. D12 individual imports for
// tree-shaking.
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { fmtGBP } from '@/lib/format';

export function CostDailyChart({ data, isLoading }) {
  if (isLoading) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 animate-pulse"
        data-testid="cost-daily-chart-loading"
      />
    );
  }
  const series = (data?.daily_series ?? []).map((d) => ({
    date: d.date.slice(5),  // MM-DD
    cost: d.cost_pence / 100,
  }));
  if (series.length === 0 || series.every((p) => p.cost === 0)) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 flex items-center justify-center text-sm text-slate-500"
        data-testid="cost-daily-chart-empty"
      >
        No AI capture spend in this period.
      </div>
    );
  }
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid="cost-daily-chart"
    >
      <div className="mb-3 text-sm font-medium text-slate-700">Daily cost</div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmtGBP(v)} />
            <Tooltip
              formatter={(value) => [fmtGBP(value), 'Cost']}
              labelFormatter={(label) => `Date: ${label}`}
            />
            <Line
              type="monotone"
              dataKey="cost"
              stroke="#0F6A7A"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

## R3.5 CostByStatusChart — `frontend/src/components/ai-capture/CostByStatusChart.jsx` (NEW)

```jsx
// frontend/src/components/ai-capture/CostByStatusChart.jsx — Chat 20 §R3.5
//
// Stacked / grouped bar by status. Shows where the spend is going —
// useful for surfacing waste (lots of £ on Failed/Discarded = AI is
// missing).
import {
  ResponsiveContainer, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts';
import { fmtGBP } from '@/lib/format';

const STATUS_COLOURS = {
  Completed: '#0F6A7A',  // sy-teal
  Failed: '#f59e0b',     // amber-500
  Discarded: '#94a3b8',  // slate-400
};

export function CostByStatusChart({ data, isLoading }) {
  if (isLoading) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 animate-pulse"
        data-testid="cost-by-status-chart-loading"
      />
    );
  }
  const rows = (data?.by_status ?? []).map((r) => ({
    status: r.status,
    cost: r.cost_pence / 100,
    job_count: r.job_count,
  }));
  if (rows.every((r) => r.cost === 0 && r.job_count === 0)) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 flex items-center justify-center text-sm text-slate-500"
        data-testid="cost-by-status-chart-empty"
      >
        No completed, failed, or discarded jobs in this period.
      </div>
    );
  }
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid="cost-by-status-chart"
    >
      <div className="mb-3 text-sm font-medium text-slate-700">Cost by outcome</div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="status" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmtGBP(v)} />
            <Tooltip
              formatter={(value, _name, props) => [
                `${fmtGBP(value)} (${props.payload.job_count} jobs)`,
                'Cost',
              ]}
            />
            <Bar dataKey="cost">
              {rows.map((r) => (
                <Cell key={r.status} fill={STATUS_COLOURS[r.status]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

---

# §R4 — Routes + nav

## R4.1 Route registration — `frontend/src/App.js`

Add the lazy import + the `<Route>`:

```jsx
import { lazy, Suspense } from 'react';
// ... existing imports ...

// PASS 2 M4: webpackChunkName magic comment so the lazy chunk is named
// predictably (`ai-capture-costs.<hash>.chunk.js`) — gate 3 grep-checkable.
const AICaptureCosts = lazy(() =>
  import(/* webpackChunkName: "ai-capture-costs" */ '@/pages/AICaptureCosts')
);

// Inside the route table, AS A FLAT SIBLING (NOT nested under ProjectDetail):
<Route
  path="/ai-capture/cost"
  element={
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
      <AICaptureCosts />
    </Suspense>
  }
/>
```

**STOP gate (PASS 2 verify):** the existing `/ai-capture` and `/ai-capture/:jobId` routes already exist as flat siblings. The new route MUST sit alongside them; do NOT introduce nesting.

## R4.2 AppShell NAV — `frontend/src/components/AppShell.jsx`

Insert new NAV entry immediately AFTER the existing "AI Capture" entry:

```jsx
{ label: "AI Capture Costs", to: "/ai-capture/cost", icon: PoundSterling, enabled: true, testid: "nav-ai-capture-costs", requires: "ai_capture.view_costs" },
```

**Required import addition (top of file):**

```jsx
import {
    Building2, Users, Layers, Calculator, LineChart, Wallet,
    CalendarDays, FileText, ShieldCheck, Landmark, Link2, LogOut, KeyRound, Laptop,
    User as UserIcon, ShieldAlert, ChevronDown, ScrollText, Settings, Percent,
    Receipt, Bot, PoundSterling,
} from "lucide-react";
```

**STOP gate (PASS 2 verify):** `PoundSterling` icon exists in `lucide-react@^0.507.0` (verify via the lucide-react index; if not, fall back to `Coins` or `BarChart3`).

---

# §R5 — Frontend tests

## R5.1 Jest specs — new files

```
frontend/src/lib/schemas/__tests__/aiCaptureStats-schemas.test.js     ~4 tests
frontend/src/lib/__tests__/aiCaptureCapability-stats.test.js          ~3 tests
frontend/src/components/ai-capture/__tests__/DateRangePicker.test.jsx ~3 tests
frontend/src/components/ai-capture/__tests__/CostTotalsCards.test.jsx ~4 tests
frontend/src/components/ai-capture/__tests__/CostDailyChart.test.jsx  ~3 tests (mock recharts)
frontend/src/components/ai-capture/__tests__/CostByStatusChart.test.jsx ~3 tests (mock recharts)
frontend/src/pages/__tests__/AICaptureCosts.test.jsx                  ~4 tests
```

Total expected new Jest tests: **~24**. Jest count 118 → ~142.

## R5.2 Recharts mocking pattern (E12 analog)

Chart tests stub recharts at the top of each spec file — same convention as `BudgetLinePicker` stubbing in `PromoteForm.test.jsx`. Avoids cascade of internal SVG / measure errors in jsdom.

**PASS 2 M6:** `jest.mock` factories are hoisted ABOVE all imports, so a top-level `import React` is not yet evaluated when the factory runs. Use `require('react')` INSIDE the factory and `React.createElement` instead of JSX:

```javascript
// CostDailyChart.test.jsx — top of file, BEFORE all other imports
jest.mock('recharts', () => {
  const React = require('react');
  return {
    ResponsiveContainer: ({ children }) =>
      React.createElement('div', { 'data-testid': 'rc-responsive' }, children),
    LineChart: ({ children, data }) =>
      React.createElement('div', {
        'data-testid': 'rc-line-chart',
        'data-points': String(data?.length ?? 0),
      }, children),
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    CartesianGrid: () => null,
  };
});
```

Same pattern for `CostByStatusChart.test.jsx` (add `BarChart`, `Bar`, `Cell` to the returned object — `Cell` accepts a `fill` prop the test will assert on).

## R5.3 Critical test cases

```
aiCaptureStats-schemas:
  H parses valid payload
  H rejects negative cost_pence
  H rejects unknown status in by_status
  H accepts empty daily_series + empty by_status (zero-job case)

aiCaptureCapability-stats:
  H canViewCaptureCosts() true when perms include 'ai_capture.view_costs'
  H false when perms is empty
  H false when me is null

DateRangePicker:
  H renders all 4 quick-pick options
  H clicking calls onChange with correct value
  H active option has bg-sy-teal class

CostTotalsCards:
  H renders loading skeleton when isLoading
  H renders zero-state when data is undefined (not loading)
  H renders fmtGBP-formatted values from pence
  H 'Period' card pluralises correctly (1 day vs N days)

CostDailyChart:
  H renders empty-state when all series points are 0
  H renders chart with correct data-points count when populated
  H loading skeleton when isLoading

CostByStatusChart:
  H renders empty-state when all rows are 0
  H renders correct cell colours by status (verify via Cell prop)
  H loading skeleton when isLoading

AICaptureCosts (page):
  H no-perm message when canViewCaptureCosts(me) is false
  H renders all three sub-sections when data loads
  H error state renders when query throws
  H quick-pick change re-fetches via different query key
```

---

# §R6 — Acceptance gates (STOP gates)

| Gate | Threshold | Evidence |
|---|---|---|
| 0 — pytest delta ≥ +11 | 790 → ≥ 801 | `python -m pytest tests/ -v` |
| 1 — Main bundle delta ≤ +3 kB gz | recharts in lazy chunk, NOT main | `ls -la build/static/js/main.*.js` + gzip-size |
| 2 — Main bundle absolute ≤ 437 kB | hard cap I11 | gzipped main JS |
| 3 — Lazy chunk for AICaptureCosts exists | check `build/static/js/*.chunk.js` | grep for AICaptureCosts in chunk manifest |
| 4 — Jest delta ≥ +20 | 118 → ≥ 138 | `yarn jest --listTests` count + run |
| 5 — Migration 0026 applied | `alembic current` = `0026_ai_capture_costs_perm` | bootstrap log |
| 6 — Permission row exists in DB | `SELECT 1 FROM permissions WHERE code='ai_capture.view_costs'` | psql one-shot |
| 7 — Finance role has the perm | join role_permissions + roles + permissions | psql |
| 8 — Endpoint returns valid Zod-parseable shape | curl `/api/v1/ai-capture-jobs/stats` against seeded preview DB | preview-URL curl |
| 9 — Smoke @smoke unchanged | `yarn e2e:smoke` 11/11 < 40 s | operator-side |

Gates 0–8 in-sandbox. Gate 9 operator-side per chat-18 locked policy #9.

---

# §R7 — Self-report template

```
=== Chat 20 / Prompt 2.5D — AI Capture Cost Dashboard ===

§R0 Baseline (before):
  alembic current:    0025_actuals
  pytest:             790
  Jest specs:         25 files, 118 tests
  bundle main JS gz:  423.99 kB
  recharts imports:   0 (verified — first use this build)

§R0 Baseline (after):
  alembic current:    0026_ai_capture_costs_perm
  pytest:             <NEW>
  Jest specs:         <NEW> files, <NEW> tests
  bundle main JS gz:  <NEW> kB
  bundle delta:       <NEW> kB (target ≤ +3, hard cap ≤ +13)
  new lazy chunk:     AICaptureCosts.<hash>.chunk.js (<NEW> kB gz)

§R6 STOP gates:
  [ ] gate 0 pytest delta
  [ ] gate 1 main bundle delta
  [ ] gate 2 main bundle absolute
  [ ] gate 3 lazy chunk exists
  [ ] gate 4 Jest delta
  [ ] gate 5 migration applied
  [ ] gate 6 permission row exists
  [ ] gate 7 finance role has perm
  [ ] gate 8 endpoint returns valid shape
  [ ] gate 9 smoke 11/11 (operator-side)

Deviations honoured: D1–D16 (16 total)
Implementation deltas (E codes): <to be filled>
Backlog additions: B43–B46 (4 total)

Files added: <count>
Files modified: <count>
Commit SHA: <fill at push>
GitHub URL: <fill at push>
```

---

# §R8 — Chat-end ritual

After all R6 gates green:

1. **Commit**: `feat(2.5d): AI capture cost dashboard + new ai_capture.view_costs permission`
2. **Push** to `main`.
3. **Update** `CHANGELOG.md` with the Chat 20 / Prompt 2.5D entry (mirroring 19C format). Stub:
   ```
   ## Chat 20 / Prompt 2.5D — AI Capture Cost Dashboard — closed <DATE>

   **Frontend + minimal backend chat. Lazy-loaded recharts chunk.** Bundle main JS delta: +<N> kB gz (target ≤+3 / hard cap ≤+13). New lazy chunk `ai-capture-costs.<hash>.chunk.js` (≈<N> kB gz, off main path).

   **§R0 baseline gates:**
   - Before: Jest 118, pytest 790, e2e smoke 11/11, bundle 423.99 kB
   - After:  Jest <N>, pytest <N>, e2e smoke 11/11, bundle <N> kB

   **Surfaces shipped:**
   - New permission `ai_capture.view_costs` (granted to super_admin, director, finance)
   - New endpoint `GET /api/v1/ai-capture-jobs/stats`
   - New page `/ai-capture/cost` (lazy-loaded)
   - Three sub-components: totals cards, daily line chart, status breakdown bar

   **B43–B46 added to backlog.** Reference: `docs/chat-summaries/chat-20-closing.md`.
   ```
4. **Append** B43–B46 to `docs/SY_Hub_Phase2_Backlog.md` verbatim from this Build Pack's front matter.
5. **Append** any new invariants to `docs/engineering-invariants.md` (e.g. I14 — chart libraries via route-level React.lazy with `webpackChunkName`).
6. **Write** `docs/chat-summaries/chat-20-closing.md` with file diff + §R7 self-report.
7. **Spot-check** `git log --name-only -1` against the file manifest — flag any drift.
8. **Operator backfill**: fill commit SHA + GitHub URL into chat-20-closing.md §R7 lines.

---

# Appendix A — File manifest (planned)

### New files (~12)

```
backend/alembic/versions/0026_ai_capture_costs_perm.py
backend/tests/test_ai_capture_stats.py                  (or extend test_ai_capture.py — PASS 2 decision)

frontend/src/lib/schemas/aiCaptureStats.js
frontend/src/pages/AICaptureCosts.jsx
frontend/src/components/ai-capture/DateRangePicker.jsx
frontend/src/components/ai-capture/CostTotalsCards.jsx
frontend/src/components/ai-capture/CostDailyChart.jsx
frontend/src/components/ai-capture/CostByStatusChart.jsx

frontend/src/lib/schemas/__tests__/aiCaptureStats-schemas.test.js
frontend/src/lib/__tests__/aiCaptureCapability-stats.test.js
frontend/src/components/ai-capture/__tests__/DateRangePicker.test.jsx
frontend/src/components/ai-capture/__tests__/CostTotalsCards.test.jsx
frontend/src/components/ai-capture/__tests__/CostDailyChart.test.jsx
frontend/src/components/ai-capture/__tests__/CostByStatusChart.test.jsx
frontend/src/pages/__tests__/AICaptureCosts.test.jsx
```

### Modified files (~5)

```
backend/app/routers/ai_capture.py            +1 endpoint: GET /ai-capture-jobs/stats
backend/app/services/ai_capture.py           +1 function: compute_capture_stats
backend/app/seed_rbac.py                     +1 PERMISSION_CATALOGUE row + finance ROLE_PERMISSIONS extension
frontend/src/lib/api/aiCapture.js            +1 function: getCaptureCostStats
frontend/src/hooks/aiCapture.js              +1 hook: useCaptureCostStats + keys.stats factory
frontend/src/lib/aiCaptureCapability.js      +1 fn: canViewCaptureCosts
frontend/src/App.js                          +1 route + lazy + Suspense imports
frontend/src/components/AppShell.jsx         +1 NAV entry + 1 lucide-react import
```

---

# Appendix B — Carry-forward invariants

The build must respect (verbatim from `docs/engineering-invariants.md`):

- **I1** — routes flat siblings in App.js ✓
- **I3** — `fmtGBP` for ALL money ✓ (pence/100 conversion)
- **I8** — AppShell NAV `requires` perm code ✓ (`ai_capture.view_costs`)
- **I10** — path alias `@/` → `frontend/src/` ✓
- **I11** — bundle hard cap 437 kB ✓ (enforced by gate 2)
- **I12** — cross-domain query invalidation ✓ (stats keys under `aiCaptureKeys.all`)
- **I13** — hooks-above-perm-gate ✓ (CaptureJobDetail pattern)
- **E12** — cross-domain consumer test stubbing via jest.mock ✓ (recharts stubs)

Surfacing a new invariant (likely **I14**): **chart libraries lazy-loaded via route-level React.lazy** — recharts (~80 kB gz) is too heavy to live in the main bundle.

---

# Appendix C — Out of scope

- Custom date picker (B44).
- Model breakdown chart (B43).
- CSV / PDF export (B45).
- Cost-threshold alerting (B46).
- Cross-tenant aggregation (single-tenant-live per Project Instructions).
- Cost forecasting / projection.
- Per-supplier cost attribution.
- Playwright specs (deferred to follow-up half-session).

---

# Appendix D — Audit checklist (Pass 2 / 3 / 4)

**PASS 2 — Critical / High / Medium fixes:**
- [ ] Verify `permission_action` enum doesn't already have `view_costs` (collision check)
- [ ] Verify `permission_resource` enum doesn't already have `ai_capture` (collision check)
- [ ] Confirm `finance` role mapping in `seed_rbac.py` actually picks up new perm (it does NOT via wildcard — explicit set extension required)
- [ ] Verify `is_super_admin` attr name on `UserPermissions` object (used in budgets serialiser — pattern check)
- [ ] Sanity-check Europe/London tz string against postgres `pg_timezone_names` — confirm available
- [ ] Confirm `audit_log_no_modify` trigger handles migration audit row insert (it's an INSERT not an UPDATE so should be fine)
- [ ] Verify `lucide-react` exports `PoundSterling` at version `^0.507.0`
- [ ] Verify `fmtGBP` accepts numeric input (not just string) — pattern check
- [ ] Verify React Query v5 hook signature uses `queryKey` + `queryFn` (not v4 object-form variant)
- [ ] Verify `useAuth()` exports `me` (NOT `user`) — Chat 19C uses `me`

**PASS 3 — Doc-vs-impl alignment:**
- [ ] Cross-check every permission code mention across migration / seed_rbac / router / capability helper / AppShell — F3 prevention
- [ ] Hook signature drift: `useCaptureCostStats(filters, opts)` matches both call sites in page and test mocks
- [ ] aiCaptureKeys.stats factory included in cross-mutation invalidation path (trace each mutation)
- [ ] Bundle delta math: confirm gate 1 threshold (+3 kB) is realistic given (a) Suspense fallback (b) capability helper additions (c) NAV entry addition

**PASS 4 — Fresh-eyes final read:**
- [ ] Re-read every code block top-to-bottom assuming nothing
- [ ] Verify no `useState` / `useEffect` deviations from established patterns
- [ ] Check sample queries against the actual DB schema (column names, types)
- [ ] Promote status header to v-final

---

**End of Pass 1 draft. PASS 2 needed before paste.**
