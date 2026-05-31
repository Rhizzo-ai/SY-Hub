# Build Pack 2.7 — Subcontractors, CIS Verifications & Supplier Documents

**Prompt:** 2.7 (Track 2 — Commercial Engine + Subcontractors)
**Type:** Backend-only. NO frontend, NO Playwright (frontend is a later split).
**Branch strategy:** push-to-main (phase-boundary audits only).
**Depends on:** 1.1, 1.2, 1.4, 1.5 (all shipped); existing `suppliers`
module (Chat 24 / Prompt 2.5, on main).
**Alembic head at draft time:** `0034_audit_sendback`. New migration chains
off whatever is HEAD at execution — VERIFY in §R0.

---

## Locked decisions (do not re-litigate)

- **LD1 — Single-table model.** Subcontractors are NOT a separate table.
  Extend `suppliers` with a `supplier_type` enum discriminator
  (`Supplier` | `Subcontractor`). The existing `suppliers.cis_status`
  column already anticipates this. One table, one portal path, one
  documents path.
- **LD2 — CIS verification depth.** Build `subcontractor_cis_verifications`
  as an append-only history table storing verification number, match
  status, verified date, expiry date, recorded-by. Auto-expiry *flagging*
  (attention-scan pattern) and payment-blocking are OUT of scope → backlog
  (payment-blocking belongs with 2.8 valuations, which do not yet exist).
- **LD3 — Lightweight documents.** Build `supplier_documents` as a
  standalone lightweight table (file ref, doc type, expiry, uploaded-by).
  Migration to the Track 5 versioned document store is OUT of scope →
  backlog.

---

## §R0 — Pre-flight verification (STOP gate — do not skip)

Emergent MUST confirm each of these against main BEFORE writing any code,
and report findings in the self-report. Do not assume; the repo layout has
drifted from earlier chats.

1. **Alembic HEAD.** Run `alembic heads`. Record the literal revision.
   New migration `down_revision` = that value. Revision NAME must be
   **≤32 chars** (`alembic_version.version_num` is varchar(32)).
   Proposed name: `0035_subcontractors` (19 chars — OK).
2. **Suppliers model surface.** Confirm `backend/app/models/suppliers.py`
   `Supplier` class columns. Confirm it does NOT already have a
   `supplier_type` column. Confirm `cis_status` exists (String(20),
   nullable).
3. **Suppliers service conventions.** Confirm
   `backend/app/services/suppliers.py` uses: `ValueError` for validation,
   `LookupError` for not-found, a `_snapshot(s)` helper for audit, and
   tenant-scoped queries. New code MUST mirror these exactly.
4. **Suppliers router conventions.** Confirm
   `backend/app/routers/suppliers.py`: prefix `/suppliers`, per-endpoint
   `_check_perm(perms, code)`, `_perm_dep` dependency returning
   `(Principal, UserPermissions)`. Mounted under `/api/v1`.
5. **Seed file.** Confirm RBAC seed lives at `backend/app/seed_rbac.py`
   (NOT `app/scripts/seed_rbac.py`). Confirm `PERMISSION_CATALOGUE` is
   built via `_perms_for(resource, include=[...], sensitive={...})` and
   that the existing `suppliers` block reads:
   `include=["view","view_sensitive","create","edit","archive"]`,
   `sensitive={"view_sensitive","archive"}`.
6. **permission_action enum.** Confirm whether new actions used below
   (`verify`) already exist in the `permission_action` PG enum. If
   `cis.verify` introduces a new action value, the migration MUST
   `ALTER TYPE permission_action ADD VALUE 'verify'` (idempotent guard).
   If reusing only existing actions (view/create/edit/etc.), no enum
   change needed. REPORT which path applies.
7. **Audit hook.** Confirm how suppliers writes audit events (find the
   audit-log call in `services/suppliers.py` create/update/archive).
   New service writes MUST use the identical mechanism.
8. **Baseline tests.** Run pytest twice (WARM-DB rule: first run on a
   fresh pod throws ~90 seed IntegrityErrors — trust the 2nd). Record the
   literal 2nd-run count. Expected baseline ~1035 passed. This is the
   regression floor: final count must be baseline + new, zero regressions.

**STOP.** If any of 1–7 differs materially from the above, HALT and report
the delta before proceeding. Do not "adapt silently."

---

## §R1 — Schema: extend suppliers + new tables (migration `0035_subcontractors`)

### R1.1 — Extend `suppliers`
Add columns (all nullable-safe for existing rows):

- `supplier_type` — PG enum `supplier_type` (`Supplier`, `Subcontractor`),
  NOT NULL, **server_default `'Supplier'`** (so existing rows backfill
  cleanly). Create the enum type in this migration.
