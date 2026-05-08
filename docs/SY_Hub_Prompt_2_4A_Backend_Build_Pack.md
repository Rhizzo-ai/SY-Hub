# SY Hub — Prompt 2.4A Build Pack: Budgets Core (Backend)

| Field | Value |
|---|---|
| Version | **v3** (post-second-audit; incorporates Tier 1 B8–B12, recommended Tier 2 B13–B18, B23, Tier 4 T21–T25; Tier 3 deferred to backlog) |
| Date drafted | 2026-05-08 |
| Author | Chat 16 (Claude Opus 4.7) for Rhys @ SY Homes |
| Predecessor | Chat 15 (Pre-2.4 Cleanup) shipped 2026-05-07 |
| Successor | Chat 17 will execute Prompt 2.4B (Budgets Frontend + E2E) |
| Alembic head BEFORE | `0023_appraisal_scenarios_cascade` |
| Alembic head AFTER | `0024_budgets` |
| Test count baseline | 597 passing (with `--ignore=tests/test_c3_governance_smoke.py`) |
| Test count target AFTER | ≥ 662 passing (baseline + ≥65 new) |
| Permission count BEFORE | 83 |
| Permission count AFTER | 84 (+1: `budgets.admin`) |
| Role count | 10 (unchanged) |
| Migration revision name length | `0024_budgets` = 12 chars (≤32 limit ✓) |
| Build Pack location in repo | `/app/docs/SY_Hub_Prompt_2_4A_Backend_Build_Pack.md` |

## Locked decisions (do NOT relitigate)

1. **Phase 1 brief lines 2711–2958 is the canonical spec.** Phase 2 detail §2.4 line 104 names `budget_line_periods` — that is a stray edit, locked-deferred. Build Phase 1 spec verbatim.
2. **Third table is `budget_line_items`** (line-item granularity). NOT `budget_line_periods`.
3. **`budget_line_periods` (monthly time-phasing) is deferred** to the cash-flow prompt. Backlog entry — Appendix A.
4. **Session split:** This prompt = **2.4A backend only**. Frontend = 2.4B in Chat 17.
5. **New permission:** `budgets.admin` added alongside existing `budgets.{view, view_sensitive, create, edit, approve}`. Total budgets perms after: 6. Net new: 1.
6. **Role mapping fix:** `project_manager` is currently missing `budgets.create` in `seed_rbac.py`. Phase 1 brief states "PM+ (requires approved appraisal)" can create. This prompt fixes that.
7. **Xero zero in scope.** Module functions standalone. Xero hooks land in Track 6.
8. **`budget_lines.linked_programme_task_id`** is a nullable `uuid` column with **no FK constraint this prompt**. FK added in Prompt 3.2 per spec line 2781.
9. **Activate gating:** `budgets.edit` (not `budgets.admin`). PM can activate budgets they created. SOX-style separation flagged for next team review with MD/Louise — not changed silently here.
10. **`scan_requires_attention` scheduling:** endpoint only this prompt, gated by `budgets.admin`. No scheduler infrastructure wired this prompt. Backlog — Appendix A.
11. **`SystemConfig` variance threshold columns:** NOT added this prompt. In-code defaults (5% amber, 10% red) shipped. Backlog — Appendix A.
12. **Idempotency keys:** deferred — backlog (Appendix A).
13. **`linked_programme_task_id` on version-bump:** **carried forward** (continuity, lower-data-loss option). Documented decision; revisit if business workflow shows version-bump means programme re-plan.
14. **Cost lines + unit aggregation merge behaviour:** **summed** into a single `budget_line` per cost_code. When `appraisal_cost_lines` and `appraisal_units` aggregation both produce entries for `(cost_code=X, subcategory=NULL)`, original_budget = cost_line.effective_value + unit_aggregation_for_X. Avoids partial-unique-index collision (B11).
15. **Shared exceptions:** `BudgetCreationError` and `BudgetStateError` live in `app/services/budget_errors.py` (B15). Both service modules and routes import from there.

## Pre-flight (read this before writing any code)

You are an Emergent agent executing **Prompt 2.4A**. Read these files in order before §R0:

1. `/app/docs/SY_Homes_Emergent_Brief_Phase1.md` — lines **2711–2958** (canonical spec)
2. `/app/docs/SY_Homes_Phase2_Brief_T2_T3_Detail.md` — §2.4 (cross-track wiring context)
3. `/app/backend/tests/test_appraisals.py` — fixture pattern reference
4. `/app/backend/tests/conftest.py` — confirm session fixtures
5. `/app/backend/app/seed_rbac.py` — `PERMISSION_CATALOGUE` and `ROLE_PERMISSIONS` structure
6. `/app/backend/alembic/versions/0011_cost_codes.py` — `cost_codes`/`cost_code_subcategories` DDL
7. `/app/backend/alembic/versions/0022_appraisal_governance.py` — confirm `appraisals.status='Approved'`
8. `/app/backend/app/models/appraisals.py` — read `Appraisal`, `AppraisalCostLine`, `AppraisalUnit`
9. `/app/backend/app/models/projects.py` and `app/models/entities.py` — FK target verification
10. `/app/backend/app/models/system_config.py` — confirm structure (no columns added this prompt)
11. **`/app/backend/app/routes/appraisals.py`** — read for tenant-scoping pattern; replicate verbatim. Security-critical.

## Hard constraints

- **Tenant isolation is a SECURITY-CRITICAL hard constraint** (B14). Every query filters by `tenant_id` via the route-layer scoping pattern (see `routes/appraisals.py`). Never trust caller-supplied tenant_id; always pull from session. Cross-tenant access returns 404 (do not leak existence).
- **Never lose financial data.** All write operations on `budgets`, `budget_lines`, `budget_line_items` produce `audit_log` entries. Audit on every CUD including item CRUD.
- **Multi-entity preserved.** `budget_lines.entity_id` REQUIRED. No silent entity defaulting.
- **Role-based access enforced server-side.** Every endpoint has a `require_permission(...)` dependency.
- **Performance budget.** Detail endpoint < 800ms for 200-line budget. Use `selectinload`. Asserted via query-count test (§R5 T_perf).
- **Multi-tenant scaffolding preserved.** New tables include `tenant_id uuid NOT NULL` FK with index.
- **Idempotent migration.** `0024_budgets.upgrade()` succeeds against fresh DB AND against alembic head `0023_*`. `downgrade()` cleanly drops all tables, enums, triggers, partial indexes.

## Out of scope this prompt (DO NOT BUILD)

Frontend, actuals (2.5), commitments (2.5), budget changes (2.6), `budget_line_periods`, `linked_programme_task_id` FK constraint, Xero, scheduling infra, idempotency keys, SystemConfig threshold columns, email notifications, reports, Future_Tasks §3/§4/§5.

If §R1 surfaces work materially beyond §R0 estimate — STOP and self-report.

---

# §R0 — Scope sizing (do this BEFORE any code)

After Pre-flight reading, post a single status message back with:

**Estimate confirmation table:**

| Item | Estimate | Confirmed? |
|---|---|---|
| Migration files | 1 (`0024_budgets.py`) | |
| New ORM models | 3 | |
| New service modules | 3 (`budgets.py`, `budget_lines.py`, `budget_errors.py`) | |
| New API route module | 1 | |
| New endpoints | 14 (see §R4) | |
| New permissions | 1 (`budgets.admin`) | |
| Role mapping fixes | 1 (PM gains `budgets.create`) | |
| Test file | 1 (`tests/test_budgets.py`) | |
| Target tests added | ≥65 | |
| Bookkeeping touches | 2 (`tests/test_bootstrap.py`, `CHANGELOG.md`) | |

**Pre-flight verification — run these BEFORE coding:**

```bash
# 1. permission_action enum has 'admin' value
psql -d $DATABASE_NAME -c "SELECT 'admin' = ANY(enum_range(NULL::permission_action)::text[]);"
# Expect: t

# 2. appraisal_status enum has 'Approved' value
psql -d $DATABASE_NAME -c "SELECT 'Approved' = ANY(enum_range(NULL::appraisal_status)::text[]);"
# Expect: t

# 3. Baseline permission count
psql -d $DATABASE_NAME -c "SELECT COUNT(*) FROM permissions;"
# Expect: 83

# 4. Pre-existing budgets test conflict check
cd /app/backend && grep -rn "budget" tests/ --include="*.py" | grep -v "test_appraisals" | grep -v ".pyc"
# Expect: empty (or only unrelated conftest references)

# 5. (B12) Appraisal model has tenant_id column
psql -d $DATABASE_NAME -c "\d appraisals" | grep -E "tenant_id"
# Expect: tenant_id | uuid | not null
```

If ANY check fails → post `STOP — pre-flight check failed` naming which check. Do not proceed.

**STOP-and-resplit triggers — escalate if any TRUE:**

1. More than 1 NEW permission beyond `budgets.admin`
2. More than 3 new tables
3. More than 1 alembic revision
4. State machine more than 5 states
5. Budget creation requires reading from a not-yet-built table
6. Pre-flight check #4 returns existing budget tests
7. Files outside §R3/R4 scope need modification (expected: only `seed_rbac.py`, `tests/test_bootstrap.py`, `app/main.py`)
8. `AppraisalUnit` model lacks usable cost_code linkage (see §R3 service guard)

Trigger fires → post `STOP — scope expansion detected` naming trigger and new estimate. Wait for human's call.

---

# §R1 — Spec reconciliation

Phase 1 brief is canonical. Phase 2 detail §2.4 line 104 (`budget_line_periods`) is locked-deferred erratum.

## Phase 1 spec walkthrough

- Tables: `budgets` (header), `budget_lines` (per cost-code+entity), `budget_line_items` (granular breakdown)
- Status enum on `budgets`: `Draft, Active, Locked, Superseded, Closed`
- FTC method on `budget_lines`: `Manual, Budget_Remaining, Committed_Only, Percentage_Complete`
- Variance status on `budget_lines`: `Green, Amber, Red`
- Cached aggregates: per spec lines 2735–2742 (header) and 2764–2779 (lines)
- Indexes: per spec, plus 2 partial unique indexes (B3, B6)

## Permissions (Phase 1 spec)

- `budgets.view`, `budgets.view_sensitive`, `budgets.create`, `budgets.edit` — already seeded
- `budgets.admin` — director (force-unlock) — **NEW THIS PROMPT**

