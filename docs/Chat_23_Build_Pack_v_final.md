# Build Pack — Chat 23 — BudgetLinesGrid v2 (Buildertrend-style)

**Version:** v-final (audit-passed, paste-ready)
**Anchor:** Phase 2 backlog HIGH-PRIORITY — BudgetLinesGrid v2
**Prompt scope:** Build Pack A — Grid + breakdown + per-line drilldown. NO bulk actions other than bulk delete + CSV export (Build Pack B follows after one week of real use).
**Repo head expected at start:** alembic `0026_ai_capture_costs_perm`; 86 permissions; 10 roles; backend 799 tests; frontend 151 tests; bundle 425 kB gz (cap 437 kB).
**Stack:** FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16 (C.UTF-8) + React 19 + CRA via craco + TanStack Query + TanStack Table v8 + dnd-kit + react-hook-form + Zod + framer-motion@12.38.0 + axios + sonner + shadcn/ui.
**Design tokens locked:** `bg-sy-teal` (primary CTAs), `bg-sy-orange` (destructive confirms). Both use `hover:brightness-110 active:brightness-95`. No `-hover` / `-foreground` token suffixes.

---

## Resumability contract

This Build Pack will run over 4–6 focused sessions (5–7 days elapsed). Each R-section is independently committable. Emergent must self-report at the end of every R-section using the format in §Self-report. STOP gates are hard pauses for operator review.

The R-numbering is the canonical execution order. **Do not parallelise across R-sections** — later sections depend on backend changes from earlier ones.

---

## §R0 — Pre-flight baseline (Day 1, ~30 min)

### R0.1 — Verify repo state

1. `git status` clean on `main`. No uncommitted work.
2. `alembic current` returns `0026_ai_capture_costs_perm`.
3. `python -m pytest backend/app/tests` → 799 passing.
4. `cd frontend && yarn test --watchAll=false` → 151 passing.
5. `cd frontend && yarn build` → bundle ≤ 437 kB gz (current 425 kB).
6. Permissions count = 86, roles = 10.

### R0.2 — Snapshot existing budget_lines count

```bash
psql $DATABASE_URL -c "SELECT COUNT(*) FROM budget_lines;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM budget_lines bl LEFT JOIN budget_line_items bli ON bli.budget_line_id = bl.id WHERE bli.id IS NULL;"
```

Record both counts in the chat session log. The second count is the backfill scope (lines with zero items). If the second count is > 0, R1.3 backfill is required. If it's 0 (greenfield case, no existing lines), the backfill migration still ships as a no-op safety net.

### R0.3 — Verify TanStack Table is installed

```bash
cd frontend && grep -A2 '"@tanstack/react-table"' package.json || echo "MISSING"
```

If `MISSING`, add `"@tanstack/react-table": "^8.20.0"` to `package.json` and run `yarn install`. Commit `package.json` + `yarn.lock` as a standalone commit titled `chore: install @tanstack/react-table for Budget Grid v2`. Do this BEFORE R2.

### R0.4 — Confirm variance constants drift

```bash
grep -A1 "VARIANCE_AMBER_PCT" backend/app/services/budgets.py
grep -A1 "VARIANCE_RED_PCT" backend/app/services/budgets.py
```

Expected current values: `5.000` and `15.000`.
Target values (per design Q2): `0.000` and `10.000`.
This is normal and fixed in R1.1.

### R0.5 — Check the current bundle composition

```bash
cd frontend && yarn build 2>&1 | tail -40
```

Note the top-3 largest chunks. If any non-main chunk approaches the cap, flag in the session log — code-splitting in R2.2 may need extension.

### R0.6 — STOP gate #1

Operator review point. Confirm:
- All R0 checks passed
- Backfill scope identified
- TanStack Table either present or installed
- No surprises in bundle composition

If anything in R0 fails, halt and surface to operator before proceeding.

---

## §R1 — Backend changes (Day 1–2, ~5 hours)

Four pieces: variance constant fix, auto-create line items, backfill migration, user_preferences scaffold.

### R1.1 — Update variance band constants

**File:** `backend/app/services/budgets.py`

**Change 1 — constants:**

```python
# BEFORE
VARIANCE_AMBER_PCT = Decimal("5.000")     # > 5% over budget
VARIANCE_RED_PCT = Decimal("15.000")      # > 15% over budget

# AFTER (Build Pack A — design Q2)
VARIANCE_AMBER_PCT = Decimal("0.000")     # > 0% over budget = amber
VARIANCE_RED_PCT = Decimal("10.000")      # >= 10% over budget = red
```

**Change 2 — operator in `_classify_variance`:**

```python
# BEFORE
def _classify_variance(variance_pct: Decimal) -> str:
    if variance_pct <= 0:
        return "Green"
    if variance_pct > VARIANCE_RED_PCT:
        return "Red"
    if variance_pct > VARIANCE_AMBER_PCT:
        return "Amber"
    return "Green"

# AFTER
def _classify_variance(variance_pct: Decimal) -> str:
    """Classify a variance pct into Green/Amber/Red (design Q2, Chat 23).

    - variance_pct <= 0   -> Green (on or under budget)
    - variance_pct >= 10  -> Red
    - otherwise (>0, <10) -> Amber
    """
    if variance_pct <= 0:
        return "Green"
    if variance_pct >= VARIANCE_RED_PCT:
        return "Red"
    if variance_pct > VARIANCE_AMBER_PCT:
        return "Amber"
    return "Green"
```

Note: the lower bound for Amber uses strict `>` (not `>=`), so exactly 0 stays Green. The upper bound for Red uses `>=`, so exactly 10 is Red. This matches design Q2 unambiguously.

**Test impact:** Any existing test that asserts variance band at thresholds (e.g. variance_pct=10 → Amber) will need updating. Catalogue these:

```bash
grep -rn "VARIANCE_AMBER_PCT\|VARIANCE_RED_PCT\|variance_status" backend/app/tests/
```

Update all of them to the new bands. **No test should be skipped or weakened** — they should be updated to the new spec and continue to assert deterministic outcomes.

**Reclassification implication:** Existing seeded data may have `variance_status` cached as Green/Amber under the old bands. After deploying R1.1, the next `recompute_summary` call on any budget will reclassify those lines. This is correct behaviour. No data migration is required — the cached fields recompute themselves through normal application flow.

**Acceptance:**
- Constants updated.
- `_classify_variance` operator flipped.
- All existing variance tests updated and passing.
- Add 6 new fence-post tests in `backend/app/tests/test_budgets_variance_bands.py`:
  - variance_pct = -5 → Green
  - variance_pct = 0 → Green
  - variance_pct = 0.001 → Amber
  - variance_pct = 9.999 → Amber
  - variance_pct = 10.000 → Red
  - variance_pct = 25.000 → Red

### R1.2 — Auto-create 4 default budget_line_items on line creation

**Decision Q3 follow-up:** every new `budget_line` gets four `budget_line_items` at amount=0: Materials, Labour, Equipment, Subcontractor.

**File:** `backend/app/services/budgets.py`

Add a module-level constant near the top of the variance section:

```python
DEFAULT_LINE_ITEMS: tuple[str, ...] = (
    "Materials",
    "Labour",
    "Equipment",
    "Subcontractor",
)
```

Add a private helper:

```python
def _create_default_items(db: Session, budget_line: BudgetLine) -> None:
    """Create the 4 default budget_line_items on a new budget_line.

    Design Q3 follow-up (Chat 23 Build Pack A): every new line gets four
    description-based items at amount=0. The names are conventions, NOT
    enforced types — users can rename/delete/add freely after creation.

    Idempotent guard: skip if the line already has any items (used by the
    backfill migration which calls this from app code in tests).
    """
    existing = db.scalar(
        select(BudgetLineItem).where(
            BudgetLineItem.budget_line_id == budget_line.id
        ).limit(1)
    )
    if existing is not None:
        return
    for idx, name in enumerate(DEFAULT_LINE_ITEMS):
        item = BudgetLineItem(
            budget_line_id=budget_line.id,
            description=name,
            quantity=None,
            unit=None,
            rate=None,
            amount=Decimal("0.00"),
            notes=None,
            display_order=idx,
        )
        db.add(item)
    db.flush()
```

**Wire-in points — based on the actual `services/budgets.py` and `routers/budgets.py` in the repo:**

1. `create_from_appraisal` (bulk-create path) — after each `db.add(new_line); db.flush()` inside the loop, call `_create_default_items(db, new_line)`.
2. Direct line-creation route (likely `POST /api/v1/budgets/{budget_id}/lines` in `routers/budgets.py`) — if it currently calls a service function, add the helper call there. If it currently constructs the BudgetLine inline in the router, refactor to a new service function `create_line(db, *, budget_id, payload, user, perms)` that does the ORM create + audit + helper call, then point the router at it. This keeps line creation paths consistent.
3. `new_version` (in `services/budgets.py`) — does NOT call the helper. The version copy logic preserves whatever items the source line had. This is intentional: don't surprise the user by adding items to a copy.
4. Any seeder, fixture factory, or test helper that creates a `BudgetLine` directly — these can bypass the helper for test data. Only the application-facing paths need it.

**Audit log:** Item creation goes through the existing audit pattern. Each of the 4 default items gets an `audit_log` row with `action='CREATE'`, `entity_type='budget_line_item'`. Four separate audit rows per line creation is acceptable — the existing audit infrastructure may or may not group them by request id; either way the trail is complete.

**Acceptance:**
- New helper `_create_default_items` exists in `services/budgets.py`.
- `create_from_appraisal` calls the helper for every line it creates.
- Any other line-creation entry point calls the helper.
- New test file `test_budgets_default_items.py` with at least 4 cases:
  - Line creation via service → exactly 4 items at amount=0.
  - Items have descriptions Materials/Labour/Equipment/Subcontractor in that display_order.
  - Idempotency: calling the helper twice on the same line still results in 4 items, not 8.
  - new_version copy preserves source items, does NOT call the helper.
- Existing tests for `create_from_appraisal` updated to expect 4 items per line.

### R1.3 — Backfill migration for existing budget_lines

**Decision Q3 follow-up:** existing lines with zero items get the 4 defaults retroactively.

**File:** new alembic revision in `backend/alembic/versions/`.

**Revision id constraint:** must be ≤32 chars (varchar(32) on `alembic_version.version_num`). Use slug `0027_budget_line_items_backfill` (29 chars).

**File contents (skeleton):**

