<!-- ================================================================
     SY HOMES PLATFORM — PHASE 2 EMERGENT BRIEF
     SESSION 4b OUTPUT: TRACKS 6 + 7 + 8 — PROMPT-LEVEL DETAIL
     ================================================================
     Version: 2.0-detail (T6 + T7 + T8)
     Date: April 2026
     Status: Replaces one-paragraph descriptions in skeleton lines
             ~318-444 (Track 6 prompts 6.1-6.5, Track 7 prompts
             7.1-7.4, Track 8 prompts 8.1-8.3).
     Companion: SY_Homes_Emergent_Brief_Phase1.md (Phase 1 brief —
                referenced in full for "carried forward" Track 6
                prompts 6.2-6.5);
                SY_Homes_Phase2_Brief_T2_T3_Detail.md (session 3 —
                referenced for portal patterns, real-time/offline
                infra, programme tasks, commitments shape);
                SY_Homes_Phase2_Brief_T4_T5_Detail.md (session 4a —
                referenced for snag/DLP wiring, document FK targets,
                portal infrastructure pattern reused in 8.1).
     ================================================================ -->

# Session 4b — Tracks 6, 7, and 8 prompt-level detail

This document supplies the full prompt detail for Tracks 6, 7, and 8, intended to replace the one-paragraph descriptions in `SY_Homes_Emergent_Brief_Phase2.md` skeleton sections "Track 6 — Xero + CSV Import/Export", "Track 7 — Sales + Post-Completion + Reporting + Public API", and "Track 8 — Polish". Same depth and structure as session 3's T2+T3 detail and session 4a's T4+T5 detail.

## Changes versus skeleton

1. **6.1 lifts CSV framework to a first-class concern.** The skeleton calls 6.1 a generic schema-driven import/export framework feeding actuals, suppliers, subcontractors, plot data, and project metadata. Detail confirms two new tables (`import_jobs`, `import_errors`) and a generalised "importer adapter" pattern — one adapter per target table, all sharing the same job machinery. Export side reuses the same adapters in reverse where possible. Critical for "platform without Xero" mode (Project Instructions hard constraint 2 — Xero must work properly, but optional-Xero framing requires the platform to remain usable when Xero is disconnected).

2. **6.4 CIS reverse charge re-validation outcome (was open from session 3 closing).** Detail review confirms the Phase 1 5.3 design treats `DRCHARGE20` correctly *for the VAT side* — input VAT recoverable matched to output VAT due, net zero VAT impact on bill. **However**, for CIS-applicable subcontractor bills under reverse charge VAT, two separate adjustments apply on the same line (CIS deduction *and* reverse charge VAT) and the Phase 1 spec did not explicitly handle the interaction. Drafting notes the deviation and the resolution: CIS deduction is computed on the *labour element* of the net amount (matches Xero CIS module behaviour), reverse charge VAT is applied to the full net amount on the bill. Both adjustments coexist on the same `actuals` row. No schema delta required — `cis_deduction_amount` and `vat_amount` are independent fields. **The CIS-Reverse-Charge interaction is now explicitly documented in 6.4 acceptance criteria** so the build verifies it on a known-shape bill (CIS-registered net subcontractor with reverse-charge applicable line).

3. **6.5 confirmed scaled back from Phase 1's two-prompt split (5.4 + 5.5).** Detail review confirms the merge is appropriate: in optional-Xero mode the reconciler's "platform actuals vs Xero bills" comparison still happens, but the depth of variance reporting (per-quarter VAT reconciliation, mapping health metrics) is one tier simpler than Phase 1 envisioned. Bank transactions and manual journals remain read-only mirrors, no auto-conversion. Sync events log remains full-fidelity (every API call logged) — that's a hard constraint for audit and is not where simplification lands.

4. **7.1 and 7.4 do not split on detail review.** Skeleton flagged 7.1 as a candidate split (plots vs buyer pipeline) and 7.4 as a candidate split (reporting vs public API). On detail:
   - 7.1 holds plots only; **7.2** is the buyer pipeline (already separated in skeleton — confirmed). The candidate split was a misread of the skeleton.
   - 7.4 reporting and public API stay unified because the public API reads the *same* report definitions and dashboard data structures the internal reporting builds. Splitting would force the public API prompt to redefine machinery 7.4 already builds. Stays as one prompt at 12h.

5. **7.4 reporting depth is operational, not BI.** Detail clarifies 7.4 builds *operational* dashboards (project status grid, cash position, open items) and a *basic* board-pack PDF export. Full BI / executive-dashboard / investor-pack remain Future Tasks Phase 7. The skeleton's ambiguous wording on dashboard depth is now bounded.

6. **Public API auth model locked rate-limited no-auth read-only.** Carried from session 4 opener and 4b opener. 7.4 detail spells out the endpoint surface (available plots, completed schemes gallery, two endpoints only at launch), rate limits (60 req/min per IP, 1000 req/day per IP), allowed fields whitelist (no internal IDs leak, no buyer PII), and audit logging on every call.

7. **8.2 designer engagement is ahead of, not during, the prompt.** Carried from 4b opener. 8.2 build phase consumes a designer deliverable — pre-engaged via the designer engagement workstream that runs in parallel to T6/T7. 8.2 spec calls out the deliverables required from the designer (mobile component library, brand tokens, key-screen mockups for 4.1/4.3/2.9 surfaces) so the engagement brief can be written and the designer chosen during T6/T7.

8. **8.2 Buildertrend cutover plan is its own deliverable, not buried in spec text.** The cutover plan (`SY_Homes_Buildertrend_Cutover_Plan.md`) is referenced by 8.2 but produced as a separate output ahead of 8.3 launch — flagged in closing.

9. **T8 shape changed from skeleton.** Skeleton had 8.1 Portal Hardening (10h), 8.2 Mobile UX + Designer (14h), 8.3 Performance + Launch Readiness (12h). Per session 4b opener pre-decision, T8 is restructured to 8.1 Performance + design polish (12h), 8.2 Buildertrend cutover plan execution (14h), 8.3 Go-live + post-launch monitoring (10h). Rationale: (a) "Portal Hardening" RBAC + error-handling content absorbs into 8.1's polish pass — it isn't a discrete prompt's worth of work; (b) "Mobile UX + Designer" collapses because designer engagement runs ahead of T8 as a parallel workstream — the designer's mobile component library, brand tokens, and key-screen mockups land *into* 8.1 rather than being produced *during* T8; (c) Buildertrend cutover is now an explicit prompt rather than buried in launch readiness. Total T8 hours unchanged at 36.

## Carried-forward prompts — note on depth

Prompts 6.2, 6.3, 6.4, 6.5 are carried forward from Phase 1 Track 5 (Prompts 5.1, 5.2, 5.3, and 5.4+5.5 merged) with deltas only. Their full schemas, OAuth flows, mapping logic, sync mechanics, and acceptance criteria already exist in the Phase 1 brief. Sections below state the Phase 1 reference, the deltas, and any out-of-scope additions surfaced by the optional-Xero reframe.

Prompts 6.1 and 7.1 through 8.3 are all new and are written here at full Phase 1 depth.

## Skeleton corrections flagged in closing

Two skeleton estimates are corrected during drafting:
- T7 final table count is 16, not the skeleton's ~12. Driver: 7.4 reporting + public-API surface adds 4 tables (`report_definitions`, `report_runs`, `public_api_endpoints`, `public_api_request_log`) the skeleton estimate didn't isolate; `dlp_defects` was avoided as a separate table by reusing `snags` with an `is_dlp_defect` flag. See 7.3 detail for the snag-flag resolution.
- T8 prompt shape changed from skeleton (see §"Changes versus skeleton" item 9). Total T8 hours unchanged at 36.

Closing section captures the final counts.

---

# Track 6 — Xero + CSV Import/Export

