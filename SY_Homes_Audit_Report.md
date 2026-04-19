# SY Homes Platform — Phase 1 Specification Audit Report

**Audit date:** 19 April 2026  
**Deliverables audited:**
- `SY_Homes_Data_Model.xlsx`
- `SY_Homes_Platform_Spec_v2.docx`
- `SY_Homes_Emergent_Brief_Phase1.md`
- `SY_Homes_Future_Tasks.md`

**Auditor:** Automated cross-document consistency check + targeted manual review

---

## Audit scope

This audit was carried out after the full Phase 1 specification pack was assembled, to verify that the four documents are internally consistent, that they agree with each other where they overlap, that naming and typing conventions are applied uniformly, and that critical calculations produce correct results.

The audit was **not** a replacement for developer review during build. It catches structural issues, not business-logic errors that only emerge when code meets real data.

---

## Summary

| Check | Result |
|---|---|
| File existence and size | ✓ All 4 files present, sizes as expected |
| Structural integrity of data model | ✓ 77 tables, 10 modules, 1,288 fields, 16 workbook tabs, 2,907 rows |
| Naming conventions (tables, fields) | ✓ All snake_case, all conventions respected |
| Timestamp handling | ✓ All 211 `_at` fields stored UTC; 46 `_date` fields stored as plain dates; UI in Europe/London |
| Money fields | ✓ All 97 money fields use DECIMAL; no FLOAT usage |
| Percentage fields | ✓ All 24 `_pct` fields use consistent suffix |
| Boolean naming | ✓ Conventions respected with reasoned exceptions for domain terms |
| All 77 tables referenced in Emergent brief | ✓ Confirmed |
| All 25 brief prompts have required sections | ✓ Dependencies + Acceptance Criteria + Out of Scope on every prompt |
| Critical SDLT calculations | ✓ Three test cases all correct |
| Cross-document schema consistency | ⚠ One substantive inconsistency found and fixed |

**Verdict: fit for purpose as a Phase 1 specification and build brief.** One schema inconsistency was identified and corrected; all other findings were either intentional design choices or cosmetic drift that doesn't affect a developer's ability to build from the spec.

---

## Detailed findings

### 1. File completeness ✓

All four documents present in `/mnt/user-data/outputs/`:

| File | Size | Content |
|---|---|---|
| `SY_Homes_Data_Model.xlsx` | 128 KB | 16 tabs, 2,907 rows |
| `SY_Homes_Platform_Spec_v2.docx` | 38 KB | 515 paragraphs, validated clean |
| `SY_Homes_Emergent_Brief_Phase1.md` | 285 KB | 6,964 lines, 31,000 words, 25 prompts |
| `SY_Homes_Future_Tasks.md` | 12 KB | 182 lines, 7 phases |

### 2. Data model structure ✓

Module breakdown:

| Module | Tables | Fields |
|---|---:|---:|
| Foundation | 2 | 76 |
| Users, Permissions & Audit | 14 | 168 |
| Cost Codes | 5 | 62 |
| Appraisal Module | 9 | 150 |
| Budget Module | 8 | 167 |
| Cash Flow Module | 5 | 65 |
| Programme Module | 10 | 160 |
| QA & Documents | 7 | 117 |
| Xero Integration | 15 | 291 |
| Cross-cutting | 2 | 32 |
| **Total** | **77** | **1,288** |

### 3. Naming conventions ✓

All 77 table names are lowercase snake_case plural. All field names are lowercase snake_case. Suffix conventions:
- `_id` on foreign keys (consistent)
- `_at` on timestamps (consistent)
- `_date` on plain date fields (consistent)
- `_pct` on percentages (consistent)
- `is_` / `has_` / `can_` / `show_` / `requires_` / `applies_to_` on booleans (with domain-standard exceptions)

### 4. Timestamp & date handling ✓

**Timestamps (211 fields with `_at` suffix):** All stored UTC per global conventions section. This is correct UK practice — UK clocks change twice a year, BST is UTC+1 in summer and UTC in winter, so storing UTC eliminates the ambiguous hour at clock-change and makes audit trails unambiguous.

**Dates (46 fields with `_date` suffix):** Stored as plain dates without timezone. Correct for dates that are civil concepts (planning_expiry_date, invoice_date, due_date, baseline snapshot dates).