- `cis_subtype` — String(30), nullable. App-level constrained to
  `Labour_Only` | `Labour_And_Plant` | `Supply_And_Fix` | NULL. Only
  meaningful when `supplier_type = 'Subcontractor'`; NULL for suppliers.
- `cis_registered` — Boolean, NOT NULL, server_default `false`.
- `utr` — String(13), nullable (UK Unique Taxpayer Reference; 10 digits).
  Sensitive field.
- `current_cis_status` — String(20), nullable. Denormalised cache of the
  latest verification's match status (`Gross` | `Net` | `Unmatched` |
  `Unverified`). Maintained by the service on verification insert.
  **Migration backfill: NULL for all existing rows** (no server_default —
  it is populated by the service, not the migration). The service sets it
  to `Unverified` when a NEW subcontractor is created and leaves it NULL
  for plain suppliers. The existing `cis_status` column is LEFT IN PLACE
  untouched (do not drop — out of scope); `current_cis_status` is the new
  authoritative field. NOTE this overlap in the migration docstring +
  CHANGELOG deviation block.

### R1.2 — New table `subcontractor_cis_verifications` (append-only)
- `id` UUID PK (gen_random_uuid via pgcrypto — already present).
- `tenant_id` UUID NOT NULL FK → `tenants.id` ON DELETE RESTRICT.
- `supplier_id` UUID NOT NULL FK → `suppliers.id` ON DELETE CASCADE.
- `verification_number` String(20), nullable (HMRC ref, e.g. `V` + digits).
- `match_status` String(20) NOT NULL — `Gross` | `Net` | `Unmatched`.
  App-validated.
- `tax_rate_pct` Numeric(5,2), nullable (0 / 20 / 30 typical).
- `verified_on` Date NOT NULL.
- `expires_on` Date, nullable (HMRC verifications valid for the tax year
  + 2 following — service may compute, but store explicitly).
- `notes` Text, nullable.
- `created_at` / `created_by` (FK users.id) — standard audit columns.
- **Append-only:** no `updated_at`, no soft-delete, no UPDATE path. A
  correction is a NEW verification row. Index on
  `(supplier_id, verified_on DESC)`.

### R1.3 — New table `supplier_documents` (lightweight)
- `id` UUID PK.
- `tenant_id` UUID NOT NULL FK → `tenants.id` ON DELETE RESTRICT.
- `supplier_id` UUID NOT NULL FK → `suppliers.id` ON DELETE CASCADE.
- `doc_type` String(40) NOT NULL — app-constrained to
  `Public_Liability` | `Employers_Liability` | `Professional_Indemnity` |
  `CIS_Certificate` | `Accreditation` | `Insurance_Other` | `Other`.
- `title` String(200) NOT NULL.
- `file_ref` String(500), nullable (storage key / path placeholder; the
  real upload pipeline is Track 5 — this is a reference string only,
  NOT a binary store).
- `issued_on` Date, nullable.
- `expires_on` Date, nullable.
- `notes` Text, nullable.
- Soft-delete: `is_archived` Boolean NOT NULL server_default false,
  `archived_at`, `archived_by` (FK users.id ON DELETE SET NULL) — mirror
  the suppliers archive pattern.
- Standard audit columns. Index on `(supplier_id, doc_type)`.

### R1.4 — Migration hygiene
- Idempotent enum creation (guard `CREATE TYPE` / `ADD VALUE`).
- `downgrade()` drops new tables, drops added supplier columns, drops the
  `supplier_type` enum (and any added `permission_action` enum value if
  applicable — note PG cannot drop enum values; document this asymmetry
  in the downgrade docstring rather than failing).
- Confirm `alembic upgrade head` then `alembic downgrade -1` then
  `upgrade head` round-trips clean on a scratch DB.

---

## §R2 — Permissions (seed_rbac.py)

Add to `PERMISSION_CATALOGUE`, mirroring the suppliers block style:

```python
# Chat 32 §R2 (Prompt 2.7) — subcontractor CIS verifications.
# sensitive: view_sensitive (UTR, banking via supplier), verify.
PERMISSION_CATALOGUE += _perms_for(
    "cis",
    include=["view", "view_sensitive", "verify"],
    sensitive={"view_sensitive", "verify"},
)
# Chat 32 §R2 (Prompt 2.7) — supplier compliance documents.
PERMISSION_CATALOGUE += _perms_for(
    "supplier_documents",
    include=["view", "view_sensitive", "create", "edit", "archive"],
    sensitive={"view_sensitive", "archive"},
)
```