---

# §R2 — Migration: `0024_budgets`

## File location

`/app/backend/alembic/versions/0024_budgets.py`

## Skeleton

```python
"""0024 budgets — schema only

Revision ID: 0024_budgets
Revises: 0023_appraisal_scenarios_cascade

Creates 3 tables, 3 enums, indexes (incl. 2 partial unique indexes for
concurrency safety: B3 one-current-per-project, B6 null-subcategory),
3 updated_at triggers.

permission_action.admin already exists; no enum migration needed.
"""
from alembic import op
import sqlalchemy as sa


revision = "0024_budgets"
down_revision = "0023_appraisal_scenarios_cascade"
branch_labels = None
depends_on = None


BUDGET_STATUSES = ("Draft", "Active", "Locked", "Superseded", "Closed")
FTC_METHODS = ("Manual", "Budget_Remaining", "Committed_Only", "Percentage_Complete")
VARIANCE_STATUSES = ("Green", "Amber", "Red")


def _attach_updated_at_trigger(table: str) -> None:
    op.execute(f"""
        CREATE TRIGGER trg_{table}_updated_at
        BEFORE UPDATE ON {table}
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)


def upgrade() -> None:
    budget_status_enum = sa.Enum(*BUDGET_STATUSES, name="budget_status")
    ftc_method_enum = sa.Enum(*FTC_METHODS, name="budget_line_ftc_method")
    variance_status_enum = sa.Enum(*VARIANCE_STATUSES, name="budget_line_variance_status")

    # ===== budgets =====
    op.create_table(
        "budgets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_appraisal_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("appraisals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("version_label", sa.String(50), nullable=False, server_default="Original"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("status", budget_status_enum, nullable=False, server_default="Draft"),
        sa.Column("created_from_appraisal_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("total_budget", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_actuals", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_committed_not_invoiced", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_forecast_to_complete", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("forecast_final_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("variance_vs_budget", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("variance_pct", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("summary_refreshed_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("notes", sa.Text),
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_budgets_project_is_current", "budgets",
                    ["project_id", "is_current"])
    op.create_index("ix_budgets_status", "budgets", ["status"])
    op.create_index("ix_budgets_tenant_id", "budgets", ["tenant_id"])
    op.create_index("ix_budgets_source_appraisal_id", "budgets", ["source_appraisal_id"])

    # B3: at most one is_current=true budget per project (DB-enforced)
    op.create_index(
        "uq_budgets_one_current_per_project",
        "budgets", ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    # ===== budget_lines =====
    op.create_table(
        "budget_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("budget_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_code_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cost_code_subcategory_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_code_subcategories.id", ondelete="RESTRICT")),
        sa.Column("line_description", sa.String(255), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_budget", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("approved_changes", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("current_budget", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("actuals_to_date", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("actuals_this_period", sa.Numeric(14, 2), server_default="0"),
        sa.Column("last_actual_posted_at", sa.DateTime(timezone=True)),
        sa.Column("committed_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("invoiced_against_commitment", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("committed_not_invoiced", sa.Numeric(14, 2),
                  nullable=False, server_default="0"),
        sa.Column("forecast_to_complete", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("ftc_method", ftc_method_enum, nullable=False, server_default="Budget_Remaining"),
        sa.Column("forecast_final_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("variance_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("variance_pct", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("variance_status", variance_status_enum, nullable=False, server_default="Green"),
        sa.Column("percentage_complete", sa.Numeric(5, 2), server_default="0"),
        # FK constraint added in Prompt 3.2
        sa.Column("linked_programme_task_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requires_attention", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("budget_id", "cost_code_id", "cost_code_subcategory_id",
                            name="uq_budget_lines_budget_cost_subcat"),
    )
    op.create_index("ix_budget_lines_budget_id", "budget_lines", ["budget_id"])
    op.create_index("ix_budget_lines_cost_code_id", "budget_lines", ["cost_code_id"])
    op.create_index("ix_budget_lines_tenant_id", "budget_lines", ["tenant_id"])
    op.create_index("ix_budget_lines_variance_attention", "budget_lines",
                    ["variance_status", "requires_attention"])

    # B6: closes the NULL-subcategory uniqueness gap
    op.create_index(
        "uq_budget_lines_no_subcat_unique",
        "budget_lines", ["budget_id", "cost_code_id"],
        unique=True,
        postgresql_where=sa.text("cost_code_subcategory_id IS NULL"),
    )

    # ===== budget_line_items =====
    op.create_table(
        "budget_line_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("budget_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("budget_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 4)),
        sa.Column("unit", sa.String(20)),
        sa.Column("rate", sa.Numeric(14, 4)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_budget_line_items_budget_line_id", "budget_line_items",
                    ["budget_line_id"])

    for t in ("budgets", "budget_lines", "budget_line_items"):
        _attach_updated_at_trigger(t)


def downgrade() -> None:
    op.drop_index("uq_budget_lines_no_subcat_unique", table_name="budget_lines")
    op.drop_index("uq_budgets_one_current_per_project", table_name="budgets")

    for t in ("budget_line_items", "budget_lines", "budgets"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_updated_at ON {t};")
        op.drop_table(t)
    for enum_name in ("budget_line_variance_status", "budget_line_ftc_method", "budget_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
```

## Migration verification

```bash
alembic current           # expect 0024_budgets

# Schema introspection
psql -d $DATABASE_NAME -c "\d budgets"
psql -d $DATABASE_NAME -c "\d budget_lines"
psql -d $DATABASE_NAME -c "\d budget_line_items"

# Enum values
psql -d $DATABASE_NAME -c "SELECT unnest(enum_range(NULL::budget_status));"

# Partial unique indexes present
psql -d $DATABASE_NAME -c "
  SELECT indexname FROM pg_indexes
  WHERE indexname IN ('uq_budgets_one_current_per_project',
                      'uq_budget_lines_no_subcat_unique');"
# expect 2 rows

# Round-trip
alembic downgrade 0023_appraisal_scenarios_cascade
alembic upgrade head
```

---

# §R3 — Models + services

## State machine

```
        ┌─── activate ──┐
        │  (edit perm)  │
   Draft ──────────────► Active ────── lock ────────► Locked
        │                │  (edit perm)              │
        │                │                          unlock
        │                │                       (admin perm)
        │                │                           │
        │                │                           ▼
        │                └────────────────────────► Active
        │                                            │
        ▼                ▼                           ▼
        Closed ◄────────────── close (edit perm) ────┤
                                                     │
        Superseded ◄── (set when create_new_version) ┘

Closed and Superseded are TERMINAL.
PATCH on lines BLOCKED when parent in {Closed, Superseded}.
```

## Shared exceptions module — `app/services/budget_errors.py` (new) [B15]

```python
"""Shared exceptions for the budget service modules and routes.
Lives outside both budgets.py and budget_lines.py to avoid circular imports.
"""


class BudgetCreationError(Exception):
    """Raised on creation-time validation failure (404/400 territory)."""
    pass


class BudgetStateError(Exception):
    """Raised on illegal state transition or terminal-state edit (409 territory)."""
    pass
```

## ORM models — `app/models/budgets.py` (new)

```python
"""Budget hierarchy ORM: Budget, BudgetLine, BudgetLineItem.

Cached aggregates are recomputed by services here and (later) by
actuals/commitments/changes services via service-layer calls — never
by ORM event listeners. Cache refresh is explicit, auditable, testable.
"""
from __future__ import annotations
import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class BudgetStatus(str, enum.Enum):
    Draft = "Draft"
    Active = "Active"
    Locked = "Locked"
    Superseded = "Superseded"
    Closed = "Closed"


class FTCMethod(str, enum.Enum):
    Manual = "Manual"
    Budget_Remaining = "Budget_Remaining"
    Committed_Only = "Committed_Only"
    Percentage_Complete = "Percentage_Complete"


class VarianceStatus(str, enum.Enum):
    Green = "Green"
    Amber = "Amber"
    Red = "Red"


TERMINAL_BUDGET_STATUSES = frozenset({BudgetStatus.Closed, BudgetStatus.Superseded})


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    source_appraisal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("appraisals.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version_label: Mapped[str] = mapped_column(String(50), nullable=False, default="Original")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[BudgetStatus] = mapped_column(
        Enum(BudgetStatus, name="budget_status",
             values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=BudgetStatus.Draft,
    )
    # ... timestamps, lock/close audit, cached aggregates, notes, created_by, created/updated ...
    lines: Mapped[list["BudgetLine"]] = relationship(
        "BudgetLine", back_populates="budget",
        cascade="all, delete-orphan", lazy="selectin",
    )


class BudgetLine(Base):
    __tablename__ = "budget_lines"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    budget_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    cost_code_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cost_codes.id"), nullable=False)
    cost_code_subcategory_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cost_code_subcategories.id"), nullable=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    line_description: Mapped[str] = mapped_column(String(255), nullable=False)
    # ... figures, FTC method, variance, flags, linked_programme_task_id, is_locked, requires_attention ...
    budget: Mapped["Budget"] = relationship("Budget", back_populates="lines")
    items: Mapped[list["BudgetLineItem"]] = relationship(
        "BudgetLineItem", back_populates="line",
        cascade="all, delete-orphan", lazy="selectin",
    )
    __table_args__ = (
        UniqueConstraint("budget_id", "cost_code_id", "cost_code_subcategory_id",
                         name="uq_budget_lines_budget_cost_subcat"),
    )


class BudgetLineItem(Base):
    __tablename__ = "budget_line_items"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    budget_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("budget_lines.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unit: Mapped[str | None] = mapped_column(String(20))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    line: Mapped["BudgetLine"] = relationship("BudgetLine", back_populates="items")
```

Fill abbreviated columns to match migration exactly.

## Header service — `app/services/budgets.py` (new)

