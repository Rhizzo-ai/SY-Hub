# SY Homes Operations Platform — Product Requirements Document

## Original Problem Statement
SY Homes is a UK property development company. This platform replaces spreadsheets, WhatsApp, and Buildertrend with a single system of record for development and construction operations. Phase 1 scope: 77 tables across 10 modules delivered via 25 sequential build prompts.

## Stack (locked)
- **Database**: PostgreSQL 15 (`syhomes` DB, user `syhomes`). Managed via `pg_ctlcluster` + idempotent bootstrap in `/root/.emergent/on-restart.sh` (survives container rebuilds). Supervisor manages backend + frontend only.
- **Schema migrations**: Alembic — `/app/backend/alembic/`. All DDL lives in versioned migration files. `create_all()` is NOT used.
- **Backend**: FastAPI + SQLAlchemy 2.x + psycopg3 (sync); APScheduler for jobs
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn/Radix + RHF + Zod + date-fns-tz
- **Fonts**: Chivo (headings), IBM Plex Sans (body), IBM Plex Mono (numbers)
- **Hosting**: Supervisor-managed backend:8001, frontend:3000; postgresql:5432 (pg_ctlcluster)

## Conventions (applied globally)
- Tables plural snake_case; fields snake_case; FKs `_id`; timestamps `_at` UTC; dates `_date`; percentages `_pct`; booleans `is_`/`has_`; enums `PascalCase_With_Underscores`.
- IDs: UUID v4; Money: `DECIMAL(14,2)`; Percentages: `DECIMAL(6,3)` stored 0–100.
- FKs default `ON DELETE RESTRICT`; junctions `CASCADE`; status field for soft-archive on audit/financial tables.
- `created_at` + `updated_at` on every table; `updated_at` auto-refresh via PG trigger function `set_updated_at()`.
- Every table carries `tenant_id UUID NOT NULL` FK → `tenants.id` (Phase 1 single-tenant, multi-tenant ready).
- `created_by_user_id` to be added retrospectively in Prompt 1.2 (new migration).
- **All schema changes go through Alembic migrations — never edit SQLAlchemy models and skip the migration.**

## User Personas (Phase 1)
- **Finance Director** — cross-entity visibility, insurance compliance, Xero oversight.
- **Construction Manager** — programme, cost codes, project progress (later prompts).
- **Office Admin** — entity maintenance, Companies House / VAT updates, insurance renewals.
- **Developer/Ops Director** (superuser) — setup, entity structure, JV creation.

## Architecture
```
/app/backend/
├── server.py                       # FastAPI entrypoint; lifespan: alembic upgrade head → seed → start scheduler
├── alembic.ini
├── alembic/
│   ├── env.py                      # Loads .env; uses Base.metadata; compare_server_default=False (intentional)
│   └── versions/
│       └── 0001_initial_entities.py  # tenants + entities + 5 enums + partial indexes + trigger fn + triggers
├── .env                            # DATABASE_URL, DEFAULT_TENANT_NAME, INSURANCE_ALERT_HOUR_UTC
├── tests/
│   ├── conftest.py                 # loads .env before imports
│   ├── test_entities_api.py        # 31 API tests
│   └── test_insurance_alerts.py    # 22 threshold-sweep tests
└── app/
    ├── db.py                       # engine, Base, TimestampMixin (server_default=func.now())
    ├── deps.py                     # get_current_tenant_id (single-tenant lookup)
    ├── models/{tenant,entity}.py
    ├── schemas/entity.py
    ├── routers/{entities,meta}.py
    ├── seed.py                     # idempotent: 1 tenant + 3 entities
    └── jobs/insurance_alerts.py    # APScheduler daily 06:00 UTC; exact-threshold emissions

/root/.emergent/on-restart.sh       # Idempotent PG install + cluster start + user/db provisioning
```

## What's Been Implemented