- `verify` is likely a NEW `permission_action` enum value → handle in the
  migration per §R0.6.
- Subcontractor CRUD itself reuses the EXISTING `suppliers.*` permissions
  (create/edit/view/archive) — a subcontractor IS a supplier row.
  Do NOT mint `subcontractors.*` permissions.
- Role mapping: grant `cis.*` and `supplier_documents.*` to the same roles
  that hold `suppliers.create`/`edit` today (finance_director,
  contracts_manager, super_admin). VERIFY which roles those are in the
  role-permission map and mirror exactly. Report the resulting permission
  count. New permissions = 3 (`cis.*`) + 5 (`supplier_documents.*`) = **8**.
  Expected 102 + 8 = **110** (confirm literal against the §R0.8 baseline;
  if baseline ≠ 102, expected = baseline + 8).

---

## §R3 — Service layer

### R3.1 — `services/suppliers.py` extensions
- Extend `create_supplier` / `update_supplier` to accept and validate the
  new fields: `supplier_type`, `cis_subtype`, `cis_registered`, `utr`.
  - `supplier_type` must be one of the enum values; default `Supplier`.
  - `cis_subtype` only permitted when `supplier_type == 'Subcontractor'`;
    raise `ValueError` if set on a plain supplier.
  - `utr`: strip whitespace and internal spaces; if present, validate
    exactly 10 digits; `ValueError` on malformed.
- Add `list_suppliers` filter param `supplier_type` (optional) so callers
  can list suppliers-only, subs-only, or both.
- Extend `_snapshot` to include the new columns (audit completeness).
- `current_cis_status` is service-maintained — NOT settable via the
  supplier create/update API. Defaults `Unverified` for a new
  subcontractor, NULL for a supplier.

### R3.2 — New `services/cis.py`
- `record_verification(db, tenant_id, supplier_id, *, verification_number,
  match_status, tax_rate_pct, verified_on, expires_on, notes, actor_id)`
  - Loads supplier (tenant-scoped); `LookupError` if missing.
  - Rejects if `supplier.supplier_type != 'Subcontractor'` →
    `ValueError("CIS verification only valid for subcontractors")`.
  - Validates `match_status` ∈ {Gross, Net, Unmatched}.
  - Inserts append-only row.
  - Updates `supplier.current_cis_status` to the new `match_status`
    (this is the ONLY writer of that cache field).
  - Writes an audit event (same mechanism suppliers uses).
  - Returns the new verification.
- `list_verifications(db, tenant_id, supplier_id)` — newest first.
- `get_current_verification(db, tenant_id, supplier_id)` — latest by
  `verified_on`, or None.
- NO update / delete functions (append-only).

### R3.3 — New `services/supplier_documents.py`
- `create_document`, `list_documents` (exclude archived by default,
  `include_archived` flag), `get_document`, `update_document`,
  `set_archived` — mirror the suppliers service patterns 1:1
  (`ValueError` / `LookupError`, `_snapshot`, audit writes, tenant scope).
- `doc_type` validated against the allowed set.
- Expiry is stored only; no scanning/flagging (LD2/backlog).

---

## §R4 — Routers

### R4.1 — Extend `routers/suppliers.py`
- Surface the new fields in the supplier create/update request + response
  schemas. Gate `utr` read behind `suppliers.view_sensitive` (same gating
  as existing banking/VAT fields — find and mirror that pattern).
- Add `?supplier_type=` query param to `GET /suppliers`.

### R4.2 — New `routers/cis.py` (mounted `/api/v1`, prefix `/cis`)
- `POST /cis/verifications` — body carries `supplier_id` + verification
  fields. Gate `cis.verify`. 201 on create. 404 if supplier missing/wrong
  tenant (do NOT leak existence — 404 not 403 for cross-tenant). 422 on
  validation. 409 if supplier is not a subcontractor.
- `GET /cis/verifications?supplier_id=` — gate `cis.view`. Strip/omit
  sensitive fields unless caller has `cis.view_sensitive`.
- `GET /cis/verifications/current?supplier_id=` — gate `cis.view`.

### R4.3 — New `routers/supplier_documents.py` (prefix `/supplier-documents`)
- `POST` (create, gate `supplier_documents.create`, 201),
  `GET ?supplier_id=` (list, gate `.view`),
  `GET /{id}` (gate `.view`),
  `PATCH /{id}` (gate `.edit`),
  `POST /{id}/archive` + `POST /{id}/unarchive` (gate `.archive`).
- Cross-tenant → 404. Validation → 422.
- Register all new routers in the app's router-include module (find where
  `suppliers` router is `include_router`'d and add alongside, same prefix
  + auth conventions).