```python
"""Budget header lifecycle services.

State machine (see §R3 ASCII diagram).
Closed/Superseded are terminal; lines on terminal-state budgets are read-only.
Concurrency: SELECT FOR UPDATE on lock/unlock/version. Partial unique index
prevents duplicate is_current.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence
from uuid import UUID
from collections import defaultdict

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.appraisals import Appraisal, AppraisalCostLine, AppraisalUnit
from app.models.budgets import (
    Budget, BudgetLine, BudgetStatus, FTCMethod, VarianceStatus,
    TERMINAL_BUDGET_STATUSES,
)
from app.services.audit import write_audit_log
from app.services.budget_errors import BudgetCreationError, BudgetStateError


def create_from_appraisal(
    db: Session, *, project_id: UUID, source_appraisal_id: UUID,
    user_id: UUID, tenant_id: UUID,
) -> Budget:
    """Clone an Approved appraisal into a Draft budget.

    Validates:
    - Appraisal exists, project_id and tenant_id match, status='Approved'
    - All cost lines have non-null effective_value (B5)
    - No existing is_current=true budget (DB-enforced via partial unique index;
      caught as IntegrityError → BudgetCreationError) (B3)

    Creates (B11 merge logic):
    - Budget header (version 1, 'Original', Draft)
    - For each unique cost_code:
        original_budget = sum(matching cost_lines.effective_value)
                        + sum(matching unit_aggregations)
      One budget_line per (cost_code, subcategory) tuple. When subcategory is NULL
      and both cost_lines and unit aggregation produce entries for the same
      cost_code, they SUM into a single budget_line.

    Returns Budget with .lines preloaded.
    """
    appraisal = db.scalar(
        select(Appraisal).where(
            Appraisal.id == source_appraisal_id,
            Appraisal.project_id == project_id,
            Appraisal.tenant_id == tenant_id,
        )
    )
    if appraisal is None:
        raise BudgetCreationError("Source appraisal not found for this project and tenant")
    if appraisal.status != "Approved":
        raise BudgetCreationError(f"Source appraisal must be Approved (is {appraisal.status})")

    # B5: validate effective_value present
    cost_lines: Sequence[AppraisalCostLine] = db.scalars(
        select(AppraisalCostLine).where(AppraisalCostLine.appraisal_id == source_appraisal_id)
    ).all()
    null_lines = [str(cl.id) for cl in cost_lines if cl.effective_value is None]
    if null_lines:
        raise BudgetCreationError(
            f"Cannot create budget: appraisal cost lines have null effective_value: "
            f"{null_lines[:5]}{'…' if len(null_lines) > 5 else ''}"
        )

    # B11: build merge map keyed by (cost_code_id, subcategory_id, entity_id)
    # so cost_lines and unit-aggregation rows summing to same key collapse to
    # one budget_line. Using tuple including entity_id because budget_lines
    # carry entity_id and we don't want to merge across entities even if
    # cost_code matches (multi-entity preservation hard constraint).
    merge_map: dict[tuple, dict] = {}

    for cl in cost_lines:
        key = (cl.cost_code_id,
               getattr(cl, "cost_code_subcategory_id", None),
               cl.entity_id)
        if key in merge_map:
            merge_map[key]["original_budget"] += cl.effective_value
        else:
            merge_map[key] = {
                "cost_code_id": cl.cost_code_id,
                "cost_code_subcategory_id": getattr(cl, "cost_code_subcategory_id", None),
                "entity_id": cl.entity_id,
                "line_description": cl.line_description,
                "original_budget": cl.effective_value,
            }

    # AppraisalUnit aggregation (spec line 2861).
    units = db.scalars(
        select(AppraisalUnit).where(AppraisalUnit.appraisal_id == source_appraisal_id)
    ).all()
    if units and not hasattr(units[0], "cost_code_id"):
        raise BudgetCreationError(
            "AppraisalUnit model has no cost_code_id — appraisal-units → budget-lines "
            "aggregation cannot proceed. Spec line 2861 requires this; STOP and clarify."
        )
    for u in units:
        key = (u.cost_code_id,
               getattr(u, "cost_code_subcategory_id", None),
               u.entity_id)
        unit_amount = u.build_cost  # adjust attr name to actual model field
        if key in merge_map:
            merge_map[key]["original_budget"] += unit_amount
        else:
            merge_map[key] = {
                "cost_code_id": u.cost_code_id,
                "cost_code_subcategory_id": getattr(u, "cost_code_subcategory_id", None),
                "entity_id": u.entity_id,
                "line_description": getattr(u, "line_description",
                                            f"Unit aggregation cost_code {u.cost_code_id}"),
                "original_budget": unit_amount,
            }

    # Build header
    budget = Budget(
        tenant_id=tenant_id,
        project_id=project_id,
        source_appraisal_id=source_appraisal_id,
        version_number=1,
        version_label="Original",
        is_current=True,
        status=BudgetStatus.Draft,
        created_by_user_id=user_id,
    )
    db.add(budget)
    try:
        db.flush()
    except IntegrityError as exc:
        if "uq_budgets_one_current_per_project" in str(exc.orig):
            db.rollback()
            raise BudgetCreationError(
                "An is_current budget already exists for this project. "
                "Use create_new_version() to supersede."
            ) from exc
        raise

    # Insert merged budget_lines
    display_order = 0
    for entry in merge_map.values():
        line = BudgetLine(
            tenant_id=tenant_id,
            budget_id=budget.id,
            cost_code_id=entry["cost_code_id"],
            cost_code_subcategory_id=entry["cost_code_subcategory_id"],
            entity_id=entry["entity_id"],
            line_description=entry["line_description"],
            original_budget=entry["original_budget"],
            current_budget=entry["original_budget"],
            ftc_method=FTCMethod.Budget_Remaining,
            forecast_to_complete=entry["original_budget"],
            forecast_final_cost=entry["original_budget"],
            variance_status=VarianceStatus.Green,
            display_order=display_order,
        )
        display_order += 1
        db.add(line)

    refresh_header_caches(db, budget)
    db.flush()

    write_audit_log(
        db, action="budgets.create", resource="budgets",
        resource_id=str(budget.id), user_id=user_id, tenant_id=tenant_id,
        metadata={
            "source_appraisal_id": str(source_appraisal_id),
            "project_id": str(project_id),
            "lines_created": len(merge_map),
            "appraisal_total_cost": str(sum(
                (e["original_budget"] for e in merge_map.values()), Decimal(0)
            )),
        },
    )
    return budget


def activate(db: Session, *, budget_id: UUID, user_id: UUID, tenant_id: UUID) -> Budget:
    b = _load_budget_for_write(db, budget_id, tenant_id)
    if b.status != BudgetStatus.Draft:
        raise BudgetStateError(f"Cannot activate budget in status {b.status.value}")
    previous = b.status.value
    b.status = BudgetStatus.Active
    write_audit_log(
        db, action="budgets.activate", resource="budgets",
        resource_id=str(b.id), user_id=user_id, tenant_id=tenant_id,
        metadata={"previous_status": previous, "new_status": b.status.value},
    )
    return b


def lock(db: Session, *, budget_id: UUID, user_id: UUID, tenant_id: UUID) -> Budget:
    """Active → Locked. Sets is_locked=true on all lines.
    Concurrency: SELECT FOR UPDATE on budget row.
    B8: synchronize_session='fetch' so in-memory line state matches DB after bulk update.
    """
    b = _load_budget_for_write(db, budget_id, tenant_id, lock_for_update=True)
    if b.status != BudgetStatus.Active:
        raise BudgetStateError(f"Cannot lock budget in status {b.status.value} (must be Active)")
    previous = b.status.value
    b.status = BudgetStatus.Locked
    b.locked_at = datetime.now(timezone.utc)
    b.locked_by_user_id = user_id
    result = db.execute(
        update(BudgetLine)
        .where(BudgetLine.budget_id == b.id)
        .values(is_locked=True)
        .execution_options(synchronize_session="fetch")  # B8
    )
    write_audit_log(
        db, action="budgets.lock", resource="budgets",
        resource_id=str(b.id), user_id=user_id, tenant_id=tenant_id,
        metadata={
            "previous_status": previous,
            "new_status": b.status.value,
            "lines_locked_count": result.rowcount,
        },
    )
    return b


def unlock(db: Session, *, budget_id: UUID, user_id: UUID, tenant_id: UUID) -> Budget:
    """Locked → Active. Director-only (gated at route layer by budgets.admin).
    B8: synchronize_session='fetch' on bulk update.
    """
    b = _load_budget_for_write(db, budget_id, tenant_id, lock_for_update=True)
    if b.status != BudgetStatus.Locked:
        raise BudgetStateError(f"Cannot unlock budget in status {b.status.value} (must be Locked)")
    previous = b.status.value
    b.status = BudgetStatus.Active
    b.locked_at = None
    b.locked_by_user_id = None
    result = db.execute(
        update(BudgetLine)
        .where(BudgetLine.budget_id == b.id)
        .values(is_locked=False)
        .execution_options(synchronize_session="fetch")  # B8
    )
    write_audit_log(
        db, action="budgets.unlock", resource="budgets",
        resource_id=str(b.id), user_id=user_id, tenant_id=tenant_id,
        metadata={
            "previous_status": previous,
            "new_status": b.status.value,
            "lines_unlocked_count": result.rowcount,
            "reason": "director force-unlock",
        },
    )
    return b


def close(db: Session, *, budget_id: UUID, user_id: UUID, tenant_id: UUID) -> Budget:
    b = _load_budget_for_write(db, budget_id, tenant_id)
    if b.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(f"Budget already in terminal state {b.status.value}")
    previous = b.status.value
    b.status = BudgetStatus.Closed
    b.closed_at = datetime.now(timezone.utc)
    b.closed_by_user_id = user_id
    b.is_current = False
    write_audit_log(
        db, action="budgets.close", resource="budgets",
        resource_id=str(b.id), user_id=user_id, tenant_id=tenant_id,
        metadata={"previous_status": previous, "new_status": b.status.value},
    )
    return b


def create_new_version(
    db: Session, *, budget_id: UUID, version_label: str, user_id: UUID, tenant_id: UUID,
) -> Budget:
    """Clone budget into new is_current=true version, mark old Superseded.

    Order: mark old superseded BEFORE inserting new (B3 partial unique index
    would otherwise reject the new insert).

    Carries forward (incl. linked_programme_task_id per locked decision 13):
    - cost_code_id, cost_code_subcategory_id, entity_id, line_description
    - current_budget → new original_budget
    - ftc_method, percentage_complete, notes, display_order, linked_programme_task_id
    Does NOT carry forward:
    - actuals, committed, audit-log entries, items, is_locked,
      requires_attention flag

    NOTE: linked_programme_task_id carry-forward is decision 13 (continuity,
    lower-data-loss). Revisit if business workflow shows version-bump means
    programme re-plan.
    """
    old = _load_budget_for_write(db, budget_id, tenant_id, lock_for_update=True)
    if old.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(f"Cannot version a {old.status.value} budget")

    # Mark old superseded BEFORE inserting new
    old.status = BudgetStatus.Superseded
    old.is_current = False
    db.flush()

    new = Budget(
        tenant_id=tenant_id,
        project_id=old.project_id,
        source_appraisal_id=old.source_appraisal_id,
        version_number=old.version_number + 1,
        version_label=version_label,
        is_current=True,
        status=BudgetStatus.Draft,
        created_by_user_id=user_id,
    )
    db.add(new)
    db.flush()

    for old_line in old.lines:
        cloned = BudgetLine(
            tenant_id=tenant_id,
            budget_id=new.id,
            cost_code_id=old_line.cost_code_id,
            cost_code_subcategory_id=old_line.cost_code_subcategory_id,
            entity_id=old_line.entity_id,
            line_description=old_line.line_description,
            original_budget=old_line.current_budget,
            current_budget=old_line.current_budget,
            ftc_method=old_line.ftc_method,
            percentage_complete=old_line.percentage_complete,
            forecast_to_complete=old_line.current_budget,
            forecast_final_cost=old_line.current_budget,
            variance_status=VarianceStatus.Green,
            display_order=old_line.display_order,
            notes=old_line.notes,
            linked_programme_task_id=old_line.linked_programme_task_id,  # B4 + decision 13
        )
        db.add(cloned)

    refresh_header_caches(db, new)
    db.flush()

    write_audit_log(
        db, action="budgets.create_version", resource="budgets",
        resource_id=str(new.id), user_id=user_id, tenant_id=tenant_id,
        metadata={
            "superseded_id": str(old.id),
            "new_version_number": new.version_number,
            "new_version_label": version_label,
            "lines_carried": len(new.lines),
        },
    )
    return new


def refresh_header_caches(db: Session, budget: Budget) -> None:
    """SQL-side aggregation (S1). Atomic, faster than Python loop."""
    row = db.execute(text("""
        SELECT
          COALESCE(SUM(current_budget), 0)            AS total_budget,
          COALESCE(SUM(actuals_to_date), 0)           AS total_actuals,
          COALESCE(SUM(committed_not_invoiced), 0)    AS total_cni,
          COALESCE(SUM(forecast_to_complete), 0)      AS total_ftc
        FROM budget_lines
        WHERE budget_id = :bid
    """), {"bid": str(budget.id)}).one()

    total_budget = Decimal(row.total_budget)
    total_actuals = Decimal(row.total_actuals)
    total_cni = Decimal(row.total_cni)
    total_ftc = Decimal(row.total_ftc)
    ffc = total_actuals + total_cni + total_ftc

    budget.total_budget = total_budget
    budget.total_actuals = total_actuals
    budget.total_committed_not_invoiced = total_cni
    budget.total_forecast_to_complete = total_ftc
    budget.forecast_final_cost = ffc
    budget.variance_vs_budget = ffc - total_budget
    budget.variance_pct = (
        ((ffc - total_budget) / total_budget * Decimal(100)) if total_budget > 0 else Decimal(0)
    )
    budget.summary_refreshed_at = datetime.now(timezone.utc)


def _load_budget_for_write(
    db: Session, budget_id: UUID, tenant_id: UUID, *, lock_for_update: bool = False,
) -> Budget:
    """Tenant-scoped load. Cross-tenant returns 404-equivalent (don't leak existence)."""
    stmt = (
        select(Budget)
        .where(Budget.id == budget_id, Budget.tenant_id == tenant_id)
        .options(selectinload(Budget.lines))
    )
    if lock_for_update:
        stmt = stmt.with_for_update()
    b = db.scalar(stmt)
    if b is None:
        raise BudgetStateError(f"Budget {budget_id} not found")
    return b
```