```python
"""Backfill 4 default items on existing budget_lines.

Revision ID: 0027_budget_line_items_backfill
Revises: 0026_ai_capture_costs_perm
Create Date: <emit>

Design Q3 follow-up (Chat 23 Build Pack A): every budget_line that has
zero items at the time this migration runs gets four description-based
items (Materials, Labour, Equipment, Subcontractor) at amount=0.00.

Idempotent: only inserts for lines with zero items. Safe to re-run.
No-op on a greenfield database.

Audit log: this migration does NOT emit audit_log rows — it's a one-time
data-shape correction, not a user action. The audit invariant continues
to hold for all CUD via app routes after the migration.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0027_budget_line_items_backfill"
down_revision = "0026_ai_capture_costs_perm"
branch_labels = None
depends_on = None

DEFAULT_ITEMS = (
    ("Materials", 0),
    ("Labour", 1),
    ("Equipment", 2),
    ("Subcontractor", 3),
)


def upgrade() -> None:
    conn = op.get_bind()
    # Find every budget_line with zero items.
    target_lines = conn.execute(sa.text("""
        SELECT bl.id
        FROM budget_lines bl
        LEFT JOIN budget_line_items bli ON bli.budget_line_id = bl.id
        WHERE bli.id IS NULL
        GROUP BY bl.id
    """)).fetchall()

    for (line_id,) in target_lines:
        for description, display_order in DEFAULT_ITEMS:
            conn.execute(
                sa.text("""
                    INSERT INTO budget_line_items (
                        id, budget_line_id, description, amount,
                        display_order, created_at, updated_at
                    )
                    VALUES (
                        gen_random_uuid(), :line_id, :description, 0.00,
                        :display_order, NOW(), NOW()
                    )
                """),
                {
                    "line_id": line_id,
                    "description": description,
                    "display_order": display_order,
                },
            )


def downgrade() -> None:
    """Remove the 4 default items if they're at amount=0.00 and display_order 0-3.

    Best-effort downgrade: only removes items that look untouched. If a user
    edited an item's description or set a non-zero amount, it stays.
    """
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM budget_line_items
        WHERE description IN ('Materials', 'Labour', 'Equipment', 'Subcontractor')
          AND amount = 0.00
          AND display_order BETWEEN 0 AND 3
    """))
```

**Notes:**
- Uses `pgcrypto`'s `gen_random_uuid()` — already provisioned in the stack.
- Raw SQL bypasses SQLAlchemy ORM events and any model-level `updated_at` `onupdate` triggers. The migration emits explicit `NOW()` for both timestamp columns, so the resulting rows are consistent with ORM-created rows.
- Idempotent: re-running upgrade is safe because the WHERE clause excludes any line that now has items.
- Greenfield-safe: empty SELECT returns zero rows; nothing happens.
- Downgrade is best-effort. Documented as such.

**Migration test:** new file `backend/app/tests/test_migration_0027_backfill.py`. Uses the existing migration test pattern (apply migration on test DB seeded with N lines having zero items, verify each ends up with exactly 4 items in correct order).

**Acceptance:**
- Revision file created.
- `alembic upgrade head` succeeds on a copy of dev DB.
- Re-running upgrade is a no-op.
- Migration test passes.
- Revision name length ≤32 chars verified.

### R1.4 — `user_preferences` table + endpoints

**Decision Q6b / Q7b:** new table, keyed by `(user_id, surface_key)`. Used by grid prefs (Chat 23) and saved views (Chat 23), and reusable by future surfaces.

**Migration file:** `backend/alembic/versions/0028_user_preferences_table.py` (28 chars — within limit).

**Schema:**

```python
"""Create user_preferences table.

Revision ID: 0028_user_preferences_table
Revises: 0027_budget_line_items_backfill
Create Date: <emit>

Per-user JSON storage for UI surface state. Used by:
  - BudgetGrid v2 column layout, sort, filters, visibility toggles
  - BudgetGrid v2 saved views (one record per saved view)
  - Future surfaces (any tabular UI with state)

Surface keys are open-ended strings; the application layer decides what
they mean. No enum constraint — adding a new surface is a code-only change.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0028_user_preferences_table"
down_revision = "0027_budget_line_items_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"),
                  primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("surface_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=True),
        # name is NULL for the "current" record (per surface_key); non-NULL
        # for saved views.
        sa.Column("payload", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    # One "current" record per (user, surface). Saved views have non-NULL
    # names and are constrained as (user, surface, name).
    op.create_index(
        "ix_user_preferences_user_surface_current",
        "user_preferences", ["user_id", "surface_key"],
        unique=True, postgresql_where=sa.text("name IS NULL"),
    )
    op.create_index(
        "ix_user_preferences_user_surface_named",
        "user_preferences", ["user_id", "surface_key", "name"],
        unique=True, postgresql_where=sa.text("name IS NOT NULL"),
    )
    op.create_index(
        "ix_user_preferences_user", "user_preferences", ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_preferences_user", "user_preferences")
    op.drop_index("ix_user_preferences_user_surface_named", "user_preferences")
    op.drop_index("ix_user_preferences_user_surface_current", "user_preferences")
    op.drop_table("user_preferences")
```

**Design notes:**
- `name IS NULL` = the "current" record (whatever state the user has on screen, autosaved on change). Exactly one per surface_key.
- `name IS NOT NULL` = a named saved view. Multiple per surface_key.
- Partial unique indexes (Postgres feature) enforce these semantics in the DB layer.
- `JSONB` (not `JSON`) for efficient indexing and partial updates. We never `UPDATE...SET payload->>'foo'` though — full-replace is the API contract.
- `surface_key` is `String(64)`. Initial usage: `budgets.grid.v2`. Future: `actuals.list`, `commitments.grid`, etc.

**Model file:** `backend/app/models/user_preferences.py`

```python
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    surface_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False,
        onupdate=text("NOW()"),
    )
```

**Service file:** `backend/app/services/user_preferences.py`

Functions:
- `get_current(db, user_id, surface_key) -> dict | None`
- `set_current(db, user_id, surface_key, payload) -> UserPreference` (upsert; creates if absent, updates `payload` + `updated_at` if present)
- `list_views(db, user_id, surface_key) -> list[UserPreference]` (name IS NOT NULL only)
- `get_view(db, user_id, surface_key, name) -> UserPreference | None`
- `save_view(db, user_id, surface_key, name, payload) -> UserPreference` (upsert by name)
- `delete_view(db, user_id, surface_key, name) -> bool`