**Goal:** Make Xero an *optional* connector while ensuring the platform is fully usable without it. CSV import/export covers the case where SY Homes wants to onboard data from elsewhere, or operate in Xero-disconnected mode (e.g. during cutover, during a Xero outage, or for an entity that hasn't been onboarded to Xero yet). The Xero connector itself is carried forward from Phase 1 Track 5 with the optional-not-required reframe: an entity may have no `xero_connections` row and the platform's commercial engine remains fully functional. Bills, invoices, payments, and credit notes can originate as `Manual` or `CSV_Import` in 2.5 actuals; the Xero source enum value lights up for entities that *are* connected.

**Duration:** ~10 weeks at 25 hrs/week
**Prompts:** 5 (1 NEW + 4 carried-forward from Phase 1 Track 5)
**Tables added:** ~17 (15 from Phase 1 Track 5 unchanged + 2 new for CSV framework)
**Audit checkpoint:** End of Track 6 — light self-audit. The substantive Xero work is carried forward and well-understood from Phase 1; 6.1 CSV is the genuinely new component and warrants verification on at least three target adapters (actuals, suppliers, subcontractors) end-to-end before T7 starts.

### Phase 1 → Phase 2 prompt mapping

| Phase 1 prompt | Phase 2 prompt | Status |
|---|---|---|
| (none) | 6.1 | NEW — CSV import/export framework |
| 5.1 Connections (OAuth + Token Mgmt) | 6.2 | Carried forward + optional-mode framing delta |
| 5.2 Reference Sync (Tracking, COA, Tax, Contacts) | 6.3 | Carried forward unchanged |
| 5.3 Financial Mirrors (Bills, Invoices, Payments, Credit Notes) | 6.4 | Carried forward + CIS-reverse-charge interaction explicit + optional-mode framing |
| 5.4 + 5.5 (Sync Queue, Webhooks, Bank Txn, Journals, Reconciler, Sync Events) | 6.5 | Merged + scaled-back depth on reconciliation reporting |

---

## Prompt 6.1 — CSV Import/Export Framework

**Dependencies:** 1.1, 1.2, 1.4, 1.6, 2.5, 2.7
**Tables in this prompt:** `import_jobs`, `import_errors`
**Estimated hours:** 12h
**Status:** NEW.

A generic, schema-driven CSV import and export framework. One central job + error machinery, plus a registry of "importer adapters" — one adapter per target entity (actuals, suppliers, subcontractors, plots, project metadata, cost-code reference, etc.). Each adapter declares the columns it accepts, the validation rules per column, and the persistence step. The job machinery handles file upload, parsing, dry-run preview, validation, partial commit, and error reporting. Export side reuses adapter column declarations to produce CSVs with the same shape that import would accept — round-trip safe.

This module is critical for the "platform without Xero" mode (an entity can run end-to-end on Manual + CSV-Import sources for actuals), for migrating historical data later (the deferred Future Tasks "historical actuals importer" builds on this framework), and for the cutover phase in 8.2 where SY Homes onboards live data that doesn't go through Xero.

The framework targets six adapters at first build:

1. `Actuals_Adapter` — bills, invoices, payments, credit notes (one CSV row per actuals line)
2. `Suppliers_Adapter` — supplier records (2.7)
3. `Subcontractors_Adapter` — subcontractor records (2.7)
4. `Plots_Adapter` — plot records (7.1)
5. `Buyers_Adapter` — buyer records (7.2) — without sensitive contact PII in CSV; PII added separately
6. `Project_Metadata_Adapter` — project name, client, address, status updates only (creation goes through 1.5 UI)

Future adapters can be registered without changing the core machinery.

### Build `import_jobs`

The job header per uploaded CSV. One row per upload attempt. Lifecycle: upload → validate → preview → commit (or cancel). Validation produces errors but doesn't block the job; commit only persists rows that passed validation, with the rest left in `import_errors` for review.

```
import_jobs
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
adapter_code                    varchar(50) NOT NULL
                                  -- 'actuals', 'suppliers', 'subcontractors', 'plots',
                                  -- 'buyers', 'project_metadata'
adapter_version                 varchar(20) NOT NULL
                                  -- 'v1' at launch; bumped if column set or validation rules change
file_storage_backend            enum NOT NULL DEFAULT 'S3'
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text NOT NULL
file_original_name              varchar(500) NOT NULL
file_size_bytes                 bigint NOT NULL
file_sha256                     varchar(64) NOT NULL
file_row_count                  int                                -- populated after parse
file_encoding                   varchar(20) DEFAULT 'utf-8'
file_delimiter                  varchar(5) DEFAULT ','
file_has_header                 boolean NOT NULL DEFAULT true
column_mapping                  jsonb NOT NULL DEFAULT '{}'
                                  -- {"csv_col_name": "target_field_name", ...}
                                  -- captured during preview step from user mapping UI
target_entity_id                uuid
                                  -- when adapter scopes to a parent entity (e.g. plots → project_id)
                                  -- generic uuid; not FK because target table varies
target_entity_type              varchar(50)
                                  -- e.g. 'project' for Plots_Adapter; 'entity' for Actuals_Adapter
status                          enum NOT NULL DEFAULT 'Uploaded'
                                  ('Uploaded','Parsing','Parsed','Validating','Validated',
                                   'Awaiting_Commit','Committing','Committed','Failed','Cancelled')
total_rows                      int NOT NULL DEFAULT 0
valid_rows                      int NOT NULL DEFAULT 0
error_rows                      int NOT NULL DEFAULT 0
warning_rows                    int NOT NULL DEFAULT 0
committed_rows                  int NOT NULL DEFAULT 0
dry_run                         boolean NOT NULL DEFAULT false
                                  -- true = validation only, never commits (cancel on review)
commit_strategy                 enum NOT NULL DEFAULT 'Partial_Commit'
                                  ('All_Or_Nothing','Partial_Commit')
                                  -- All_Or_Nothing: any error blocks entire commit
                                  -- Partial_Commit: commit valid rows, leave errors in error log
duplicate_strategy              enum NOT NULL DEFAULT 'Reject'
                                  ('Reject','Skip','Update','Upsert')
                                  -- Reject: any duplicate fails the row
                                  -- Skip: silently skip duplicates (logged as warning)
                                  -- Update: duplicates update existing record (where adapter supports)
                                  -- Upsert: insert if new, update if existing
                                  -- adapter declares which strategies are valid for its target
notes                           text
uploaded_at                     timestamp NOT NULL DEFAULT now()
uploaded_by_user_id             uuid NOT NULL FK→users.id
parsed_at                       timestamp
validated_at                    timestamp
committed_at                    timestamp
committed_by_user_id            uuid FK→users.id
cancelled_at                    timestamp
cancelled_by_user_id            uuid FK→users.id
cancellation_reason             text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (tenant_id, adapter_code, uploaded_at DESC)
- INDEX (status) WHERE status NOT IN ('Committed','Cancelled')
- INDEX (uploaded_by_user_id, uploaded_at DESC)
- INDEX (target_entity_type, target_entity_id) WHERE target_entity_id IS NOT NULL
```

The `file_sha256` field guards against accidental double-import — uploading the same file twice within the same adapter scope produces a warning ("This file matches an import committed at <timestamp> by <user>") with the option to proceed anyway. Hash is computed during upload (multipart-friendly: use streaming SHA-256).

`column_mapping` is a JSON object captured during the preview step where the user maps each CSV column to a target field. The adapter declares which target fields are required vs optional; the mapping UI enforces required-field coverage before allowing transition to validation.

### Build `import_errors`

Per-row error log. One row per (job, csv_row, error). Multiple errors per row are common — each becomes its own record so the user sees the full list, not just the first.

```
import_errors
─────────────────────────────────────────────
id                              uuid PK
import_job_id                   uuid NOT NULL FK→import_jobs.id ON DELETE CASCADE
csv_row_number                  int NOT NULL                       -- 1-indexed; row 1 is first data row
                                                                   -- (header row is row 0)
csv_row_content                 jsonb                              -- the parsed row as {col_name: value}
severity                        enum NOT NULL
                                  ('Error','Warning')
error_code                      varchar(50) NOT NULL
                                  -- 'missing_required', 'invalid_format', 'unknown_reference',
                                  -- 'duplicate', 'out_of_range', 'foreign_key_not_found',
                                  -- 'business_rule_violation', 'parse_error', 'encoding_error'
error_field                     varchar(100)                       -- which CSV column / target field
error_message                   text NOT NULL                      -- human-readable
suggested_fix                   text
                                  -- adapter may emit a hint, e.g. "Supplier 'AB Plant' not found —
                                  -- create supplier first or use the suppliers import"
detected_at                     timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (import_job_id, csv_row_number)
- INDEX (import_job_id, severity)
- INDEX (error_code)
```

Errors are persisted across the job lifecycle. After a partial commit, the rows that errored remain in `import_errors` for the user to download as a "rejected rows" CSV alongside their fix-and-re-upload workflow.

### Adapter pattern

Each adapter is a registered class implementing a fixed interface. The interface (in pseudocode):

```
class ImporterAdapter:
    code: str                    # 'actuals', etc.
    version: str                 # 'v1'
    target_table: str            # 'actuals' (table name) — informational
    target_entity_required: bool # whether target_entity_id is required (e.g. plots need project)
    columns: list[ColumnSpec]    # declared column list
    duplicate_strategies: list[DuplicateStrategy]   # which are valid for this adapter
    
    def parse_row(raw: dict[str, str]) -> ParsedRow:
        # Type coercion: 'date' → date, 'decimal' → Decimal, 'enum' → enum value
        # Strip whitespace, normalise case where appropriate (codes upper, names title)
    
    def validate_row(parsed: ParsedRow, ctx: ImportContext) -> list[ValidationResult]:
        # Required-field checks, format checks, FK resolution, range checks
        # Returns list of (Error|Warning|Pass) per field
        # ctx provides access to existing data for FK resolution (cached per job)
    
    def detect_duplicate(parsed: ParsedRow, ctx: ImportContext) -> Optional[ExistingRecord]:
        # Adapter-specific duplicate detection
        # e.g. for Actuals: (entity_id, supplier_invoice_ref, transaction_date) match
        # e.g. for Suppliers: (name, postcode) fuzzy match
    
    def persist_row(parsed: ParsedRow, ctx: ImportContext, strategy: DuplicateStrategy) -> uuid:
        # Insert or update target record, return its id
    
    def export_rows(filter: ExportFilter) -> Iterator[dict]:
        # Yields rows matching filter, in the same shape import expects
        # Reuses column declarations
```

`ColumnSpec` declares per column:
- `name` (CSV header text the import wizard suggests; user can override mapping)
- `target_field` (the destination model field)
- `required` (true/false)
- `type` (`string`, `decimal`, `int`, `date`, `datetime`, `boolean`, `enum`, `uuid_lookup`)
- `enum_values` (for type=enum)
- `max_length` (for type=string)
- `regex` (optional pattern check)
- `min` / `max` (for type=decimal/int/date)
- `lookup_adapter` (for type=uuid_lookup, e.g. supplier code → supplier UUID resolution)
- `description` (shown in the mapping UI tooltip)

Adapters live in a single registry; new adapters register at module load time. The framework knows nothing about specific entity domains.

### `Actuals_Adapter` declaration (illustrative; six required for launch)

For `actuals` (the most complex and most common adapter), the declared columns are:

| CSV header (suggested) | Target field | Required | Type | Notes |
|---|---|---|---|---|
| `Entity Code` | entity_id | yes | uuid_lookup | resolves via entities.entity_code |
| `Project Code` | project_id | yes (when applicable) | uuid_lookup | via projects.project_code; NULL for non-project actuals like overhead |
| `Cost Code` | budget_line_id (via cost_code_id) | yes (when project) | uuid_lookup | via cost_codes.code, then resolves budget_line_id from project budget |
| `Type` | transaction_type | yes | enum | `Bill`, `Invoice`, `Payment`, `Credit_Note` |
| `Date` | transaction_date | yes | date | UK format DD/MM/YYYY accepted; ISO accepted |
| `Posting Date` | posting_date | no (defaults to Date) | date | |
| `Supplier/Customer Name` | supplier_name_snapshot | yes | string | |
| `Reference` | supplier_invoice_ref | yes (for Bill/Credit_Note) | string | |
| `Description` | description | yes | string | max 500 |
| `Net Amount` | net_amount | yes | decimal | 14,2 |
| `VAT Amount` | vat_amount | no (defaults 0) | decimal | 14,2 |
| `VAT Rate %` | vat_rate_pct | no | decimal | 5,2; if blank inferred from other fields |
| `Gross Amount` | gross_amount | no | decimal | computed if blank; validated against net+vat if provided |
| `VAT Treatment` | vat_treatment | no | enum | `Standard`, `Zero`, `Exempt`, `Reverse_Charge`, `No_VAT` |
| `CIS Applicable` | is_cis_applicable | no | boolean | inferred from cost_code if blank |
| `CIS Deduction` | cis_deduction_amount | no | decimal | for subcontractor bills |
| `Source Reference` | source_reference | no | string | external system ref for trace |
| `Notes` | notes | no | string | |

Validation rules applied during the validate step include: net + vat = gross (within £0.01), VAT rate consistent with treatment, CIS deduction non-zero only when CIS applicable, supplier resolved or warning emitted (with `suggested_fix`: "Create supplier 'X' first or use the Suppliers import"), project + cost code combination resolves to a budget line in the project's current budget (or a new "unbudgeted" line is auto-created with a warning, mirroring the Xero behaviour in 6.4).

### Job lifecycle

```
1. Upload (UI: drag CSV onto adapter page)
   → import_jobs row created with status='Uploaded'
   → file streamed to storage with SHA-256 computed inline
   → if duplicate file SHA-256 found: warn user, allow proceed

2. Parse
   → status='Parsing'
   → CSV streamed and parsed; total_rows computed
   → if header row missing or unrecognisable: status='Failed', single import_errors row
     with error_code='parse_error'
   → status='Parsed' on success
   → mapping UI shown to user: source columns vs target fields

3. Mapping & dry-run preview
   → user adjusts column_mapping
   → "Validate" button triggers status='Validating'
   → adapter.parse_row + adapter.validate_row called for each row
   → import_errors populated with all errors and warnings
   → first 50 rows shown in preview pane (parsed) with error/warning markers per row
   → status='Validated' (or 'Awaiting_Commit')

4. Commit
   → user reviews errors and chooses commit strategy (All_Or_Nothing or Partial_Commit)
   → confirms via button
   → status='Committing'
   → adapter.persist_row called for each non-error row
     - inside a transaction
     - if All_Or_Nothing and any persist fails: rollback, status='Failed'
     - if Partial_Commit and a row fails persist (rare; means validation missed something):
       record as new import_errors row, continue
   → status='Committed', committed_at, committed_rows populated
   → audit_log entry: 'csv_import_committed' with adapter, file, counts

5. Cancel
   → from any non-committed state, user may cancel
   → status='Cancelled', cancellation_reason captured
   → no rows persisted

6. Dry run
   → if dry_run flag set on upload, the lifecycle ends at 'Validated' and the
     "Commit" button is disabled. Used for "what would happen?" testing.
```

A user reaching the validate step then closing the tab leaves the job in `Validated` state. When they return, they see a "Resume" prompt on the imports list. After 30 days of inactivity in non-committed states, jobs are auto-cancelled with `cancellation_reason='auto_cancel_inactive_30_days'` and the file is deleted from storage (job row preserved for audit).

### Export side

Every adapter implementing `export_rows` lights up an "Export CSV" action on the corresponding list view. The action:

- Captures the active filter on the list (e.g. on `/actuals?entity=SPV1&date_from=2026-01-01`)
- Calls `adapter.export_rows(filter)` to stream rows
- Generates CSV with the same column shape import would accept
- Includes a header row matching the adapter's declared CSV header names (exact strings)
- Adds a metadata header in the first non-data row commented with `# adapter=actuals version=v1 exported_at=2026-04-28T14:30:00Z filter={...}`
- Streams to the user as `attachment; filename="<adapter>_<filter>_<date>.csv"`

Round-trip property: an export from the platform should be re-importable with no errors (modulo records that have changed since export). The build verifies this for each adapter — export from a known dataset, re-import to a sibling test environment, confirm row counts and amounts match.

Large exports (>10,000 rows) are queued as a background job rather than streamed inline; the user gets a notification and a download link when ready. Implementation details (worker, link expiry) are pragmatic; the framework does not over-engineer.

### Permissions

- `csv_import.upload` — finance, contracts manager (per-adapter granularity in Phase 3 if needed; Phase 2 single permission gates all adapters)
- `csv_import.commit` — finance, contracts manager, director — same as upload at Phase 2; tightened in Phase 3 if a separation-of-duties need emerges
- `csv_import.cancel` — finance, contracts manager, director, the original uploader
- `csv_import.view_history` — finance, contracts manager, director, audit (read-only past jobs)
- `csv_export.run` — anyone with read access to the underlying entity (finance for actuals, contracts for subcontractors, etc.); no separate seed permission, derived per adapter

Adapter-level scoping respects existing entity-level RBAC: a user without access to entity X cannot import actuals targeting entity X (the entity-code lookup fails or is blocked at validate).

### Seed data

None for the framework tables. The six launch adapters are registered in code and discovered at module load.

### Acceptance criteria

- [ ] CSV upload with progress, accepting files up to 50MB
- [ ] SHA-256 computed during upload; duplicate-file warning surfaces previous import
- [ ] Header parsing tolerant of leading/trailing whitespace, BOM, mixed quoting
- [ ] Encoding auto-detection for utf-8, utf-8-bom, windows-1252; user can override
- [ ] Mapping UI displays each CSV column with a target-field dropdown; required fields enforced
- [ ] Adapter declared columns drive the dropdown options; type coercion happens at parse
- [ ] Validation produces structured `import_errors` rows with `error_code`, `severity`, `error_field`, `error_message`, `suggested_fix`
- [ ] Preview pane shows first 50 parsed rows with error/warning indicators per cell
- [ ] Dry-run mode validates without permitting commit
- [ ] Partial commit persists valid rows, leaves errored rows in `import_errors` for download
- [ ] All-or-nothing commit rolls back on any error
- [ ] Duplicate strategies (Reject / Skip / Update / Upsert) work per adapter declaration
- [ ] Audit log records every commit with adapter, file SHA-256, row counts
- [ ] Round-trip verified: export → re-import produces zero new errors and zero data drift on at least 3 adapters (actuals, suppliers, subcontractors)
- [ ] CIS-applicable subcontractor bill imports correctly with `cis_deduction_amount` set
- [ ] Reverse-charge VAT imports correctly with `vat_treatment='Reverse_Charge'` and 0 VAT amount
- [ ] Permissions enforced: a user without entity X access cannot import actuals targeting entity X
- [ ] 30-day auto-cancel of inactive jobs runs; file purged from storage
- [ ] Large export (>10,000 rows) queues a background job and notifies user on completion

### Out of scope

- ML / fuzzy column auto-mapping ("which column is the date?") — Future Tasks Phase 5; Phase 2 provides explicit user mapping
- Excel (.xlsx) import — explicitly CSV only; users save Excel as CSV
- Real-time collaborative editing of in-progress imports — out of scope; one user per job
- Scheduled/recurring CSV imports (e.g. nightly drop folder) — out of scope; manual upload only
- Adapter authoring UI (admin defines new adapters via UI) — out of scope; new adapters land via code
- Two-way sync semantics on imports (i.e. detecting that an actuals row imported is the same as one already in Xero) — out of scope; reconciliation between Xero and CSV-imported actuals lives in 6.5 if both sources exist
- Pre-import data transformation steps (e.g. apply a multiplier, prepend a code) — out of scope; user transforms CSV before upload

---

## Prompt 6.2 — Xero Connections (OAuth + Token Management)

**Dependencies:** 1.1, 1.2, 1.3, 1.4
**Tables in this prompt:** `xero_connections` (existing — no schema changes)
**Estimated hours:** 14h
**Status:** Carried forward from Phase 1 Prompt 5.1 with optional-mode framing delta only.

Reference Phase 1 brief Prompt 5.1 (lines 5559-5790) in full. Tables, OAuth flow (state, PKCE, callback, token exchange, scopes, redirect URI, encryption with AES-256-GCM and per-tenant HKDF key derivation), token refresh job (5-min cadence, refresh token rotation, expired-connection detection, finance notification), API client centralisation, rate limiting (60 calls/min, 5000/day per tenant, 429 retry honouring `Retry-After`), entity↔tenant binding, circuit breaker on repeated failures, disconnect flow with token revocation — all carried unchanged.

### Phase 2 deltas

**Schema deltas:** None.

**Optional-mode framing:**

The Phase 1 brief implies every entity is connected to Xero. Phase 2 explicitly relaxes this — an entity may operate without a `xero_connections` row indefinitely. The deltas to Phase 1 5.1 implementation are:

1. **`/entities/:id` page does not block on missing Xero connection.** In Phase 1, the entity detail page surfaced the Xero connection card prominently with "Connect Xero" as an implicitly-required action. Phase 2 reframes this: the card shows "Xero: Not connected. The platform works fully without Xero. [Connect Xero]" — and "fully without Xero" is a clickable link to a help article explaining the Manual / CSV_Import flows.

2. **Entity creation does not nudge toward Xero connection.** The post-create wizard from Phase 1 (run on first entity setup) included Xero as step 1. Phase 2 makes this step optional and skippable with no follow-up nag; users can connect Xero later from `/entities/:id/xero`.

3. **System-config flag `xero_connection_required_per_entity` defaults to `false`.** A super-admin may flip this true at the tenant level if SY Homes wants to enforce that every operating entity has an active Xero connection (for an audit-tight environment). When true, entities without an active connection show a banner; when false (default), no banner. Stored in `system_config` (1.7) — no schema delta because `system_config` is key-value JSON.

4. **Notifications recipient list relaxed.** Phase 1 sent connection-loss notifications to "the entity's finance team". Phase 2 sends to users with `xero_connections.admin` permission for that entity, falling back to all `Director` users if no scoped admin exists. This avoids silent failures when finance roles change.

**No deltas to:**

- OAuth callback URL, scope set, encryption scheme, refresh cadence
- Disconnect flow including Xero-side token revocation
- Circuit breaker triggers
- Connection-status state machine (Active / Expired / Revoked / Error / Disconnected)
- Per-entity uniqueness constraints

### Cross-track wiring

- 6.2 must complete before 6.3 (reference sync) and 6.4 (financial mirrors) — same as Phase 1.
- 6.4 actuals creation reads `actuals.source` enum; the value `Xero` lights up only for entities with an active 6.2 connection. For entities without, only `Manual` and `CSV_Import` source values appear in the actuals creation UI.
- 6.5 sync queue depends on 6.2 connection records as before.

### Acceptance criteria

Per Phase 1 5.1 acceptance list (carried forward unchanged), plus:

- [ ] Entity without Xero connection has fully functional commercial flow: create bill manually → 2.5 actuals → 2.6 BCR → 2.4 budget recalc → 2.7 cash flow update, all without any Xero touch
- [ ] `xero_connection_required_per_entity` system-config flag toggles the banner correctly
- [ ] Notifications on connection loss reach `xero_connections.admin` users (or fallback Directors)
- [ ] Help article link from "Not connected" card resolves
- [ ] Skipping Xero in the entity creation wizard does not produce any nag prompts in subsequent sessions

### Out of scope

Per Phase 1 5.1 out-of-scope list (webhook receiver moves to 6.5; reference sync to 6.3; financial mirrors to 6.4; bank/journals to 6.5).

Additionally:
- Migration tool to retire a Xero connection (i.e. "disconnect and re-source historical actuals as Manual") — Future Tasks Phase 4. Disconnecting an entity in Phase 2 leaves historical Xero-sourced actuals intact and tagged as Xero-sourced; new actuals from that point are Manual or CSV_Import.

---

## Prompt 6.3 — Reference Sync: Tracking Categories, COA, Tax Rates, Contacts

**Dependencies:** 1.1, 1.2, 1.4, 1.5, 1.6, 6.2
**Tables in this prompt:** `xero_tracking_categories`, `xero_tracking_options`, `xero_chart_of_accounts`, `xero_tax_rates`, `xero_contacts` (existing — no schema changes)
**Estimated hours:** 10h
**Status:** Carried forward from Phase 1 Prompt 5.2 unchanged.

Reference Phase 1 brief Prompt 5.2 (lines 5793-6096) in full. Tables, setup wizard (5 steps: tracking categories, options auto-seed, COA mapping, contacts, review), initial sync sequence (org details → tracking → options → COA → tax rates → contacts paginated), auto-mapping (exact match on project_code / cost_code; fuzzy via Levenshtein < 3; ambiguous flagged for manual; archive detection on Xero status change), delta sync every 15 minutes, push of new tracking options when projects/cost codes are created in platform, 100-option Xero limit with blocking error and clear guidance — all carried unchanged.

### Phase 2 deltas

**Schema deltas:** None.

**Behavioural deltas:**

1. **Setup wizard skippable post-OAuth.** Phase 1 ran the wizard automatically on first OAuth completion. Phase 2 still runs it but adds a "Skip for now" option at each step — incomplete mappings are persisted and can be revisited via `/xero/mappings`. This supports the optional-mode framing: a user might OAuth-connect to confirm credentials, skip mapping setup, and return to it weeks later.

2. **Subcontractor records (2.7) participate in contact mapping.** Phase 1 contact auto-mapping targeted entities only (Xero contact ↔ SY Homes entity). Phase 2 extends to suppliers (2.7) and subcontractors (2.7) — when a Xero contact's `is_supplier=true` and matches a supplier name (exact or fuzzy), a new `mapped_supplier_id` field is populated. Same for subcontractors. **Schema delta to `xero_contacts`** (small):

```
xero_contacts (additions)
─────────────────────────────────────────────
mapped_supplier_id              uuid FK→suppliers.id
mapped_subcontractor_id         uuid FK→subcontractors.id

Indexes (additions):
- INDEX (mapped_supplier_id) WHERE mapped_supplier_id IS NOT NULL
- INDEX (mapped_subcontractor_id) WHERE mapped_subcontractor_id IS NOT NULL
```

The Phase 1 `mapped_entity_id` remains. A given Xero contact can map to at most one of (entity, supplier, subcontractor); validation blocks two mappings.

3. **Manual override is durable.** If a user manually overrides an auto-match (e.g. corrects an ambiguous mapping), the next delta sync does not overwrite the manual mapping. A `mapping_override_at` timestamp + `mapping_override_by_user_id` capture this. **Small schema delta** to `xero_tracking_options` and `xero_contacts`:

```
xero_tracking_options (additions)
─────────────────────────────────────────────
mapping_override_at             timestamp
mapping_override_by_user_id     uuid FK→users.id
```

(Same two columns added to `xero_contacts`.)

When `mapping_override_at IS NOT NULL`, auto-mapping during delta sync skips this row.

### Cross-track wiring

- 6.3 must complete before 6.4 (financial mirrors) — same as Phase 1.
- 6.3 contact mapping now feeds 2.7 supplier/subcontractor records: a Xero contact mapped to a supplier surfaces on the supplier detail view as "Linked to Xero contact <name>".

### Acceptance criteria

Per Phase 1 5.2 acceptance list (carried forward unchanged), plus:

- [ ] Skip-for-now option works at each wizard step; partial state persisted and resumable
- [ ] Xero contact maps correctly to platform supplier (auto-match on name)
- [ ] Xero contact maps correctly to platform subcontractor (auto-match on name)
- [ ] Mutual-exclusion validation: a Xero contact can map to at most one of (entity, supplier, subcontractor)
- [ ] Manual override persists across delta syncs (mapping not overwritten)
- [ ] `mapping_override_at` populated on manual edit; `auto-suggest` UI button available to revert and re-apply auto-mapping

### Out of scope

Per Phase 1 5.2 out-of-scope list, plus:
- Custom mapping rules engine ("if Xero contact name contains 'Plant' then map to supplier") — Future Tasks Phase 5

---

## Prompt 6.4 — Financial Mirrors: Bills, Invoices, Payments, Credit Notes

**Dependencies:** 1.1–1.7, 2.4, 2.5, 6.2, 6.3
**Tables in this prompt:** `xero_bills`, `xero_invoices`, `xero_payments`, `xero_credit_notes` (existing — no schema changes)
**Estimated hours:** 16h
**Status:** Carried forward from Phase 1 Prompt 5.3 with optional-mode framing delta + CIS-reverse-charge interaction made explicit.

Reference Phase 1 brief Prompt 5.3 (lines 6098-6432) in full. Tables, initial 12-month backfill, bill processing (sync_hash, line-item-by-line-item project + cost code resolution, budget line resolution with auto-create of unbudgeted lines, actuals creation on AUTHORISED, void on VOIDED/DELETED, draft suppression), VAT treatment derivation (NONE / OUTPUT / INPUT / ZERORATED / EXEMPT / DRCHARGE20 reverse charge / RRINPUT-RROUTPUT reduced rate), CIS handling read from Xero CIS module's bill markings, payment processing (matches bill, updates `amount_paid`, marks PAID, links to platform actuals as paid status), credit note processing (negative actuals with `linked_reversing_actual_id`), edit detection via sync_hash diff, push of platform-generated sales invoices to Xero with tracking — all carried unchanged.

### Phase 2 deltas

**Schema deltas:** None.

**Optional-mode framing:**

1. **Actuals from manual or CSV sources are not "missing" from Xero.** Phase 1 operated on the assumption that every actuals row originated in Xero. Phase 2 lights up a third source (`Manual`) and a fourth (`CSV_Import`). The reconciler in 6.5 must distinguish "this Manual actual has no Xero counterpart" (expected — entity unconnected, or one-off manual) from "this Xero-sourced actual went missing" (a problem). The 6.4 build does not need to change behaviour, but the reconciler in 6.5 *does*.

2. **Source field on actuals respected on read.** Phase 1 `actuals.source` enum was `('Manual','Xero','Generated')`; Phase 2 adds `CSV_Import` (added in 2.5 build). 6.4 reads this enum but does not write `Xero` to actuals where source is already set to `Manual` or `CSV_Import` — i.e. if a Xero bill arrives later with the same `supplier_invoice_ref` as a manually-entered actual, the reconciler in 6.5 raises a "potential duplicate" warning rather than silently overwriting. The build flow for this is in 6.5; 6.4 only ensures it does not blindly upsert.

**CIS reverse-charge interaction (made explicit — was open from session 3 closing):**

The Phase 1 5.3 spec correctly handles VAT for reverse charge (`DRCHARGE20`) — input VAT recoverable matches output VAT due, net zero VAT impact. The Phase 1 spec also correctly handles CIS deduction read from Xero's CIS module markings on bill lines.

**The interaction was not explicitly documented**: a CIS-registered subcontractor bill that is also subject to reverse charge VAT carries *both* adjustments on the same line. Detail review confirms the Phase 1 implementation handles this correctly at the data level (CIS deduction and VAT amount are independent fields on `actuals`), but the build verification did not include a reverse-charge CIS scenario. Phase 2 fixes this gap by adding it to the acceptance criteria below.

The mechanics:

```
Subcontractor bill from CIS-registered Net-status subcontractor,
  for labour-and-plant work, where customer applies reverse charge:
  
Bill line:
  Net amount:           £1,000.00 (e.g. £700 labour + £300 plant)
  VAT treatment:        DRCHARGE20 (reverse charge 20%)
  VAT amount on bill:   £0.00 (reverse charge — VAT not paid to subcontractor)
  
Platform processing:
  Line resolution:
    project + cost code → budget_line (per Phase 1 logic)
  
  Actuals creation:
    net_amount = £1,000.00
    vat_amount = £0.00 (reverse charge — no VAT changes hands)
    gross_amount = £1,000.00
    vat_treatment = 'Reverse_Charge'
    
    is_cis_applicable = true (cost code allows AND subcontractor is CIS Net)
    cis_deduction_basis = labour element only = £700.00
    cis_deduction_rate = 20% (Net status)
    cis_deduction_amount = £700.00 × 20% = £140.00
    
    Net to subcontractor (per payment notice):
      net_amount - cis_deduction_amount = £1,000 - £140 = £860.00
  
  Reverse charge VAT entries (handled by Xero CIS module + reverse charge module):
    Input VAT entry:  +£200 (recoverable; £1,000 × 20%)
    Output VAT entry: -£200 (output due; £1,000 × 20%)
    Net VAT to HMRC:  £0
```

The labour-element split (`cis_deduction_basis` < `net_amount` when materials/plant are bundled) reads from Xero CIS module's marked breakdown. If Xero marks the *entire* line as CIS-applicable (which happens for labour-only subcontracts), `cis_deduction_basis = net_amount`. If Xero marks zero CIS, `cis_deduction_amount = 0`. The platform does not second-guess Xero on the CIS classification.

Where Xero CIS marking is missing or appears wrong (e.g. cost code is CIS-applicable but Xero shows zero deduction), the line creates an actuals row with `cis_deduction_amount=0` *and* a `sync_error_type='Other'` flag with message "CIS expected but not marked in Xero — check Xero CIS module configuration." Finance reviews via `/xero/bills` filter on `sync_error_type`.

**Schema delta to `actuals`** (small — should land in 2.5 build, not 6.4 build, to avoid sync skew):

```
actuals (additions to existing Phase 1 schema):
─────────────────────────────────────────────
cis_deduction_basis             decimal(14,2)
                                  -- net amount the CIS rate applies to
                                  -- (typically labour element of mixed labour+plant bill)
                                  -- equals net_amount for labour-only bills
                                  -- equals 0 for non-CIS bills
```

**This delta lands in 2.5 (Actuals and Commitments) build, NOT 6.4.** Capturing here for completeness — the field is referenced from 6.4 logic.

**No further schema deltas.** `vat_treatment`, `vat_amount`, `cis_deduction_amount`, `cis_deduction_rate` are already in the Phase 1 actuals schema.

### Cross-track wiring

- 6.4 reads `actuals.source` set by 2.5 / 6.1 to avoid writing over Manual or CSV_Import actuals (deferred check to 6.5 reconciler).
- Subcontractor bill processing requires the bill's contact to map to a `subcontractors` row (via 6.3 `xero_contacts.mapped_subcontractor_id`). If unmapped, the bill processes with `subcontractor_id = NULL` on actuals and a warning emitted.
- The interaction with 2.8a/2.8b subcontract valuations: a valuation issued via 2.8b that produces a payment notice creates a *platform-side* actuals row (via the valuation → payment-notice flow). When the corresponding bill arrives in Xero post-payment, the reconciler in 6.5 matches them via `subcontractor_id + reference`. 6.4 itself is unchanged on this — the matching lives in 6.5.

### Acceptance criteria

Per Phase 1 5.3 acceptance list (carried forward unchanged), plus:

- [ ] **CIS + reverse charge bill on a CIS Net subcontractor for labour-and-plant work creates actuals with**:
  - `vat_treatment='Reverse_Charge'`, `vat_amount=0`, `gross_amount=net_amount`
  - `is_cis_applicable=true`, `cis_deduction_basis=labour_element` (per Xero marking), `cis_deduction_rate=20%`, `cis_deduction_amount=labour_element × 20%`
- [ ] CIS + reverse charge bill on a CIS Gross subcontractor creates actuals with `cis_deduction_amount=0` (gross status exempts deduction) and `vat_treatment='Reverse_Charge'`
- [ ] Reverse-charge bill on a non-CIS supplier (materials only) creates actuals with `vat_treatment='Reverse_Charge'`, `cis_deduction_amount=0`, `is_cis_applicable=false`
- [ ] When Xero CIS marking is missing on a CIS-eligible line (cost code marked CIS, supplier marked CIS, but Xero CIS module shows 0 deduction): actuals row created with `cis_deduction_amount=0` AND `sync_error_type='Other'` AND error message references "Xero CIS module configuration"
- [ ] Bill from a Xero contact mapped to a `subcontractor_id` populates `actuals.subcontractor_id` (existing field) correctly
- [ ] Bill from a Xero contact unmapped to subcontractor records but matching a supplier mapping populates `actuals.supplier_id`
- [ ] Bill from a Xero contact unmapped entirely creates actuals with `supplier_id=NULL, subcontractor_id=NULL` and a warning
- [ ] Actuals with `source='Manual'` or `source='CSV_Import'` are not overwritten by 6.4 sync (deferred to 6.5 reconciler for duplicate detection)

### Out of scope

Per Phase 1 5.3 out-of-scope list, plus:
- HMRC CIS300 monthly return generation from `actuals.cis_deduction_amount` aggregation — Phase 4 (HMRC CIS direct submission). Phase 2 still relies on Xero CIS module for HMRC submission.
- Reverse-charge classification engine inside the platform (i.e. "should this bill be reverse charge?" — currently we trust Xero) — out of scope; SY Homes's accountant sets this in Xero.
- Re-sourcing actuals between Xero and Manual after the fact (i.e. "this bill was Manual; now connect Xero and back-source it") — Future Tasks Phase 4. Source is set on creation and immutable thereafter.

---

## Prompt 6.5 — Sync Queue, Webhooks, Bank Transactions, Manual Journals, Reconciler

**Dependencies:** 1.1–1.7, 6.2, 6.3, 6.4
**Tables in this prompt:** `xero_sync_queue`, `xero_webhooks`, `xero_bank_transactions`, `xero_manual_journals`, `xero_sync_events` (existing — no schema changes)
**Estimated hours:** 14h
**Status:** Carried forward from Phase 1 Prompts 5.4 + 5.5 merged. Scaled-back depth on reconciliation reporting; full-fidelity sync events log retained.

Reference Phase 1 brief Prompts 5.4 (lines 6435-6731) and 5.5 (lines 6734-6906) in full. Tables, webhook endpoint with HMAC-SHA256 verification + dedup + 5-second response, sync queue worker with priority + exponential backoff + dead-letter handling + cascade logic, bank transaction read-only mirror, manual journal read-only mirror, sync events row per API call (event_type / resource_type / outcome / duration / error / correlation_id), nightly delta reconciliation per connection (orphan detection, amount reconciliation, VAT reconciliation, mapping health), manual reconciliation trigger, dashboard KPIs — all carried.

### Phase 2 deltas

**Schema deltas:** None.

**Merge consequences:**

The Phase 1 5.4+5.5 split was a length-management decision — both prompts touched the same conceptual surface (queue + webhooks + reconciliation). Phase 2 merges them at the prompt level (one Emergent build cycle) but the build internally remains two coherent units: (a) sync queue + webhooks + bank/journals; (b) reconciler + sync events. Build verification covers both halves.

**Scaled-back reconciliation reporting:**

Phase 1 5.5 specified a rich nightly reconciliation:
- Orphan detection (Xero bill voided → platform actual voided)
- Amount reconciliation per quarter (sum bills vs sum actuals, warn if > £1)
- VAT reconciliation per quarter (compute platform VAT vs Xero VAT Return totals)
- Mapping health (% bills tagged, top untagged suppliers)

Phase 2 retains the *core checks* — orphan detection, amount reconciliation per quarter, mapping health — but **VAT-return-level reconciliation is scaled back to "alert if month-on-month variance > 5%" rather than per-quarter Xero VAT Return reconciliation**. Reasoning:

- VAT Return reconciliation requires `GET /Reports/TaxReturns` with quarter-end parameters; reliable but introduces additional API surface to maintain
- The optional-Xero framing means some entities won't have a Xero-side return to reconcile against
- A simpler month-on-month variance alert covers the practical case (catch a sudden divergence) without the complexity

Quarterly Xero VAT Return reconciliation moves to **Future Tasks Phase 7** (reporting and data enhancements) where it belongs alongside investor reporting and BI work.

**New: Reconciler handles 6.4's optional-mode duplicate detection.**

The 6.4 carry-forward defers Manual / CSV_Import duplicate detection to the reconciler. The mechanics:

```
For each Xero bill ingested (post-6.4 actuals creation):
  Search for actuals with:
    - source IN ('Manual','CSV_Import')
    - entity_id = bill.entity_id
    - supplier_invoice_ref = bill.invoice_number (or fuzzy match)
    - transaction_date within ±3 days of bill.invoice_date
    - net_amount within £0.50 of bill.net_amount
  
  If match found:
    Do NOT void the existing Manual/CSV_Import actual.
    Do NOT skip the Xero ingest (the Xero version is still ingested as a Xero-source actual).
    Create a 'potential_duplicate' record in xero_sync_events with severity='Warning':
      details = { manual_actuals_id, xero_actuals_id, match_basis }
    Notify finance via xero_sync.admin notification: 
      "Possible duplicate: Manual/CSV actual £X for <supplier> on <date> matches Xero bill <number>. 
       Review and void one if confirmed duplicate."
  
  If no match found:
    Proceed normally (Xero ingest creates its own actual).
```

This deliberately doesn't auto-resolve. SY Homes's finance team makes the call; the platform surfaces the candidate match and provides a "void this one as duplicate" action on either record.

**No deltas to:**
- Webhook HMAC verification, dedup, 5-second response
- Sync queue worker, priority handling, dead-letter, cascade
- Bank transaction / manual journal mirror behaviour (read-only)
- Sync events log fidelity (every API call logged)
- Dashboard KPIs structure
- Manual reconciliation trigger

### Cross-track wiring

- 6.5 reconciler is the only piece that touches `actuals.source` to detect Xero-vs-Manual/CSV duplicates; 6.4 ingest does not.
- Sync events log is read by 7.4 reporting (Xero health KPI tile on director dashboard) and by 8.3 launch readiness (verify zero `Failure` outcomes in the 24h preceding go-live).
- Notifications go via 1.7 system_config + notifications infrastructure; reconciliation summary is a queued notification (not real-time).

### Acceptance criteria

Per Phase 1 5.4 + 5.5 acceptance lists (carried forward unchanged), plus:

- [ ] Manual/CSV actual matching a later-arriving Xero bill produces a `potential_duplicate` warning in `xero_sync_events`
- [ ] Notification raised to xero_sync.admin users with both actuals references
- [ ] Neither actual is auto-voided; the warning is informational
- [ ] Reconciler runs even when entity has no active Xero connection — produces a "no Xero — skipping Xero-side checks" event row, but still runs orphan detection on previously-Xero-sourced actuals (which should now be stranded)
- [ ] Month-on-month variance alert (>5% change in actuals total per entity) fires correctly (replaces Phase 1's per-quarter VAT Return reconciliation in 6.5; full reconciliation deferred to Phase 7)
- [ ] Sync events log retains every API call with full fidelity (event_type, resource, outcome, duration_ms, request_url redacted, response_status, error_code/message)
- [ ] Sync events log has at least 90-day retention with index health (Phase 1 retention spec was unbounded; Phase 2 caps at 90 days online with archive job to cold storage)

### Out of scope

Per Phase 1 5.4 + 5.5 out-of-scope lists, plus:
- Quarterly Xero VAT Return reconciliation — moved to Future Tasks Phase 7
- Auto-resolution of Manual/CSV vs Xero duplicates — explicitly deferred (humans decide)
- Sync events SIEM export — Future Tasks Phase 6 (security hardening)
- Cross-tenant webhook routing for Xero Practice connections — out of scope; SY Homes uses standard Organisation connections

---

## Track 7 — Sales + Plots + Public Surface

**Duration:** 8 weeks
**Prompts:** 4 (all NEW)
**New tables:** 14
**Dependencies:** 1.5 (RBAC), 2.4–2.8b (financial spine), 3.4 (procurement → subcontract for retentions), 4.5 (programme for plot status auto-transitions), 4.6 (snags → DLP defects via flag), 6.5 (sync events for public API audit parity)

### Track goal

Stand up the sales side of the business: house types, plots, buyers, viewings, reservations, sales progression through exchange and completion, post-completion retention release and DLP management, and a small public read-only API surface that exposes available-plot data for the marketing site. This track converts SY Homes from a build-side platform into a complete property development OS.

### Phase 1 → Phase 2 mapping

Track 7 is entirely new. Phase 1 had no sales, plots, or public API content; the only adjacent Phase 1 content was the document model (Phase 1 Track 4) which is extended via deltas in 7.1 and 7.2.

### Resolution: DLP defects

Skeleton flagged a `dlp_defects` table as candidate for 7.3. Resolved as a flag on `snags` (`is_dlp_defect boolean` + `dlp_period_id` FK) rather than a separate table. Rationale: DLP defects ARE snags — same severity model, same photo evidence, same assignment workflow, same customer-visible status. Splitting them would force duplicate workflows and dual-write risk. Track 7.3 inherits 4.6's snag machinery and adds a DLP scoping layer above it.

---

### 7.1 Plot Management + House Types Library

**Duration:** 10 hours
**Status:** NEW
**Dependencies:** 1.5 (RBAC), 3.4 (subcontracts for cost rollup), 4.5 (programme for status auto-transitions), 4.6 (snags), Track 6.1 (CSV framework for bulk import)

#### Schema

**`house_types`** — tenant-level reusable library of house type templates. A scheme uses house types from this library; multiple schemes can reuse the same Type B 3-bed semi.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | |
| `code` | varchar(32) | e.g. `TYPE_B_3BED_SEMI`; UNIQUE per tenant |
| `name` | varchar(128) | display name |
| `property_class` | enum | `Detached / Semi_Detached / Terraced / End_Terrace / Apartment / Bungalow / Townhouse / Other` |
| `bedrooms` | smallint | |
| `bathrooms` | smallint | (including ensuites) |
| `storeys` | smallint | |
| `gia_sqm` | decimal(8,2) | gross internal area, baseline |
| `gia_sqft` | decimal(10,2) GENERATED | `gia_sqm × 10.7639` |
| `parking_spaces` | smallint | |
| `garage_type` | enum | `None / Integral / Attached / Detached / Carport` |
| `build_cost_baseline` | decimal(14,2) | reference cost; not contractually binding |
| `floor_plan_document_id` | uuid FK → documents | |
| `elevation_document_id` | uuid FK → documents | |
| `specification_document_id` | uuid FK → documents | full spec PDF |
| `status` | enum | `Draft / Active / Retired` |
| `created_at`, `updated_at`, `created_by_user_id` | | standard audit |

UNIQUE `(tenant_id, code)`. Soft-delete via `Retired` status — house types referenced by historical plots cannot be hard-deleted.

**`plots`** — per-scheme plot records.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `project_id` | uuid FK | |
| `plot_number` | varchar(32) | e.g. `Plot 14`; UNIQUE per project |
| `uprn` | varchar(16) | Unique Property Reference Number when issued |
| `house_type_id` | uuid FK → house_types | nullable for bespoke plots |
| `gia_sqm_actual` | decimal(8,2) | as-built; can deviate from house type baseline |
| `address_line_1`, `address_line_2`, `town`, `county`, `postcode` | varchar | full postal address when assigned |
| `sale_stage` | enum | `Pre_Construction / Under_Construction / Available / Reserved / Exchanged / Completed / Sold / Withdrawn` |
| `construction_status` | enum | `Not_Started / In_Progress / Practical_Completion / Defects_Period_Closed` |
| `listing_price` | decimal(14,2) | asking price |
| `agreed_sale_price` | decimal(14,2) | contracted price (set on reservation) |
| `buyer_id` | uuid FK → buyers | denormalised to active buyer |
| `reservation_id` | uuid FK → reservations | denormalised to active reservation |
| `listing_published_to_public_api` | boolean DEFAULT false | gates publication via 7.4 |
| `listing_summary` | text | 1–2 paragraph marketing blurb |
| `listing_features` | jsonb | array of bullet-point features for marketing |
| `hero_image_document_id` | uuid FK → documents | required to publish |
| `gallery_document_ids` | jsonb | ordered array of document UUIDs |
| `energy_rating_target` | varchar(2) | e.g. `B`, `A` — target SAP rating |
| `energy_rating_actual` | varchar(2) | EPC after PC |
| `build_cost_to_date` | decimal(14,2) | denormalised, refreshed nightly from actuals attributed to plot |
| `forecast_final_cost` | decimal(14,2) | manual or computed |
| `margin_at_listing` | decimal(14,2) GENERATED | `listing_price - forecast_final_cost` |
| `pc_date` | date | practical completion |
| `completion_date` | date | legal completion (sale) |
| `created_at`, `updated_at`, `created_by_user_id` | | |

UNIQUE `(project_id, plot_number)`. Indexed on `(tenant_id, sale_stage)`, `(project_id, sale_stage)`, `(listing_published_to_public_api) WHERE listing_published_to_public_api = true`.

**`plot_status_history`** — append-only audit of `sale_stage` and `construction_status` transitions.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `plot_id` | uuid FK | |
| `field_changed` | enum | `sale_stage / construction_status` |
| `old_value`, `new_value` | varchar(32) | |
| `change_reason` | text | manual change reason or auto-trigger code |
| `triggered_by` | enum | `Manual / Programme_Task / Reservation / Exchange / Completion / Snag_Closure / System` |
| `triggered_by_ref_id` | uuid | task/reservation/etc. ID |
| `changed_at`, `changed_by_user_id` | | |

#### Schema deltas

- **`documents`**: add `related_house_type_id uuid FK`, `related_plot_id uuid FK`, both nullable, both indexed. (The `related_plot_id` was flagged in session 4a's 5.2 detail — confirmed here as the formal landing point.)

#### Business logic

**Status auto-transitions.** When all programme tasks tagged with `is_pc_milestone = true` for a plot's parent project complete, the plot's `construction_status` auto-advances to `Practical_Completion` and `pc_date` is set to the latest completion date. Auto-transitions write a `plot_status_history` row with `triggered_by = 'Programme_Task'`. Manual override permitted for directors, with mandatory `change_reason`.

**Plot publication gate.** A plot can only have `listing_published_to_public_api = true` if all of: `listing_price IS NOT NULL`, `listing_summary IS NOT NULL`, `hero_image_document_id IS NOT NULL`, `sale_stage IN ('Available')`. Enforced at the API layer with a structured error listing missing fields, and re-checked nightly — plots that fall out of compliance are auto-unpublished with a director notification.

**Bulk plot creation.** When a project is created with a known unit count, a "Generate plots" wizard creates N plots with `plot_number = 'Plot 1'`, `'Plot 2'`, … and a chosen house type. Director can then edit each individually.

**CSV import via 6.1.** `Plots_Adapter` registered with the CSV framework; columns: `plot_number, house_type_code, gia_sqm_actual, address_line_1, postcode, listing_price, sale_stage`. Import is project-scoped (project selected at upload time, not in the file).

**Build cost rollup.** Nightly job computes `build_cost_to_date` per plot by summing `actuals.amount_net_gbp` where `actuals.related_plot_id = plot.id` plus a project-overhead allocation share (allocated by GIA proportion across active plots). Allocation rule is documented per project in `project_metadata.cost_allocation_basis` (default: `gia_proportional`; alternatives: `equal_per_plot`, `manual_per_plot_override`).

#### UI

- **`/projects/:id/plots`** — plot board with toggle between card grid (default) and list table. Cards show plot number, house type, sale stage badge, listing price, hero image thumbnail. Filter by sale_stage, construction_status, house_type. Bulk select for status updates.
- **`/projects/:id/plots/:plot_id`** — plot detail with 7 tabs:
  1. **Overview** — addresses, house type, dimensions, construction + sale status.
  2. **Buyer & Reservation** — current buyer, reservation, sales progression links into 7.2.
  3. **Programme** — programme tasks scoped to this plot (filter on 4.5).
  4. **QA & Handover** — snags filtered by `related_plot_id`, PC checklist, EPC link, handover pack status.
  5. **Financials** — actuals attributed to plot, build cost vs forecast, margin.
  6. **Documents** — documents with `related_plot_id = this`.
  7. **History** — `plot_status_history` timeline.
- **`/house-types`** — tenant-level house types library. Card grid with thumbnail (elevation document preview), code, name, key dimensions.
- **`/house-types/:id`** — full editor with embedded floor plan + elevation viewer.

#### Permissions

| Permission | Scope | Roles |
|---|---|---|
| `plots.view` | tenant | sales, contracts, finance, director, project_manager |
| `plots.create` | project | director, project_manager |
| `plots.edit` | project | director, project_manager, sales (limited to listing fields only) |
| `plots.delete` | tenant | director (with audit + only if `sale_stage = 'Pre_Construction'`) |
| `plots.publish` | project | director, sales (via project assignment) |
| `house_types.view` | tenant | all roles |
| `house_types.manage` | tenant | director, design_manager (new role flagged in closing) |

`plots.edit` is field-scoped: sales can edit `listing_price`, `listing_summary`, `listing_features`, `hero_image_document_id`, `gallery_document_ids`, `listing_published_to_public_api` only. Construction fields, prices contracted into a reservation, and address fields require `director` or `project_manager`.

#### Acceptance criteria

- [ ] House types library at tenant level; multiple projects can reference the same type
- [ ] Plot CSV import via 6.1 framework with project scope at upload
- [ ] Plot status auto-transitions on programme PC milestone task completion
- [ ] Status history records every transition with trigger source
- [ ] Plot publication blocked unless all required listing fields populated; nightly recheck unpublishes drift
- [ ] Sales role can edit listing fields but not construction status or contracted price
- [ ] Build cost rollup nightly with documented allocation basis
- [ ] Plot detail tabs all populate from existing track data (programme, snags, actuals, documents)
- [ ] Soft-delete only — historical plots referenced by completed sales cannot be hard-deleted
- [ ] Bulk plot generation wizard at project creation with house type assignment

#### Out of scope

- Full unit-mix library with planning-permission cross-reference (Phase 4)
- Plot-level cost forecasting at sub-cost-code granularity (Future Tasks)
- Off-plan waitlist with deposits (Phase 4)
- Plot map view / GIS overlay (Phase 4)
- Marketing PDF brochure generation per plot (Phase 5)
- VR / 3D walkthrough integration (Phase 6)
- Rightmove / Zoopla feed integration (Phase 4)
- Sales price negotiation history tracking — the contracted price overwrites the listing price; prior offers not retained (Phase 5 if needed)

---

### 7.2 Buyer Pipeline + Reservations + Sales Progression

**Duration:** 10 hours
**Status:** NEW
**Dependencies:** 7.1 (plots), 1.5 (RBAC), Track 2 (deposits land as actuals), Track 4 documents (reservation forms, contracts)

#### Schema

**`buyers`** — buyer records, supporting joint buyers, company/trust buyers, and full GDPR consent capture.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | |
| `buyer_type` | enum | `Individual / Joint / Company / Trust / Other` |
| `primary_first_name`, `primary_last_name` | varchar(64) | |
| `primary_email`, `primary_phone` | varchar | indexed for search |
| `secondary_first_name`, `secondary_last_name`, `secondary_email`, `secondary_phone` | varchar | for `Joint` |
| `company_name`, `company_number` | varchar | for `Company / Trust` |
| `correspondence_address_line_1`, `_line_2`, `town`, `county`, `postcode` | varchar | |
| `buying_position` | enum | `First_Time_Buyer / Selling_Existing / Cash_Buyer / Investment_Buyer / Help_To_Buy / Shared_Ownership / Other` |
| `mortgage_required` | boolean | |
| `mortgage_lender` | varchar(128) | |
| `mortgage_status` | enum | `Not_Started / DIP_Obtained / Application_Submitted / Valuation_Booked / Valuation_Complete / Offer_Issued / Offer_Accepted / Withdrawn` |
| `mortgage_amount` | decimal(14,2) | |
| `solicitor_id` | uuid FK → solicitors | nullable until appointed |
| `gdpr_marketing_consent` | boolean DEFAULT false | |
| `gdpr_consent_at` | timestamptz | |
| `gdpr_consent_record` | jsonb | full consent capture: source, ip, text version, channels (email/phone/post/sms) |
| `lead_source` | varchar(64) | how they heard about the development |
| `notes` | text | sales-team free text |
| `status` | enum | `Active / Withdrawn / Lost / Completed` |
| `created_at`, `updated_at`, `created_by_user_id` | | |

GDPR feeds into the 5.3 GDPR register: every buyer with `gdpr_marketing_consent = true` is exposed to the register via the `gdpr_consent_record` jsonb evidence field.

**`buyer_viewings`** — tracks viewings, conversion signal for sales pipeline.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `buyer_id`, `plot_id` | uuid FK | plot_id nullable for general scheme viewings |
| `project_id` | uuid FK | |
| `viewing_type` | enum | `In_Person / Virtual_Live / Self_Guided` |
| `scheduled_at` | timestamptz | |
| `completed_at` | timestamptz | |
| `status` | enum | `Scheduled / Completed / Cancelled / No_Show` |
| `buyer_interest_level` | enum | `Hot / Warm / Cold / Not_Interested` (set post-viewing) |
| `notes` | text | |
| `created_at`, `updated_at`, `created_by_user_id` | | |

**`solicitors`** — firm-level reusable.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | |
| `firm_name` | varchar(128) | |
| `sra_number` | varchar(16) | SRA regulation number |
| `dx_number` | varchar(32) | DX exchange address |
| `office_address_line_1`, `_line_2`, `town`, `county`, `postcode` | varchar | |
| `fee_earner_name` | varchar(128) | |
| `fee_earner_email`, `fee_earner_phone` | varchar | |
| `acts_for` | enum | `Buyer / Seller / Both / Either` (declared at firm level) |
| `notes` | text | |
| `status` | enum | `Active / Inactive` |
| `created_at`, `updated_at`, `created_by_user_id` | | |

**`reservations`** — the central sales-progression entity.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `project_id`, `plot_id`, `buyer_id` | uuid FK | |
| `reservation_date` | date | |
| `reservation_fee_amount` | decimal(10,2) | |
| `reservation_fee_status` | enum | `Pending / Received / Refunded / Forfeited / Applied_To_Purchase` |
| `reservation_fee_received_at` | timestamptz | |
| `reservation_fee_actual_id` | uuid FK → actuals | the receipt actual when banked |
| `agreed_sale_price` | decimal(14,2) | contracted price (overrides listing) |
| `expiry_date` | date | default `reservation_date + 28 days`; configurable per `system_config.reservation_expiry_days` |
| `status` | enum | `Active / Exchanged / Lapsed / Withdrawn / Cancelled` |
| `reservation_form_document_id` | uuid FK → documents | signed reservation form |
| `withdrawal_reason` | text | required when status set to Withdrawn/Cancelled |
| `exchanged_at`, `completed_at` | timestamptz | |
| `notes` | text | |
| `created_at`, `updated_at`, `created_by_user_id` | | |

CRITICAL CONSTRAINT: `UNIQUE (plot_id) WHERE status = 'Active'` — at most one active reservation per plot at the database level. Prevents race-condition double-reservations.

**`conveyancing_milestones`** — progression checklist per reservation.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `reservation_id` | uuid FK | |
| `milestone_type` | enum | 21 values: `Reservation_Form_Signed / Reservation_Fee_Received / Solicitor_Appointed_Buyer / Solicitor_Appointed_Seller / Memorandum_Of_Sale_Issued / Searches_Ordered / Searches_Returned / Mortgage_DIP / Mortgage_Application / Mortgage_Valuation / Mortgage_Offer / Enquiries_Raised / Enquiries_Answered / Contract_Issued_Buyer / Contract_Signed_Buyer / Contract_Signed_Seller / Deposit_Received / Exchange_Completed / Completion_Statement_Issued / Legal_Completion / Land_Registry_Submitted` |
| `target_date` | date | |
| `completed_date` | date | |
| `status` | enum | `Pending / In_Progress / Complete / Blocked / Skipped` |
| `blocker_reason` | text | required if Blocked |
| `notes` | text | |
| `evidence_document_id` | uuid FK → documents | optional |
| `created_at`, `updated_at`, `updated_by_user_id` | | |

UNIQUE `(reservation_id, milestone_type)` — one of each per reservation. Seeded based on `buying_position` config: e.g. `Cash_Buyer` skips Mortgage_* milestones (created with `Skipped` status).

#### Schema deltas

- **`documents`**: add `related_buyer_id uuid FK`, `related_reservation_id uuid FK`, both nullable, both indexed.

#### Business logic

**Reservation creation transaction.** A single atomic transaction:
1. Insert `reservations` row with `status = 'Active'`.
2. Update `plots.sale_stage = 'Reserved'`, `plots.buyer_id`, `plots.reservation_id`, `plots.agreed_sale_price`.
3. Insert `plot_status_history` row with `triggered_by = 'Reservation'`.
4. Seed `conveyancing_milestones` rows per `buying_position` config (Cash_Buyer skips mortgage track, etc.).
5. Insert `activity_events` row.
6. Notify directors and assigned project manager.

If the unique constraint on `(plot_id) WHERE status = 'Active'` rejects, surface a clear "Plot already reserved" error including the existing reservation reference.

**Reservation expiry job (daily).**
- 7 days before `expiry_date`: notify sales team and director with "Reservation expiring soon" alert.
- On `expiry_date < CURRENT_DATE` AND `status = 'Active'`: auto-set `status = 'Lapsed'`, set `reservation_fee_status = 'Forfeited'` UNLESS director has explicitly set it to `Refunded` first. Update plot back to `Available`. Log to history. Notify director and sales.

**Exchange action.** Available only when ALL of:
- `reservation_fee_status IN ('Received', 'Applied_To_Purchase')`
- `Contract_Signed_Buyer.status = 'Complete'`
- `Contract_Signed_Seller.status = 'Complete'`
- `Deposit_Received.status = 'Complete'`

On exchange, set `status = 'Exchanged'`, `exchanged_at = NOW()`, update plot to `sale_stage = 'Exchanged'`, log history, notify all parties.

**Completion action.** Available only when `status = 'Exchanged'` AND `Legal_Completion.status = 'Complete'`. On completion:
- Set `reservations.status = 'Completed'`, `completed_at = NOW()`.
- Update plot: `sale_stage = 'Completed'`, `completion_date = today`.
- Trigger 7.3 retention release schedule (PC date already set; completion is a separate event for the buyer-side, not the contractor-side).
- Trigger 7.3 plot-scope DLP period start (12 months from completion by default).
- Update buyer status to `Completed`.
- Notify directors, finance, sales.

**Conveyancing milestone updates.** Each milestone update writes an `activity_events` row. `Blocked` status with `blocker_reason` triggers an immediate notification to director and sales. Re-opening a blocked milestone (back to `In_Progress`) clears the blocker notification.

#### UI

- **`/buyers`** — list with filter by status, buying_position, mortgage_status, project, sales_owner. Search by name/email/phone.
- **`/buyers/:id`** — buyer detail with 6 tabs: Overview, Viewings, Reservation, Communications, Documents, History.
- **`/projects/:id/sales-pipeline`** — kanban-style board with columns for `Available / Reserved / Exchanged / Completed`. NOT drag-drop — actions trigger transitions. Each card shows plot number, buyer name, agreed price, days-in-stage, next milestone.
- **`/sales/dashboard`** — KPI tiles (active reservations count, exchanges this month, completions this month, total pipeline value, average days-to-exchange), reservation expiry watchlist (next 14 days), conveyancing blockers list, recent activity feed.
- **`/reservations/:id`** — reservation detail with conveyancing milestones panel, fee status, document grid, history. Action buttons: Mark Fee Received, Exchange, Complete, Cancel/Withdraw (with reason).
- **`/solicitors`** — firm directory with usage count.

#### Permissions

| Permission | Scope | Roles |
|---|---|---|
| `buyers.view` | tenant | sales, director, project_manager, finance |
| `buyers.create`, `buyers.edit` | tenant | sales, director |
| `buyers.delete` | tenant | director (only if no reservation history) |
| `viewings.manage` | project | sales, director |
| `reservations.create` | project | sales, director |
| `reservations.exchange` | project | director only |
| `reservations.complete` | project | director only |
| `reservations.cancel` | project | director only |
| `conveyancing.update` | reservation | sales, director, project_manager |
| `solicitors.manage` | tenant | director, sales |

Director-only gates on exchange/complete/cancel are deliberate: these are commercially binding actions that should not be executable by sales staff alone.

#### Acceptance criteria

- [ ] Buyer record supports Individual, Joint, Company, Trust types
- [ ] GDPR consent capture with full evidence (source, IP, text version, channels) feeds the 5.3 register
- [ ] Solicitors are firm-level reusable across multiple buyers
- [ ] Reservation creation is atomic: rejecting at the unique constraint produces a clear error
- [ ] At most one active reservation per plot enforced at DB level
- [ ] Conveyancing milestones seeded based on buying_position; Cash_Buyer skips mortgage track
- [ ] Daily expiry job notifies 7 days ahead and lapses on past expiry
- [ ] Lapsed reservation auto-forfeits fee unless director explicitly set Refunded first
- [ ] Exchange blocked unless all gating milestones complete
- [ ] Exchange/Complete/Cancel restricted to director role
- [ ] Completion triggers 7.3 retention release + plot-scope DLP period start
- [ ] Sales pipeline board uses action triggers, not drag-drop
- [ ] Reservation form document linkable via `related_reservation_id`
- [ ] Activity events written for every status transition

#### Out of scope

- Customer-facing buyer portal (Phase 3) — buyers access progress via direct sales contact
- AML/KYC integration with Smartsearch/Veriphy (Phase 4)
- E-signature integration for contracts (Phase 4) — currently document upload of wet-signed PDFs
- Marketing automation / drip campaigns (Project Instructions: explicit Phase 4 if at all)
- Lead scoring / behavioural analytics (Project Instructions: explicit Phase 5)
- Two-way solicitor portal for milestone updates (Phase 4) — currently sales updates milestones manually based on solicitor calls/emails
- HTB ASA submission integration (Phase 4)
- Customer feedback / NPS surveys post-completion (Phase 3)
- Multi-buyer-per-plot for housing-association shared ownership schemes — current model assumes one buyer entity per plot (Phase 4 if SY Homes enters HA market)
- Sales price negotiation history (already flagged in 7.1)

---

### 7.3 Post-Completion: Retentions + DLP + Final Accounts

**Duration:** 10 hours
**Status:** NEW
**Dependencies:** 2.8a/2.8b (subcontract valuations + payment certificates), 4.6 (snags), 5.3 (compliance documents for handover packs), 7.1 (plots for plot-scope DLP), 7.2 (completion triggers plot DLP start)

#### Schema

**`retentions`** — one row per subcontract; auto-created when subcontract created.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `project_id`, `subcontract_id` | uuid FK | UNIQUE on subcontract_id |
| `retention_pct` | decimal(5,2) | from subcontract terms (typically 5%) |
| `retention_cap` | decimal(14,2) | absolute cap, nullable |
| `total_accrued` | decimal(14,2) | cumulative accrued from valuations |
| `total_released` | decimal(14,2) | cumulative released across release rows |
| `total_outstanding` | decimal(14,2) GENERATED | `total_accrued - total_released` |
| `practical_completion_date` | date | trigger for first release schedule |
| `dlp_end_date` | date | trigger for second release schedule |
| `status` | enum | `Accruing / Holding / Releasing / Released / Forfeited` |
| `forfeiture_reason` | text | required when Forfeited |
| `created_at`, `updated_at` | | |

**`retention_releases`** — scheduled release rows.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `retention_id` | uuid FK | |
| `release_type` | enum | `Practical_Completion / DLP_End / Interim / Final / Other` |
| `release_pct_of_total` | decimal(5,2) | typically 50/50 across PC and DLP_End; configurable |
| `scheduled_date` | date | trigger date + grace period (default 30 days, configurable) |
| `release_amount` | decimal(14,2) | computed at schedule time |
| `status` | enum | `Scheduled / Approved / Released / Withheld / Cancelled` |
| `withhold_reason` | text | required if Withheld |
| `withhold_until_date` | date | optional review date |
| `release_actual_id` | uuid FK → actuals | the payment actual when released |
| `approved_by_user_id`, `approved_at` | | |
| `released_by_user_id`, `released_at` | | |
| `notes` | text | |
| `created_at`, `updated_at` | | |

**`dlp_periods`** — defects liability periods, scoped to project, plot, or subcontract.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `project_id` | uuid FK | |
| `scope_type` | enum | `Project / Plot / Subcontract` |
| `plot_id` | uuid FK | populated iff scope_type = Plot |
| `subcontract_id` | uuid FK | populated iff scope_type = Subcontract |
| `start_date` | date | |
| `duration_months` | smallint | default 12, configurable per project |
| `end_date` | date GENERATED | `start_date + duration_months months` |
| `extended_end_date` | date | overrides end_date if extended |
| `extension_reason` | text | required when extended |
| `status` | enum | `Active / Expired / Extended / Terminated` |
| `defect_count` | int | denormalised count of open is_dlp_defect snags within scope, refreshed on snag write |
| `created_at`, `updated_at` | | |

CHECK constraint: `(scope_type = 'Project' AND plot_id IS NULL AND subcontract_id IS NULL) OR (scope_type = 'Plot' AND plot_id IS NOT NULL AND subcontract_id IS NULL) OR (scope_type = 'Subcontract' AND plot_id IS NULL AND subcontract_id IS NOT NULL)`.

Multiple DLP rows per project coexist (Project + per-Plot + per-Subcontract). When raising a snag flagged as DLP defect, the system picks the most specific scope: Subcontract > Plot > Project.

**`final_accounts`** — one per subcontract; agreed final value reconciliation.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `project_id`, `subcontract_id` | uuid FK | UNIQUE on subcontract_id |
| `contract_sum` | decimal(14,2) | original contract |
| `total_variations` | decimal(14,2) | sum of approved VOs |
| `adjusted_contract_sum` | decimal(14,2) GENERATED | `contract_sum + total_variations` |
| `total_certified` | decimal(14,2) | sum of certified valuations |
| `total_paid` | decimal(14,2) | sum of payments + retentions held |
| `agreed_final_value` | decimal(14,2) | the negotiated number |
| `adjustment_amount` | decimal(14,2) GENERATED | `agreed_final_value - total_certified` (positive = pay subby more, negative = recover) |
| `agreement_status` | enum | `Pending / In_Negotiation / Agreed / Disputed / Closed` |
| `agreed_at` | timestamptz | |
| `agreed_by_user_id` | uuid FK | |
| `subby_signoff_document_id` | uuid FK → documents | signed final account agreement |
| `notes` | text | |
| `wash_up_actual_id` | uuid FK → actuals | the adjustment actual when closed |
| `created_at`, `updated_at` | | |

#### Schema deltas

- **`snags`** (4.6): add `is_dlp_defect boolean DEFAULT false`, `dlp_period_id uuid FK → dlp_periods` (nullable). Index on `(dlp_period_id) WHERE is_dlp_defect = true`. When `is_dlp_defect = true` is set, `dlp_period_id` must be populated (CHECK constraint).

#### Business logic

**Retention accrual.** On subcontract valuation approval (2.8a), compute retention amount: `gross_certified × retention_pct`, capped at `retention_cap` if set. Add to `retentions.total_accrued`. The valuation payment net of retention is what gets paid; retention is held.

**First release schedule.** When `plots.pc_date` set OR (for non-plot subcontracts) the project-level PC milestone hits:
1. Set `retentions.practical_completion_date`.
2. Schedule `retention_releases` row: `release_type = 'Practical_Completion'`, `release_pct_of_total = 50%` (configurable), `scheduled_date = pc_date + 30 days` grace, `release_amount = total_accrued × 0.5`, `status = 'Scheduled'`.

**Second release schedule.** When PC date is set, also:
1. Compute `dlp_end_date = pc_date + 12 months` (or per-subcontract DLP duration if specified).
2. Set `retentions.dlp_end_date`.
3. Schedule `retention_releases` row: `release_type = 'DLP_End'`, `release_pct_of_total = 50%`, `scheduled_date = dlp_end_date + 30 days` grace, `release_amount = total_accrued - first_release_amount`, `status = 'Scheduled'`.

**Withhold logic.** Daily job, 14 days before any `Scheduled` release: check for open `is_dlp_defect = true` snags within the relevant DLP scope where `severity IN ('Major', 'Critical')` attributable to this subcontract. If found, auto-set `release.status = 'Withheld'`, populate `withhold_reason` with snag references, notify contracts manager and director. The release does NOT auto-approve when defects close — that requires explicit director action via "Re-schedule release" (which sets a new `scheduled_date`, status back to `Scheduled`).

**DLP extension.** When extended, `extended_end_date` is set, status moves to `Extended`. If a release is already `Scheduled` for the original DLP_End date, recompute: cancel the existing release row (status `Cancelled`, reason "DLP extended") and create a new release with the extended date.

**DLP snag scoping.** When raising a snag with `is_dlp_defect = true`, the system finds the most specific active DLP period:
1. If snag has `related_subcontract_id` AND a Subcontract DLP period exists → use that.
2. Else if snag has `related_plot_id` AND a Plot DLP period exists → use that.
3. Else use the Project DLP period.
4. If no Active DLP period in any scope → reject the flag with a clear error.

**Final account closure.** Agreed final value workflow:
1. Director or contracts manager moves status `Pending → In_Negotiation`.
2. After agreement, upload signed sign-off document, set status `Agreed`.
3. Director closes: status `Closed`. If `adjustment_amount ≠ 0`, create a wash-up actual (positive: bill the subcontractor for an additional payment; negative: a credit/recovery). Move subcontract status to `Complete`. This is the only path to closing a subcontract financially.

#### UI

- **`/projects/:id/post-completion`** — overview hub with 4 tabs:
  1. **DLP Overview** — project + plot + subcontract DLP periods, defect counts, expiry watchlist.
  2. **Plot DLPs** — per-plot DLP cards with completion date, end date, extension status, open defects.
  3. **Subcontract Retentions** — table of all retentions with status, accrued, released, outstanding, next release date.
  4. **Final Accounts** — table of subcontract final accounts with agreement status.
- **`/retentions/:id`** — retention detail with release schedule, valuation history, withhold reasons.
- **`/dlp-periods/:id`** — DLP detail with associated defects (snags filtered by `dlp_period_id`).
- **`/final-accounts/:id`** — final account detail with negotiation log, adjustment computation, sign-off document upload, close workflow.
- **`/dashboard/post-completion`** — director cross-project view: retentions outstanding by project, DLP periods expiring next 90 days, final accounts in negotiation, defect-driven withholds requiring action.

#### Permissions

| Permission | Scope | Roles |
|---|---|---|
| `retentions.view` | project | finance, contracts, director, project_manager |
| `retentions.approve_release` | retention | director, finance_director |
| `retentions.withhold` | retention | director, contracts_manager |
| `retentions.release` | retention | finance_director (creates the actual) |
| `retentions.forfeit` | retention | director only |
| `dlp.view` | project | all roles |
| `dlp.manage` | project | director, contracts_manager |
| `dlp.extend` | project | director only |
| `final_accounts.view` | project | finance, contracts, director |
| `final_accounts.negotiate` | subcontract | contracts_manager, director |
| `final_accounts.agree` | subcontract | director only |
| `final_accounts.close` | subcontract | director only |

#### Acceptance criteria

- [ ] Retention auto-created per subcontract; auto-accrues on valuation approval
- [ ] Retention cap respected (does not accrue beyond cap)
- [ ] First release scheduled on PC date set, 30-day grace
- [ ] Second release scheduled on DLP_End date computed from PC + duration
- [ ] 14-day withhold check fires on Major+ open DLP defects attributable to subcontract
- [ ] Withheld release does NOT auto-release on defect closure — director must re-schedule
- [ ] DLP defect snag picks most specific scope (Subcontract > Plot > Project)
- [ ] DLP extension recalculates DLP_End release with cancellation of original release row
- [ ] Plot DLP period auto-starts on legal completion (from 7.2)
- [ ] Subcontract DLP period auto-starts on subcontract Practical_Completion milestone
- [ ] Final account closure with non-zero adjustment creates wash-up actual
- [ ] Subcontract cannot be moved to Complete except via final account closure
- [ ] All retention and DLP actions logged to activity_events
- [ ] is_dlp_defect snags reuse 4.6 photo + severity + assignment workflow

#### Out of scope

- Customer DLP defect reporting via portal (Phase 3 customer portal)
- Customer aftercare warranty notifications / reminders (Phase 3)
- NHBC / Premier Guarantee structural warranty integration (Phase 4)
- Formal adjudication workflow (Construction Act Part II) (Phase 5 — separate solicitor consult workstream already logged)
- Statutory hold-back beyond standard retention (Phase 5)
- Auto-forfeiture of retention without director sign-off (deliberately excluded — always human-gated)
- Multi-currency retentions (Phase 5)
- Retention bond / insurance policy substitution (Phase 5)
- Adjudicator / mediator firm directory (Phase 5)

---

### 7.4 Reporting + Dashboards + Public-Data API

**Duration:** 12 hours
**Status:** NEW
**Dependencies:** 1.5 (RBAC), 2.4 (cost codes), 2.5 (actuals), 2.7 (commitments), 2.8a/2.8b (subcontract financials), 4.6 (snags), 6.5 (sync events for parity), 7.1 (plots), 7.2 (sales pipeline), 7.3 (post-completion)

#### Resolution: unified track confirmed

Skeleton flagged a possible split between operational reporting and the public API. Resolved as one prompt: the public API consumes the same report machinery (definitions, runs, filters) as the internal dashboards. Splitting them duplicates the report definition layer. Two halves of the same prompt:

- **(a) Operational reporting + dashboards** — director, project, finance dashboards seeded with KPI tiles, a small set of canned report definitions, and a basic board pack PDF. Full BI / custom report builder deferred to Phase 7.
- **(b) Public read-only API** — rate-limited, no-auth, two endpoints at launch (available plots, completed schemes), deliberately narrow surface, defence-in-depth field whitelisting.

#### Schema

**`report_definitions`** — registry of every report the system can produce.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | nullable for global system definitions |
| `code` | varchar(64) | e.g. `cash_position_12_week`, `available_plots_public` |
| `name`, `description` | varchar | human-readable |
| `report_type` | enum | `Tabular / KPI_Tile / Chart / Geo / Pivot / Public_Endpoint` |
| `data_source` | enum | `SQL_View / SQL_Query / Programmatic / Aggregate` |
| `source_definition` | text | view name, SQL, or function name (server-side resolved) |
| `is_public_safe` | boolean DEFAULT false | DEFENCE-IN-DEPTH gate: must be true to be exposable via public API |
| `public_api_field_whitelist` | jsonb | array of field names — only these returned when surfaced via public API |
| `default_filters`, `default_sort` | jsonb | |
| `category` | enum | `Financial / Sales / Programme / Compliance / Operational / Public` |
| `permission_required` | varchar(64) | RBAC permission key |
| `status` | enum | `Active / Deprecated / Retired` |
| `created_at`, `updated_at`, `created_by_user_id` | | |

UNIQUE `(tenant_id, code)` (treating null tenant as global). Seeded with 15 built-in definitions on install (listed below).

**`report_runs`** — audit log of every report execution.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `report_definition_id` | uuid FK | |
| `run_context` | enum | `Dashboard / Board_Pack / Public_API / Manual / Scheduled` |
| `triggered_by_user_id` | uuid FK | nullable for public/scheduled |
| `triggered_by_ip` | inet | public API capture |
| `filter_params` | jsonb | |
| `row_count` | int | |
| `duration_ms` | int | |
| `outcome` | enum | `Success / Error / Timeout / Cached` |
| `error_message` | text | |
| `cache_status` | enum | `Hit / Miss / Bypass` |
| `created_at` | timestamptz | |

90-day retention online, archive job to cold storage.

**`public_api_endpoints`** — registry of public endpoints; each maps to a report definition.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | |
| `endpoint_path` | varchar(128) | e.g. `/api/public/v1/plots/available` |
| `report_definition_id` | uuid FK → report_definitions | must have `is_public_safe = true` |
| `hard_coded_filters` | jsonb | filters applied server-side, NOT overridable by query string |
| `allowed_filter_params` | jsonb | array of param names users CAN provide via query string |
| `allowed_sort_params` | jsonb | array of sortable fields |
| `page_size_default` | smallint DEFAULT 20 | |
| `page_size_max` | smallint DEFAULT 100 | |
| `rate_limit_per_minute` | smallint DEFAULT 60 | per client_ip |
| `rate_limit_per_day` | int DEFAULT 1000 | per client_ip |
| `cache_ttl_seconds` | int DEFAULT 300 | server-side cache |
| `cors_allowed_origins` | jsonb | array of origins; default empty (CORS disabled) |
| `is_enabled` | boolean DEFAULT false | director must explicitly enable |
| `notes` | text | |
| `created_at`, `updated_at`, `enabled_by_user_id`, `enabled_at` | | |

UNIQUE `endpoint_path`. Defence-in-depth checks at request time:
1. Endpoint exists AND `is_enabled = true`.
2. Linked `report_definition.is_public_safe = true`.
3. Requested fields are in the whitelist.
4. Filter params are in `allowed_filter_params`.
5. Hard-coded filters merged in (cannot be overridden).
6. Rate limit not exceeded.

**`public_api_request_log`** — every public API hit.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `endpoint_id` | uuid FK | |
| `client_ip` | inet | |
| `user_agent` | varchar(256) | |
| `request_path`, `request_query` | text | |
| `response_status` | smallint | |
| `response_cached` | boolean | |
| `duration_ms` | int | |
| `created_at` | timestamptz | |

90-day retention online. Rate limit reads from this log (Redis cache fronts it for performance, but log is source-of-truth for daily caps).

#### Public API request/response shape

Standardised JSON shape across all public endpoints:

```json
{
  "data": [ ... whitelisted fields per row ... ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 142,
    "total_pages": 8,
    "next_page_url": "..."
  },
  "meta": {
    "endpoint": "/api/public/v1/plots/available",
    "generated_at": "2026-04-28T10:15:00Z",
    "cache_status": "Hit"
  }
}
```

Errors:

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit of 60 requests per minute exceeded",
    "retry_after_seconds": 42
  }
}
```

Error codes: `RATE_LIMIT_EXCEEDED`, `INVALID_FILTER`, `INVALID_SORT`, `INVALID_PAGE`, `ENDPOINT_DISABLED`, `INTERNAL_ERROR`.

#### Two seeded public endpoints (both `is_enabled = false` at install)

**`/api/public/v1/plots/available`**
- Hard-coded filter: `sale_stage = 'Available'` AND `listing_published_to_public_api = true`.
- Whitelist: `plot_number`, `project_name`, `postcode_locality_only` (first half of postcode only — e.g. `SW19` not `SW19 4AB`), `listing_price`, `bedrooms`, `bathrooms`, `gia_sqm`, `property_class`, `listing_summary`, `hero_image_url`, `gallery_image_urls`, `energy_rating_target`, `listing_features`.
- Allowed filter params: `bedrooms_min`, `bedrooms_max`, `price_min`, `price_max`, `property_class`, `project_name`.
- Allowed sort: `listing_price`, `bedrooms`, `gia_sqm`, `created_at`.

**`/api/public/v1/schemes/completed`**
- Hard-coded filter: project status = Completed.
- Whitelist: `project_name`, `town`, `county`, `postcode_locality_only`, `unit_count`, `completion_year`, `hero_image_url`, `description`.
- Allowed filter params: `completion_year_min`, `completion_year_max`, `county`.
- Allowed sort: `completion_year`, `unit_count`.

CORS disabled by default. Image URLs resolved via a separate **public-asset-proxy** route (e.g. `/api/public/v1/assets/:public_asset_id`) that maps a generated `public_asset_id` to an internal `documents.id` server-side. Internal `documents/` paths are never exposed.

#### Three seeded internal dashboards

- **`/dashboard/director`** — KPI tiles (active projects, total pipeline value, exchanges this month, completions this month, open critical snags, retentions outstanding, cash position 12-week summary), project status grid, cash position 12-week chart, pipeline value by stage, red-flag list.
- **`/projects/:id/dashboard`** — financial summary (commitments, actuals, forecast, EAC, variance), programme summary (% complete, critical path days slipped, milestones next 30 days), sales summary (plots available/reserved/exchanged, pipeline value), site activity (recent snags, recent valuations, recent compliance entries).
- **`/dashboard/finance`** — bills awaiting approval, bills overdue for payment, cash position by entity, CIS month-to-date summary, Xero sync health (last successful sync per entity, error count).

#### Board pack PDF

Director-only action: "Generate Board Pack" with date-range picker. Renders as PDF via `wkhtmltopdf` or `weasyprint` server-side. Content: cover page, executive summary tiles, financial section (cash position, P&L summary by project, commitment vs actual variance), sales section (pipeline value, exchanges/completions YTD, reservation watchlist), programme section (critical path projects, slipped milestones), compliance section (open critical snags by project). Quality is scaffold — investor-grade design polish deferred to Phase 7.

#### Seeded report definitions (15)

| Code | Type | Public-safe |
|---|---|---|
| `cash_position_12_week` | Chart | No |
| `commitment_vs_actual_by_project` | Tabular | No |
| `pipeline_value_by_stage` | KPI_Tile | No |
| `exchanges_completions_ytd` | KPI_Tile | No |
| `reservation_expiry_watchlist` | Tabular | No |
| `bills_awaiting_approval` | Tabular | No |
| `bills_overdue` | Tabular | No |
| `cis_month_to_date` | Tabular | No |
| `xero_sync_health` | Tabular | No |
| `open_critical_snags` | Tabular | No |
| `retentions_outstanding` | Tabular | No |
| `dlp_periods_expiring_90d` | Tabular | No |
| `available_plots_public` | Public_Endpoint | **Yes** |
| `completed_schemes_public` | Public_Endpoint | **Yes** |
| `programme_milestones_next_30d` | Tabular | No |

#### Permissions

| Permission | Scope | Roles |
|---|---|---|
| `reports.view.operational` | tenant | all internal roles |
| `reports.view.financial` | tenant | finance, director |
| `reports.view.sales` | tenant | sales, director |
| `reports.view.compliance` | tenant | h_and_s, director, project_manager |
| `dashboards.view.director` | tenant | director |
| `dashboards.view.project` | project | director, project_manager, sales (own projects) |
| `dashboards.view.finance` | tenant | finance, director |
| `board_pack.generate` | tenant | director only |
| `public_api_endpoints.view` | tenant | director, super_admin |
| `public_api_endpoints.manage` | tenant | director, super_admin |
| `public_api_endpoints.enable` | tenant | director only |

#### Acceptance criteria

- [ ] Report definitions registry with `is_public_safe` flag at definition level
- [ ] Public API endpoint registry with `is_enabled = false` default — director must explicitly enable
- [ ] Defence-in-depth: a public endpoint cannot serve a report whose `is_public_safe = false`
- [ ] Field whitelist enforced at response build time — non-whitelisted fields stripped server-side
- [ ] Hard-coded filters cannot be overridden via query string
- [ ] Rate limits enforced per client_ip (per minute + per day) with 429 response and `retry_after_seconds`
- [ ] Page size capped at `page_size_max`
- [ ] CORS disabled by default; explicit allow-list per endpoint
- [ ] Public asset proxy resolves `public_asset_id` → internal document; internal paths never exposed
- [ ] Postcode locality redaction: only first half of postcode in public responses
- [ ] All public API requests logged to `public_api_request_log` with response status, cache status, duration
- [ ] `report_runs` audit captures every dashboard render and every public API hit
- [ ] Three seeded dashboards present with documented KPIs
- [ ] Board pack PDF generates from any date range with all four content sections
- [ ] Two seeded public endpoints present, both disabled at install
- [ ] Director enable workflow writes activity_events row for compliance audit

#### Out of scope

- Custom report builder / SQL-by-user (Phase 5)
- Scheduled email reports (Phase 5)
- Investor-grade board pack design (Phase 7)
- Authenticated public API for buyer-specific data — buyer portal is Phase 3
- Webhook subscriptions for marketing site (Phase 4) — marketing site polls
- Geographic / map plot search via public API (Phase 4)
- API versioning beyond v1 (no v2 contract until Phase 4 buyer portal)
- GraphQL surface (out of scope permanently — REST is the contract)
- Audit log dashboards beyond report_runs basic table (Phase 6 security hardening)
- Cross-tenant aggregate reporting (deliberately excluded — strict per-tenant isolation)
- BI tool integration / data warehouse export (Phase 7)

---

## Track 8 — Polish + Cutover + Buildertrend Retirement

**Duration:** 5 weeks
**Prompts:** 3 (all NEW)
**New tables:** 0
**Dependencies:** all prior tracks

### Track goal

Production hardening, design polish (consuming the designer deliverables produced ahead of the track), Buildertrend cutover plan execution, and go-live with structured post-launch monitoring. T8 is deliberately the final track and consumes — rather than produces — design and content artefacts. No new schema is built in T8; everything is operational maturity, performance, UX consistency, and migration discipline.

### Phase 1 → Phase 2 mapping

Track 8 is restructured versus skeleton. Skeleton had 8.1 Portal Hardening, 8.2 Mobile UX + Designer, 8.3 Performance + Launch Readiness. Per session 4b opener pre-decision (opener wins), T8 is 8.1 Performance + design polish, 8.2 Buildertrend cutover plan, 8.3 Go-live + post-launch monitoring. The skeleton's "Portal Hardening" content is absorbed into 8.1's polish pass (RBAC review, error handling, permission edge cases). The skeleton's "Mobile UX + Designer" content collapses because the designer engagement runs ahead of T8 as a separate workstream — the deliverables land into 8.1's polish pass rather than being a discrete prompt.

This deviation is documented in §"Changes versus skeleton" item 9 (added by this session).

---

### 8.1 Performance + Design Polish Pass

**Duration:** 12 hours
**Status:** NEW
**Dependencies:** all prior tracks; consumes designer engagement deliverables (mobile component library, brand tokens, key-screen mockups for 4.1 site activity, 4.3 daily logs, 2.9 commitment register)

#### Scope

A consolidated polish pass covering performance, RBAC robustness, error-handling consistency, accessibility baseline, and design-system consistency. No new business logic and no new tables — this prompt closes the gap between "feature-complete" and "production-grade".

#### Performance work

**Database query review.** Audit the slow-query log from staging soak test (run the soak test as a precondition before this prompt). Target: every API endpoint serving a user-facing page returns p95 < 500ms with realistic seed data (1,000 plots, 5,000 actuals, 50,000 audit rows, 10,000 documents). Specific targets:
- Project dashboard page: p95 < 800ms (12 widgets — heaviest page).
- Site activity feed page (4.1): p95 < 600ms (timeline aggregation).
- Plot board (7.1): p95 < 500ms.
- Public API endpoints (7.4): p95 < 200ms with 5min cache.

**Index audit.** Every foreign key indexed; every status enum used in `WHERE` clauses indexed; every `(tenant_id, X)` composite where X is the most-common second filter (status, project_id, date). Document the index list and rationale. Drop unused indexes flagged by `pg_stat_user_indexes` (after 2 weeks of staging traffic).

**N+1 query audit.** Run a static analysis pass + dynamic check via query log: every list endpoint must use eager-load / explicit joins for relationships rendered in the response. Target: zero N+1 queries on any endpoint serving > 10 rows.

**Background job tuning.** Review every nightly/scheduled job:
- Document expected duration and observed duration on staging soak data.
- Add timeout protection (default 30 min, configurable per job).
- Add structured logging with start/end markers and row counts.
- Add Sentry/equivalent error capture.
- Daily-job order documented (Xero sync → reconciler → reservation expiry → retention release schedule check → DLP defect withhold check → build cost rollup → variance alert → archive jobs).

**Cache layer.** Introduce Redis cache (or platform-native equivalent) for:
- Public API responses (TTL per endpoint, default 300s).
- Dashboard KPI tiles (TTL 5 min, invalidate on write events tagged to the relevant scope).
- Permission resolution (per-user permission set, TTL 5 min, invalidate on RBAC write).
- House types library (TTL 1 hour, invalidate on write).

#### Design polish

**Component library consumption.** Designer engagement delivers: brand tokens (colour palette, typography scale, spacing scale, radius scale), mobile component library (forms, cards, tables, navigation, modals, dialogs at mobile breakpoints), and key-screen mockups for the three highest-friction surfaces (4.1 site activity feed, 4.3 daily logs, 2.9 commitment register). 8.1 implements these:
- Replace ad-hoc inline styles with design-token references throughout the codebase. Document any deviations.
- Apply mobile component library to all responsive surfaces; ensure no hardcoded breakpoints remain.
- Implement the three key-screen mockups pixel-accurate at mobile and desktop.

**Loading states.** Every async surface has a documented loading state: skeleton screens for lists, inline spinners for actions, full-page overlays for slow operations (>2s). No surface should show a blank or flashing state.

**Error states.** Every async surface has a documented error state: inline error message with retry button for failed loads, toast for failed actions, full-page error for catastrophic failures. Errors include a correlation ID surfaced to the user (for support).

**Empty states.** Every list surface has a documented empty state: helpful copy explaining what the surface shows, primary action to populate it ("Create your first project", "Import suppliers via CSV"), illustration or icon (from designer library).

**Accessibility baseline.** Target WCAG 2.1 AA on the top 20 surfaces (director dashboard, project dashboard, plot board, sales pipeline, daily logs, site activity, all forms in 2.5/2.7/3.4/4.6/7.2). Specific checks:
- All interactive elements keyboard-reachable.
- Focus indicators visible.
- Colour contrast ratio ≥ 4.5:1 for text.
- Form labels associated with inputs.
- Error messages announced to screen readers (`aria-live`).
- Tables use proper `<th>` and scope.
- Modals trap focus and restore on close.
- Documented exceptions only for surfaces not in the top-20 list.

#### RBAC robustness

**Permission edge case audit.** For every prior-track permission, write a test verifying:
- A user without the permission gets a 403 (not 200, not 500).
- A user with the permission scoped to project A cannot act on project B.
- Field-level scoped permissions (e.g. `plots.edit` for sales = listing fields only) reject writes to non-permitted fields with a 403 and clear field reference.
- Director-only actions (reservations.exchange, reservations.complete, retentions.release, final_accounts.close) reject all non-director roles.

**Audit log coverage.** For every state-changing endpoint, verify an `activity_events` row is written. Document any deliberate exclusions.

#### Error handling consistency

**Error envelope.** Every API error response uses the standard envelope: `{ error: { code, message, details?, correlation_id } }`. Document the error code catalogue. Internal errors NEVER leak stack traces or SQL fragments.

**Validation error consistency.** Every form validation error returns 422 with field-level error map: `{ error: { code: 'VALIDATION_ERROR', fields: { field_name: ['error message'] } } }`. Frontend displays inline per-field.

**Idempotency.** Document idempotency behaviour for every state-changing endpoint. Where retries are safe (most reads, most idempotent writes), document. Where retries are unsafe (creating reservations, releasing retentions, posting actuals), require an idempotency-key header and dedupe within 24h.

#### Permissions

No new permissions; this prompt audits existing ones.

#### Acceptance criteria

- [ ] Slow query log review with p95 < 500ms target met on top 20 endpoints
- [ ] Every FK indexed; every status enum used in WHERE indexed
- [ ] Zero N+1 queries on list endpoints serving >10 rows
- [ ] Background jobs documented with timeouts, logging, error capture
- [ ] Redis cache layer in place for public API, dashboards, permissions, house types
- [ ] Cache invalidation tested on every relevant write path
- [ ] Design tokens consumed throughout codebase; documented deviations only
- [ ] Mobile component library applied; no hardcoded breakpoints
- [ ] Three key-screen mockups (4.1, 4.3, 2.9) implemented pixel-accurate
- [ ] Loading, error, empty states present on every async surface
- [ ] WCAG 2.1 AA baseline on top 20 surfaces, documented exceptions only
- [ ] RBAC edge case tests for every permission (no permission, wrong scope, wrong field, director-only)
- [ ] Audit log coverage verified on every state-changing endpoint
- [ ] Standard error envelope on every API error
- [ ] Validation errors return 422 with field-level map
- [ ] Idempotency-key required on unsafe-retry endpoints, 24h dedupe window

#### Out of scope

- Full WCAG 2.1 AAA (Phase 6)
- Internationalisation / multi-language (Phase 4)
- Right-to-left layout support (out of scope permanently — UK-only product)
- Theme switching / dark mode (Phase 5)
- Performance budgets enforced in CI (Phase 5)
- Distributed tracing (OpenTelemetry) full rollout (Phase 6 — basic only here)
- Penetration testing (Phase 6 — separate workstream)
- Load testing beyond soak (Phase 5)
- Skeleton's "Portal Hardening" 10h prompt is absorbed here — RBAC + error handling content lands in 8.1; no separate portal prompt

---

### 8.2 Buildertrend Cutover Plan Execution

**Duration:** 14 hours
**Status:** NEW
**Dependencies:** all prior tracks complete; cutover plan deliverable (`SY_Homes_Buildertrend_Cutover_Plan.md`) signed off ahead of this prompt

#### Scope

Execution of the Buildertrend cutover plan. The plan itself is a separate deliverable produced ahead of T8 (referenced but not duplicated in this prompt). 8.2 implements the cutover *tooling and procedures* the plan calls for: data extraction, mapping, dual-running window operations, and final cutover.

This prompt does NOT replicate the cutover plan content. It implements what the plan specifies.

#### Cutover plan reference

The cutover plan (separate document) defines:
- Source data inventory in Buildertrend (active projects, RFIs, daily logs, schedules, photos, documents, contacts, financial data).
- Mapping table: each Buildertrend entity → SY Hub target table (or "do not migrate" with rationale).
- Cutover phases: Phase A (read-only Buildertrend export + ingest into SY Hub staging), Phase B (parallel-run with both systems), Phase C (Buildertrend marked read-only in SY Homes operations), Phase D (Buildertrend subscription terminated).
- Per-project cutover schedule (which projects cut over when, dependency ordering).
- Rollback plan for each phase.
- Communication plan for site teams.

#### What 8.2 builds

**Buildertrend export ingestion.** Buildertrend offers data export (CSV, ZIP archives for documents). Build ingestion adapters that consume these exports and load into SY Hub:
- Project metadata → `projects` (via 6.1 framework Projects_Adapter).
- Contacts → `suppliers` / `subcontractors` (via 6.1 framework adapters).
- Schedule items → `programme_tasks` (4.5).
- Daily logs → `daily_logs` (4.3).
- RFIs → `rfis` (4.2 if implemented in Phase 2 scope, else `notes` on project).
- Documents → `documents` with appropriate `related_*_id` mapping based on Buildertrend folder structure.
- Photos → `documents` with `document_type = 'site_photo'` and `related_daily_log_id` where date-matchable.
- Financial transactions → `actuals` with `source = 'CSV_Import'` and a "Buildertrend cutover" import_job tag.

Each ingestion adapter is registered with the 6.1 CSV framework. They are NOT first-class adapters in 6.1 — they are cutover-only and marked as such (`is_cutover_adapter = true`, hidden from regular CSV import UI).

**Cutover dashboard.** Per-project cutover progress page:
- Buildertrend extract status (pending / extracted / loaded / verified).
- SY Hub data presence (counts of programmes, actuals, contacts, documents, daily logs).
- Side-by-side comparison view (sample 20 records from each source for spot-check).
- Cutover phase indicator (A / B / C / D).
- Sign-off log: who verified each entity type, when.

**Dual-run safeguards (Phase B).** During parallel-run, both systems are in use. Build:
- Daily reconciliation report: diff in counts (programmes, actuals, daily logs) between Buildertrend export-of-day and SY Hub same-day.
- Conflict detection: same date + same supplier + same amount actuals → flag as potential duplicate, manual resolution required.
- Site-team notification system: when a project moves from Phase A to Phase B, an in-app banner on the project dashboard explains "this project is in dual-run; record actions in both systems". When Phase C: "Buildertrend is read-only for this project; record actions in SY Hub only".

**Buildertrend read-only enforcement (Phase C).** A project flag `buildertrend_read_only_at` (timestamptz). When set, daily reconciliation checks that no NEW Buildertrend records are created post-flag — any new ones are escalated to director (this catches site teams forgetting to switch).

**Document migration tooling.** Buildertrend documents export as ZIP archives with folder structures. Build:
- A ZIP unpacker that walks folder paths and infers `related_*_id` mappings (e.g. folder `Plot 14 / Snags / 2025-Q3` → `related_plot_id = plot_14`, `document_type = 'snag_evidence'`).
- A staging-then-import flow: documents land in a quarantine state, director reviews mappings, bulk-approves or reassigns, then imports.
- Photo metadata extraction: EXIF date → `taken_at`, GPS coords → `taken_at_location` (jsonb).

**Cutover audit log.** Every cutover action (export ingested, sign-off, phase transition, conflict resolution) writes to a dedicated `cutover_events` log (in-memory or as a tagged subset of `activity_events` with `event_type = 'cutover_*'` — implementation choice; no new table needed).

**Rollback tooling.** For each project, a "Revert to Buildertrend primary" action that:
- Reopens Buildertrend write operations (clears the read-only flag).
- Marks SY Hub data for that project as "rollback — do not trust" via a project flag.
- Preserves all SY Hub data for forensic review (no deletion).
- Notifies director and project manager.
- Logs to cutover_events.

#### UI

- **`/cutover`** — director-only cutover hub. Project list with per-project phase indicator. Drill-down to per-project cutover dashboard.
- **`/cutover/projects/:id`** — per-project cutover dashboard described above.
- **`/cutover/document-quarantine`** — document review queue for the ZIP-import flow.
- **`/cutover/conflict-resolution`** — conflict queue from daily reconciliation.

#### Permissions

| Permission | Scope | Roles |
|---|---|---|
| `cutover.view` | tenant | director, super_admin |
| `cutover.execute` | tenant | director, super_admin |
| `cutover.signoff` | project | director only |
| `cutover.rollback` | project | director only |
| `cutover.document_review` | tenant | director, super_admin |

Cutover surfaces are not exposed to general users — site teams interact with the normal SY Hub UI; cutover progress is internal to the migration team.

#### Acceptance criteria

- [ ] Cutover plan deliverable signed off ahead of prompt start
- [ ] Buildertrend export ingestion adapters built for all entity types in mapping table
- [ ] Cutover-specific adapters marked `is_cutover_adapter = true`, hidden from regular CSV UI
- [ ] Per-project cutover dashboard shows phase, counts, sign-off log
- [ ] Daily reconciliation report runs during Phase B with diff counts and conflict flags
- [ ] Phase C read-only enforcement detects new Buildertrend records and escalates
- [ ] Document ZIP import with folder-path-to-related-id inference, quarantine review, bulk approve
- [ ] EXIF metadata extraction for photo documents (taken_at, GPS to jsonb)
- [ ] Rollback action preserves data, sets flag, notifies, logs
- [ ] Site-team in-app banners explain phase per project
- [ ] All cutover events logged to activity_events with cutover_ prefix
- [ ] At least one project end-to-end cut over from Phase A through Phase D in staging before production

#### Out of scope

- Two-way sync between Buildertrend and SY Hub during dual-run (out of scope — too risky; manual dual-entry by site teams is the deliberate choice)
- Buildertrend API direct integration (out of scope — Buildertrend's API is incomplete for SY Homes' needs and the cutover horizon is short)
- Historical project migration (>2 years old) — cutover scope is current + last-12-months projects only; older projects archived as flat document dumps
- Customer-facing Buildertrend account migration (out of scope — buyer portal is Phase 3)
- Buildertrend mobile app data extraction (no API for this — site team manually exports any pending mobile-only data)
- Re-engagement with Buildertrend post-cutover (out of scope — clean break)
- Cutover for entities other than current SY Homes operating entity (Phase 4 if SY Homes acquires another developer)

---

### 8.3 Go-Live + Post-Launch Monitoring

**Duration:** 10 hours
**Status:** NEW
**Dependencies:** 8.1 (polish pass complete), 8.2 (cutover executed for at least one pilot project)

#### Scope

Production go-live execution and the first 30 days of structured post-launch monitoring. This prompt builds the *monitoring infrastructure* and *operational runbooks* — the actual go-live event is governed by them rather than scripted in code.

#### Production environment readiness

**Environment provisioning checklist.**
- Production database with point-in-time recovery, daily snapshots, 35-day retention.
- Production application servers with documented capacity (target: 5x peak observed staging load).
- Redis cache provisioned and replicated.
- Object storage for documents with lifecycle policies (cold storage transition for documents > 2 years).
- Backup restoration tested at least once before go-live (full restore to staging, sanity check).
- DNS, SSL, CDN configured.
- Email delivery configured (transactional + notification).
- Sentry or equivalent error capture configured for production.
- Structured log aggregation configured (Datadog/equivalent).

**Secrets management.** All credentials in production secrets manager (no env files in code). Documented rotation schedule: Xero OAuth tokens auto-refresh, API keys rotated quarterly, database credentials rotated annually.

**Backup / restore runbook.** Documented procedure for:
- Hourly transaction-log backups, daily full snapshots, 35-day retention.
- Restore-to-point-in-time within 30 minutes (tested in staging).
- Document object storage snapshots daily.
- Full disaster recovery: restore database + restart application within 4 hours RTO, < 1 hour RPO.

#### Monitoring infrastructure

**Application metrics.**
- Request rate per endpoint (p50, p95, p99 latency).
- Error rate per endpoint (4xx, 5xx separately).
- Background job duration and failure rate per job type.
- Xero sync success/failure rate per entity.
- Public API rate limit hit counts.
- Cache hit ratio per cache key namespace.

**Business metrics.**
- Active users per day (login event count by role).
- Actuals created per day.
- Reservations created per day.
- Documents uploaded per day.
- Notifications sent / failed per day.

**Health-check endpoints.** Internal `/healthz` (basic up/down) and `/health` (deeper check: database reachable, Redis reachable, Xero last-sync recency, background job queue depth). External monitoring (UptimeRobot or equivalent) on `/healthz` every minute.

**Alert thresholds.**
- 5xx error rate > 1% over 5min → page on-call.
- p95 latency > 2s on any user-facing endpoint over 10min → notify.
- Background job failure rate > 5% over 1 hour → notify.
- Xero sync failure for any entity > 2 consecutive runs → notify and surface to user.
- Disk usage > 80% on any tier → notify.
- Backup job failure → page on-call (zero tolerance).

**On-call rotation (first 30 days).** Daily named on-call from the build team. Escalation path: on-call → tech lead → director. Documented runbook for the top 10 likely incident types (Xero outage, mass-email failure, slow query, full disk, deploy rollback, RBAC incident, bad data import, document storage outage, third-party API outage, full DB recovery).

#### Go-live procedure

**Pilot phase (Days 1–7).** One project moved fully to production from staging cutover. Site team trained. Director monitors daily.

**Expansion phase (Days 8–21).** Remaining active projects rolled in over two weeks. Daily director check-in, weekly retrospective with build team, issue triage queue.

**Steady-state phase (Days 22–30).** All projects live. Build team supports incidents only — no new feature work. Final 30-day retro at day 30 with structured findings document.

**Communication plan.** In-app banner during pilot phase: "Pilot — please report any issues via [feedback channel]". Removed at expansion phase. Email digest to all users on Day 1, Day 7, Day 21, Day 30.

#### Post-launch issue triage

**Issue triage workflow.**
- Critical (data loss risk, security incident, blocks all users): page on-call, target fix < 4h.
- High (blocks a workflow, affects multiple users): notify on-call, target fix < 24h.
- Medium (workaround exists, affects some users): notify, target fix < 1 week.
- Low (cosmetic, single user, edge case): backlog, target fix in next planned cycle.

**Issue dashboard.** Internal dashboard pulling from issue tracker showing open issues by severity, average resolution time, repeat-pattern detection (same root cause flagged > 3 times triggers a "deeper investigation" task).

#### 30-day retrospective deliverable

End of Day 30: structured retrospective document covering:
- Incident log: every incident, severity, resolution time, root cause.
- Performance against targets: p95 latency observed vs target, error rate observed vs target, uptime observed.
- User feedback summary: top complaints, top requests.
- Adoption metrics: active users, feature usage by track, cutover completion (Buildertrend usage drop-off).
- Findings: what worked, what didn't, what to change.
- Phase 3 inputs: feature backlog from user feedback.

#### UI

- **`/admin/monitoring`** — director-only operational dashboard with the application + business metrics described.
- **`/admin/incidents`** — issue triage dashboard.
- **`/admin/health`** — deep health-check display for internal use.
- **`/admin/backups`** — backup status display (last successful, retention compliance).

No user-facing UI in this prompt — all surfaces are admin/director.

#### Permissions

| Permission | Scope | Roles |
|---|---|---|
| `admin.monitoring.view` | tenant | director, super_admin |
| `admin.incidents.view` | tenant | director, super_admin |
| `admin.incidents.manage` | tenant | super_admin |
| `admin.health.view` | tenant | director, super_admin |
| `admin.backups.view` | tenant | director, super_admin |

#### Acceptance criteria

- [ ] Production environment provisioned per checklist with backup restoration tested
- [ ] Secrets in secrets manager; rotation schedule documented
- [ ] Application metrics captured: request rate, latency p50/p95/p99, error rate per endpoint, background job stats, Xero sync stats, public API rate limits, cache hit ratios
- [ ] Business metrics captured: active users, actuals/day, reservations/day, documents/day, notifications/day
- [ ] Health-check endpoints live; external uptime monitoring on `/healthz` every minute
- [ ] Alert thresholds configured per spec; tested via deliberate fault injection in staging
- [ ] On-call rotation documented for first 30 days with named individuals and escalation path
- [ ] Top-10 incident runbooks written and reviewed by build team
- [ ] Pilot → expansion → steady-state phases communicated via in-app banners and email digests
- [ ] Issue triage dashboard with severity, resolution time, repeat-pattern detection
- [ ] 30-day retrospective deliverable produced with all required sections
- [ ] Phase 3 backlog populated from retrospective findings

#### Out of scope

- Multi-region failover (Phase 6)
- Advanced APM (full OpenTelemetry distributed tracing) (Phase 6)
- Synthetic transaction monitoring beyond healthz (Phase 5)
- SLA contracts with users (no formal SLA at launch — best-effort with documented internal targets)
- Penetration testing (Phase 6 — separate workstream)
- ISO 27001 / SOC 2 readiness (Phase 6 — separate workstream)
- Customer-facing status page (Phase 4)
- Public incident communication policy (Phase 4)
- Long-term capacity planning beyond 5x peak (Phase 5)
- A/B testing infrastructure (Phase 5)
- Feature flag platform beyond simple boolean config (Phase 5)
- Continuous deployment pipeline maturity (basic CI/CD assumed; advanced gating Phase 5)

---

## Track 6 + 7 + 8 closing summary

This file completes the Phase 2 detail brief at the prompt level for Tracks 6, 7, and 8. Combined with the session 3 output (T2+T3) and session 4a output (T4+T5), the four detail files cover all 44 prompts of Phase 2.

**Final table count for Phase 2 (across all detail files):**
- T2: 16 tables
- T3: 11 tables
- T4: 14 tables
- T5: 9 tables
- T6: 17 tables (15 carry-forward from Phase 1 + 2 new for CSV framework)
- T7: 14 tables (house_types, plots, plot_status_history, buyers, buyer_viewings, solicitors, reservations, conveyancing_milestones, retentions, retention_releases, dlp_periods, final_accounts, report_definitions, report_runs, public_api_endpoints, public_api_request_log — counting 16 against the skeleton's ~12 estimate; resolved by absorbing dlp_defects as a snags flag rather than a separate table)
- T8: 0 new tables

**Final prompt count:** 44 across 8 tracks (no candidate splits landed in T7 detail review — 7.1/7.2 were already separate in skeleton; 7.4 stayed unified).

**Skeleton corrections to flag in chat-9 closing:**
1. T7 final table count is 16, not the skeleton's ~12 — the dashboard/reporting/public-API tables (4) and the snag-DLP flag resolution drove the final number.
2. T8 shape changed from skeleton (Portal Hardening / Mobile UX+Designer / Performance+Launch Readiness) to opener-defined (Performance+design polish / Buildertrend cutover / Go-live+monitoring). The "Portal Hardening" content absorbed into 8.1; "Mobile UX + Designer" collapsed because designer engagement runs as a parallel workstream feeding 8.1.
3. Buildertrend cutover plan (`SY_Homes_Buildertrend_Cutover_Plan.md`) is a new sibling deliverable required ahead of 8.2 — flag in closing.
4. Public asset proxy route (small additional infra in 7.4) — note in closing whether it warrants its own line in skeleton diagram.
5. Phase 1 5.4 + 5.5 merged to 6.5 with VAT-return reconciliation deferred to Phase 7 — already noted in §"Changes versus skeleton" item 3 but reiterate in closing for visibility.
6. Statutory payment-notice solicitor consult unchanged from session 4a — still scheduled, not blocked by 6.4 work.
7. New `design_manager` role flagged in 7.1 permissions — confirm role exists in 1.5 RBAC seed, otherwise add as schema delta.

---