## Line service — `app/services/budget_lines.py` (new)

```python
"""Budget-line services: cache refresh, FTC, FFC, variance, lock-aware editing,
requires_attention scan, item CRUD with audit.
"""
from __future__ import annotations
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models.budgets import (
    BudgetLine, BudgetLineItem, FTCMethod, VarianceStatus,
    TERMINAL_BUDGET_STATUSES,
)
from app.models.system_config import SystemConfig
from app.services.audit import write_audit_log
from app.services.budget_errors import BudgetStateError
from app.services.budgets import refresh_header_caches


VARIANCE_AMBER_DEFAULT = Decimal("5")
VARIANCE_RED_DEFAULT = Decimal("10")
ITEM_AMOUNT_TOLERANCE = Decimal("0.01")


def compute_ftc(
    *, ftc_method: FTCMethod, current_budget: Decimal, actuals_to_date: Decimal,
    committed_value: Decimal, committed_not_invoiced: Decimal,
    percentage_complete: Decimal | None, manual_value: Decimal | None,
) -> Decimal:
    if ftc_method == FTCMethod.Manual:
        return manual_value if manual_value is not None else Decimal(0)
    if ftc_method == FTCMethod.Budget_Remaining:
        return max(Decimal(0), current_budget - actuals_to_date - committed_value)
    if ftc_method == FTCMethod.Committed_Only:
        return Decimal(0)
    if ftc_method == FTCMethod.Percentage_Complete:
        if percentage_complete and percentage_complete > 0:
            base = current_budget * (Decimal(100) - percentage_complete) / Decimal(100)
            return max(Decimal(0), base - committed_not_invoiced)
        return max(Decimal(0), current_budget - actuals_to_date - committed_value)
    raise ValueError(f"Unknown FTC method: {ftc_method}")


def compute_ffc_variance(
    *, current_budget: Decimal, actuals_to_date: Decimal,
    committed_not_invoiced: Decimal, ftc: Decimal,
    amber_threshold_pct: Decimal, red_threshold_pct: Decimal,
) -> tuple[Decimal, Decimal, Decimal, VarianceStatus]:
    """Returns (ffc, variance_value, variance_pct, variance_status).

    variance_pct is decimal(6,3) in DB. Caller is expected to clamp at
    presentation layer if business-realistic |variance_pct| > 999.999%.
    """
    ffc = actuals_to_date + committed_not_invoiced + ftc
    variance_value = ffc - current_budget
    variance_pct = (
        (variance_value / current_budget * Decimal(100)) if current_budget > 0 else Decimal(0)
    )
    abs_pct = abs(variance_pct)
    if abs_pct < amber_threshold_pct:
        status = VarianceStatus.Green
    elif abs_pct < red_threshold_pct:
        status = VarianceStatus.Amber
    else:
        status = VarianceStatus.Red
    return ffc, variance_value, variance_pct, status


def refresh_caches(db: Session, line: BudgetLine, *, manual_ftc: Decimal | None = None) -> None:
    line.current_budget = line.original_budget + line.approved_changes
    line.committed_not_invoiced = line.committed_value - line.invoiced_against_commitment

    amber_pct, red_pct = _load_variance_thresholds(db)
    ftc = compute_ftc(
        ftc_method=line.ftc_method,
        current_budget=line.current_budget,
        actuals_to_date=line.actuals_to_date,
        committed_value=line.committed_value,
        committed_not_invoiced=line.committed_not_invoiced,
        percentage_complete=line.percentage_complete,
        manual_value=manual_ftc if line.ftc_method == FTCMethod.Manual else None,
    )
    line.forecast_to_complete = ftc

    ffc, var_val, var_pct, status = compute_ffc_variance(
        current_budget=line.current_budget,
        actuals_to_date=line.actuals_to_date,
        committed_not_invoiced=line.committed_not_invoiced,
        ftc=ftc,
        amber_threshold_pct=amber_pct,
        red_threshold_pct=red_pct,
    )
    line.forecast_final_cost = ffc
    line.variance_value = var_val
    line.variance_pct = var_pct
    line.variance_status = status


def _load_variance_thresholds(db: Session) -> tuple[Decimal, Decimal]:
    """Load from SystemConfig if columns exist; fallback to in-code defaults.
    Columns added in a future prompt — see backlog."""
    cfg = db.scalar(select(SystemConfig).limit(1))
    if cfg is None:
        return VARIANCE_AMBER_DEFAULT, VARIANCE_RED_DEFAULT
    amber = getattr(cfg, "budget_variance_amber_threshold_pct", None) or VARIANCE_AMBER_DEFAULT
    red = getattr(cfg, "budget_variance_red_threshold_pct", None) or VARIANCE_RED_DEFAULT
    return Decimal(str(amber)), Decimal(str(red))


def update_line_fields(
    db: Session, *, line_id: UUID, fields: dict, user_id: UUID, tenant_id: UUID,
) -> BudgetLine:
    """Lock-aware AND terminal-state-aware (B2). Header rollup runs after (B1)."""
    line = db.scalar(
        select(BudgetLine)
        .where(BudgetLine.id == line_id, BudgetLine.tenant_id == tenant_id)
        .options(selectinload(BudgetLine.budget))
    )
    if line is None:
        raise ValueError(f"Budget line {line_id} not found")

    # B2: terminal-state guard
    if line.budget.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot edit lines on a {line.budget.status.value} budget"
        )

    EDITABLE_LOCKED = {"ftc_method", "forecast_to_complete", "percentage_complete", "notes"}
    EDITABLE_UNLOCKED = EDITABLE_LOCKED | {"line_description", "original_budget"}
    allowed = EDITABLE_LOCKED if line.is_locked else EDITABLE_UNLOCKED
    rejected = set(fields.keys()) - allowed
    if rejected:
        raise ValueError(
            f"Fields {rejected} cannot be edited "
            f"({'budget locked' if line.is_locked else 'not in editable set'})"
        )

    manual_ftc = None
    for k, v in fields.items():
        if k == "ftc_method":
            line.ftc_method = FTCMethod(v)
        elif k == "forecast_to_complete":
            manual_ftc = Decimal(str(v))
        else:
            setattr(line, k, v)

    refresh_caches(db, line, manual_ftc=manual_ftc)
    refresh_header_caches(db, line.budget)  # B1

    write_audit_log(
        db, action="budget_lines.edit", resource="budget_lines",
        resource_id=str(line.id), user_id=user_id, tenant_id=tenant_id,
        metadata={
            "fields_changed": list(fields.keys()),
            "budget_id": str(line.budget_id),
            "is_locked": line.is_locked,
        },
    )
    return line


def scan_requires_attention(db: Session, *, tenant_id: UUID | None = None) -> dict:
    """Endpoint-triggered (no scheduler — see backlog).
    Implements clauses 1 (variance_status=Red) and 2 (stale actuals).
    Clause 3 (programme task complete + under-billed) deferred to Prompt 3.2.
    Returns {flagged: int, cleared: int}.
    """
    # Two atomic UPDATE statements (set + clear), tenant-filtered when provided.
    # See spec lines 2911–2916.
    ...


# ===== budget_line_items CRUD with audit (B7) =====

def create_item(
    db: Session, *, budget_line_id: UUID, fields: dict, user_id: UUID, tenant_id: UUID,
) -> BudgetLineItem:
    """B13: append via relationship collection (keeps in-memory state consistent)."""
    line = _load_line_for_item_write(db, budget_line_id, tenant_id)
    item = BudgetLineItem(**fields)
    line.items.append(item)  # B13: relationship-driven, not direct FK assignment
    db.flush()
    _validate_items_sum(db, line)
    write_audit_log(
        db, action="budget_line_items.create", resource="budget_line_items",
        resource_id=str(item.id), user_id=user_id, tenant_id=tenant_id,
        metadata={"budget_line_id": str(budget_line_id), "amount": str(item.amount)},
    )
    return item


def update_item(
    db: Session, *, item_id: UUID, fields: dict, user_id: UUID, tenant_id: UUID,
) -> BudgetLineItem:
    item = db.scalar(
        select(BudgetLineItem)
        .where(BudgetLineItem.id == item_id)
        .options(selectinload(BudgetLineItem.line))
    )
    if item is None:
        raise ValueError(f"Item {item_id} not found")
    if item.line.tenant_id != tenant_id:
        raise ValueError(f"Item {item_id} not found")  # don't leak existence
    if item.line.budget.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot edit items on lines of a {item.line.budget.status.value} budget"
        )
    for k, v in fields.items():
        setattr(item, k, v)
    db.flush()
    _validate_items_sum(db, item.line)
    write_audit_log(
        db, action="budget_line_items.update", resource="budget_line_items",
        resource_id=str(item.id), user_id=user_id, tenant_id=tenant_id,
        metadata={"fields_changed": list(fields.keys())},
    )
    return item


def delete_item(db: Session, *, item_id: UUID, user_id: UUID, tenant_id: UUID) -> None:
    item = db.scalar(
        select(BudgetLineItem)
        .where(BudgetLineItem.id == item_id)
        .options(selectinload(BudgetLineItem.line))
    )
    if item is None:
        raise ValueError(f"Item {item_id} not found")
    if item.line.tenant_id != tenant_id:
        raise ValueError(f"Item {item_id} not found")
    if item.line.budget.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot delete items on lines of a {item.line.budget.status.value} budget"
        )
    line = item.line
    write_audit_log(
        db, action="budget_line_items.delete", resource="budget_line_items",
        resource_id=str(item.id), user_id=user_id, tenant_id=tenant_id,
        metadata={"budget_line_id": str(line.id), "amount": str(item.amount)},
    )
    db.delete(item)
    db.flush()
    _validate_items_sum(db, line)


def _load_line_for_item_write(db: Session, line_id: UUID, tenant_id: UUID) -> BudgetLine:
    line = db.scalar(
        select(BudgetLine)
        .where(BudgetLine.id == line_id, BudgetLine.tenant_id == tenant_id)
        .options(selectinload(BudgetLine.budget), selectinload(BudgetLine.items))
    )
    if line is None:
        raise ValueError(f"Budget line {line_id} not found")
    if line.budget.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot manage items on lines of a {line.budget.status.value} budget"
        )
    return line


def _validate_items_sum(db: Session, line: BudgetLine) -> None:
    """Spec 2946: sum validates against line but non-blocking. Log warning only."""
    items_total = sum((i.amount for i in line.items), Decimal(0))
    if abs(items_total - line.original_budget) > ITEM_AMOUNT_TOLERANCE:
        import logging
        logging.getLogger(__name__).warning(
            "Items sum mismatch on budget_line %s: items=%s, original_budget=%s",
            line.id, items_total, line.original_budget,
        )
```