No tenant scoping needed — preferences are per-user, not per-project. The `user_id` itself is the scope. (Note: cross-tenant leakage isn't possible since every user belongs to one tenant and the user_id PK is unforgeable.)

**Schemas file:** `backend/app/schemas/user_preferences.py`

```python
from pydantic import BaseModel, Field
from typing import Any
import uuid
from datetime import datetime


class UserPreferenceOut(BaseModel):
    id: uuid.UUID
    surface_key: str
    name: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserPreferencePayloadIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
```

**Router file:** `backend/app/routers/user_preferences.py`

Endpoints (all under `/api/v1/me/preferences/{surface_key}`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/me/preferences/{surface_key}` | Get current payload + list of named views in one response |
| PUT | `/api/v1/me/preferences/{surface_key}` | Replace current payload (autosave from grid UI) |
| GET | `/api/v1/me/preferences/{surface_key}/views/{name}` | Get one named view |
| POST | `/api/v1/me/preferences/{surface_key}/views` | Save a new view (name + payload) |
| PUT | `/api/v1/me/preferences/{surface_key}/views/{name}` | Overwrite a named view |
| DELETE | `/api/v1/me/preferences/{surface_key}/views/{name}` | Delete a named view |

All require authentication (`require_user`). No permission gating — every authenticated user manages their own preferences. The implicit scope is `WHERE user_id = current_user.id`.

GET `/preferences/{surface_key}` response shape:

```json
{
  "surface_key": "budgets.grid.v2",
  "current": { "payload": { ... } },
  "views": [
    { "id": "...", "name": "Quick", "payload": { ... }, "updated_at": "..." },
    { "id": "...", "name": "Margin watch", "payload": { ... }, "updated_at": "..." }
  ]
}
```

If no current row exists, `current.payload` is `{}`. If no views exist, `views` is `[]`. No 404 from this endpoint.

**Audit log:** Preference reads are NOT audited (high volume, no business significance). Preference writes (PUT/POST/DELETE) ARE audited — but at info level only, with `entity_type='user_preference'`. This is enough to investigate if a user reports lost views, without polluting the audit log with column-resize events.

Actually — second thought: PUT on the autosave path will fire on every grid state change. That's high volume. **Revised:** PUT `/preferences/{surface_key}` (autosave) is NOT audited. POST/PUT/DELETE on named views IS audited. This matches the user's mental model: "Saving a view" feels like a deliberate act; resizing a column doesn't.

**Acceptance:**
- Migration 0028 ships.
- Model, service, schema, router files created.
- Router registered in `app/main.py`.
- New test file `test_user_preferences_api.py` with the following minimum cases (~14 tests):
  - GET on empty surface returns `{"current": {"payload": {}}, "views": []}`.
  - PUT current creates row.
  - PUT current twice updates row (no duplicate via partial unique index).
  - POST view creates named view.
  - POST view with duplicate name returns 409.
  - PUT named view overwrites.
  - DELETE named view → 204; subsequent GET returns 404.
  - GET surface lists all named views, sorted by `updated_at DESC`.
  - Cross-user isolation: User A's prefs invisible to User B.
  - Cascade: deleting a user removes their preferences.
  - Audit log: POST/PUT named view emits audit row; PUT current does NOT.
  - Surface key max length (64): longer rejected.
  - Name max length (128): longer rejected.
  - Empty name on POST: rejected (min_length=1).

### R1.5 — STOP gate #2

Operator review point. Backend changes shipped. Confirm:
- Backend tests passing (799 + ~30 new = ~830).
- Migrations 0027 and 0028 applied cleanly.
- `alembic current` returns `0028_user_preferences_table`.
- New endpoints visible at `/docs`.

If clean, proceed to R2. If not, fix and re-run.

---
## §R2 — Frontend dependencies + code-splitting (Day 2, ~2 hours)

### R2.1 — Confirm TanStack Table install

Already addressed in R0.3. If `@tanstack/react-table` wasn't present, it was added there. Verify version is `^8.20.0` or higher.

### R2.2 — Code-split the budgets route

**Goal:** the budgets module loads as a separate JS chunk, not in `main.<hash>.js`. This buys back roughly 30–60 kB of headroom against the 437 kB cap.

**Approach:** React.lazy + Suspense on the route entry point.

**File:** `frontend/src/App.jsx` (or wherever routes are defined — verify the actual filename).

Replace direct imports of budget pages with lazy versions:

```jsx
// BEFORE
import BudgetDetail from '@/pages/projects/BudgetDetail';
import BudgetsList from '@/pages/projects/BudgetsList';

// AFTER
import { lazy, Suspense } from 'react';
const BudgetDetail = lazy(() => import('@/pages/projects/BudgetDetail'));
const BudgetsList = lazy(() => import('@/pages/projects/BudgetsList'));
```

Wrap the routes in `<Suspense>` with a small spinner fallback. If a route-level suspense wrapper already exists in the app, reuse it.

**Fallback component:** use existing `<PageSpinner />` or equivalent. If none exists, ship a minimal one in `frontend/src/components/common/PageSpinner.jsx`:

```jsx
export function PageSpinner() {
  return (
    <div className="flex h-64 items-center justify-center text-sm text-slate-500">
      Loading…
    </div>
  );
}
```

**Test verification:**
- `yarn build` succeeds.
- Bundle output now shows a separate chunk for budgets (filename pattern like `BudgetDetail.<hash>.chunk.js`).
- `main.<hash>.js` size drops by at least 10 kB gz vs the 425 kB baseline.
- Existing Jest tests still pass — `lazy()` is invisible to Jest because Suspense resolves synchronously in the test renderer when the import is mocked.

**Test infrastructure caveat:** any Jest test that renders a route containing a lazy-loaded budgets page needs the lazy import resolved. If `BudgetsList` or `BudgetDetail` is referenced in a route-rendering test, mock the lazy import:

```js
jest.mock('@/pages/projects/BudgetDetail', () => ({
  __esModule: true,
  default: () => <div>BudgetDetail mock</div>,
}));
```

If no Jest test currently renders the route shell with budgets pages mounted, no test changes are needed.

**Acceptance:**
- Budget pages lazy-loaded.
- Bundle analysis confirms separate chunk emitted.
- main bundle reduced by ≥10 kB gz.
- All existing Jest tests still pass.

### R2.3 — STOP gate #3

Operator review of R2. Confirm bundle now has budgets as a separate chunk and headroom is restored. Proceed to R3.

---

## §R3 — Grid v2 build (Day 2–4, ~12 hours)

This is the big section. The new grid replaces `BudgetLinesGrid.jsx` completely (Q10a). No legacy fallback.

### R3.1 — Component architecture

New component tree under `frontend/src/components/budgets/`:

```
grid/
  BudgetGridV2.jsx               <- top-level (replaces old BudgetLinesGrid.jsx)
  BudgetGridToolbar.jsx          <- filters, view presets, column visibility
  BudgetGridHeaderTiles.jsx      <- 5 tiles above grid
  BudgetGridTable.jsx            <- TanStack Table render
  BudgetGridRow.jsx              <- single row (line)
  BudgetGridGroupRow.jsx         <- top-level category group row
  BudgetGridSubRow.jsx           <- line_item breakdown row
  BudgetGridDrilldown.jsx        <- transaction sections under a line
  BudgetGridColumns.jsx          <- column definitions (12 columns)
  ColumnVisibilityMenu.jsx       <- toggle menu
  ViewPresetsDropdown.jsx        <- 4 presets + saved views
  SaveViewDialog.jsx             <- modal for naming a view
  ManageViewsDialog.jsx          <- modal for editing/deleting views
  VarianceCell.jsx               <- heat-map cell renderer
  MoneyCell.jsx                  <- standard money cell (right-aligned, formatted)
  NotesCell.jsx                  <- inline-editable Notes cell
  CategoryGroupLabel.jsx         <- "1 Land & Acquisition" header text
  BulkActionsBar.jsx             <- shows when rows are selected
  CsvExportButton.jsx            <- on-screen CSV export
  BulkDeleteConfirmDialog.jsx
  PerLineTransactionDrilldown/
    BillsSection.jsx             <- LIVE
    POsSectionStub.jsx           <- empty state
    VariationsSectionStub.jsx    <- empty state
    LineItemsBreakdown.jsx       <- the 4 default items editor
```

This is a lot of files but each is small (~50–200 LOC). The split is for testability and reviewability — each piece has a clear single responsibility.

**Mobile gating:** the mobile read-only treatment (Q8) is a parallel component, `BudgetGridMobileReadOnly.jsx`. The top-level component picks between desktop and mobile based on `useIsDesktop()`.

```jsx
// BudgetGridV2.jsx (top-level)
export function BudgetGridV2({ budget, projectId }) {
  const isDesktop = useIsDesktop();
  if (!isDesktop) {
    return <BudgetGridMobileReadOnly budget={budget} projectId={projectId} />;
  }
  return <BudgetGridV2Desktop budget={budget} projectId={projectId} />;
}
```

**Two concerns carried over from v1 that need explicit handling:**

1. **Line drag-reorder.** v1 uses `@dnd-kit` + `useReorderBudgetLines` to let users drag a line and update its `display_order`. v2 keeps this — drag-reorder remains enabled **only when no sort is applied** (sorting=`[]`). When a sort is active, drag handles are hidden because reordering manually is meaningless under a sort. Implementation: pass `dragDisabled = sorting.length > 0 || !editable || !canEdit || reorderMut.isPending` to the line rows. The `useReorderBudgetLines` hook is reused unchanged from v1.

2. **LineDrawer vs. BudgetGridDrilldown — distinct things.** v1 has `LineDrawer` (right-side panel) for editing line money fields, % complete, FTC method, etc. v2 KEEPS `LineDrawer` for all of those edits — it's not removed. v2 ADDS `BudgetGridDrilldown` (expansion row content under each line) for showing breakdowns and read-only transactions (POs stub, Variations stub, Bills live). When the user clicks the `⋯` action button → drawer opens for editing. When they click the chevron → row expands inline with the drilldown. The two are independent UIs serving different jobs.

**Inline-edit regression (Q7 decision, called out explicitly):** v1 supports inline edit on description and money fields. v2 supports inline edit ONLY on Notes. All other field edits route through `LineDrawer`. This is a deliberate UX simplification — Q7 in the handoff locks it. Existing tests that assert inline edit on description/money will need to be deleted or rewritten to test the drawer path instead. Catalogue these during R5 / R9.2 work:

```bash
cd frontend && grep -rln "inlineEditEnabled\|onInlineEdit\|EditableMoneyCell" src/
```

Any test that exercises inline-edit-via-grid for non-Notes fields → delete and replace with a drawer test (or trust the existing drawer tests to cover it).

### R3.2 — TanStack Table column definitions

**File:** `frontend/src/components/budgets/grid/BudgetGridColumns.jsx`

12 columns total, 6 visible by default (per Q1).

```jsx
import { createColumnHelper } from '@tanstack/react-table';
import { MoneyCell } from './MoneyCell';
import { VarianceCell } from './VarianceCell';
import { NotesCell } from './NotesCell';

const ch = createColumnHelper();

export function makeColumns({
  costCodeMap,
  canEdit,
  canViewSensitive,
  onOpenDrawer,
  onUpdateNotes,
}) {
  return [
    ch.display({
      id: 'select',
      header: ({ table }) => (
        <input
          type="checkbox"
          checked={table.getIsAllRowsSelected()}
          onChange={table.getToggleAllRowsSelectedHandler()}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) =>
        row.depth === 0 ? null : (   // groups not selectable
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            aria-label={`Select line ${row.original.cost_code_id ?? ''}`}
          />
        ),
      enableHiding: false,
      size: 32,
    }),
    ch.display({
      id: 'expand',
      header: '',
      cell: ({ row }) => row.getCanExpand() && (
        <button
          onClick={row.getToggleExpandedHandler()}
          aria-label={row.getIsExpanded() ? 'Collapse' : 'Expand'}
          className="text-slate-500 hover:text-slate-700"
        >
          {row.getIsExpanded() ? '▾' : '▸'}
        </button>
      ),
      enableHiding: false,
      size: 24,
    }),
    ch.accessor((row) => row.cost_code_id, {
      id: 'cost_code',
      header: 'Cost code',
      cell: ({ getValue }) => costCodeMap.get(getValue())?.code ?? '—',
      size: 110,
    }),
    ch.accessor('line_description', {
      header: 'Description',
      cell: (info) => info.getValue() ?? '—',
      size: 240,
    }),

    // Default-hidden:
    ch.accessor('original_budget', {
      header: 'Original budget',
      cell: (info) => <MoneyCell value={info.getValue()} />,
      // hidden by default — see initialVisibility
    }),

    // Default-visible:
    ch.accessor('current_budget', {
      header: 'Current budget',
      cell: (info) => <MoneyCell value={info.getValue()} />,
    }),

    // Default-hidden:
    ch.accessor('approved_changes', {
      id: 'pending_changes',
      header: 'Pending changes',
      cell: (info) => <MoneyCell value={info.getValue()} />,
    }),

    // Default-visible:
    ch.accessor('committed_value', {
      id: 'committed',
      header: 'Committed',
      cell: (info) => <MoneyCell value={info.getValue()} />,
    }),
    ch.accessor('actuals_to_date', {
      id: 'actual_spent',
      header: 'Actual spent',
      cell: (info) => <MoneyCell value={info.getValue()} />,
    }),
    ch.accessor('variance_value', {
      id: 'variance_to_budget',
      header: 'Variance to budget',
      cell: (info) => (
        <VarianceCell
          value={info.getValue()}
          status={info.row.original.variance_status}
          pct={info.row.original.variance_pct}
        />
      ),
    }),
    ch.accessor('forecast_final_cost', {
      id: 'forecast_cost',
      header: 'Forecast cost',
      cell: (info) => (
        <MoneyCell
          value={info.getValue()}
          tintByStatus={info.row.original.variance_status}
        />
      ),
    }),
    ch.accessor('forecast_to_complete', {
      id: 'cost_to_complete',
      header: 'Cost to complete',
      cell: (info) => <MoneyCell value={info.getValue()} />,
    }),

    // Default-hidden, computed:
    ch.display({
      id: 'variance_to_forecast',
      header: 'Variance to forecast',
      cell: ({ row }) => {
        const ffc = Number(row.original.forecast_final_cost ?? 0);
        const orig = Number(row.original.original_budget ?? 0);
        const variance = ffc - orig;
        return (
          <VarianceCell
            value={variance}
            status={row.original.variance_status}
            pct={orig > 0 ? (variance / orig) * 100 : 0}
          />
        );
      },
    }),

    // Sensitive-field gated, computed.
    // ⚠️ DATA SOURCE STOP: `budget_lines` has no `allocated_sale_price` column today.
    // Per handoff Q1b, Forecast profit = sale_price/N − FFC (N = line count). We pull
    // project-level `sale_price` from the source appraisal (Budget → source_appraisal_id
    // → Appraisal.revenue/sale_price) and divide it equally across lines as the
    // provisional allocation. The UI receives `_allocated_sale_price_provisional` per
    // line from the backend serializer (see R3.9b).
    //
    // If the operator wants a real per-line allocation (weighted by current_budget, or
    // user-set via a separate UI), that's a follow-up build pack — out of scope here.
    ...(canViewSensitive ? [
      ch.display({
        id: 'forecast_profit',
        header: 'Forecast profit',
        cell: ({ row }) => {
          const sale = Number(row.original._allocated_sale_price_provisional ?? 0);
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          return <MoneyCell value={sale - ffc} />;
        },
      }),
      ch.display({
        id: 'forecast_margin_pct',
        header: 'Forecast margin %',
        cell: ({ row }) => {
          const sale = Number(row.original._allocated_sale_price_provisional ?? 0);
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          if (sale <= 0) return '—';
          const margin = ((sale - ffc) / sale) * 100;
          return `${margin.toFixed(1)}%`;
        },
      }),
    ] : []),

    ch.accessor('ftc_method', {
      id: 'projection_reference',
      header: 'Projection reference',
      cell: (info) => info.getValue() ?? '—',
    }),

    ch.accessor('notes', {
      header: 'Notes',
      cell: (info) => (
        <NotesCell
          value={info.getValue()}
          canEdit={canEdit}
          onSave={(v) => onUpdateNotes(info.row.original.id, v)}
        />
      ),
    }),

    ch.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <button
          onClick={() => onOpenDrawer(row.original.id)}
          aria-label="Open line details"
          className="text-slate-400 hover:text-slate-600"
        >
          ⋯
        </button>
      ),
      enableHiding: false,
      size: 32,
    }),
  ];
}