**UI display:** `users.timezone` defaults to `Europe/London`. Frontend converts UTC to local for display. Industry-standard pattern.

### 5. Money fields ✓

97 genuine money fields identified across the data model. All use DECIMAL type (mostly `DECIMAL(14,2)` for amounts, `DECIMAL(14,4)` for rates/quantities). No FLOAT usage — correct practice for money to avoid rounding errors.

Samples verified:
- `projects.gdv_actual` = decimal(14,2)
- `appraisals.residual_land_value` = decimal(14,2)
- `budget_lines.forecast_final_cost` = decimal(14,2)
- `actuals.net_amount`, `vat_amount`, `gross_amount` = decimal(14,2)
- `xero_bills.total`, `amount_due`, `amount_paid` = decimal(14,2)

### 6. Percentage fields ✓

All 24 percentage fields use `_pct` suffix and are stored as `DECIMAL(5,2)` or `DECIMAL(6,3)`. Values stored as 0–100 (not 0–1) per convention. Notable examples:
- `appraisals.margin_on_cost_pct`
- `budget_lines.variance_pct`
- `cost_codes.vat_rate_pct`
- `appraisal_finance_model.interest_rate_pct`

### 7. Boolean naming ✓ (with noted exceptions)

92 boolean fields across the schema. Most use the `is_` / `has_` prefix convention. The following intentional exceptions use domain-standard UK construction/planning/tax terminology:

| Field | Rationale |
|---|---|
| `projects.implementation_required` | UK planning term — permissions must be "implemented" within N years |
| `projects.s106_required` | UK planning term — Section 106 agreement |
| `projects.cil_required` | UK planning term — Community Infrastructure Levy |
| `projects.vat_opt_to_tax` | UK tax term — option to tax |
| `appraisals.passes_hurdle` | Finance term — hurdle rate check |
| `appraisals.sdlt_developer_relief_claimed` | Tax term |

These are accepted because the domain language is more meaningful than forcing a generic prefix.

### 8. Cross-document consistency

A cross-document schema comparison was run between the XLSX data model and the Emergent brief prompts. Ten tables showed partial field-name divergence:

- `programme_task_updates` (naming drift only — e.g. `taken_at` vs `submitted_at`)
- `programme_baselines` (naming drift)
- `programme_calendars` ⚠ **substantive inconsistency** — see below
- `programme_weekly_reports` (brief has more detail than XLSX summary)
- `document_approvals` (brief has more detail)
- `xero_connections` (different modelling — both workable)
- `xero_contacts` (brief adds some fields)
- `xero_bills` (brief delegates some sync state to `xero_sync_queue`)
- `xero_invoices` (similar)
- `xero_sync_queue` (brief is more detailed)

Most of these are cases where the Emergent brief, written after the XLSX, refined or added detail. The brief is the more recent and detailed specification and should be treated as authoritative for field-level details during build.

#### 8a. Substantive inconsistency identified and fixed

**`programme_calendars` schema:**

The XLSX originally had 7 per-weekday boolean columns (`working_monday` through `working_sunday`) and two text fields for Christmas shutdown dates. The Emergent brief had a better modern schema using JSONB arrays. These are substantively different designs, not just naming differences.

**Resolution:** The XLSX was updated to align with the brief's schema:
- Removed: `working_monday`, `working_tuesday`, `working_wednesday`, `working_thursday`, `working_friday`, `working_saturday`, `working_sunday`, `includes_bank_holidays`, `christmas_shutdown_start`, `christmas_shutdown_end` (10 fields)
- Added: `working_days` (JSONB), `working_hours_per_day` (decimal), `bank_holidays` (JSONB), `standard_shutdowns` (JSONB), `timezone` (varchar) (5 fields)

Net effect: –5 fields (1,293 → 1,288 total). The JSONB-based approach supports multiple annual shutdowns, is forward-compatible with additional calendar features, and aligns with the build-ready prompt in the brief.

### 9. Seed data ✓

All major seed data verified present in the Emergent brief:

- SDLT rate bands effective April 2025 (Residential Standard, Residential Surcharge, Non-Residential, Corporate Flat Rate) — present
- 10 seeded roles (super_admin, director, project_manager, finance, site_manager, sales, read_only, investor_read_only, subcontractor_portal, consultant_portal) — present
- 19 cost code prefixes (ACQ, PLN, DES, FAC, SUB, SUP, INT, FIT, SER, PRE, EXB, EXT, PRL, MCP, SAL, FIN, OHD, ACC, CTG) — present
- 3 group entities (SY Homes Ltd, SY Homes Shrewsbury Ltd, SY Homes Construction Ltd) — present
- 6 programme templates (Pure Dev, D&B Small/Medium/Large, D&B Contract, Main Contract) — present
- Bank holidays seeded through 2028 — present
- 13 compliance register types (CDM, BSA, Part L/O/Q, Fire Safety, Warranty, GDPR, Planning Discharge, Building Control, Insurance, Certificates, Contract) — present
- ~40 system_config keys — present
- 15 notification types — present

### 10. Critical calculations verified ✓

**SDLT engine** — three test cases computed manually and verified against spec:

| Price | Category | Expected SDLT | Computed | Match |
|---|---|---:|---:|:-:|
| £500,000 | Residential Standard | £15,000 | £15,000 | ✓ |
| £2,000,000 | Residential Standard | £153,750 | £153,750 | ✓ |
| £250,000 | Non-Residential | £2,000 | £2,000 | ✓ |

### 11. Emergent brief structural consistency ✓

- 5 build tracks (Foundation, Commercial Engine, Programme, QA & Documents, Xero Integration)
- 25 prompts with consistent structure
- Every prompt has: Dependencies declared, Acceptance criteria block, Out of scope block
- 64 schema build sections across the 25 prompts
- 140 foreign key relationships documented in the Relationships tab
- All 77 tables covered by the 25 prompts (no orphan tables)

---

## What was updated after audit

| File | Update |
|---|---|
| `SY_Homes_Data_Model.xlsx` | `programme_calendars` schema modernised to JSONB-based design (aligned with Emergent brief). Field count 1,293 → 1,288. |
| `SY_Homes_Emergent_Brief_Phase1.md` | Footer count updated from 1,293 to 1,288 for consistency. |
| `SY_Homes_Platform_Spec_v2.docx` | Executive Summary count updated from 1,293 to 1,288. |
| `SY_Homes_Future_Tasks.md` | No changes needed. |

---

## Non-issues noted during audit

These were flagged by automated checks but examined and confirmed as **correct** design decisions, not errors:

1. **`xero_connections` has granular sync-enabled booleans** rather than the brief's simpler `webhook_enabled` flag. Both approaches are valid; the granular version gives admin finer control, the simpler version is easier to maintain. For build, follow the brief; if finer-grained control is wanted later, the XLSX pattern is documented.

2. **Some field names differ cosmetically** between XLSX and brief (e.g. `baseline_taken_at` vs `taken_at`). Not worth rebuilding the XLSX for — the brief's field names should be used during build.

3. **Booleans for UK planning/tax terms** (`implementation_required`, `s106_required`, `cil_required`, `vat_opt_to_tax`) don't use `is_` prefix. This is intentional — domain-standard naming is clearer than forced convention.

---

## Recommendations for build

1. **Treat the Emergent brief as the authoritative build reference** for field-level details. The XLSX is the overview; the brief is the detail.

2. **Log any deviations** encountered during actual building in a running change log so that the spec can be kept in sync with what's built.

3. **Re-run this audit at the end of Phase 1** before committing to Phase 2 planning, to verify drift is minimal and the built system still matches the specification.

4. **Test SDLT, RLV solver, and CPM algorithms extensively** — these are the three most complex pieces of business logic. Unit tests covering the SDLT test cases in this audit are a good starting point.

5. **Pay particular attention to the Xero Integration track** — it has the most moving parts (OAuth, webhooks, sync queue, reconciler) and the most opportunity for subtle bugs. Consider building it as a dedicated service rather than entirely within Emergent.

---

## Closing

The Phase 1 specification is structurally sound, internally consistent (after this audit's one fix), and comprehensive enough to build from. It represents ~40,000 words of combined specification across four formats (tabular, narrative, prompt-based, deferred items), describing a system of 77 tables, 1,288 fields, 140 foreign key relationships, 25 build prompts, and all the calculations, workflows, permissions, and seed data necessary to deliver it.

Nothing flagged in this audit is a blocker for starting Phase 1 build. Prompt 1.1 (Entities) can be worked on immediately.

---

_Audit report version 1.0 — April 2026_