---

# §R4 — API endpoints

## Route module

`/app/backend/app/routes/budgets.py` (new). **Read `/app/backend/app/routes/appraisals.py` first; replicate tenant-scoping verbatim.** Register in `app/main.py`:

```python
from app.routes.budgets import router as budgets_router
app.include_router(budgets_router, prefix="/api/v1", tags=["budgets"])
```

## Endpoint table

| # | Method & Path | Purpose | Permission | Returns |
|---|---|---|---|---|
| 1 | `GET    /api/v1/projects/{project_id}/budgets` | List (filter `?is_current=true`) | `budgets.view` | `list[BudgetSummary]` |
| 2 | `GET    /api/v1/budgets/{budget_id}` | Detail with lines (eager) | `budgets.view` | `BudgetDetail` |
| 3 | `POST   /api/v1/projects/{project_id}/budgets/from-appraisal` | Create from approved appraisal | `budgets.create` | `BudgetDetail` (201) |
| 4 | `POST   /api/v1/budgets/{budget_id}/activate` | Draft → Active | `budgets.edit` | `BudgetDetail` |
| 5 | `POST   /api/v1/budgets/{budget_id}/lock` | Active → Locked | `budgets.edit` | `BudgetDetail` |
| 6 | `POST   /api/v1/budgets/{budget_id}/unlock` | Locked → Active (force-unlock) | `budgets.admin` | `BudgetDetail` |
| 7 | `POST   /api/v1/budgets/{budget_id}/close` | Any → Closed | `budgets.edit` | `BudgetDetail` |
| 8 | `POST   /api/v1/budgets/{budget_id}/new-version` | Clone, supersede old | `budgets.edit` | `BudgetDetail` (201) |
| 9 | `PATCH  /api/v1/budget-lines/{line_id}` | Edit line | `budgets.edit` | `BudgetLineDetail` |
| 10 | `GET    /api/v1/budget-lines/{line_id}/items` | List items | `budgets.view` | `list[BudgetLineItem]` |
| 11 | `POST   /api/v1/budget-lines/{line_id}/items` | Create item | `budgets.edit` | `BudgetLineItem` (201) |
| 12 | `PATCH  /api/v1/budget-line-items/{item_id}` | Edit item | `budgets.edit` | `BudgetLineItem` |
| 13 | `DELETE /api/v1/budget-line-items/{item_id}` | Delete item | `budgets.edit` | 204 |
| 14 | `POST   /api/v1/internal/budgets/refresh-attention` | Trigger scan | `budgets.admin` | `{flagged, cleared}` |

## Pydantic request schemas (B10)

`app/schemas/budgets.py` (new). Locked request bodies — DO NOT improvise.

| Endpoint | Schema | Required | Optional |
|---|---|---|---|
| POST `/from-appraisal` | `CreateBudgetFromAppraisalRequest` | `source_appraisal_id: UUID` | `notes: str` |
| POST `/{id}/new-version` | `CreateNewVersionRequest` | `version_label: str` (max 50) | `notes: str` |
| POST `/{id}/activate` | `(no body)` | — | — |
| POST `/{id}/lock` | `(no body)` | — | — |
| POST `/{id}/unlock` | `(no body)` | — | — |
| POST `/{id}/close` | `(no body)` | — | — |
| PATCH `/budget-lines/{id}` | `UpdateBudgetLineRequest` (all optional) | — | `line_description, ftc_method, forecast_to_complete, percentage_complete, notes, original_budget` |
| POST `/budget-lines/{id}/items` | `CreateBudgetLineItemRequest` | `description, amount, display_order` | `quantity, unit, rate, notes` |
| PATCH `/budget-line-items/{id}` | `UpdateBudgetLineItemRequest` (all optional) | — | `description, quantity, unit, rate, amount, notes, display_order` |

All schemas inherit `BaseModel` from pydantic v2; use `model_config = ConfigDict(extra='forbid')` to reject unknown fields strictly.

## Response shapes

Three response shapes (`BudgetSummary`, `BudgetDetail`, `BudgetLineDetail`).

`view_sensitive` permission gates whether `total_actuals`, `total_committed_not_invoiced`, `forecast_final_cost`, `variance_vs_budget`, `variance_pct` appear — when caller lacks `budgets.view_sensitive`, fields are **omitted** (not nulled).

```python
def _serialise_budget(b: Budget, *, include_sensitive: bool) -> dict:
    base = {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "version_number": b.version_number,
        "version_label": b.version_label,
        "is_current": b.is_current,
        "status": b.status.value,
        "total_budget": float(b.total_budget),
        # ... non-sensitive fields ...
    }
    if include_sensitive:
        base.update({
            "total_actuals": float(b.total_actuals),
            "total_committed_not_invoiced": float(b.total_committed_not_invoiced),
            "forecast_final_cost": float(b.forecast_final_cost),
            "variance_vs_budget": float(b.variance_vs_budget),
            "variance_pct": float(b.variance_pct),
        })
    return base
```

## Error responses

- `BudgetCreationError` → `400 Bad Request`
- `BudgetStateError` → `409 Conflict`
- Permission denial → `403 Forbidden`
- Not found / cross-tenant → `404 Not Found`
- Pydantic validation failure → `422 Unprocessable Entity`

---

# §R5 — Tests

## File: `/app/backend/tests/test_budgets.py` (new)

Match `tests/test_appraisals.py` fixture pattern exactly (module-scoped engine, function-scoped session, `_wipe_*()` teardown with `ALTER TABLE audit_log DISABLE TRIGGER USER`).

## Second-tenant fixture (B17) — locally scoped to test_budgets.py

```python
@pytest.fixture(scope="module")
def second_tenant(db_engine):
    """Second tenant for isolation tests. Cleaned up in module teardown."""
    from sqlalchemy import text
    with db_engine.begin() as conn:
        result = conn.execute(text(
            "INSERT INTO tenants (id, name) VALUES (gen_random_uuid(), 'Test Tenant 2 (budgets)') RETURNING id"
        ))
        tenant_id = result.scalar()
    yield tenant_id
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
```