export const INITIAL_COLUMN_VISIBILITY = {
  // Default-visible (6 money columns + cost code + description + select/expand/notes/actions are always-on):
  cost_code: true,
  line_description: true,
  current_budget: true,
  committed: true,
  actual_spent: true,
  variance_to_budget: true,
  forecast_cost: true,
  cost_to_complete: true,
  notes: true,
  select: true,
  expand: true,
  actions: true,

  // Default-hidden:
  original_budget: false,
  pending_changes: false,
  variance_to_forecast: false,
  forecast_profit: false,
  forecast_margin_pct: false,
  projection_reference: false,
};
```

**Notes:**
- Display order in the array is the default column order. Reordering is persisted via user_preferences and applied via TanStack Table's `columnOrder` state.
- `forecast_profit` and `forecast_margin_pct` are conditionally created — if the user lacks `budgets.view_sensitive`, they don't exist as columns at all. This is safer than relying on hiding for security.
- `allocated_sale_price` is needed on each row to compute profit/margin. Verify the budget API serializer includes this field. If not, R3.9 adds it.

### R3.3 — View presets

**File:** `frontend/src/components/budgets/grid/ViewPresetsDropdown.jsx`

4 starter presets:

```jsx
export const VIEW_PRESETS = {
  Quick: {
    visibility: {
      cost_code: true, line_description: true,
      current_budget: true, actual_spent: true,
      variance_to_budget: true, notes: true,
      select: true, expand: true, actions: true,
    },
    columnOrder: [
      'select', 'expand', 'cost_code', 'line_description',
      'current_budget', 'actual_spent', 'variance_to_budget',
      'notes', 'actions',
    ],
    sorting: [],
    filters: {},
  },
  Standard: {
    visibility: INITIAL_COLUMN_VISIBILITY,
    columnOrder: null,  // default
    sorting: [],
    filters: {},
  },
  Full: {
    visibility: Object.fromEntries(
      Object.keys(INITIAL_COLUMN_VISIBILITY).map(k => [k, true]),
    ),
    columnOrder: null,
    sorting: [],
    filters: {},
  },
  Profit: {
    visibility: {
      cost_code: true, line_description: true,
      current_budget: true, actual_spent: true,
      forecast_cost: true, forecast_profit: true,
      forecast_margin_pct: true, notes: true,
      select: true, expand: true, actions: true,
    },
    columnOrder: [
      'select', 'expand', 'cost_code', 'line_description',
      'current_budget', 'actual_spent', 'forecast_cost',
      'forecast_profit', 'forecast_margin_pct', 'notes', 'actions',
    ],
    sorting: [],
    filters: {},
  },
};
```

**UI:** dropdown button in toolbar. Top section lists the 4 starter presets. Middle section lists saved views (from API). Bottom section: "Save current view…" + "Manage views…".

**On preset click:** apply visibility + columnOrder + sorting + filters from the preset, then call PUT `/preferences/budgets.grid.v2` to persist as current state. The user can then drift away from the preset; the preset itself is unchanged.

**Profit preset gating:** if the user lacks `budgets.view_sensitive`, the Profit preset is hidden from the dropdown (the columns don't exist for them anyway, so clicking it would no-op suspiciously).

### R3.4 — Variance heat-map

**File:** `frontend/src/components/budgets/grid/VarianceCell.jsx`

```jsx
import { formatMoney } from '@/lib/format';

const STATUS_CLASSES = {
  Green: 'bg-emerald-50 text-emerald-800',
  Amber: 'bg-amber-50 text-amber-800',
  Red: 'bg-rose-50 text-rose-800',
};

export function VarianceCell({ value, status, pct }) {
  const klass = STATUS_CLASSES[status] ?? 'bg-slate-50 text-slate-700';
  return (
    <span
      className={`inline-flex items-baseline gap-2 rounded px-2 py-1 ${klass}`}
      data-variance-status={status}
      data-testid="variance-cell"
    >
      <span className="font-medium tabular-nums">{formatMoney(value)}</span>
      {pct != null && (
        <span className="text-xs text-current/70 tabular-nums">
          ({Number(pct).toFixed(1)}%)
        </span>
      )}
    </span>
  );
}
```

**Forecast cost lighter tint:** `MoneyCell` accepts a `tintByStatus` prop. When set, applies a 50%-opacity version of the status class:

```jsx
const TINT_CLASSES = {
  Green: 'bg-emerald-50/40',
  Amber: 'bg-amber-50/40',
  Red: 'bg-rose-50/40',
};
```

**Brand-token note:** the variance heat-map uses Tailwind's emerald/amber/rose families, NOT `sy-teal`/`sy-orange`. These are semantic status colours, not brand colours — keep them distinct. Brand tokens stay reserved for CTAs and destructive actions per Chat 17 convention.

### R3.5 — Row hierarchy: categories → lines → items

TanStack Table's expanding rows feature is used for the line → items level (Q3 sub-rows). The category-level grouping is done manually in the data shape, not via TanStack's grouping feature, because:

1. Categories are derived from the cost-code prefix (not a real data column).
2. Categories don't need their own sortable money columns aggregated client-side — the backend will eventually emit category totals (see "Future_Tasks" note below).
3. TanStack grouping with aggregation can be heavy; doing the bucket-by-category manually is lighter and gives full control over the visual treatment.

**Data shape passed to the table:**

```js
// Input: flat lines from API
// Output: tree of group rows + line rows + item rows

[
  {
    isGroup: true,
    groupKey: 'land_acquisition',
    groupLabel: '1 Land & Acquisition',
    totals: { current_budget: 1234567, actual_spent: 999999, ... },
    subRows: [
      {
        ...line,
        subRows: [
          { ...item, isItem: true },
          { ...item, isItem: true },
          { ...item, isItem: true },
          { ...item, isItem: true },
        ],
      },
      ...
    ],
  },
  ...
]
```

The category mapping function:

```js
// frontend/src/lib/budgetCategoryGroup.js
const CATEGORY_BY_PREFIX = {
  ACQ: { key: 'land_acquisition', label: '1 Land & Acquisition' },
  PLN: { key: 'planning',         label: '2 Planning' },
  PRO: { key: 'professional',     label: '3 Professional Fees' },
  CON: { key: 'construction',     label: '4 Construction' },
  INT: { key: 'internal',         label: '4 Internal Finishes' },
  EXT: { key: 'externals',        label: '5 Externals' },
  FIN: { key: 'finance',          label: '6 Finance & Holding' },
  SAL: { key: 'sales',            label: '7 Sales & Marketing' },
  CTG: { key: 'contingency',      label: '8 Contingency' },
};

export function groupLinesByCategory(lines, costCodeMap) {
  const buckets = new Map();
  for (const line of lines) {
    const code = costCodeMap.get(line.cost_code_id)?.code ?? '';
    const prefix = code.split('-')[0].toUpperCase();
    const cat = CATEGORY_BY_PREFIX[prefix]
      ?? { key: `other_${prefix}`, label: prefix || '— Uncategorised —' };
    if (!buckets.has(cat.key)) {
      buckets.set(cat.key, { ...cat, lines: [] });
    }
    buckets.get(cat.key).lines.push(line);
  }
  return Array.from(buckets.values()).map(bucket => ({
    isGroup: true,
    groupKey: bucket.key,
    groupLabel: bucket.label,
    totals: computeTotals(bucket.lines),
    subRows: bucket.lines.map(line => ({
      ...line,
      subRows: (line.items ?? []).map(it => ({ ...it, isItem: true })),
    })),
  }));
}