---

## §R5 — Acceptance gates (tests — `backend/tests/`)

Target **≥ 28 new test functions**. Files:
`test_subcontractors.py`, `test_cis_service.py`, `test_cis_api.py`,
`test_supplier_documents.py`. Mirror existing supplier test structure.

**Schema / migration**
1. `alembic upgrade head` clean; `supplier_type` enum exists; all three
   new tables/columns present.
2. Downgrade → upgrade round-trips without error.
3. Existing supplier rows backfill `supplier_type='Supplier'`,
   `cis_registered=false` (no NULLs, no orphan rows).

**Suppliers extension**
4. Create supplier with `supplier_type='Subcontractor'` + valid UTR →
   persists; `current_cis_status` defaults `Unverified`.
5. Create plain supplier → `cis_subtype` rejected (`ValueError`).
6. Malformed UTR → `ValueError` / 422.
7. `GET /suppliers?supplier_type=Subcontractor` returns subs only.
8. UTR hidden without `suppliers.view_sensitive`; visible with it.

**CIS verifications**
9. `record_verification` on a subcontractor → row created, append-only.
10. `record_verification` on a plain supplier → `ValueError` / 409.
11. Recording a verification updates `supplier.current_cis_status` to the
    new `match_status`.
12. A second verification creates a NEW row (history preserved, prior row
    unchanged) and re-points `current_cis_status`.
13. `match_status` outside {Gross,Net,Unmatched} rejected.
14. `get_current_verification` returns the newest by `verified_on`.
15. No update/delete path exists (assert service module exposes none;
    API has no PATCH/DELETE on verifications).
16. `POST /cis/verifications` cross-tenant supplier → 404 (not 403).
17. `cis.view` without `cis.view_sensitive` → verification list omits
    sensitive fields (verification_number).
18. `cis.verify` absent → 403 on POST.

**Supplier documents**
19. Create document → persists with doc_type validated.
20. Invalid `doc_type` → `ValueError` / 422.
21. List excludes archived by default; `include_archived` returns them.
22. Archive → `is_archived=true`, `archived_at`/`archived_by` set;
    unarchive reverses.
23. Cross-tenant document fetch → 404.
24. `supplier_documents.create` absent → 403.
25. Expiry date stored and returned; NO attention/scan side-effect fires
    (asserts LD2 boundary — nothing auto-flags).

**Permissions / regression**
26. Permission count = prior baseline + 8 (literal assert; expected 110
    if baseline is 102).
27. `cis.verify` and `supplier_documents.*` are mapped to exactly the same
    roles that hold `suppliers.create` in the role-permission map (assert
    against the actual map confirmed in §R0, not a hardcoded list).
28. Full suite 2nd-run: baseline + new, **zero regressions**, 0 failed.

---

## Out of scope (explicit)

- Any frontend / React / Playwright (later split: 2.7-FE).
- CIS auto-expiry flagging + attention scan → **backlog B48**.
- Payment-blocking on lapsed CIS → belongs with 2.8 valuations → backlog.
- Migration of `supplier_documents` to Track 5 versioned store →
  **backlog B49**.
- Dropping the legacy `suppliers.cis_status` column (left in place;
  noted as deviation).
- Real file-upload binary pipeline (file_ref is a reference string only).
- Subcontract records, variations, valuations, payment notices → 2.8.
- Per-project supplier/subcontractor ratings → **backlog B50** (brief
  mentions "ratings per project"; deferred to keep 2.7 single-session).
- HMRC API integration for live verification → not in any current track.

---

## Self-report format (REQUIRED at end of build)

```
## 2.7 Self-Report
- §R0 pre-flight deltas: <any>
- Alembic: HEAD was <X>; new migration <0035_subcontractors>;
  down/up round-trip: <pass/fail>
- permission_action enum: <added 'verify' | reused existing>
- Permission count: <before> → <after> (expected baseline + 8 = 110)
- Tables added: subcontractor_cis_verifications, supplier_documents (+ 5
  supplier columns + supplier_type enum)
- Routers registered: cis, supplier_documents (+ suppliers extended)
- Tests: <N> new functions. pytest 2nd-run:
  <P passed>/<F failed>/<E errors>. Regression floor <baseline>:
  <pass/fail>
- Deviations: <list or "none">
- Files changed: <list>
- Commits: <SHAs>
- NOT pushed-confirmed (pod has no origin remote) — operator verifies on
  GitHub web.
```

**STOP gates are real. No auto-advance past §R0. Do not add scope
(no activate-preview-style extras); log any idea to the backlog instead.**
