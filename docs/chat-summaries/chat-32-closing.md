# Chat 32 — Closing Summary (Prompt 2.7: Subcontractors, CIS & Supplier Documents)

**Date:** 2026-02-01
**Track:** 2 (Commercial Engine) — Subcontractor + CIS verification + supplier compliance documents
**Outcome:** Build Pack 2.7 §R0–§R5 shipped backend-only. 28 acceptance gates green; pytest 2nd-run WARM-DB **1071 passed / 0 failed / 0 errors**. Frontend split deferred to **2.7-FE**.
**Predecessor anchor:** Chat 31 close — Build Pack 2.4C (Budget self-approval SoD). main alembic head `0034_audit_sendback`, 102 permissions, 10 roles, backend pytest baseline 1038 passing.
**Scope this chat:** Build Pack `BuildPack_2.7_Subcontractors_CIS.md`, §R0 (pre-flight) → §R5 (tests). No frontend, no auto-expiry scan, no preview/warm-up endpoints, no scope creep.

---

## Repo state at close

```
Branch:            main (push via "Save to GitHub")
Alembic head:      0035_subcontractors  (was 0034; +1 migration)
Permissions:       110  (was 102; +8: 3 cis.* + 5 supplier_documents.*)
Roles:             10   (unchanged)
Backend pytest:    1071 passed, 3 xpassed, 0 failed, 0 errors (2nd-run, 196.53s)
                   42 new test functions (5 new test files)
Frontend Jest:     unchanged (no frontend in scope)
```

---

## What shipped per §R-section

### §R0 — Pre-flight (STOP gate cleared)

All 8 items verified against `main` before any code was written:

1. Alembic HEAD literal `0034_audit_sendback` (matches Build Pack draft).
2. `suppliers` model has `cis_status` String(20); no `supplier_type` yet.
3. `services/suppliers.py` uses `ValueError`/`LookupError`/`_snapshot`/tenant scope — new code mirrors.
4. `routers/suppliers.py` `prefix="/suppliers"`, `_check_perm`, `_perm_dep` pattern — new code mirrors.
5. RBAC seed at `backend/app/seed_rbac.py`; existing suppliers block reads `_perms_for(... include=["view","view_sensitive","create","edit","archive"], sensitive={"view_sensitive","archive"})` — matches Build Pack literal.
6. `permission_action` enum: `verify` was **NEW** — migration `ALTER TYPE permission_action ADD VALUE IF NOT EXISTS 'verify'`. `permission_resource` also extended with `cis` + `supplier_documents`. ACTIONS tuple in `app/models/rbac.py` updated.
7. Audit hook: `record_audit(...)` with `field_diff(before, after)` via `_snapshot` — identical mechanism reused.
8. Pytest 2nd-run WARM-DB baseline: **1038 passed**.

No HALT-worthy deltas reported; the only material finding (item 6) was anticipated by the Build Pack's "report which path applies" instruction.

### §R1 — Schema (migration `0035_subcontractors`)

- **NEW PG enum** `supplier_type` (`Supplier`, `Subcontractor`) — guarded `CREATE TYPE` via `DO $$ ... $$` block.
- **`suppliers` extension** — 5 columns:
  - `supplier_type` NOT NULL `server_default 'Supplier'::supplier_type` — existing rows backfill cleanly.
  - `cis_subtype` String(30) nullable (app-constrained: `Labour_Only` | `Labour_And_Plant` | `Supply_And_Fix`).
  - `cis_registered` Boolean NOT NULL `server_default false`.
  - `utr` String(13) nullable, sensitive.
  - `current_cis_status` String(20) nullable, service-maintained cache (`Gross` | `Net` | `Unmatched` | `Unverified`).