function computeTotals(lines) {
  const sum = (key) => lines.reduce((acc, l) => acc + Number(l[key] ?? 0), 0);
  return {
    original_budget: sum('original_budget'),
    current_budget: sum('current_budget'),
    actuals_to_date: sum('actuals_to_date'),
    committed_value: sum('committed_value'),
    forecast_final_cost: sum('forecast_final_cost'),
    forecast_to_complete: sum('forecast_to_complete'),
    variance_value: sum('variance_value'),
  };
}
```

**Future_Tasks entry (add to repo):** `groupLinesByCategory` does client-side aggregation across lines. Once we hit 200+ lines per budget, this becomes a perf concern. Note for future: shift to a backend `GET /budgets/:id/category-summary` endpoint that returns pre-aggregated totals. Out of scope for Build Pack A.

### R3.6 — Default expansion state (Q3b)

On first load: categories expanded, line→items collapsed.

```jsx
const [expanded, setExpanded] = useState(() => {
  // All group rows expanded by default.
  const groupRows = data.filter(r => r.isGroup);
  return Object.fromEntries(groupRows.map(g => [g.groupKey, true]));
});
```

User's expansion state persists via user_preferences (`expanded` key in payload).

### R3.7 — Toolbar with 5 filters (Q5)

**File:** `frontend/src/components/budgets/grid/BudgetGridToolbar.jsx`

Components left-to-right:
1. Full-text search input (debounced 200ms)
2. Cost-code category multi-select dropdown
3. Variance band chips (All / Green / Amber / Red)
4. "Show only with actuals" checkbox/chip
5. "Show only with variance" checkbox/chip
6. View presets dropdown (rightmost)
7. Column visibility menu (rightmost)

Filter state is local React state, persisted via user_preferences `filters` key. On filter change → autosave to current preferences.

**Filter logic — applied client-side in a `useMemo`:**

```js
const filteredLines = useMemo(() => {
  return rawLines.filter(line => {
    if (filters.search) {
      const haystack = `${costCodeMap.get(line.cost_code_id)?.code ?? ''} ${line.line_description ?? ''}`.toLowerCase();
      if (!haystack.includes(filters.search.toLowerCase())) return false;
    }
    if (filters.categories?.length) {
      const code = costCodeMap.get(line.cost_code_id)?.code ?? '';
      const prefix = code.split('-')[0].toUpperCase();
      if (!filters.categories.includes(prefix)) return false;
    }
    if (filters.varianceBand && filters.varianceBand !== 'All') {
      if (line.variance_status !== filters.varianceBand) return false;
    }
    if (filters.onlyWithActuals && !(line.actuals_to_date > 0)) return false;
    if (filters.onlyWithVariance && Number(line.variance_value ?? 0) === 0) return false;
    return true;
  });
}, [rawLines, filters, costCodeMap]);
```

Filtered lines then pass through `groupLinesByCategory`. Empty groups are dropped automatically (no lines in bucket → bucket is never created).

### R3.8 — Sticky columns + reorder + sort (Q6 / Q6c)

**Sticky columns:** TanStack Table supports `column.pinning` natively. Each column header gets a menu (right-click or via a chevron icon) with "Pin to left" / "Pin to right" / "Unpin".

The grid container uses CSS sticky for pinned columns:

```css
.pinned-left {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--column-bg, white);
  box-shadow: 2px 0 4px -2px rgb(0 0 0 / 0.1);
}
.pinned-right {
  position: sticky;
  right: 0;
  z-index: 2;
  background: var(--column-bg, white);
  box-shadow: -2px 0 4px -2px rgb(0 0 0 / 0.1);
}
```

**Column reorder:** TanStack supports `columnOrder` state. Pair it with `@dnd-kit` for the drag handle on column headers. Reuse the existing dnd-kit setup from the previous grid — the import already exists.

**Sort:** TanStack's built-in `sorting` state. Three-state click cycle (asc → desc → none) is the default.

**Q6c (sort at both levels):** when sorting is applied to lines, the categories themselves are sorted by the same column's group total (computed in `groupLinesByCategory`).

**Important — column id vs. backend field name:** TanStack Table column ids (like `actual_spent`, `committed`, `variance_to_budget`) are UI-friendly aliases. The `totals` object and the raw line objects use backend field names (`actuals_to_date`, `committed_value`, `variance_value`). A `SORT_KEY_MAP` translates between them; the sort logic MUST go through this map or it will silently sort by undefined and produce unstable order.

**Mapping the column id to the totals/field key:**

```js
const SORT_KEY_MAP = {
  current_budget: 'current_budget',
  actual_spent: 'actuals_to_date',
  committed: 'committed_value',
  variance_to_budget: 'variance_value',
  forecast_cost: 'forecast_final_cost',
  cost_to_complete: 'forecast_to_complete',
  original_budget: 'original_budget',
  pending_changes: 'approved_changes',
  // computed columns — skip group-level sort (they only sort within groups
  // because computing the aggregate would require re-walking lines):
  variance_to_forecast: null,
  forecast_profit: null,
  forecast_margin_pct: null,
};
```

If `SORT_KEY_MAP[id]` is `null`, the group order stays default; only line-within-group sort applies, and that uses a computed-on-the-fly value.

**Implementation:**

```js
// In BudgetGridV2Desktop, after groupLinesByCategory:
const sortedGrouped = useMemo(() => {
  if (!sorting.length) return grouped;
  const { id, desc } = sorting[0];
  const backendKey = SORT_KEY_MAP[id];

  // Helper for line-level sort. For computed columns where the mapping is
  // null (variance_to_forecast / forecast_profit / forecast_margin_pct),
  // compute the value inline; otherwise use the mapped backend field.
  function lineValue(line) {
    if (id === 'variance_to_forecast') {
      return Number(line.forecast_final_cost ?? 0) - Number(line.original_budget ?? 0);
    }
    if (id === 'forecast_profit') {
      return Number(line._allocated_sale_price_provisional ?? 0)
        - Number(line.forecast_final_cost ?? 0);
    }
    if (id === 'forecast_margin_pct') {
      const sale = Number(line._allocated_sale_price_provisional ?? 0);
      if (sale <= 0) return -Infinity;
      return (sale - Number(line.forecast_final_cost ?? 0)) / sale;
    }
    return Number(line[backendKey] ?? 0);
  }

  // Group-level sort: only if backendKey exists in totals.
  const groupsSorted = backendKey == null
    ? [...grouped]   // computed columns — don't reorder groups
    : [...grouped].sort((a, b) => {
        const av = a.totals[backendKey] ?? 0;
        const bv = b.totals[backendKey] ?? 0;
        return desc ? bv - av : av - bv;
      });

  // Line-within-group sort (always applies).
  return groupsSorted.map(g => ({
    ...g,
    subRows: [...g.subRows].sort((a, b) => {
      const av = lineValue(a);
      const bv = lineValue(b);
      return desc ? bv - av : av - bv;
    }),
  }));
}, [grouped, sorting]);
```

If a column id has no entry in `SORT_KEY_MAP` (e.g. a column added later that the developer forgot to add to the map), the sort silently treats the line value as 0 — keeping order stable but doing nothing useful. Add a dev-mode `console.warn` when `id` is missing from the map to catch this during development:

```js
if (process.env.NODE_ENV !== 'production' && !(id in SORT_KEY_MAP)) {
  console.warn(`[BudgetGridV2] No SORT_KEY_MAP entry for column "${id}". Sort will no-op.`);
}
```

### R3.9 — Sensitive-field gating

The Profit and Margin columns rely on `allocated_sale_price` per line. Two cases:

1. **User has `budgets.view_sensitive`:** the backend includes `allocated_sale_price` in the budget_lines serializer. The two computed columns are added to the column array.
2. **User lacks `budgets.view_sensitive`:** the backend OMITS `allocated_sale_price` from the response (existing behaviour from Chat 17). The two computed columns are not added to the column array. The Profit preset is hidden from the dropdown.

**Server-side check:** verify `routers/budgets.py` GET endpoints strip `allocated_sale_price` when the user lacks the permission. If they don't, this Build Pack adds that — but it should already exist from Chat 17 R7 work. Look for a `SENSITIVE_FIELDS` constant or similar.

**CSV export of sensitive fields:** see R7. Server-side enforcement: if the user lacks `budgets.view_sensitive`, the CSV they generate cannot include Profit/Margin columns even if some weird client-side bug tried to.

### R3.9b — Provisional sale-price allocation (backend serializer change)

**Why this exists:** the Forecast profit and Forecast margin % columns need a per-line sale price. The schema doesn't have one. Per design Q1b the formula is `sale_price / N − FFC`. The cleanest minimal-impact implementation: compute the per-line allocation server-side in the serializer and emit it as `_allocated_sale_price_provisional` (underscored to signal "computed, not stored").

**File:** `backend/app/schemas/budgets.py` (find the existing `BudgetLineOut` schema or equivalent).

**Logic — added to the serializer or service-layer response builder:**

```python
def _attach_provisional_allocation(budget: Budget, can_view_sensitive: bool) -> None:
    """Stamp each line with _allocated_sale_price_provisional if the user
    is allowed to see sensitive fields. Otherwise leave the attribute off.

    Allocation: project source_appraisal.sale_price / line_count. Equal split.
    Returns nothing — mutates the line objects in place for serialization.
    """
    if not can_view_sensitive:
        return
    appraisal = budget.source_appraisal  # already loaded via existing relationship
    if appraisal is None:
        return
    sale = getattr(appraisal, "sale_price", None) \
        or getattr(appraisal, "revenue", None) \
        or 0
    sale = Decimal(sale or 0)
    n = len(budget.lines)
    if n == 0 or sale <= 0:
        return
    per_line = (sale / Decimal(n)).quantize(Decimal("0.01"))
    for line in budget.lines:
        line._allocated_sale_price_provisional = per_line