DO NOT promote to global conftest without separate review.

## Concurrency simulation pattern (B9)

Synchronous pytest cannot run real concurrent threads against shared session. Tests #11, #13 use simulation: insert conflicting rows directly via raw SQL bypassing service, then call service expecting IntegrityError → mapped exception.

```python
def test_one_current_budget_per_project_invariant(db_session, sample_project, ...):
    # Manually insert an is_current=true row bypassing the service
    db_session.execute(text("""
        INSERT INTO budgets (id, tenant_id, project_id, source_appraisal_id, ...,
                             is_current, status, created_by_user_id)
        VALUES (gen_random_uuid(), :t, :p, :a, ..., true, 'Draft', :u)
    """), {"t": tenant_id, "p": sample_project.id, "a": appraisal.id, "u": user_id})
    db_session.commit()
    # Service call should fail at DB level
    with pytest.raises(BudgetCreationError, match="is_current budget already exists"):
        create_from_appraisal(db_session, project_id=sample_project.id,
                              source_appraisal_id=appraisal.id,
                              user_id=user_id, tenant_id=tenant_id)
```

## Query-count test pattern (B16)

```python
from sqlalchemy import event

def test_query_count_on_detail_endpoint(db_session, sample_budget_with_200_lines, admin_session):
    queries = []
    engine = db_session.get_bind()
    @event.listens_for(engine, "before_cursor_execute")
    def capture(conn, cursor, stmt, *args, **kwargs):
        queries.append(stmt)
    
    response = admin_session.get(f"/api/v1/budgets/{sample_budget_with_200_lines.id}")
    
    event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert len(queries) <= 5, f"N+1 regression: {len(queries)} queries fired"
```

## Test list (target ≥65)

### Unit — service layer (`TestBudgetCreation`)
1. `test_create_from_approved_appraisal_succeeds`
2. `test_create_blocked_when_appraisal_not_approved`
3. `test_create_blocked_when_no_approved_appraisal_exists`
4. `test_create_blocked_when_existing_current_budget`
5. `test_clone_preserves_cost_code_id_and_entity_id_per_line`
6. `test_original_budget_total_matches_appraisal_total_cost` (AC line 2936)
7. `test_create_writes_audit_log_with_metadata`
8. `test_create_handles_appraisal_units_aggregation`
9. `test_create_blocked_when_cost_line_effective_value_null` (B5)
10. `test_create_handles_zero_cost_lines_appraisal`
11. `test_create_from_appraisal_merges_cost_line_and_unit_aggregation` (B11/T21) — given a cost_line at (cost_code=X, NULL subcat) AND a unit aggregation at (cost_code=X, NULL subcat), assert ONE budget_line with summed original_budget

### Concurrency simulation (`TestBudgetConcurrency`)
12. `test_concurrent_create_from_appraisal_one_succeeds_one_409s` (B3, simulation)
13. `test_one_current_budget_per_project_invariant` (B3, simulation)
14. `test_concurrent_lock_serialised_via_select_for_update` — verifies the SELECT FOR UPDATE pattern doesn't deadlock; runs two sessions in sequence

### Tenant isolation (`TestTenantIsolation`)
15. `test_tenant_isolation_get_budget_detail_404_cross_tenant`
16. `test_tenant_isolation_list_budgets_excludes_other_tenants`
17. `test_tenant_isolation_create_from_appraisal_rejects_cross_tenant_appraisal`
18. `test_tenant_isolation_patch_line_404_cross_tenant`
19. `test_tenant_isolation_item_crud_404_cross_tenant`

### Status transitions (`TestBudgetStatus`)
20. `test_activate_draft_to_active`
21. `test_activate_blocked_from_non_draft`
22. `test_lock_active_to_locked` (asserts is_locked=true on lines)
23. `test_lock_blocked_from_draft`
24. `test_unlock_locked_to_active`
25. `test_unlock_blocked_from_active`
26. `test_close_from_each_non_terminal_status` (parameterised)
27. `test_close_blocked_from_terminal` (parameterised)
28. `test_create_new_version_supersedes_old`
29. `test_create_new_version_clones_lines_with_current_as_original`
30. `test_create_new_version_carries_programme_task_link` (B4 / decision 13)
31. `test_create_new_version_does_not_carry_items`
32. `test_create_new_version_blocked_from_terminal`
33. `test_lock_in_memory_line_state_consistent_with_db` (B8/T22) — load lines, lock, assert b.lines all show is_locked=true without re-query
34. `test_unlock_in_memory_line_state_consistent_with_db` (B8/T23)

### Audit log coverage (`TestAuditLog`)
35. `test_lock_writes_audit_log_with_previous_status_metadata` (S6)
36. `test_unlock_writes_audit_log_with_director_metadata`
37. `test_close_writes_audit_log`
38. `test_activate_writes_audit_log`
39. `test_create_version_writes_audit_log_with_superseded_id`
40. `test_item_crud_writes_audit_log` (parameterised: create/update/delete) (B7)

### FTC / FFC / variance (`TestFTCAndVariance`)
41. `test_ftc_manual_uses_provided_value`
42. `test_ftc_budget_remaining`
43. `test_ftc_budget_remaining_zero_floor`
44. `test_ftc_committed_only_returns_zero`
45. `test_ftc_percentage_complete`
46. `test_ftc_percentage_complete_falls_back_to_budget_remaining_when_zero`
47. `test_ffc_equals_actuals_plus_cni_plus_ftc`
48. `test_variance_value_equals_ffc_minus_current_budget`
49. `test_variance_pct_zero_when_current_budget_zero`
50. `test_variance_status_green_amber_red_thresholds` (parameterised)
51. `test_variance_status_uses_system_config_thresholds`
52. `test_current_budget_equals_original_plus_approved_changes`
53. `test_variance_pct_overflow_handled_gracefully`

### Line edits (`TestLineEdits`)
54. `test_update_line_unlocked_allows_description_edit`
55. `test_update_line_locked_rejects_description_edit`
56. `test_update_line_locked_allows_ftc_method_change`
57. `test_update_line_locked_allows_percentage_complete`
58. `test_update_line_locked_allows_notes`
59. `test_update_line_writes_audit_log`
60. `test_patch_line_blocked_when_parent_budget_closed_409` (B2)
61. `test_patch_line_blocked_when_parent_budget_superseded_409` (B2)
62. `test_header_caches_refresh_after_line_edit` (B1)

### Items (`TestBudgetLineItems`)
63. `test_create_item_attaches_to_line`
64. `test_create_item_via_relationship_collection_populated` (B13/T24) — assert line.items contains new item without re-query
65. `test_item_amount_validation_warns_but_does_not_block`
66. `test_delete_line_cascades_items`
67. `test_item_crud_blocked_when_parent_budget_terminal`
68. `test_update_item_cross_tenant_404`

### Header rollup (`TestHeaderRollup`)
69. `test_header_caches_sum_lines_correctly` (S1: SQL aggregation)
70. `test_header_summary_refreshed_at_advances_on_recompute`
71. `test_unique_constraint_enforced_when_subcategory_null` (B6)

### Permissions (`TestPermissions`)
72. `test_existing_budgets_approve_perm_still_present` (B23/T25) — regression guard
73. `test_pm_role_has_budgets_create_after_seed`
74. `test_pm_role_does_not_have_budgets_admin`
75. `test_director_role_has_budgets_admin_via_set_difference`

### Scheduled job (`TestRequiresAttention`)
76. `test_requires_attention_flags_red_variance`
77. `test_requires_attention_flags_stale_actuals`
78. `test_requires_attention_clears_when_no_longer_matching`

### HTTP integration (`TestBudgetEndpoints`)
79. `test_post_from_appraisal_201_with_pm_session`
80. `test_post_from_appraisal_403_with_readonly_session`
81. `test_post_from_appraisal_403_with_site_manager_session`
82. `test_get_budget_detail_includes_lines_eager`
83. `test_get_budget_detail_omits_sensitive_for_pm_without_view_sensitive`
84. `test_get_budget_detail_includes_sensitive_for_finance_session`
85. `test_post_lock_endpoint_with_pm_session`
86. `test_post_unlock_endpoint_403_with_pm_session`
87. `test_post_unlock_endpoint_with_director_session`
88. `test_post_new_version_returns_201_supersedes_old`
89. `test_get_list_budgets_for_project_filters_by_is_current`
90. `test_post_create_rejects_unknown_fields_via_pydantic_strict` (B10) — extra='forbid' enforced

### Performance / N+1 guard (`TestPerformance`)
91. `test_query_count_on_detail_endpoint` (S4 — assert ≤5 queries for 200-line budget)

**91 distinct test functions.** With parameterisation expansion → ~110 cases. Target lower bound: **≥65**.

### Test run command

```bash
cd /app/backend && python -m pytest tests/test_budgets.py -xvs --ignore=tests/test_c3_governance_smoke.py
cd /app/backend && python -m pytest --ignore=tests/test_c3_governance_smoke.py
```

Expected: 597 + ≥65 new = **≥662 passing, 0 failing**.

---

# §R6 — Permissions + role mappings

## `app/seed_rbac.py` modifications

### 1. Append to PERMISSION_CATALOGUE

```python
# OLD
PERMISSION_CATALOGUE += _perms_for(
    "budgets",
    include=["view", "view_sensitive", "create", "edit", "approve"],
)

# NEW
PERMISSION_CATALOGUE += _perms_for(
    "budgets",
    include=["view", "view_sensitive", "create", "edit", "approve", "admin"],
    sensitive={"admin"},
)
```

### 2. Fix `project_manager` role mapping

Add `"budgets.create"`:
```python
"budgets.view", "budgets.view_sensitive", "budgets.create", "budgets.edit",
```

DO NOT add `budgets.admin` to PM (director-only).

### 3. Director — auto-includes via set-difference (verify)

### 4. Other roles — no action

## Verification