### 2026-04-19 — Prompt 1.1: Entities ✅
- **Tables** (migration 0001): `tenants`, `entities` + 5 native PG enums. Partial-unique indexes on CH#/VAT# scoped `(tenant_id, field)`. Composite `(tenant_id, entity_type, status)`. Partial on `xero_org_id`. `set_updated_at()` trigger function + per-table `trg_*_updated_at` triggers.
- **API**: `/api/entities` (GET list q/type/status/sort/dir/page/page_size; GET detail with parent+children; POST; PUT; DELETE with children-guard + RESTRICT). `/api/meta/{tenant,enums,insurance-alerts}`. `/api/health`.
- **Validation**: CH 8-alphanumeric; VAT 9–12 digits; year_end `MM-DD`; bank account 8 digits → stored as `****NNNN`; parent cycle-prevention on create + update.
- **Seed** (idempotent): `SY Homes` tenant + `SY Homes Ltd` (Parent) + `SY Homes (Shrewsbury) Ltd` (SPV) + `SY Homes (Construction) Ltd` (ConstructionCo, CIS Contractor).
- **Scheduled job**: daily 06:00 UTC sweep — fires `_emit_alert` at exact threshold days `{60,30,14,7,0}` with severity labels `{60_day, 30_day, 14_day, 7_day, 0_day}` and daily `expired` while past due. Replaced with notifications-table writes in Prompt 1.7.
- **Preview endpoint** `/api/meta/insurance-alerts` returns UI-bucket severity `{upcoming, warning, critical, expired}` for the dashboard — independent vocabulary from the emit hook.
- **Frontend**: App shell (10 nav items, only Entities enabled); full CRUD UI; inline blur validation; insurance urgency highlighting; parent/children hierarchy navigation; UK date/money formatting; data-testid throughout.
- **Testing** (2026-04-19, iteration 2): 53/53 backend tests pass (31 API + 22 insurance-threshold sweep); all frontend scenarios verified; `alembic check` clean; `alembic current` → `0001_initial_entities (head)`.

## Prioritised Backlog (25-prompt plan — 7 foundation prompts)

### P0 — Next prompts (Foundation: 1.1 → 1.7)
- **1.2 — Users, Roles, Permissions**: argon2id, 10 roles, ~90 permissions, seed superuser, wire `created_by_user_id` retroactively onto entities (new Alembic migration). Register + enforce the 5 entity permissions (`entities.view`, `entities.view_sensitive`, `entities.create`, `entities.edit`, `entities.delete`).
- **1.3 — Sessions, Login History, Invitations, SSO, API Keys**: 15-min access + 30/90d refresh tokens, MFA (TOTP/SMS/Email), Google/Microsoft/Apple SSO link.
- **1.4, 1.5, 1.6** — remainder of Module 1.
- **1.7 — Notifications**: swap `_emit_alert` log hook for real notifications inserts scoped to director-role users.

### P1 — Other modules
- Projects (2.x), Cost Codes (3.x), Appraisals, Budgets, Cash Flow, Programme, Documents, Compliance.

### P2 — Integrations & phase 2
- Xero OAuth (5.1) populates `xero_org_id` / `xero_org_name`.
- Bank feed integration (deferred).
- Group consolidation reporting.
- Multi-tenancy surfacing.

## Deferred / Out of Scope for 1.1
- Xero connection (Prompt 5.1).
- Insurance document uploads (Prompt 4.2 — Documents).
- Bank feed (future).
- Group consolidation (Phase 2+).

## Operational Notes
- **Container restart**: `/root/.emergent/on-restart.sh` re-installs PG 15 and re-provisions the role/db if needed. Supervisor then starts backend (runs `alembic upgrade head` + seed in lifespan) and frontend. Data in `/var/lib/postgresql/15/main` survives supervisor restarts but **not** container rebuilds.
- **Adding a migration**: edit models → `cd /app/backend && alembic revision --autogenerate -m "<title>"` → review the generated file by hand (especially enums, partial indexes, triggers which don't autogenerate reliably) → `alembic upgrade head`. Backend lifespan re-runs `upgrade head` on next restart.
- **Drift check**: `alembic check` — must return `No new upgrade operations detected.` before declaring a prompt complete.
- `DEFAULT_TENANT_NAME=SY Homes` in `backend/.env` — seed resolves tenant by name.

## Process Commitments
- Never silently defer agreed-upon standards. If a deviation becomes attractive mid-flight (complexity, time, uncertainty), surface it in-channel before making the change — don't wait to be asked.