```

**Wire-in:** call this from the `get_budget` route handler in `routers/budgets.py` after `_load_budget_for_read` returns the budget and BEFORE the response is serialized. The exact attribute name (`sale_price` vs `revenue`) needs verification against the Appraisal model — search for it during R3.9b. If neither exists, the value defaults to 0 and the columns show `—`.

**Schema field:** in `BudgetLineOut`, add an optional field `_allocated_sale_price_provisional: Decimal | None = None`. The leading underscore is a deliberate signal that this is a computed field, not a column. Document this in the schema docstring.

**Sensitive-field gating:** because this is only attached when `can_view_sensitive=True`, users without the permission never see the field. The frontend respects this — if the field is absent, the Profit and Margin columns aren't created (R3.2 ternary).

**Acceptance:**
- New helper `_attach_provisional_allocation` exists.
- GET `/api/v1/budgets/{id}` returns `_allocated_sale_price_provisional` per line for users with `budgets.view_sensitive`; omits it for users without.
- Greenfield test: budget with no source_appraisal → field omitted.
- Source appraisal with `sale_price=0` → field omitted.
- Test users with/without `budgets.view_sensitive` get different shapes.

**STOP gate #3b (optional operator review):** if the operator wants a real per-line allocation (weighted by current_budget, or user-set), surface this before continuing past R3.9b. The provisional sale_price/N implementation is acceptable for v1 of the grid but not ideal long-term. Add a Future_Tasks entry: "Per-line sale-price allocation — replace `sale_price/N` provisional with a real allocation model (e.g. weighted by current_budget %, or user-set per line)."

### R3.10 — Header tiles (Q9)

5 tiles above the grid:

| Tile | Computed from |
|---|---|
| Original budget total | `sum(line.original_budget)` |
| Current budget total | `sum(line.current_budget)` |
| Actual spent total | `sum(line.actuals_to_date)` |
| Forecast cost total | `sum(line.forecast_final_cost)` |
| Cost to complete total | `sum(line.forecast_to_complete)` |

Reuse the existing `<StatTile>` component from Chat 17 if present; otherwise create a small one.

**Plus the existing chips from Chat 17:** variance status badge (whole-budget-level) and sensitive-fields warning if the user lacks `budgets.view_sensitive`.

### R3.11 — STOP gate #4

Operator review point. Confirm:
- Grid renders with 6 default columns visible.
- Category groups expand/collapse.
- Line sub-rows (4-type breakdown) expand/collapse.
- Filters work.
- Sort works at both levels.
- Heat-map colours correct.
- 5 header tiles render with correct totals.

If anything looks off, surface to operator before proceeding to R4.

---
## §R4 — Per-line transaction drilldown (Day 4, ~3 hours)

When a user clicks the chevron on a budget line, a sub-section opens BELOW the line row (still inside the table, expanded row content). It contains two stacked sections:

1. **4-type breakdown** (line items)
2. **Transactions** with three sub-sections (POs stubbed, Variations stubbed, Bills live)

### R4.1 — 4-type breakdown editor

**File:** `frontend/src/components/budgets/grid/PerLineTransactionDrilldown/LineItemsBreakdown.jsx`

Renders the 4 (or more, after edits) `budget_line_items` for the line. Each item shows description, quantity, unit, rate, amount, notes.

**Editable on desktop when `canEdit`:**
- Click any item field → inline edit (description, amount, notes).
- "+ Add item" button at the bottom.
- "Delete" button per item (with confirmation if amount > 0 or notes present).

**Read-only on mobile** (Q8) and when the budget is Locked/Closed/Superseded.

Reuse the existing item-CRUD hooks from `frontend/src/hooks/budgets.js` (Chat 17 wired these up for the LineItemsPanel — confirm and reuse).

**Auto-create caveat:** new lines now get 4 items via R1.2. Older lines have items via the R1.3 backfill. So every line in the system has at least 4 items. The "Add item" path is for users who need a 5th or beyond.

### R4.2 — POs section stub

**File:** `PerLineTransactionDrilldown/POsSectionStub.jsx`

```jsx
export function POsSectionStub() {
  return (
    <div className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500">
      No POs raised yet — Purchase Orders ship in Prompt 2.5.
    </div>
  );
}
```

Hardcoded empty state. When 2.5 ships, this file gets replaced with a real PO list component.

### R4.3 — Variations section stub

**File:** `PerLineTransactionDrilldown/VariationsSectionStub.jsx`

Same pattern as POs. Empty state text: "No Variations issued yet — Variations ship in Prompt 2.6."

### R4.4 — Bills section (LIVE)

**File:** `PerLineTransactionDrilldown/BillsSection.jsx`

This is the live one. Queries the existing `actuals` records linked to this `budget_line_id`.

**Hook:** new file `frontend/src/hooks/actuals.js` (if not already present from Chat 19B):

```js
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function useActualsForBudgetLine(budgetLineId, projectId) {
  return useQuery({
    queryKey: ['actuals', 'by-budget-line', budgetLineId],
    queryFn: () => api.get('/api/v1/actuals', {
      params: { budget_line_id: budgetLineId, project_id: projectId, limit: 50 },
    }).then(r => r.data.items ?? r.data),
    enabled: !!budgetLineId,
    staleTime: 30_000,
  });
}
```

Confirm the endpoint signature matches `routers/actuals.py`. If the query parameter is named differently (e.g. `line_id` vs `budget_line_id`), adjust accordingly. The handoff confirms the FK exists; the query string just needs to match the route.

**Component:**

```jsx
export function BillsSection({ budgetLineId, projectId }) {
  const { data: bills, isLoading, isError } = useActualsForBudgetLine(budgetLineId, projectId);

  if (isLoading) return <div className="p-3 text-sm text-slate-500">Loading bills…</div>;
  if (isError) return <div className="p-3 text-sm text-rose-600">Failed to load bills.</div>;
  if (!bills?.length) {
    return (
      <div className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500">
        No bills posted to this line yet.
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="text-xs uppercase tracking-wide text-slate-500">
        <tr>
          <th className="text-left">Reference</th>
          <th className="text-left">Supplier</th>
          <th className="text-right">Amount</th>
          <th className="text-left">Status</th>
          <th className="text-left">Date</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {bills.map(bill => (
          <tr key={bill.id} className="border-t border-slate-100">
            <td className="py-2">{bill.reference ?? '—'}</td>
            <td>{bill.supplier_name ?? '—'}</td>
            <td className="text-right tabular-nums">{formatMoney(bill.amount)}</td>
            <td><BillStatusBadge status={bill.status} /></td>
            <td>{formatDate(bill.posted_at ?? bill.created_at)}</td>
            <td>
              <Link
                to={`/projects/${projectId}/actuals/${bill.id}`}
                className="text-sky-700 hover:underline"
              >
                Open
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

**Bill status badge:** new small component. Statuses (per Chat 19A): Draft / Posted / Paid / Disputed / Void. Map to colour classes.

**Status colour map:**
- Draft → slate
- Posted → sky
- Paid → emerald
- Disputed → rose
- Void → zinc (muted)

### R4.5 — Drilldown wrapper

**File:** `BudgetGridDrilldown.jsx`

```jsx
export function BudgetGridDrilldown({ row, budget, projectId }) {
  const line = row.original;
  return (
    <div className="bg-slate-50 px-6 py-4 space-y-4">
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
          Breakdown (4-type)
        </h4>
        <LineItemsBreakdown
          line={line}
          budget={budget}
          projectId={projectId}
        />
      </section>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
          Transactions
        </h4>
        <div className="grid gap-3">
          <div>
            <h5 className="text-xs text-slate-600 mb-1">Purchase Orders</h5>
            <POsSectionStub />
          </div>
          <div>
            <h5 className="text-xs text-slate-600 mb-1">Variations</h5>
            <VariationsSectionStub />
          </div>
          <div>
            <h5 className="text-xs text-slate-600 mb-1">Bills</h5>
            <BillsSection budgetLineId={line.id} projectId={projectId} />
          </div>
        </div>
      </section>
    </div>
  );
}
```

TanStack Table renders this via `getRowCanExpand` + `renderSubComponent` on expanded rows.

### R4.6 — STOP gate #5

Operator review of R4. Confirm drilldown renders correctly, bills query works against a project that has posted actuals.

---

## §R5 — Inline-edit (Notes only) (Day 4, ~1 hour)

### R5.1 — NotesCell

**File:** `frontend/src/components/budgets/grid/NotesCell.jsx`

```jsx
import { useState, useEffect, useRef } from 'react';
import { useUpdateBudgetLine } from '@/hooks/budgets';

export function NotesCell({ value, canEdit, lineId, budgetId, projectId }) {
  const [editing, setEditing] = useState(false);
  const [local, setLocal] = useState(value ?? '');
  const inputRef = useRef();
  const mutation = useUpdateBudgetLine(budgetId, projectId);

  useEffect(() => { setLocal(value ?? ''); }, [value]);

  function commit() {
    if (local === (value ?? '')) {
      setEditing(false);
      return;
    }
    mutation.mutate(
      { lineId, patch: { notes: local } },
      {
        onSuccess: () => setEditing(false),
        onError: () => {
          setLocal(value ?? '');
          setEditing(false);
        },
      },
    );
  }

  if (!canEdit) {
    return <span className="text-sm text-slate-700">{value || <em className="text-slate-400">—</em>}</span>;
  }

  if (!editing) {
    return (
      <button
        className="w-full text-left text-sm text-slate-700 hover:bg-slate-50 rounded px-1"
        onClick={() => setEditing(true)}
      >
        {value || <em className="text-slate-400">Click to add notes…</em>}
      </button>
    );
  }

  return (
    <input
      ref={inputRef}
      autoFocus
      type="text"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit();
        if (e.key === 'Escape') {
          setLocal(value ?? '');
          setEditing(false);
        }
      }}
      className="w-full rounded border border-slate-300 px-1 text-sm focus:outline-none focus:ring-1 focus:ring-sy-teal"
      maxLength={500}
    />
  );
}
```

Optimistic update via TanStack Query's `useMutation` `onMutate` (existing pattern in `hooks/budgets.js`).

**Audit log:** every Notes update goes through PATCH `/budget-lines/{id}` which already emits audit_log. No new audit code needed.

**Mobile:** NotesCell receives `canEdit=false` on mobile (via the desktop-only gating in BudgetGridV2 top-level). Notes display as read-only text. Per Q8 follow-up the operator wants Notes editable on mobile too — implement that in the mobile read-only component (R8.2), not here.

---

## §R6 — Saved Views (Day 4–5, ~2 hours)

### R6.1 — State sync to user_preferences

The grid maintains state for: column visibility, column order, sorting, filters, expanded groups, pinned columns. All of this is one JSON blob persisted to `/api/v1/me/preferences/budgets.grid.v2` (current row, `name=null`).

**Hook:** `frontend/src/hooks/userPreferences.js`

```js
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function usePreferences(surfaceKey) {
  return useQuery({
    queryKey: ['preferences', surfaceKey],
    queryFn: () => api.get(`/api/v1/me/preferences/${surfaceKey}`).then(r => r.data),
    staleTime: 60_000,
  });
}

export function useSetCurrentPreference(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.put(`/api/v1/me/preferences/${surfaceKey}`, { payload }),
    // Optimistic — don't wait for response, don't invalidate (the local state is the source of truth in the UI).
    onSuccess: (_data, variables) => {
      // Update the cache silently with the payload we just sent.
      qc.setQueryData(['preferences', surfaceKey], (old) => ({
        ...(old ?? {}),
        current: { payload: variables },
      }));
    },
  });
}

export function useSaveView(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, payload }) =>
      api.post(`/api/v1/me/preferences/${surfaceKey}/views`, { name, payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['preferences', surfaceKey] }),
  });
}

export function useUpdateView(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, payload }) =>
      api.put(`/api/v1/me/preferences/${surfaceKey}/views/${encodeURIComponent(name)}`, { payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['preferences', surfaceKey] }),
  });
}

export function useDeleteView(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name) =>
      api.delete(`/api/v1/me/preferences/${surfaceKey}/views/${encodeURIComponent(name)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['preferences', surfaceKey] }),
  });
}
```

### R6.2 — Autosave debouncing

State changes (column reorder, sort change, filter change, etc.) fire frequently. Debounce the autosave PUT by 500ms so a flurry of changes results in one network call.

```js
// In BudgetGridV2Desktop:
const setCurrentMutation = useSetCurrentPreference('budgets.grid.v2');
const debouncedSave = useDebounce(setCurrentMutation.mutate, 500);

useEffect(() => {
  const snapshot = { visibility, columnOrder, sorting, filters, expanded, columnPinning };
  debouncedSave(snapshot);
}, [visibility, columnOrder, sorting, filters, expanded, columnPinning, debouncedSave]);
```

Use existing `useDebounce` hook if present; if not, add a small one in `lib/useDebounce.js` (10 LOC).

### R6.3 — SaveViewDialog

Modal triggered by "Save current view…" in the presets dropdown. Asks for a name (1-128 chars, no duplicates within this user/surface). On submit, calls `useSaveView` with the current snapshot.

### R6.4 — ManageViewsDialog

Modal triggered by "Manage views…". Shows a list of the user's named views with rename and delete actions per row. Rename = useUpdateView. Delete = useDeleteView with confirmation.

### R6.5 — Initial state hydration

On mount, BudgetGridV2Desktop reads `usePreferences('budgets.grid.v2')`. If `current.payload` has state, apply it. Otherwise apply `Standard` preset defaults.

---

## §R7 — Bulk actions: delete + on-screen CSV export (Day 5, ~2 hours)

Two actions only (Q4). Build Pack B will add the rest after a week of real use.

### R7.1 — Row selection model

TanStack Table's built-in row selection. Selection is line-level only — group rows and item rows are not selectable. Enforce via the `select` column's `cell` renderer:

```jsx
cell: ({ row }) => row.depth === 0 || row.original.isItem
  ? null
  : <Checkbox checked={row.getIsSelected()} ... />
```

### R7.2 — BulkActionsBar

**File:** `BulkActionsBar.jsx`

Renders above the grid, BELOW the header tiles, when ≥1 line is selected:

```jsx
{selectedCount > 0 && (
  <div className="flex items-center justify-between rounded bg-slate-100 px-3 py-2">
    <span className="text-sm text-slate-700">
      {selectedCount} {selectedCount === 1 ? 'line' : 'lines'} selected
    </span>
    <div className="flex items-center gap-2">
      <CsvExportButton selectedRows={selectedRows} />
      {canEdit && editable && (
        <button
          onClick={() => setConfirmDelete(true)}
          className="rounded bg-sy-orange px-3 py-1.5 text-sm font-medium text-white hover:brightness-110 active:brightness-95"
        >
          Delete selected
        </button>
      )}
      <button
        onClick={() => table.resetRowSelection()}
        className="text-sm text-slate-600 hover:underline"
      >
        Clear
      </button>
    </div>
  </div>
)}
```

### R7.3 — Bulk delete

**Confirmation dialog:** `BulkDeleteConfirmDialog.jsx`. Shows count + warning text + "Cancel" / "Delete N lines" buttons. Delete button uses `bg-sy-orange`.

**Hook:** new mutation in `hooks/budgets.js`:

```js
export function useBulkDeleteBudgetLines(budgetId, projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (lineIds) => {
      // Backend doesn't have a bulk endpoint — fan out sequentially.
      // Capped at 100 selected rows on the client (UI guard) so we don't hammer the API.
      for (const id of lineIds) {
        await api.delete(`/api/v1/budgets/${budgetId}/lines/${id}`);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets', budgetId] }),
  });
}
```

**Note on backend:** a real bulk-delete endpoint would be cleaner (one transaction, one audit batch). For Build Pack A, fan-out is acceptable because the audit log already exists per-line via the single-line DELETE. Build Pack B can introduce `POST /budgets/{id}/lines/bulk-delete` for transactional atomicity.

**Concurrency:** if a delete fails mid-loop, the user sees a partial success. Surface via toast: "Deleted N of M lines. M-N failed." Refetch on completion so the grid reflects the actual state.

### R7.4 — On-screen CSV export

**Decision locked:** export only what's visible on screen (filtered + currently-visible columns), so sensitive-field hiding is respected automatically. Client-side generation; no new backend endpoint.

**File:** `CsvExportButton.jsx`

```jsx
// Inline CSV builder — no new dependency.
// Quote values containing comma, double-quote, or newline; escape inner quotes.
function toCsv(rows) {
  return rows.map(row =>
    row.map(cell => {
      const s = String(cell ?? '');
      return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(',')
  ).join('\r\n');
}

export function CsvExportButton({ table, selectedRows, budget }) {
  function exportCsv() {
    const visibleColumns = table.getVisibleLeafColumns()
      .filter(col => !['select', 'expand', 'actions'].includes(col.id));

    // If rows are selected, export those; otherwise export everything on screen.
    const rowsToExport = selectedRows.length
      ? selectedRows
      : table.getRowModel().rows.filter(r => !r.original.isGroup && !r.original.isItem);

    const headers = visibleColumns.map(col => col.columnDef.header ?? col.id);

    const rows = rowsToExport.map(row =>
      visibleColumns.map(col => {
        // Pull raw value, not the rendered cell. For computed columns
        // (forecast_profit, forecast_margin_pct, variance_to_forecast),
        // recompute the number so the CSV holds the same value the user sees.
        if (col.id === 'forecast_profit') {
          const sale = Number(row.original._allocated_sale_price_provisional ?? 0);
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          return sale - ffc;
        }
        if (col.id === 'forecast_margin_pct') {
          const sale = Number(row.original._allocated_sale_price_provisional ?? 0);
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          if (sale <= 0) return '';
          return (((sale - ffc) / sale) * 100).toFixed(2);
        }
        if (col.id === 'variance_to_forecast') {
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          const orig = Number(row.original.original_budget ?? 0);
          return ffc - orig;
        }
        // Default: use the accessor if defined, otherwise the field.
        return col.accessorFn
          ? col.accessorFn(row.original)
          : row.original[col.id] ?? '';
      }),
    );

    const csv = toCsv([headers, ...rows]);
    const blob = new Blob(["\ufeff" + csv], { type: 'text/csv;charset=utf-8' });
    // BOM prefix so Excel opens it as UTF-8 instead of as a Windows-1252 string.
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `budget-${budget.id}-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success(`Exported ${rowsToExport.length} lines.`);
  }

  return (
    <button
      onClick={exportCsv}
      className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
    >
      Export CSV
    </button>
  );
}
```

**No new dependencies.** The inline `toCsv` function is RFC-4180-compliant for the field types this grid emits (numbers, short strings, no embedded line breaks expected but handled if present). Adding a BOM prefix makes Excel-on-Windows recognise UTF-8.

**Sensitive-field handling:** because the export uses `table.getVisibleLeafColumns()`, and the Profit/Margin columns were never added to the column array for users without `budgets.view_sensitive` (R3.2), those users physically cannot export them. Same protection on the server side already — `allocated_sale_price` is stripped from the API response, so even if some bug added the column, the data would be `undefined`.

**Audit:** CSV export is NOT a server action, so it doesn't hit the audit log. This is a deliberate trade-off — the alternative is a "ping the server we exported" endpoint, which the operator chose to skip. **Future_Tasks entry to add:** "CSV export audit — POST `/api/v1/budgets/{id}/export-recorded` fire-and-forget call from frontend whenever CSV is generated, so audit log captures who exported when. Out of scope for Build Pack A."

### R7.5 — STOP gate #6

Operator review of R7. Confirm bulk delete works, CSV exports current visible state, no sensitive fields leak.

---
## §R8 — Mobile read-only treatment (Day 5, ~2 hours)

Per Q8: mobile is read-only with one exception — Notes is editable on mobile because it's the only field that's inline-editable on desktop too.

### R8.1 — BudgetGridMobileReadOnly

**File:** `frontend/src/components/budgets/grid/BudgetGridMobileReadOnly.jsx`

Top-level layout:
1. Header tiles (vertically stacked, 5 cards full-width)
2. Search input (the only filter on mobile)
3. Stripped-down list: cost code + current budget + variance

```jsx
export function BudgetGridMobileReadOnly({ budget, projectId }) {
  const [search, setSearch] = useState('');
  const { data: costCodes = [] } = useCostCodes(projectId);
  const costCodeMap = useMemo(() => buildCostCodeMap(costCodes), [costCodes]);
  const [openLineId, setOpenLineId] = useState(null);

  const filtered = useMemo(() => {
    if (!search) return budget.lines ?? [];
    const q = search.toLowerCase();
    return (budget.lines ?? []).filter(l => {
      const code = costCodeMap.get(l.cost_code_id)?.code ?? '';
      return code.toLowerCase().includes(q)
        || (l.line_description ?? '').toLowerCase().includes(q);
    });
  }, [budget.lines, search, costCodeMap]);

  return (
    <div className="space-y-3">
      <MobileHeaderTiles budget={budget} />
      <input
        type="search"
        placeholder="Search cost code or description…"
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
      />
      <ul className="divide-y divide-slate-200 rounded border border-slate-200">
        {filtered.map(line => (
          <li key={line.id}>
            <button
              onClick={() => setOpenLineId(line.id)}
              className="flex w-full items-center justify-between px-3 py-3 text-left"
            >
              <div>
                <div className="text-sm font-medium text-slate-900">
                  {costCodeMap.get(line.cost_code_id)?.code ?? '—'}
                </div>
                <div className="text-xs text-slate-500 truncate max-w-[60vw]">
                  {line.line_description ?? '—'}
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm tabular-nums">{formatMoney(line.current_budget)}</div>
                <VarianceBadge status={line.variance_status} pct={line.variance_pct} />
              </div>
            </button>
          </li>
        ))}
      </ul>
      <MobileLineDetailDrawer
        lineId={openLineId}
        budget={budget}
        projectId={projectId}
        onClose={() => setOpenLineId(null)}
      />
    </div>
  );
}
```

### R8.2 — MobileLineDetailDrawer

Stacked drawer (full-screen on mobile) showing all line fields read-only, except Notes which is editable. Reuses `NotesCell` with `canEdit=true` AND a mobile flag — but the mobile gating is at component level, so Notes is the only editable thing here.

The drawer also surfaces the per-line transaction sections from R4 (POs stub, Variations stub, Bills live) so a site manager can check what's been billed without leaving mobile.

**No bulk actions on mobile.** No filtering beyond search. No column visibility menu. No saved views chooser.

### R8.3 — STOP gate #7

Operator quick check on real mobile device. Confirm mobile mode renders, search works, Notes edit works.

---

## §R9 — Tests (Day 5–6, ~4 hours)

### R9.1 — Backend tests (target: ~+30 cases, taking 799 → ~830 passing)

Already enumerated per R-section above. Summary:

| Test file | Cases |
|---|---|
| `test_budgets_variance_bands.py` | 6 (R1.1 fence-posts) |
| Existing variance tests | ~4 updates to new bands |
| `test_budgets_default_items.py` | 4 (R1.2 auto-create) |
| `test_migration_0027_backfill.py` | 3 (R1.3 backfill) |
| `test_user_preferences_api.py` | 14 (R1.4) |
| `test_migration_0028_user_preferences.py` | 2 (R1.4 migration) |

All run under `python -m pytest backend/app/tests` with the existing `env -i` + 14 CI vars contract. Migration revision name length check is part of CI; verify both new revisions pass.

### R9.2 — Jest component tests (target: +25 cases, taking ~151 → ~176+ passing)

| Test file | Cases |
|---|---|
| `BudgetGridV2.test.jsx` | 4 (renders, switches desktop/mobile, applies preset, persists state) |
| `BudgetGridColumns.test.jsx` | 3 (column visibility, profit/margin gated by permission, INITIAL_COLUMN_VISIBILITY correctness) |
| `VarianceCell.test.jsx` | 3 (renders green/amber/red, shows pct, falls back gracefully on null status) |
| `BudgetGridToolbar.test.jsx` | 5 (search, category filter, variance chip filter, actuals toggle, variance toggle) |
| `NotesCell.test.jsx` | 4 (read-only when canEdit=false, edit-then-blur saves, escape reverts, enter saves) |
| `LineItemsBreakdown.test.jsx` | 2 (renders 4 default items, add-item button visible when canEdit) |
| `BillsSection.test.jsx` | 2 (empty state, list with mocked actuals) |
| `useSetCurrentPreference.test.jsx` | 1 (debounced calls coalesce) |
| `groupLinesByCategory.test.js` | 1 (clusters by prefix correctly) |

Total: +25 cases (`151 → 176+`).

Mocking strategy:
- TanStack Query: use a fresh `QueryClient` per test, no MSW unless already present.
- `api.get/put/post/delete`: mock at the `@/lib/api` module level.
- `useIsDesktop`: mock to control desktop/mobile branch.

### R9.3 — Playwright

**OUT OF SCOPE for Build Pack A.** Per locked decision: Playwright E2E specs land in the next chat (Chat 24 equivalent). The existing flat-grid Playwright specs WILL go red the moment v2 lands. Document this in chat closing notes: "Playwright suite expected to be red on `main` after Build Pack A merges. Build Pack A-followup ships Playwright adaptation."

### R9.4 — CI green-keeping

Build Pack must keep CI green. Specifically:
- `env -i` + 14 CI vars contract preserved.
- New migrations apply cleanly in CI's ephemeral DB.
- Bundle stays ≤ 437 kB gz on main bundle (code-splitting from R2.2 makes this comfortable).
- Permissions count remains 86 (no new permissions added — saved views and grid prefs are per-user, not permissioned).
- Roles count remains 10.
- Backend tests passing.
- Frontend tests passing.

### R9.5 — STOP gate #8

Operator review of test state. Confirm all green before promoting to v-final.

---

## §R10 — Acceptance gates

The Build Pack is complete when ALL of the following are true:

### Backend
- [ ] G1. Variance constants updated to 0%/10% (R1.1).
- [ ] G2. `_classify_variance` uses `>=` for red threshold (R1.1).
- [ ] G3. New helper `_create_default_items` exists and is wired into `create_from_appraisal` and any other line-creation path (R1.2).
- [ ] G4. Migration 0027 (backfill) applied; existing zero-item lines have 4 items each (R1.3).
- [ ] G5. Migration 0028 (user_preferences) applied; table exists with partial unique indexes (R1.4).
- [ ] G6. New router `/api/v1/me/preferences/{surface_key}` mounted and visible at `/docs` (R1.4).
- [ ] G7. `alembic current` returns `0028_user_preferences_table`.
- [ ] G8. Backend tests passing (~830).

### Frontend
- [ ] G9. `@tanstack/react-table` installed at `^8.20.0`+ (R2.1).
- [ ] G10. Budgets routes lazy-loaded; separate chunk emitted (R2.2).
- [ ] G11. Main bundle size dropped vs baseline by ≥10 kB gz (R2.2).
- [ ] G12. `BudgetGridV2` replaces `BudgetLinesGrid` at `frontend/src/components/budgets/grid/` (R3.1).
- [ ] G13. 12 columns defined, 6 visible by default (R3.2).
- [ ] G14. 4 view presets (Quick / Standard / Full / Profit) load and persist (R3.3).
- [ ] G15. Variance cells render with correct heat-map colour (Green/Amber/Red) (R3.4).
- [ ] G16. 3-level row hierarchy: Category → Line → Items renders (R3.5).
- [ ] G17. Categories default expanded, items default collapsed (R3.6).
- [ ] G18. Toolbar shows 5 filters; each filters correctly (R3.7).
- [ ] G19. Column reorder, pinning, and sort all work (R3.8).
- [ ] G19b. Line drag-reorder preserved from v1; disabled when sort is active (R3.1 / R3.8).
- [ ] G19c. Inline edit on non-Notes fields removed; all other line-field edits route through LineDrawer (R3.1 / R5).
- [ ] G20. Sort applies at both group and line levels (R3.8 / Q6c).
- [ ] G21. Profit/Margin columns hidden for users without `budgets.view_sensitive` (R3.9).
- [ ] G21b. Backend serializer attaches `_allocated_sale_price_provisional` for sensitive-view users only (R3.9b).
- [ ] G22. 5 header tiles render with correct totals (R3.10).
- [ ] G23. Drilldown opens on chevron click; shows breakdown + POs/Variations/Bills (R4.5).
- [ ] G24. Bills section shows real actuals for the line (R4.4).
- [ ] G25. Notes inline-editable on desktop and mobile; not editable on terminal-status budgets (R5.1).
- [ ] G26. Saved views CRUD works (R6.3 / R6.4).
- [ ] G27. Grid state autosaves via debounced PUT (R6.2).
- [ ] G28. Bulk delete works with confirmation (R7.3).
- [ ] G29. CSV export exports visible columns + visible (filtered) rows OR selected rows (R7.4).
- [ ] G30. Mobile shows stripped-down read-only list with Notes editable (R8.1 / R8.2).
- [ ] G31. Jest tests passing (~176+).
- [ ] G32. Bundle ≤ 437 kB gz on `main.<hash>.js`.

### Cross-cutting
- [ ] G33. Permissions count = 86 (unchanged).
- [ ] G34. Roles count = 10 (unchanged).
- [ ] G35. CI green on `main` after merge.
- [ ] G36. No regression in existing budget endpoints (verified by existing tests still passing).
- [ ] G37. Audit log emitted on bulk delete (one row per line deleted) and on saved-view CRUD (NOT on autosave).
- [ ] G38. Old `BudgetLinesGrid.jsx`, `SortableLineRow.jsx`, `LineItemsPanel.jsx` deleted from repo.
- [ ] G39. `chat-23-closing.md` committed to `docs/chat-summaries/` summarising what shipped, what deferred, and Playwright deferral note.

---

## §Self-report format

After every R-section, Emergent must produce a report block matching this template:

```
SECTION: R<n>.<sub>
STATUS: complete | partial | blocked
FILES CHANGED:
  - <path> (created | modified | deleted) — <one-line note>
  ...
COMMITS:
  - <sha7> <message>
  ...
TESTS:
  backend: <prev> -> <new> passing (<delta> new)
  frontend: <prev> -> <new> passing (<delta> new)
BUNDLE: <size> kB gz (<delta> vs prior)
ALEMBIC HEAD: <revision>
DEVIATIONS FROM SPEC:
  - <none | specific item with reason>
NEXT: R<n>.<sub+1> or STOP gate #<m>
```

If `STATUS=blocked`, include `BLOCKER: <reason>` and stop. Operator unblocks before continuing.

If `STATUS=partial`, include `REMAINING: <what's left>` and continue cautiously into the next sub-section only if the remaining work is non-blocking for it. Otherwise stop.

**Drift caveat:** if any acceptance criterion in §R10 would fail with the work done in this R-section, the section is NOT complete. Mark `partial` or `blocked` and surface.

---

## §STOP gates summary

8 hard pauses across the build:

| # | After | What operator verifies |
|---|---|---|
| 1 | R0.5 | Baseline clean, backfill scope known, TanStack Table present |
| 2 | R1.4 | Backend migrations apply, new endpoints work, tests passing |
| 3 | R2.2 | Bundle headroom restored via code-splitting |
| 3b (optional) | R3.9b | Sale-price provisional allocation acceptable, or operator wants weighted/manual model |
| 4 | R3.10 | Grid renders, hierarchy + filters + sort + heat-map all work |
| 5 | R4.5 | Drilldown works including live Bills section |
| 6 | R7.4 | Bulk actions + CSV export work |
| 7 | R8.2 | Mobile read-only verified on real device |
| 8 | R9.4 | All tests green, CI green, bundle under cap |

After STOP gate #8, the Build Pack is ready for v-final → merge to main → ship to operator for spot-check + visual review.

---

## §In scope (Build Pack A)

1. Grid v2 replacing the flat 6-col Chat 17 grid.
2. 12-column model with 6 default-visible.
3. 4 view presets + saved views CRUD per user.
4. Variance heat-map at 0/10 bands.
5. 3-level row hierarchy (category → line → items).
6. Smart-default expansion (categories expanded, items collapsed).
7. 5 toolbar filters (search, category, variance band, actuals toggle, variance toggle).
8. Sticky columns + reorder + sort, sort at both levels.
9. Notes inline-editable; all other money fields editable via existing drawer.
10. Per-line drilldown: 4-type breakdown + POs stub + Variations stub + LIVE Bills.
11. 5 header tiles + existing chips.
12. Mobile read-only treatment with Notes-editable exception.
13. Bulk delete + CSV export of on-screen data.
14. Sensitive-field gating for Profit/Margin columns.
15. Code-splitting for the budgets route.
16. New `user_preferences` table + 6 API endpoints.
17. Variance constants updated to design Q2 spec.
18. Auto-create 4 default `budget_line_items` on line creation + backfill migration for existing.
19. Backend + Jest test coverage for all of the above.

## §Out of scope (deferred to Build Pack B or later)

1. All bulk actions other than delete + CSV (reassign cost code, bulk % complete, bulk lock/unlock, bulk move version, bulk forecast method).
2. % complete column display in grid v2 — defer to Build Pack B.
3. Schedule → budget % derivation (Future_Tasks entry only).
4. Real POs and Variations records — Prompts 2.5 and 2.6.
5. Bill reassignment from grid (clicking a bill in the drilldown takes you to the actual detail page; reassignment is P3 polish).
6. Configurable variance thresholds in `system_config` — Future_Tasks §10.
7. Line-level statuses (Q5b deferred — no data model support).
8. CSV import — only export in scope.
9. Per-item money columns in the breakdown (Forecast/Actual/Committed at item level) — those stay at the line level.
10. Sharing saved views between users — per-user only.
11. Mobile bulk-action features.
12. Renaming/restructuring existing `budget_lines` columns — UI labels translate, backend field names unchanged.
13. Playwright E2E for v2 — next chat.
14. Backend bulk-delete endpoint (one transaction, batched audit) — Build Pack B.
15. CSV export audit trail (server-side ping) — Future_Tasks entry.
16. Backend category-summary endpoint — Future_Tasks entry.

---

## §Future_Tasks additions (Emergent appends to repo `Future_Tasks.md`)

Emergent appends each of these on first invocation:

1. **Schedule-to-budget % complete derivation** — when Programme module ships, `budget_lines.percentage_complete` derives from `linked_programme_task.percentage_complete` instead of being human-set. FK `linked_programme_task_id` already exists from migration 0024.
2. **Configurable variance thresholds** — surface VARIANCE_AMBER_PCT / VARIANCE_RED_PCT in `system_config` so finance can tune them without a code change.
3. **Backend category-summary endpoint** — `GET /api/v1/budgets/{id}/category-summary` returns pre-aggregated totals per cost-code category. Replaces client-side `groupLinesByCategory` aggregation once budgets exceed 200 lines.
4. **Bulk-delete transactional endpoint** — `POST /api/v1/budgets/{id}/lines/bulk-delete` that does the delete in one transaction with one audit batch instead of N fan-out calls.
5. **CSV export audit trail** — `POST /api/v1/budgets/{id}/export-recorded` fire-and-forget from frontend whenever CSV is exported.
6. **Bill reassignment from grid** — "click bill in drilldown → reassign to a different budget_line" workflow. P3.
7. **Saved-view sharing** — promote a view from per-user to project-level or org-level. Currently per-user only.
8. **Line-level statuses** — define and surface `BudgetLine.status` (e.g. On track / At risk / Blocked). No data model support today.

---

## §Hard constraints (carried forward — must not violate)

1. Bundle cap: 437,000 bytes gzipped on `main.<hash>.js`.
2. Migration revision names: ≤32 characters (varchar(32) on `alembic_version`).
3. Tenant scoping: Pattern α via `_visible_project_ids` join. No `tenant_id` columns on new tables (R1.4 is user-scoped, not tenant-scoped, so this doesn't apply).
4. Brand tokens: `bg-sy-teal` for primary CTAs, `bg-sy-orange` for destructive confirms. No `-hover` / `-foreground` suffixes.
5. Audit log on every CUD endpoint, except: high-volume preference autosave (deliberately excluded).
6. `env -i` + 14 CI vars contract preserved.
7. Permissions count stays at 86 (no new permissions added in Build Pack A).
8. Roles count stays at 10.
9. Postgres 16 + `pgcrypto` extension (already provisioned).
10. No `cost_type` enum on `budget_line_items` — items remain description-based.

---

## §Drafting / audit notes for the next chat

This file is **v1**. Before paste-ready, expect:

- **Audit pass 1:** fresh-reader review. Look for: undefined references, missing files, contradiction with existing code conventions, gaps in acceptance criteria.
- **Audit pass 2:** acceptance-gate completeness. Every R-section's deliverables should map to one or more gates in §R10.
- **Audit pass 3:** spec-level consistency. Cross-check Q1–Q10 in the handoff against R1–R10 in this Build Pack.
- **Audit pass 4 (if needed):** edge cases and error paths. What happens when…
  - The user has zero permissions to budgets?
  - The budget has zero lines?
  - The line has zero items (post-backfill, shouldn't happen but defensive UI)?
  - The actuals endpoint returns 500?
  - The user reorders columns mid-autosave-debounce?

Each audit pass produces a delta — apply in-place to this file, do not start a new version until v-final.

When the file is paste-ready (no Critical or High defects remain), promote to **v-final** by renaming to `Chat_23_Build_Pack_v_final.md` and produce the Emergent opener as a separate chat code block.

---

_End of v1 draft. Length target ~1,800–2,300 lines; current draft is in that range. Proceed to audit pass 1._