```bash
cd /app/backend && python -c "from app.seed_rbac import seed_rbac; seed_rbac()"

psql -d $DATABASE_NAME -c "SELECT code FROM permissions WHERE code LIKE 'budgets.%' ORDER BY code;"
# Expect 6 rows

psql -d $DATABASE_NAME -c "SELECT COUNT(*) FROM permissions;"
# Expect: 84

# Director has budgets.admin
psql -d $DATABASE_NAME -c "
  SELECT 1 FROM permissions p
  JOIN role_permissions rp ON rp.permission_id = p.id
  JOIN roles r ON r.id = rp.role_id
  WHERE r.code='director' AND p.code='budgets.admin';"

# PM has budgets.create
psql -d $DATABASE_NAME -c "
  SELECT 1 FROM permissions p
  JOIN role_permissions rp ON rp.permission_id = p.id
  JOIN roles r ON r.id = rp.role_id
  WHERE r.code='project_manager' AND p.code='budgets.create';"

# PM does NOT have budgets.admin
psql -d $DATABASE_NAME -c "
  SELECT 1 FROM permissions p
  JOIN role_permissions rp ON rp.permission_id = p.id
  JOIN roles r ON r.id = rp.role_id
  WHERE r.code='project_manager' AND p.code='budgets.admin';"
# Expect 0 rows
```

---

# §R7 — Bookkeeping

## 1. `tests/test_bootstrap.py` head sentinel

```python
assert head.startswith("0024_"), f"Expected head 0024_*, got {head}"
```

## 2. CHANGELOG.md entry

```markdown
### Prompt 2.4A — Budgets Core (Backend)

**Scope:** Backend only. Frontend deferred to 2.4B.

**Migrations:**
- `0024_budgets` — 3 tables, 3 enums, 6 standard indexes, 2 partial unique indexes
  (`uq_budgets_one_current_per_project`, `uq_budget_lines_no_subcat_unique`),
  3 updated_at triggers.

**Models:** `app/models/budgets.py` — `Budget`, `BudgetLine`, `BudgetLineItem` + 3 enums.

**Services:**
- `app/services/budget_errors.py` — shared `BudgetCreationError` and `BudgetStateError`.
- `app/services/budgets.py` — header lifecycle (create_from_appraisal with cost_lines+units
  merge, activate, lock, unlock, close, create_new_version, refresh_header_caches via
  SQL aggregation). SELECT FOR UPDATE on lock/unlock/version operations.
  synchronize_session='fetch' on bulk line is_locked updates.
- `app/services/budget_lines.py` — line cache refresh, FTC/FFC/variance computation,
  lock-aware AND terminal-state-aware editing, scan_requires_attention (endpoint-only),
  item CRUD via line.items.append() with audit logging.

**API:** `app/routes/budgets.py` — 14 endpoints. Tenant-scoped. Pydantic strict
(extra='forbid') on all request bodies.

**Permissions:** `+1` (`budgets.admin`). Total: 84.

**Role mapping fix:** `project_manager` gains `budgets.create`.

**Tests:** `tests/test_budgets.py` — 65+ tests. Total: ≥662 passing.

**Concurrency safety:**
- Partial unique indexes prevent duplicate is_current and null-subcategory collisions.
- SELECT FOR UPDATE on lock/unlock/version-bump.
- `synchronize_session='fetch'` on bulk line updates.

**Deferred / out of scope:**
- `budget_line_periods` → cash-flow prompt; backlog.
- `linked_programme_task_id` FK → Prompt 3.2.
- Frontend → 2.4B.
- Xero hooks → Track 6.
- Scheduling, idempotency keys, SystemConfig threshold cols, decimal-as-string serialisation,
  audit metadata standardisation, item-warnings response array, project-completion gating
  on close — all backlog.

**Bootstrap:** rc=0 against `0024_budgets`.
```

## 3. Build Pack at `/app/docs/SY_Hub_Prompt_2_4A_Backend_Build_Pack.md`

## 4. Backlog updated — Appendix A

## 5. Chat-summary at `/app/docs/chat-summaries/chat-16-closing.md`

```markdown
# Chat 16 closing — 2026-05-08

## What shipped this session
- Prompt 2.4A — migration `0024_budgets`, 3 ORM models, 3 service modules
  (incl. shared budget_errors), 14 API endpoints with strict Pydantic schemas, 65+ tests.
- Permissions: +1 (`budgets.admin`). Total 84.
- Role mapping fix: PM gains `budgets.create`.
- Concurrency safeguards: 2 partial unique indexes + SELECT FOR UPDATE + synchronize_session='fetch'.
- Bootstrap rc=0; head sentinel updated to `0024_`.

## What's next
- Chat 17: Prompt 2.4B (frontend grid, drawer, lock/close UI, E2E).

## Locked state for Chat 17
- alembic head: `0024_budgets`
- test count: ≥662 passing (with `--ignore=tests/test_c3_governance_smoke.py`)
- Permissions: 84. Roles: 10.

## Open items rolled forward
- Future_Tasks §3 (CI), §4 (smoke test reclassification), §5 (4 RESTRICT FKs in 0022).
- 9 backlog entries from this prompt (see SY_Homes_Phase2_Backlog.md):
  budget_line_periods, scheduling infra, SystemConfig thresholds, idempotency keys,
  internal endpoint auth, SOX activate gating, decimal-as-string serialisation,
  audit metadata standardisation, item-warnings response array, project-completion
  gating on close.
```

---

# §R8 — Self-verification (acceptance criteria)

| # | AC | Verified by |
|---|---|---|
| 1 | Cannot create budget without Approved appraisal | Tests #2, #3 |
| 2 | Budget creation clones cost lines correctly | Test #5 |
| 3 | Original_budget total matches appraisal total | Test #6 |
| 4 | Manual FTC override works | Test #41 |
| 5 | Budget_Remaining FTC auto-calculates | Tests #42, #43 |
| 6 | Committed_Only FTC returns 0 | Test #44 |
| 7 | Percentage_Complete FTC | Tests #45, #46 |
| 8 | FFC = actuals + CNI + FTC | Test #47 |
| 9 | Variance status thresholds | Test #50 |
| 10 | Lock disables original_budget edits | Test #55 |
| 11 | Lock allows FTC/%/notes edits | Tests #56, #57, #58 |
| 12 | Unlock re-enables direct edits | Test #87 + post-unlock edit |
| 13 | Item sums non-blocking | Test #65 |
| 14 | Cached header refresh on line change | Tests #62, #69 |
| 15 | requires_attention scheduled job | Tests #76, #77, #78 (clause 3 deferred) |

---

# §5 — Self-report template

```markdown
## Prompt 2.4A self-report — <DATE>

### Shipped THIS session
- [ ] Migration `0024_budgets` applied; head confirmed
- [ ] 3 ORM models, 3 service modules, 1 schemas module, 1 routes module
- [ ] `seed_rbac.py` modified (+1 perm, PM mapping fix)
- [ ] `tests/test_budgets.py` with N tests (state N)
- [ ] `tests/test_bootstrap.py` head sentinel → `0024_`
- [ ] CHANGELOG entry
- [ ] Build Pack committed at `/app/docs/SY_Hub_Prompt_2_4A_Backend_Build_Pack.md`
- [ ] Backlog updated at `/app/docs/SY_Homes_Phase2_Backlog.md` (10 entries total)
- [ ] Chat-summary at `/app/docs/chat-summaries/chat-16-closing.md`

### Already there (NOT re-shipped)
- `budgets.{view, view_sensitive, create, edit, approve}` (already seeded)
- audit-log, fixtures, bootstrap, cost_codes/appraisals/entities/projects/users/tenants/system_config tables
- `require_permission()`, session fixtures, audit_log teardown pattern

### Numerical verification
- `alembic current`: <PASTE>
- Tests: <N> passing, <N> failed (target: ≥662 passing)
- Permissions: <N> (target: 84)
- Roles: <N> (target: 10)
- Bootstrap rc: <N> (target: 0)

### Concurrency / safety
- [ ] Partial unique indexes present (both)
- [ ] SELECT FOR UPDATE confirmed in lock/unlock/version code
- [ ] `synchronize_session='fetch'` confirmed on bulk line updates
- [ ] Concurrency simulation tests pass

### Deviations from Build Pack
- <List any.>

### Risks surfaced
- <List any.>
```

---

# §6 — Chat-end ritual

```bash
cd /app/backend && python -m pytest --ignore=tests/test_c3_governance_smoke.py 2>&1 | tee /tmp/test-run.log
cd /app/backend && python -m app.bootstrap; echo "BOOTSTRAP_RC=$?"
cd /app/backend && alembic current
psql -d $DATABASE_NAME -c "SELECT COUNT(*) AS perm_count FROM permissions;"
psql -d $DATABASE_NAME -c "SELECT COUNT(*) AS role_count FROM roles;"
psql -d $DATABASE_NAME -c "
  SELECT indexname FROM pg_indexes
  WHERE indexname IN ('uq_budgets_one_current_per_project',
                      'uq_budget_lines_no_subcat_unique');"
cd /app && git status

cd /app && git add backend/alembic/versions/0024_budgets.py \
                  backend/app/models/budgets.py \
                  backend/app/services/budget_errors.py \
                  backend/app/services/budgets.py \
                  backend/app/services/budget_lines.py \
                  backend/app/schemas/budgets.py \
                  backend/app/routes/budgets.py \
                  backend/app/seed_rbac.py \
                  backend/app/main.py \
                  backend/tests/test_budgets.py \
                  backend/tests/test_bootstrap.py \
                  docs/SY_Hub_Prompt_2_4A_Backend_Build_Pack.md \
                  docs/SY_Homes_Phase2_Backlog.md \
                  docs/chat-summaries/chat-16-closing.md \
                  CHANGELOG.md

cd /app && git commit -m "Prompt 2.4A: Budgets Core (backend) — migration 0024, 3 models, 14 endpoints, 65+ tests"
cd /app && git push origin main

# Self-report (paste §5 template)
```

---

# §7 — Risks

## Tier 1 (security or ship-blocking)