- **New table `subcontractor_cis_verifications`** — append-only. Columns: `id`, `tenant_id`, `supplier_id`, `verification_number`, `match_status` (CHECK Gross/Net/Unmatched), `tax_rate_pct` (0–100 CHECK), `verified_on`, `expires_on`, `notes`, `created_at`, `created_by`. Indexes: `(supplier_id, verified_on DESC)`, `(tenant_id)`. **No `updated_at`, no soft-delete, no UPDATE path.**
- **New table `supplier_documents`** — lightweight. Columns: `id`, `tenant_id`, `supplier_id`, `doc_type` (CHECK against 7 allowed values), `title`, `file_ref` (reference string only; binary upload pipeline migrates to Track 5 — B49), `issued_on`, `expires_on`, `notes`, soft-delete fields (`is_archived` + `archived_at`/`archived_by`), audit cols. Indexes: `(supplier_id, doc_type)`, `(tenant_id)`.
- **Downgrade** drops new tables and added supplier columns + drops the `supplier_type` enum. PG cannot drop enum values — documented asymmetry on `permission_action`/`permission_resource` extensions (mirrors the 0029 downgrade pattern).
- **Round-trip verified** live: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` clean.

### §R2 — Permissions (102 → 110)

Catalogue additions in `seed_rbac.py`:

```python
PERMISSION_CATALOGUE += _perms_for(
    "cis",
    include=["view", "view_sensitive", "verify"],
    sensitive={"view_sensitive", "verify"},
)
PERMISSION_CATALOGUE += _perms_for(
    "supplier_documents",
    include=["view", "view_sensitive", "create", "edit", "archive"],
    sensitive={"view_sensitive", "archive"},
)
```

Role mapping (asserted live in `test_permissions_2_7`):

| Permission                              | Granted to                                                |
|-----------------------------------------|-----------------------------------------------------------|
| `cis.view`                              | super_admin, director, finance, project_manager, site_manager, read_only |
| `cis.view_sensitive`                    | super_admin, director, finance                            |
| `cis.verify`                            | super_admin, director, finance, project_manager *(mirrors `suppliers.create`)* |
| `supplier_documents.view`               | super_admin, director, finance, project_manager *(mirrors `suppliers.create`)* |
| `supplier_documents.view_sensitive`     | super_admin, director, finance, project_manager *(mirrors `suppliers.create`)* |
| `supplier_documents.create`             | super_admin, director, finance, project_manager           |
| `supplier_documents.edit`               | super_admin, director, finance, project_manager           |
| `supplier_documents.archive`            | super_admin, director, finance, project_manager           |

Test gate #27 literal: "`cis.verify` AND `supplier_documents.*` are mapped to exactly the same roles that hold `suppliers.create`" — passes against the live map, not a hardcoded list.

### §R3 — Services

- **`services/suppliers.py` extensions.** `_validate_supplier_type` (defaults `Supplier`); `_validate_cis_subtype(value, supplier_type=…)` rejects with `ValueError` when `cis_subtype` is set on a non-Subcontractor; `_validate_utr` strips ALL whitespace and validates 10 digits. `list_suppliers(supplier_type=…)` filter (router-side `ValueError → 422`). `_AUDIT_COLS` extended to include all 5 new columns. `current_cis_status` defaults `Unverified` on new Subcontractor creates, NULL on plain Suppliers. `current_cis_status` is **NOT** settable via supplier-update payload (silently ignored). UTR added to `SENSITIVE_RESPONSE_FIELDS`.
- **`services/cis.py` (new).** `record_verification(..., actor_id, request)` — rejects non-Subcontractor with `ValueError("CIS verification only valid for subcontractors")`; validates `match_status ∈ {Gross,Net,Unmatched}`; coerces `tax_rate_pct` (0–100); inserts append-only row; **only writer** of `supplier.current_cis_status`; emits `Create` audit via `record_audit + field_diff + _snapshot`. `list_verifications` (newest first by `verified_on`, tiebreak `created_at`). `get_current_verification` (latest or None). **No update/delete helpers exported** — asserted by `test_cis_service::test_no_update_or_delete_helpers_exposed`.
- **`services/supplier_documents.py` (new).** Mirrors suppliers service patterns 1:1: `create_document`, `list_documents` (excludes archived by default, `include_archived` flag, ordered by `doc_type, created_at DESC`), `get_document`, `update_document`, `set_archived(archived: bool)` (idempotent — no-op when state matches; audits Archive/Restore). `file_ref` + `notes` listed in `SENSITIVE_RESPONSE_FIELDS`.

### §R4 — Routers

- **`routers/suppliers.py` extensions.** GET `/suppliers` adds `?supplier_type=` query param; surfaces 4 new body fields on create/update (`supplier_type`, `cis_subtype`, `cis_registered`, `utr` — `utr` body `max_length=30` per deviation note). Serialiser surfaces all subcontractor fields; `utr` gated by `suppliers.view_sensitive`.
- **`routers/cis.py` (new)** — prefix `/cis`, mounted under `/api/v1` in `server.py`:
  - `POST /verifications` — gate `cis.verify`; 201 on create. Cross-tenant supplier → **404** (not 403). Non-Subcontractor supplier → **409**. Other `ValueError` → **422**. 201 response includes `verification_number` regardless of `view_sensitive` (the creator just wrote it).
  - `GET /verifications?supplier_id=…` — gate `cis.view`; sensitive fields (`verification_number`) gated by `cis.view_sensitive`.
  - `GET /verifications/current?supplier_id=…` — gate `cis.view`.
  - **No PATCH, no DELETE.** Append-only enforced at the API by simply not registering those verbs (asserted via OpenAPI introspection in `test_cis_api::test_no_patch_endpoint_on_verifications`).
- **`routers/supplier_documents.py` (new)** — prefix `/supplier-documents`:
  - `POST` (201, gate `.create`), `GET` (gate `.view`), `GET /{id}` (gate `.view`), `PATCH /{id}` (gate `.edit`), `POST /{id}/archive` and `POST /{id}/unarchive` (gate `.archive`). Cross-tenant → 404. Validation → 422.

### §R5 — Tests

42 new test functions across 5 files, covering all 28 build-pack acceptance gates:

| File                            | Tests | Gates covered                       |
|---------------------------------|-------|-------------------------------------|
| `test_subcontractors.py`        | 13    | 1–8 (schema/migration + suppliers extension) |
| `test_cis_service.py`           | 7     | 9–15 (append-only contract, cache update, history) |
| `test_cis_api.py`               | 7     | 16–18 (cross-tenant 404, sensitive gating, perm gating) + extras |
| `test_supplier_documents.py`    | 11    | 19–25 (doc_type validation, archive lifecycle, LD2 boundary) |
| `test_permissions_2_7.py`       | 4     | 26–27 (perm count = 110, role mapping vs `suppliers.create`) |

Baseline-drift literal bumps (chat-15 §3 pattern): `test_auth_rbac` (super_admin 102→110, director 98→106, read_only 12→13), `test_bootstrap` (alembic head sentinel 0034_→0035_), `test_migration_0025_actuals`, `test_migration_0028_user_preferences`, `test_patch_3` (102→110), `test_retro_wires` (102→110).

**Pytest 2nd-run WARM-DB:** 1071 passed, 3 xpassed, 0 failed, 0 errors, 196.53s. Regression floor 1038 honoured.

---

## Deviations from the Build Pack

1. **`utr` body field `max_length=30`** (looser than the DB column's `String(13)`). The Build Pack §R3.1 contract explicitly calls for whitespace-strip on the service side — to honour that, the body layer must accept whitespace-decorated input ("`12 345 67890`" is a valid input form). The service strips and validates against the 10-digit contract before persistence; the DB column remains `String(13)` and stores 10 cleaned digits.

2. **`seed_rbac.py` mirrors the migration role grants.** The 0035 migration writes role-permission rows directly so a fresh-DB upgrade is consistent on its own (no app boot required). The same grants are also declared in `seed_rbac.py` so the bootstrap path (which idempotent-upserts from `PERMISSION_CATALOGUE` + the role-permission map) stays in sync. Either path lands the same final state.

3. **Legacy `suppliers.cis_status` column LEFT IN PLACE.** Per Build Pack §R1.1 — the new `current_cis_status` is the authoritative cache (only writer: `services/cis.record_verification`); dropping the legacy column is OUT OF SCOPE for 2.7. Documented in the migration docstring; consumers should read `current_cis_status` going forward.

---

## Backlog items spawned

(All four also live in `docs/SY_Hub_Phase2_Backlog.md`.)

- **B48** — CIS verification auto-expiry flagging. 2.7 stores `expires_on` on `subcontractor_cis_verifications` but does NOT scan or flag lapsed verifications. Add an attention-scan (mirror the budgets `requires_attention` pattern) that flags subcontractors whose current CIS verification has expired or is within N days. Payment-blocking on a lapsed verification belongs with 2.8 valuations.
- **B49** — Migrate `supplier_documents` to the Track 5 versioned document store. 2.7 ships a lightweight `supplier_documents` table with `file_ref` as a reference string only. When Track 5 lands the versioned store + approval workflow, migrate supplier compliance docs onto it and deprecate the standalone table's file-path.
- **B50** — Per-project supplier/subcontractor ratings. The Phase 2 brief mentions "ratings per project"; deferred from 2.7 to keep it a single backend session. Needs a ratings table keyed on `(supplier_id, project_id)` + a scoring scheme.
- **B51** — Subcontractor onboarding checklist widget (read-only). Surface each Subcontractor's `current_cis_status` plus most-recent `supplier_documents` expiry on a dashboard panel. 2-endpoint backend addition (no migration). Held back to keep 2.7 scope-locked; spec when 2.7-FE picks up.

---

## Commits

- `09d5367` — Build Pack 2.7 §R1–§R5 implementation (backend code + 42 tests + literal-bump drift fixes).
- *(this commit)* — Closing docs: CHANGELOG entry + this summary + B51 backlog entry.

NOT pushed-confirmed until the operator runs **Save to GitHub** — pod's commits live locally on the working tree until then.
