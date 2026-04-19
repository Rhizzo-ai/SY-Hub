# SY Homes Operations Platform — Product Requirements Document

## Original Problem Statement
SY Homes is a UK property development company. This platform replaces spreadsheets, WhatsApp, and Buildertrend with a single system of record for development and construction operations. Phase 1 scope: 77 tables across 10 modules delivered via 25 sequential build prompts.

## Stack (locked)
- **Database**: PostgreSQL 15 (`syhomes` DB, user `syhomes`)
- **Backend**: FastAPI + SQLAlchemy 2.x + psycopg3 (sync); APScheduler for jobs
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn/Radix + RHF + Zod + date-fns-tz
- **Fonts**: Chivo (headings), IBM Plex Sans (body), IBM Plex Mono (numbers)
- **Hosting**: Supervisor-managed backend:8001, frontend:3000, postgresql:5432

## Conventions (applied globally)
- Tables plural snake_case; fields snake_case; FKs `_id`; timestamps `_at` UTC; dates `_date`; percentages `_pct`; booleans `is_`/`has_`; enums `PascalCase_With_Underscores`.
- IDs: UUID v4; Money: `DECIMAL(14,2)`; Percentages: `DECIMAL(6,3)` stored 0–100.
- FKs default `ON DELETE RESTRICT`; junctions `CASCADE`; status field for soft-archive on audit/financial tables.
- `created_at` + `updated_at` on every table; `updated_at` auto-refresh via PG trigger function `set_updated_at()`.
- Every table carries `tenant_id UUID NOT NULL` FK → `tenants.id` (Phase 1 single-tenant, multi-tenant ready).
- `created_by_user_id` to be added retrospectively in Prompt 1.2.

## User Personas (Phase 1)
- **Finance Director** — cross-entity visibility, insurance compliance, Xero oversight.
- **Construction Manager** — programme, cost codes, project progress (later prompts).
- **Office Admin** — entity maintenance, Companies House / VAT updates, insurance renewals.
- **Developer/Ops Director** (superuser) — setup, entity structure, JV creation.

## Architecture
```
/app/backend/
├── server.py                 # FastAPI entrypoint, lifespan: init schema + seed + start scheduler
├── .env                      # DATABASE_URL, DEFAULT_TENANT_NAME, INSURANCE_ALERT_HOUR_UTC
├── requirements.txt
└── app/
    ├── db.py                 # engine, Base, TimestampMixin, updated_at trigger installer
    ├── deps.py               # get_current_tenant_id (single-tenant lookup)
    ├── models/
    │   ├── tenant.py
    │   └── entity.py         # enums, partial-unique indexes, self-FK parent_entity_id
    ├── schemas/entity.py     # EntityCreate/Update/Read/Detail/ListResponse + InsuranceAlert
    ├── routers/
    │   ├── entities.py       # CRUD + cycle prevention + children block on delete
    │   └── meta.py           # /meta/enums, /meta/tenant, /meta/insurance-alerts
    ├── seed.py               # idempotent: 1 tenant + 3 entities
    └── jobs/
        └── insurance_alerts.py  # APScheduler daily 06:00 UTC; thresholds 60/30/14/7/0

/app/frontend/src/
├── App.js                    # router + AppShell + Toaster
├── components/
│   ├── AppShell.jsx          # sidebar (10 nav items, only Entities active) + topbar tenant badge
│   └── entity/
│       ├── EntityStatusBadge.jsx
│       ├── InsuranceBadge.jsx
│       └── EntityForm.jsx    # RHF + Zod; onBlur validation
├── pages/
│   ├── EntitiesList.jsx      # filters (type, status), search, sort, 50/page pagination, URL-sync
│   ├── EntityDetail.jsx      # Identity, Tax, Addresses, Insurance, Banking, Xero, Hierarchy, Notes
│   ├── EntityNew.jsx
│   └── EntityEdit.jsx
├── hooks/useTenant.js        # cached /meta/tenant + /meta/enums
└── lib/
    ├── api.js                # axios client, friendlyMessage interceptor
    └── format.js             # UK dates, GBP money, VAT/CH formatters, daysUntil
```

## What's Been Implemented

### 2026-04-19 — Prompt 1.1: Entities ✅
- **Tables**: `tenants`, `entities` (all spec fields + enum types: entity_type, vat_scheme, vat_return_period, cis_status, entity_status).
- **Indexes**: partial-unique on `companies_house_number` and `vat_number` (per tenant); composite on `(tenant_id, entity_type, status)`; partial on `xero_org_id`.
- **API**: `/api/entities` (GET list with `q`, `entity_type`, `status`, `include_struck_off`, `sort`, `dir`, pagination; GET by id with parent + children; POST; PUT; DELETE with children-guard + RESTRICT). `/api/meta/{tenant,enums,insurance-alerts}`. `/api/health`.
- **Validation**: CH 8-alphanumeric; VAT 9–12 digits; year_end `MM-DD`; bank account 8 digits → stored as `****NNNN`; cycle-prevention on parent changes.
- **Seed** (idempotent): `SY Homes` tenant + `SY Homes Ltd` (Parent) + `SY Homes (Shrewsbury) Ltd` (SPV) + `SY Homes (Construction) Ltd` (ConstructionCo, CIS Contractor).
- **Scheduled job**: daily 06:00 UTC insurance-expiry sweep across all tenants, logs alerts at thresholds 60/30/14/7/0 (replaces with notifications-table write in Prompt 1.7).
- **Frontend**: App shell with 10 disabled future-module nav items; full CRUD UI with inline blur validation; insurance badge urgency (amber <60d, red <14d, red "EXPIRED"); parent/children hierarchy navigation; UK-format dates; tabular-nums monospaced financial columns.
- **Testing**: 31/31 backend API tests pass (pytest); all frontend scenarios verified (list, filter, search, sort, create, edit, delete, hierarchy, insurance highlighting).

## Prioritised Backlog (25-prompt plan)

### P0 — Next prompts
- **Prompt 1.2 — Users, Roles, Permissions**: argon2id, 10 roles, ~90 permissions, seed superuser, wire `created_by_user_id` retroactively to entities.
- **Prompt 1.3 — Sessions, Login History, Invitations, SSO, API Keys**: 15-min access + 30/90d refresh tokens, MFA (TOTP/SMS/Email), Google/Microsoft/Apple SSO link.
- **Prompt 1.4–1.8 — remainder of Module 1** (notifications in 1.7 — replaces the insurance-alert log hook).

### P1 — Other modules
- Projects (2.x), Cost Codes (3.x), Appraisals, Budgets, Cash Flow, Programme, Documents, Compliance.

### P2 — Integrations & phase 2
- Xero OAuth (5.1) populates `xero_org_id` / `xero_org_name`.
- Bank feed integration (deferred).
- Group consolidation reporting.
- Multi-tenancy surfacing (per-tenant config, billing, data isolation).

## Deferred / Out of Scope for 1.1
- Xero connection (Prompt 5.1).
- Insurance document uploads (Prompt 4.2 — Documents).
- Bank feed (future).
- Group consolidation (Phase 2+).

## Operational Notes
- Supervisor: `postgresql`, `backend` (uvicorn), `frontend` (yarn) — all auto-start.
- Database bootstrap: `CREATE USER syhomes` + `CREATE DATABASE syhomes` + `pgcrypto` extension. Schema is `create_all()` on startup; migrate to Alembic when table count exceeds ~20 or mutations become non-trivial (likely by Prompt 1.3).
- `DEFAULT_TENANT_NAME=SY Homes` in `backend/.env` — seed resolves tenant by name.