1. **Tenant isolation** (B14). Multi-tenant data leak is a security bug. Mitigation: read `routes/appraisals.py` first, replicate verbatim. Tests #15–#19 verify.
2. **AppraisalUnit cost_code_id assumption.** Service guards by raising loud (STOP-and-resplit trigger #8). Agent reads model in pre-flight; if no `cost_code_id`, posts STOP.
3. **Performance budget** on detail endpoint. Asserted via test #91 (≤5 queries).
4. **Permission count drift.** Pre-flight check verifies actual count = expected 83 before changes.

## Tier 2 (mid-build issues)

5. **`appraisals.status='Approved'` enum verification** — pre-flight check.
6. **`Appraisal.tenant_id` column existence (B12)** — pre-flight check.
7. **`SystemConfig` threshold attribute names** — fallback to in-code defaults; backlog.
8. **Cost lines + unit aggregation merge** (B11) — locked sum behaviour. Test #11 verifies.
9. **Concurrent lock** — mitigated by SELECT FOR UPDATE; verified by test #14.
10. **Concurrent create_from_appraisal** — mitigated by partial unique index; verified by tests #12, #13.

## Tier 3 (low impact)

11. **`linked_programme_task_id` no FK constraint** — comment in migration.
12. **`linked_programme_task_id` carry-on-version-bump** — locked decision 13. Revisitable.
13. **`variance_pct` decimal(6,3) overflow** — test #53 documents.
14. **Internal endpoint auth strategy** — backlog.
15. **`budget_lines.original_budget` editable when unlocked but approved_changes > 0** — Phase 1 spec doesn't constrain. 2.6 may add gate.

---

# §8 — Pre-paste auditor notes (Chat 16 → Rhys)

1. **`AppraisalUnit.cost_code_id` is the highest-risk unknown** — Tier 1 R2. Worth uploading `app/models/appraisals.py` if you want v4 to lock aggregation logic concretely.
2. **B11 merge logic** — uses `(cost_code_id, subcategory_id, entity_id)` as merge key. Doesn't merge across entities (multi-entity hard constraint). Test #11 verifies.
3. **B18 carry-on-version-bump** — locked as decision 13 (carry forward, lower data loss). Documented in `create_new_version` docstring. Revisitable.
4. **Test count ≥65; spec lists 91 functions** — parameterisation expansion → ~110 cases.
5. **`budgets.approve` perm** — exists, not exercised this prompt. Likely 2.6 or alternate-activate-gate. Don't reassign.
6. **Migration `0024_budgets`** — 12 chars, comfortable margin under 32-char limit.
7. **`budget_line_periods` deferral + 9 other backlog entries** committed in same commit as code.
8. **Bootstrap orchestrator interactions** — confirm rc=0.
9. **B8 synchronize_session='fetch'** — necessary for in-memory line consistency after bulk update on lock/unlock. Tested by #33, #34.
10. **B13 `line.items.append(item)` pattern** — keeps relationship collection consistent. Tested by #64.
11. **Pydantic strict mode** (`extra='forbid'`) — rejects unknown fields with 422. Tested by #90.
12. **`ITEM_AMOUNT_TOLERANCE = £0.01`** — match spec line 2946 exactly.

---

# §9 — Audit changelog

| Version | Date | Author | Changes |
|---|---|---|---|
| v1 | 2026-05-08 | Chat 16 | Initial draft, ~1,500 lines. |
| v2 | 2026-05-08 | Chat 16 | Tier 1 fixes B1–B7, recommended Tier 2/3 items, Tier 4 (20 new tests). ~1,950 lines. |
| v3 | 2026-05-08 | Chat 16 | **Tier 1 fixes B8–B12**: synchronize_session='fetch' on bulk line updates (B8), concurrency simulation pattern for tests (B9), Pydantic request schema enumeration table (B10), cost_lines+units merge behaviour locked (B11), Appraisal.tenant_id pre-flight check (B12). **Recommended Tier 2 items B13–B18**: relationship-driven item add (B13), tenant scoping elevated to Tier 1 risk (B14), shared `budget_errors.py` module (B15), query-count test snippet (B16), second-tenant fixture spec (B17), carry-on-version-bump decision documented as locked decision 13 (B18). **B23**: existing-perm regression test added. **Tier 4 tests T21–T25**: merge logic, in-memory state consistency × 2, relationship-collection populated, existing-perm regression. **Tier 3 deferred to backlog**: decimal-as-string serialisation (B19), audit metadata standardisation (B20), item-warnings response array (B21), close project-completion gating (B22). Test target now ≥65 (91 functions specced). 5 new locked decisions (13–15 + reaffirmation of 1–8). |

---

# Appendix A — Phase 2 Backlog entries

Add a new top-level section to `/app/docs/SY_Homes_Phase2_Backlog.md`, between `# SY Homes Platform — Future Tasks` (line 1) and `## Phase 2 — Operational Modules` (line 9):

```markdown
## Spec Reconciliation & Infrastructure Deferrals

Granular spec deferrals and infrastructure deferrals surfaced during build cycles.

### `budget_line_periods` — monthly time-phasing on budget lines

**Surfaced in:** Chat 16 / Prompt 2.4A drafting (2026-05-08)
**Conflict:** Phase 2 detail line 104 lists `budget_line_periods` as 3rd table for 2.4; Phase 1 names `budget_line_items`. Phase 2 says "deltas: none" — internally inconsistent.
**Resolution:** Phase 1 wins. `budget_line_items` shipped in 2.4A. `budget_line_periods` deferred.
**Target prompt:** Cash-flow prompt (TBD; `cash_flow` resource already in `seed_rbac.py`).
**What it does:** Time-phases budget lines across calendar months for cash-flow forecasting.
**Action:** Reconcile Phase 2 detail brief at next sweep.

### Scheduling infrastructure (APScheduler/Celery)

**Surfaced in:** Chat 16 / Prompt 2.4A drafting (2026-05-08)
**Item:** No background-job scheduler wired. Prompt 2.4A specs daily `scan_requires_attention` job; shipped as endpoint-only requiring external trigger.
**Action when picked up:** Dedicated infra prompt covering scheduler choice, failure handling, monitoring, backfill semantics across all background jobs.

### SystemConfig variance threshold columns

**Surfaced in:** Chat 16 / Prompt 2.4A drafting (2026-05-08)
**Item:** Spec requires variance thresholds from SystemConfig. 2.4A ships in-code defaults (5% amber, 10% red).
**Action:** Add `budget_variance_amber_threshold_pct numeric(5,2)` and `budget_variance_red_threshold_pct numeric(5,2)`. Replace `_load_variance_thresholds()` fallback with hard-fail.

### Idempotency keys on create endpoints

**Surfaced in:** Chat 16 / Prompt 2.4A audit (2026-05-08)
**Item:** Network retry could double-create. Need cross-cutting `Idempotency-Key` header pattern.
**Action:** Dedicated infra prompt covering all create endpoints.

### Internal-endpoint auth strategy

**Surfaced in:** Chat 16 / Prompt 2.4A audit (2026-05-08)
**Item:** Internal endpoints currently gated by user perms; cron callers awkward.
**Action:** Choose between service tokens, bootstrap super_admin service principal, or IPC.

### SOX-style separation of duties on activate

**Surfaced in:** Chat 16 / Prompt 2.4A audit (2026-05-08)
**Item:** Currently `Draft → Active` gated by `budgets.edit` (PM can activate). SOX practice = director sign-off.
**Action:** Raise at next team review with MD/Louise. Cheap fix: re-gate to `budgets.admin`.

### Decimal-as-string JSON serialisation across financial APIs

**Surfaced in:** Chat 16 / Prompt 2.4A audit (B19, 2026-05-08)
**Item:** `_serialise_budget` uses `float(decimal)`. Loses precision above ~£10M. State-of-the-art financial APIs serialise as string ("123456.78"); frontend parses back to BigDecimal.
**Why deferred:** Cross-cutting; affects appraisals, budgets, actuals, commitments, etc. Should land as a single coordinated change.
**Action:** Audit all financial endpoints; introduce `Decimal` → string serialiser; update frontend parsing.

### Audit-log metadata standardisation

**Surfaced in:** Chat 16 / Prompt 2.4A audit (B20, 2026-05-08)
**Item:** Current audit metadata is ad-hoc (`previous_status`, `lines_locked_count`, `superseded_id`...). State-of-the-art: standard `{before: {...}, after: {...}, context: {...}}` shape across all writers.
**Why deferred:** Cross-cutting. Forensic-grade audit is a dedicated cleanup pass.
**Action:** Audit-schema cleanup prompt covering all writers.

### Warnings array on item validation responses

**Surfaced in:** Chat 16 / Prompt 2.4A audit (B21, 2026-05-08)
**Item:** Spec requires items.amount sum validation against line.original_budget to be "non-blocking." Currently logs warning only; API consumer never sees it.
**Action:** Add `warnings: list[str]` to `BudgetLineItem` and `BudgetLine` response shapes; populate when sum mismatch; UI shows yellow banner. Cheap, useful.

### Close trigger gating on project completion

**Surfaced in:** Chat 16 / Prompt 2.4A audit (B22, 2026-05-08)
**Item:** Spec line 2909 implies project completion as the trigger for close. 2.4A lets any user with `budgets.edit` close.
**Action:** Integrate project lifecycle when projects gain a status field. Gate close on `project.status='Completed'` or director override.
```

---

# Appendix B — Locked filenames cheat-sheet

| Purpose | Path |
|---|---|
| Migration | `/app/backend/alembic/versions/0024_budgets.py` |
| ORM models | `/app/backend/app/models/budgets.py` |
| Shared exceptions | `/app/backend/app/services/budget_errors.py` (NEW MODULE — B15) |
| Header service | `/app/backend/app/services/budgets.py` |
| Line service | `/app/backend/app/services/budget_lines.py` |
| Pydantic schemas | `/app/backend/app/schemas/budgets.py` |
| API routes | `/app/backend/app/routes/budgets.py` |
| Tests | `/app/backend/tests/test_budgets.py` |
| Seed RBAC | `/app/backend/app/seed_rbac.py` (modify in place) |
| Bootstrap test | `/app/backend/tests/test_bootstrap.py` (modify head sentinel) |
| Main app | `/app/backend/app/main.py` (register router) |
| CHANGELOG | `/app/CHANGELOG.md` (append) |
| Build Pack | `/app/docs/SY_Hub_Prompt_2_4A_Backend_Build_Pack.md` (this file) |
| Backlog | `/app/docs/SY_Homes_Phase2_Backlog.md` (Appendix A entries) |
| Chat summary | `/app/docs/chat-summaries/chat-16-closing.md` |

---

**End of Build Pack v3.** Paste-ready pending Rhys's confirmation.
