<!-- ================================================================
     SY HOMES PLATFORM — PHASE 2 EMERGENT BRIEF
     SESSION 3 OUTPUT: TRACKS 2 + 3 — PROMPT-LEVEL DETAIL
     ================================================================
     Version: 2.0-detail (T2 + T3 only)
     Date: April 2026
     Status: Replaces one-paragraph descriptions in skeleton lines
             ~173-251 (Track 2 prompts 2.1-2.9, Track 3 prompts 3.1-3.5).
             Track 4-8 detail follows in session 4.
     Companion: SY_Homes_Emergent_Brief_Phase1.md (Phase 1 brief —
                referenced extensively for "carried forward" prompts)
     ================================================================ -->

# Session 3 — Tracks 2 and 3 prompt-level detail

This document supplies the full prompt detail for Tracks 2 and 3, intended to replace the one-paragraph descriptions in `SY_Homes_Emergent_Brief_Phase2.md` skeleton sections "Track 2 — Commercial Engine + Subcontractors" and "Track 3 — Real-time + Offline + Programme".

## Changes versus skeleton

1. **Prompt 2.8 split into 2.8a and 2.8b.** Subcontracts + variations (2.8a) is a setup module — formal contract record, variation instruction workflow, BCR generation. Valuations + payment notices (2.8b) is the monthly operating cycle on top, with statutory payment-notice wording requirements that warrant their own focus and test cycle. Track 2 is therefore 10 prompts, not 9. Total brief moves from 43 to 44 — within the "honest reading 43-46" range flagged in the skeleton.
2. **Real-time choice locked: WebSockets.** Open question 1 from the skeleton. Reasoning in 3.1 below.
3. **Offline conflict policy locked: last-write-wins with overwrite toast for the loser.** Open question 2 from the skeleton. Reasoning in 3.2 below.
4. **Prompt 3.1 not split.** Skeleton flagged as candidate; on detail review, 14h is tight but coherent. Build and test are per-prompt anyway.

## Carried-forward prompts — note on depth

Prompts 2.1, 2.2, 2.3, 2.4, 2.6, 3.3, 3.4, 3.5 are carried forward from Phase 1 brief unchanged or with minor deltas only. Their full schemas, business logic, and acceptance criteria already exist in `SY_Homes_Emergent_Brief_Phase1.md`. Sections below state only the deltas (where any), the Phase 1 brief reference, and any cross-track wiring needed for Phase 2. Reproducing the full Phase 1 detail in this document would duplicate ~6,000 words verbatim with no value.

Prompts 2.5, 2.7, 2.8a, 2.8b, 2.9, 3.1, 3.2 are new or substantially modified, and are written here at full Phase 1 depth.

---

# Track 2 — Commercial Engine + Subcontractors

**Goal:** Build the appraisal-to-budget-to-actuals-to-payment-notice pipeline, fully Xero-independent (Xero connector layered on later in Track 6). Add native subcontractor records, formal subcontracts, variations, monthly valuations and statutory payment notices, plus an embedded supplier/subcontractor portal so external commercial parties can confirm POs, submit valuations, and raise variations.

**Duration:** ~13 weeks at 25 hrs/week (was 12 weeks at 9 prompts; +1 prompt from 2.8 split adds ~1 week)
**Prompts:** 10 (was 9 in skeleton — see "Changes versus skeleton" above)
**Tables added:** ~30
**Audit checkpoint:** End of Track 2 — self-audit + Rhys review, deviations logged in CHANGELOG.

---

## Prompt 2.1 — Reference Data: SDLT Bands, Appraisal Defaults

**Dependencies:** 1.1, 1.2, 1.4
**Tables in this prompt:** `sdlt_rate_bands`, `appraisal_default_settings`
**Estimated hours:** 6h
**Status:** Carried forward from Phase 1 unchanged.

Reference Phase 1 brief Prompt 2.1 in full. Two reference tables, read-only seed data with admin-only edit. SDLT bands seeded with England rates effective April 2025; Scotland LBTT and Wales LTT remain Future Tasks (Phase 5). `appraisal_default_settings` seeds build-cost-per-sq-ft defaults, finance assumptions, hurdle rate. Used as inputs by Prompt 2.2.

### Phase 2 deltas
- None.

### Out of scope (unchanged from Phase 1)
- LBTT (Scotland), LTT (Wales) — Future Tasks Phase 5.
- Stamp duty for commercial / mixed-use schemes — Future Tasks if SY Homes pivots.

---

## Prompt 2.2 — Appraisals Core: Header, Units, Cost Lines, Finance Model

**Dependencies:** 1.1, 1.2, 1.4, 1.5, 1.6, 2.1
**Tables in this prompt:** `appraisals`, `appraisal_units`, `appraisal_cost_lines`, `appraisal_finance_model`
**Estimated hours:** 16h
**Status:** Carried forward from Phase 1 unchanged.

Reference Phase 1 brief Prompt 2.2 in full. Heaviest single prompt in Track 2 because of three calculation engines:
- **SDLT calculator** — uses 2.1 bands; consumes purchase price, returns SDLT due.
- **RLV solver** — iterative search for residual land value given target profit margin and inputs.
- **Finance model** — interest cost over construction period, peak debt, profit on cost / on GDV.

UI: appraisal builder with three views (units, costs, finance), summary tile (GDV, total cost, profit, margin %, RLV), revision-aware (revisions live in 2.3).

### Phase 2 deltas
- None to schemas or engines.
- Add `is_public_visible` field on appraisal — **deferred** to Prompt 7.1 (plot management) where public-data API readiness lives. Not appraisal-level.

### Out of scope (unchanged from Phase 1)
- Sensitivity analysis dashboard — Phase 5 enhancement.
- Multi-currency appraisals — UK only, GBP only.
- Per-unit profit attribution — single appraisal-level profit only.

---

## Prompt 2.3 — Appraisal Governance: Revisions, Scenarios, Decision Log

**Dependencies:** 2.2
**Tables in this prompt:** `appraisal_revisions`, `appraisal_scenarios`, `appraisal_decision_log`
**Estimated hours:** 10h
**Status:** Carried forward from Phase 1 unchanged.

Reference Phase 1 brief Prompt 2.3 in full. Revision history (immutable snapshots), scenario branching (e.g. "what if build cost +10%"), decision log capturing director-level approvals/rejections, locked vs draft states. Underpins audit story for any appraisal that becomes a budget.

### Phase 2 deltas
- None.

---

## Prompt 2.4 — Budgets Core

**Dependencies:** 1.6, 2.3
**Tables in this prompt:** `budgets`, `budget_lines`, `budget_line_periods` (monthly profile)
**Estimated hours:** 12h
**Status:** Carried forward from Phase 1 unchanged.

Reference Phase 1 brief Prompt 2.4 in full. Budget header per project + entity, budget lines keyed to cost codes, opening budget locked from approved appraisal, separate "live budget" with change control wired in 2.6. FFC (Forecast Final Cost) derived from budget + actuals + commitments + change orders.

### Phase 2 deltas
- None.

---

## Prompt 2.5 — Actuals and Commitments (Xero-independent)

**Dependencies:** 2.4
**Tables in this prompt:** `actuals`, `commitments`, `commitment_lines`
**Estimated hours:** 14h
**Status:** Modified from Phase 1. Native creation flows added; Xero is not a prerequisite.

The Phase 1 prompt assumed actuals and commitments would primarily come from Xero sync (Track 5.3). The Phase 2 reframe makes the platform fully self-sufficient: actuals and commitments are first-class platform records that may *optionally* sync to Xero via Track 6.4. Schema is largely the Phase 1 schema with one source-enum extension and a small set of UI / business-logic additions for native creation.

### Build `actuals`

Carried forward from Phase 1 brief Prompt 2.5 with one schema delta:

```
actuals (delta only — full schema in Phase 1 brief)
─────────────────────────────────────────────
source_type           enum NOT NULL
                      ('Manual','Xero','CSV_Import')   -- was ('Manual','Xero')
                      -- 'CSV_Import' added for Track 6.1 framework
```

All other fields unchanged from Phase 1:
- Identity: `id`, `tenant_id`, `entity_id`, `project_id`, `budget_line_id`, `external_id`
- Financial: `transaction_date`, `posting_date`, `description`, `net_amount`, `vat_amount`, `gross_amount`, `vat_rate_pct`, `is_vat_recoverable`, `currency`, `exchange_rate`
- Supplier: `supplier_id` (FK to `suppliers` from 2.7 — was Phase 4 in original brief; now active in 2.7), `supplier_name_snapshot`, `supplier_invoice_ref`
- CIS: `is_cis_applicable`, `cis_deduction_rate_pct`, `cis_labour_amount`, `cis_materials_amount`, `cis_deduction_amount`, `cis_reported_to_hmrc`
- Retention: `retention_rate_pct`, `retention_amount`, `retention_released`, `retention_release_date`
- Subcontract link: `related_subcontract_id` (FK to `subcontracts` from 2.8a — was Phase 4 in original brief; now active in 2.8a)
- Reconciliation: `is_reconciled_to_xero`, `reconciled_at`, `reconciliation_variance`
- State: `status` enum (`Draft`, `Posted`, `Paid`, `Void`, `Disputed`), `paid_date`, `payment_reference`, `document_ids`
- Audit: `created_by_user_id`, `created_at`, `updated_at`, `voided_at`, `voided_by_user_id`, `void_reason`

### Build `commitments` and `commitment_lines`

Carried forward from Phase 1 brief Prompt 2.5 unchanged.

`commitments` covers Subcontract / PurchaseOrder / Engagement (consultant) / Other types, with a status machine `Draft` → `Issued` → `Confirmed` → `Goods_Received` (POs) or `Fully_Invoiced` → `Closed`.

`commitment_lines` carries individual line items keyed to cost codes for granular budget consumption.

### Business logic — Phase 2 additions

**Native actual entry (UI-driven, no Xero dependency):**

```
User: finance / contracts manager / director
Form fields:
  Required: project, entity, budget_line, transaction_date, description, net_amount, vat_rate, supplier (free text or select from 2.7)
  Optional: supplier_invoice_ref, document upload, CIS flags, retention flags
  
Validation:
  - gross = net + vat (must match within £0.01 tolerance)
  - cost code must be enabled for (project, entity) combo
  - transaction date cannot be future-dated more than 7 days
  - if supplier selected from 2.7 with is_cis_subcontractor=true, CIS flags pre-populated
  - if supplier has retention_rate_default > 0 on linked subcontract, retention pre-populated
  
Submit creates Draft actual.
Approval: Director or Finance must approve to move Draft → Posted.
Posted is immutable except via Void + new correction.
```

**Native commitment entry (PO creation, no Xero dependency):**

```
User: contracts manager / director
Form fields:
  Required: project, entity, supplier (from 2.7), commitment_type, expected_total_value, expected_start, expected_end
  Lines: cost_code, description, quantity, unit_price, line_total
  
Submit creates Draft commitment.
Issue action: sets status=Issued, generates PO PDF (template per entity), emails supplier (if 2.9 portal not yet active) or notifies via portal (if 2.9 active).
Confirmation flow:
  - Pre-2.9: supplier emails confirmation; user marks as Confirmed manually.
  - Post-2.9: supplier confirms via portal; status auto-updates to Confirmed and notifies CM.
```

**Cache refresh on actual Post or Void** — unchanged from Phase 1:

```
For affected budget_line:
  actuals_to_date_sum = sum(CASE WHEN is_vat_recoverable THEN net_amount ELSE gross_amount END)
                       FILTERED status IN ('Posted','Paid')
  actuals_this_period = same sum filtered by transaction_date in current month
  last_actual_posted_at = max(posting_date)
  FFC and variance recalculated.
  Async job recalculates project.gdv_actual / .build_cost_actual etc.
```

**Cache refresh on commitment status change:**

```
On commitment.status → Issued or Confirmed:
  budget_line.committed_to_date += commitment.remaining_commitment

On actual posted with related_commitment_id set:
  commitment.invoiced_to_date += actual.net_amount
  commitment.remaining_commitment = current - invoiced
  if invoiced >= current: status = Fully_Invoiced
  else if invoiced > 0:   status = Partially_Invoiced
```

**CIS auto-calc** — unchanged from Phase 1.

**Retention auto-calc** — unchanged from Phase 1, with one extension: if the actual is linked to a subcontract (`related_subcontract_id` set), retention rate comes from `subcontracts.retention_rate_pct` (2.8a) and overrides any manual entry. Retentions held flow into 7.3 retention release schedule.

**Posted immutability** — unchanged from Phase 1: void requires reason, audit-logged, never deletes the row.

**Append-only enforcement (hard constraint 5):**
- Database-level: actuals and commitments tables have `created_at` immutable trigger after first insert.
- Application-level: any update to `Posted` actual rejected by API with 409 Conflict.
- Audit log records all state transitions including void.

### UI — additions over Phase 1

**Native bill entry page** (`/projects/:id/financials/actuals/new`):
- Mobile-friendly (finance director may need to review on the go).
- Document upload first, OCR-light extraction (filename, total) suggested as defaults — no real OCR engine, just heuristics. Future Tasks Phase 5 for proper AI document ingestion.
- "Save as draft" prominent — bills land in queue; approver sees a list of drafts pending posting.

**PO creation page** (`/projects/:id/financials/commitments/new`):
- Multi-line entry like an estimate: cost code, description, qty, unit price, line total.
- Supplier picker pulls from 2.7 with recently-used supplier list.
- "Issue PO" generates PDF via templating (entity letterhead, PO terms standard text).
- Internal preview of PDF before send.

**Posted actuals immutability surfaced clearly:**
- Posted actuals show a locked icon with "Posted — void to correct" hint.
- Void modal requires reason ≥ 10 chars, audit-logged.

### Permissions

- `actuals.view` — finance, director, project lead, contracts manager
- `actuals.create_draft` — finance, director, contracts manager
- `actuals.post` — finance, director (approval gate)
- `actuals.void` — finance, director with reason
- `commitments.view` — finance, director, project lead, contracts manager
- `commitments.create` — contracts manager, director
- `commitments.issue` — contracts manager, director
- `commitments.approve_change` — director (size-threshold; configurable in 1.7)

### Acceptance criteria

- [ ] Actuals can be created entirely via UI without any Xero connection
- [ ] Commitments (POs and subcontract orders) can be created entirely via UI
- [ ] PO PDF generated on Issue with correct entity letterhead
- [ ] Draft → Posted requires director or finance approval
- [ ] Posted actuals cannot be edited (only voided)
- [ ] Void requires reason and is audit-logged
- [ ] Cache refresh on Post / Void updates budget_line.actuals_to_date correctly
- [ ] Commitment cache refresh on status change updates budget_line.committed_to_date
- [ ] CIS auto-calc unchanged from Phase 1 spec
- [ ] Retention auto-calc unchanged, with subcontract override applied when linked
- [ ] `source_type` enum includes `CSV_Import` for Track 6.1
- [ ] Append-only at DB and API level — Posted record cannot be UPDATEd
- [ ] All actions appear in audit_log with old / new state
- [ ] FK to `suppliers` (2.7) and `subcontracts` (2.8a) populated when applicable

### Out of scope

- Xero sync of actuals / commitments — Track 6.4.
- OCR / AI document ingestion of bills — Future Tasks Phase 5.
- Bank feed integration to auto-mark Paid — Future Tasks Phase 4.
- Multi-currency — single currency (GBP) only.
- Intercompany billing automation — Future Tasks Phase 4.

---

## Prompt 2.6 — Budget Change Control and Forecasts

**Dependencies:** 2.4, 2.5
**Tables in this prompt:** `budget_change_requests`, `budget_change_request_lines`, `budget_forecasts`
**Estimated hours:** 10h
**Status:** Carried forward from Phase 1 unchanged.

Reference Phase 1 brief Prompt 2.6 in full. BCR workflow with approval gates, transfer between cost lines, contingency drawdown, automatic FFC recalc, change log per budget.

### Phase 2 deltas
- **Variation BCR generation hook added.** Approved subcontract variations (2.8a) automatically generate a BCR of type `Variation` with line items mirroring the variation cost. The BCR follows normal approval workflow.
- BCR `source_type` enum extends from Phase 1 (`Manual`, `Contingency`, `Scope_Change`) to add `Variation` → links via `source_subcontract_variation_id` FK to 2.8a.
- BCR auto-approval rule available in 1.7 config: variations under £1,000 may be auto-approved if `config.budget.auto_approve_variation_threshold_gbp` is set; otherwise standard approval applies.

### Out of scope (unchanged from Phase 1)
- AI-suggested cost-impact analysis on BCRs — Future Tasks Phase 5.

---

## Prompt 2.7 — Suppliers and Subcontractors

**Dependencies:** 1.1, 1.2, 1.4, 1.5
**Tables in this prompt:** `suppliers`, `subcontractors`, `subcontractor_cis_verifications`, `supplier_documents`, `supplier_project_assignments`
**Estimated hours:** 12h
**Status:** NEW — absorbed from Future Tasks v1 "Subcontractor Database and CIS".

Replaces supplier records that have lived across spreadsheets and Buildertrend's Subs/Vendors module. Provides the master record for everything commercial-facing in Tracks 2.5, 2.8, 2.9, 6.4.

### Multi-entity scoping decision

Suppliers and subcontractors are **tenant-scoped, not entity-scoped**. A subcontractor engaged on multiple SY Homes projects across SPV and ConstructionCo is one record. Per-project / per-entity engagement data lives in `supplier_project_assignments`. This avoids duplicate records and supports the planned subcontractor portal in 2.9 cleanly. Hard-constraint check: multi-entity (#6) preserved because financial postings (actuals, commitments, valuations) carry their own `entity_id` — supplier identity is shared, financial flow is per-entity.

### Build `suppliers`

```
suppliers
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
supplier_code                   varchar(20) NOT NULL    -- short code, e.g. "JEW001"
display_name                    varchar(255) NOT NULL
legal_name                      varchar(255)
trading_name                    varchar(255)
supplier_type                   enum NOT NULL
                                  ('Materials','Plant_Hire','Services','Consultant','Mixed')
is_subcontractor                boolean NOT NULL DEFAULT false  -- if true, subcontractor row also exists
companies_house_number          varchar(20)
vat_number                      varchar(20)
vat_status                      enum DEFAULT 'Standard'
                                  ('Standard','Flat_Rate','Not_Registered','Outside_Scope')
primary_contact_name            varchar(255)
primary_contact_email           varchar(255)
primary_contact_phone           varchar(50)
billing_address_line_1          varchar(255)
billing_address_line_2          varchar(255)
billing_city                    varchar(100)
billing_postcode                varchar(20)
billing_country                 varchar(100) DEFAULT 'United Kingdom'
delivery_address_line_1         varchar(255)
delivery_address_line_2         varchar(255)
delivery_city                   varchar(100)
delivery_postcode               varchar(20)
default_payment_terms_days      int NOT NULL DEFAULT 30
default_currency                varchar(3) NOT NULL DEFAULT 'GBP'
default_account_id              uuid    -- mapping to chart of accounts; populated by 6.3 after Xero sync
preferred_status                enum NOT NULL DEFAULT 'Active'
                                  ('Preferred','Active','On_Hold','Blocked','Archived')
on_hold_reason                  text
risk_rating                     enum DEFAULT 'Unrated'
                                  ('Unrated','Low','Medium','High')
notes                           text
xero_contact_id                 varchar(100)    -- populated by 6.3
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
archived_at                     timestamp
archived_by_user_id             uuid FK→users.id

Indexes:
- UNIQUE (tenant_id, supplier_code)
- INDEX (display_name)
- INDEX (preferred_status) WHERE archived_at IS NULL
- INDEX (xero_contact_id) WHERE xero_contact_id IS NOT NULL
```

### Build `subcontractors`

A subcontractor is a supplier with CIS / labour-and-plant characteristics. One supplier *may* have a one-to-one subcontractor row when `suppliers.is_subcontractor = true`. The subcontractors table holds CIS-specific data so the suppliers table doesn't get polluted with nullable CIS fields for materials-only vendors.

```
subcontractors
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
supplier_id                     uuid NOT NULL UNIQUE FK→suppliers.id ON DELETE CASCADE
trades                          jsonb NOT NULL DEFAULT '[]'
                                  -- e.g. ["groundworks", "drainage"] — controlled vocabulary in 1.7
hmrc_utr                        varchar(20)             -- Unique Taxpayer Reference, 10 digits
hmrc_company_utr                varchar(20)             -- corporate UTR if Ltd
ni_number                       varchar(20)             -- if sole trader
cis_status                      enum NOT NULL DEFAULT 'Pending_Verification'
                                  ('Gross','Net_20','Net_30','Pending_Verification','Not_Applicable')
                                  -- Gross = 0% deduction
                                  -- Net_20 = 20% deduction (verified registered)
                                  -- Net_30 = 30% deduction (unverified or unregistered)
last_verified_at                date
next_verification_due_at        date    -- HMRC requires re-verification if no payment in 2 tax years
default_labour_ratio_pct        decimal(5,2)    -- e.g. 80 for carpentry, 60 for groundworks
                                                 -- used in CIS auto-calc on actuals
default_retention_rate_pct      decimal(5,2) DEFAULT 5
default_payment_terms_days      int             -- can override supplier-level
public_liability_insurance_amount   decimal(14,2)
public_liability_expires_at         date
employers_liability_insurance_amount    decimal(14,2)
employers_liability_expires_at          date
professional_indemnity_amount       decimal(14,2)
professional_indemnity_expires_at   date
health_and_safety_competent     boolean NOT NULL DEFAULT false  -- evidence in supplier_documents
cscs_card_required              boolean NOT NULL DEFAULT true
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (supplier_id)
- INDEX (cis_status)
- INDEX (next_verification_due_at) WHERE next_verification_due_at IS NOT NULL
```

### Build `subcontractor_cis_verifications`

Audit history of CIS verifications. Required because HMRC verification is point-in-time and rules apply at payment date — needs to be replayable.

```
subcontractor_cis_verifications
─────────────────────────────────────────────
id                              uuid PK
subcontractor_id                uuid NOT NULL FK→subcontractors.id ON DELETE CASCADE
verified_at                     date NOT NULL
verified_by_user_id             uuid NOT NULL FK→users.id
hmrc_verification_number        varchar(20)     -- 14-char ref from HMRC online verification
result                          enum NOT NULL
                                  ('Gross','Net_20','Net_30','Failed_Verification')
hmrc_response_screenshot_id     uuid    -- FK to documents (5.2) once available
notes                           text
expires_at                      date            -- 2 years from verified_at, per HMRC rules
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (subcontractor_id, verified_at DESC)
- INDEX (expires_at)
```

### Build `supplier_documents`

Insurance certificates, accreditations, training records. Linked to documents (5.2) once Track 5 is built; in the interim, documents store as direct file uploads.

```
supplier_documents
─────────────────────────────────────────────
id                              uuid PK
supplier_id                     uuid NOT NULL FK→suppliers.id ON DELETE CASCADE
document_type                   enum NOT NULL
                                  ('Public_Liability_Insurance','Employers_Liability_Insurance',
                                   'Professional_Indemnity','Method_Statement','Risk_Assessment',
                                   'CSCS_Card','Training_Record','Accreditation','Other')
document_id                     uuid    -- FK to documents (5.2) — null until 5.2 built
file_path                       varchar(500)    -- direct file path in interim
display_name                    varchar(255) NOT NULL
expires_at                      date
notification_sent_30_days       boolean NOT NULL DEFAULT false
notification_sent_7_days        boolean NOT NULL DEFAULT false
notification_sent_expired       boolean NOT NULL DEFAULT false
uploaded_by_user_id             uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
archived_at                     timestamp

Indexes:
- INDEX (supplier_id, document_type)
- INDEX (expires_at) WHERE archived_at IS NULL AND expires_at IS NOT NULL
```

### Build `supplier_project_assignments`

Per-project supplier engagement, including project-specific ratings. Supports "this groundworker was good on Site A but slow on Site B" without polluting the master record.

```
supplier_project_assignments
─────────────────────────────────────────────
id                              uuid PK
supplier_id                     uuid NOT NULL FK→suppliers.id ON DELETE CASCADE
project_id                      uuid NOT NULL FK→projects.id ON DELETE CASCADE
entity_id                       uuid NOT NULL FK→entities.id     -- which SY Homes entity engaged them
first_engaged_at                date
last_engaged_at                 date
total_committed_value           decimal(14,2) DEFAULT 0    -- cached from commitments
total_invoiced_value            decimal(14,2) DEFAULT 0    -- cached from actuals
quality_rating                  int             -- 1-5
reliability_rating              int             -- 1-5
commercial_rating               int             -- 1-5
overall_rating                  decimal(3,2)    -- computed avg
rating_notes                    text
last_rated_at                   timestamp
last_rated_by_user_id           uuid FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (supplier_id, project_id, entity_id)
- INDEX (project_id)
```

### Business logic

**CIS verification expiry job (daily, runs 06:00):**

```
For each subcontractor with cis_status IN ('Gross','Net_20'):
  Check most recent subcontractor_cis_verifications row.
  If expires_at <= now() + 30 days AND notification not sent:
    Send notification to finance + contracts manager
    "CIS verification for [subcontractor] expires [date]. Re-verify before next payment."
  If expires_at <= now():
    Set subcontractor.cis_status = 'Pending_Verification'
    Notify finance: "[subcontractor] CIS expired. Future payments will deduct at 30% until re-verified."
    Block 2.8b valuation submission until re-verified (soft block — finance can override with reason).
```

**Insurance expiry job (daily, runs 06:00):**

```
For each supplier_documents with expires_at NOT NULL AND archived_at IS NULL:
  If expires_at <= now() + 30 days AND notification_sent_30_days = false:
    Send notification to contracts manager + finance
    Set notification_sent_30_days = true
  If expires_at <= now() + 7 days AND notification_sent_7_days = false:
    Send notification with severity High
    Set notification_sent_7_days = true
  If expires_at <= now() AND notification_sent_expired = false:
    Send Critical notification
    Block PO issue / valuation approval for this supplier (soft block — director override allowed)
    Set notification_sent_expired = true
```

**Rating cache refresh:**

```
On supplier_project_assignments rating update:
  overall_rating = (quality + reliability + commercial) / 3
  
On supplier select-list rendering:
  Sort by: preferred_status DESC, overall_rating DESC, last_engaged_at DESC.
```

### UI

**Suppliers list** (`/suppliers`):
- Table with columns: Code, Name, Type, Trades (subs only), Status, Last engaged, Rating.
- Filters: type, preferred status, has-expiring-docs, trade.
- Quick actions: archive, set on hold, mark preferred.

**Supplier detail** (`/suppliers/:id`):
- Tabs: Overview, Subcontractor (if applicable), Insurance & Documents, Project History, Activity.
- Subcontractor tab shows CIS verification history with "Verify Now" action that opens HMRC verification modal — manual data entry for now (Future Tasks Phase 4 covers HMRC direct submission).
- Project History pulls from `supplier_project_assignments` with rating UI per project.

**New supplier form** (`/suppliers/new`):
- Stepped form: Basic info → Type & VAT → Subcontractor details (conditional) → Insurance & docs.
- Sub flag triggers extra step.

### Permissions

- `suppliers.view` — finance, director, contracts manager, project lead
- `suppliers.create` — finance, contracts manager, director
- `suppliers.edit` — finance, contracts manager
- `suppliers.archive` — finance, director
- `subcontractors.cis_verify` — finance, director (recording verification)
- `supplier_documents.upload` — contracts manager, finance, supplier user (via 2.9 portal)
- `supplier_project_assignments.rate` — project lead, contracts manager, director

### Acceptance criteria

- [ ] Supplier and subcontractor records can be created with full required field validation
- [ ] One supplier may correspond to one subcontractor record (1:1 when `is_subcontractor=true`)
- [ ] CIS verification can be recorded, with `expires_at` auto-set to verified_at + 2 years
- [ ] CIS expiry job notifies finance 30 days before, and downgrades to Pending_Verification on expiry
- [ ] Insurance expiry job runs and sends notifications at 30 / 7 / 0 day thresholds
- [ ] Insurance expiry blocks PO issue (soft block, director override allowed)
- [ ] `supplier_project_assignments` cache (committed / invoiced) refreshes on commitment / actual changes
- [ ] Per-project ratings stored separately from supplier master record
- [ ] Suppliers list filters by trade, status, expiring-docs work
- [ ] Sort order on supplier picker correctly prioritises Preferred, then highest-rated, then most-recent
- [ ] Archived suppliers excluded from creation pickers

### Out of scope

- HMRC direct CIS verification API integration — Future Tasks Phase 4.
- Automated CIS300 monthly return generation — relies on Xero in Phase 2 (Track 6); native generation is Future Tasks Phase 4.
- Supplier self-onboarding (supplier signs themselves up via portal) — out of scope; SY Homes invites suppliers explicitly via 2.9.
- Tender invitations / RFQs to suppliers — Tender module deferred per Chat 5.

---

## Prompt 2.8a — Subcontracts and Variations

**Dependencies:** 2.5, 2.7
**Tables in this prompt:** `subcontracts`, `subcontract_milestones`, `subcontract_variations`, `subcontract_variation_lines`
**Estimated hours:** 10h
**Status:** NEW — first half of skeleton's Prompt 2.8 (split per "Changes versus skeleton" above).

Formal subcontract record linking a subcontractor (2.7) to a commitment (2.5). Captures contract sum, retention regime, payment terms, and the variation workflow that modifies it. Valuations and payment notices live in 2.8b.

### Build `subcontracts`

```
subcontracts
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
entity_id                       uuid NOT NULL FK→entities.id
subcontractor_id                uuid NOT NULL FK→subcontractors.id
commitment_id                   uuid NOT NULL UNIQUE FK→commitments.id  -- 1:1 with a commitment
subcontract_ref                 varchar(40) NOT NULL    -- e.g. SY-2026-001-GW
subcontract_title               varchar(255) NOT NULL
trade                           varchar(100) NOT NULL
form_of_contract                enum
                                  ('JCT_SBSub_2016','JCT_DBSub_2016','JCT_ICSub_2016',
                                   'NEC4_Sub','Bespoke','Letter_of_Intent','Other')
                                  DEFAULT 'JCT_DBSub_2016'
contract_sum_excl_vat           decimal(14,2) NOT NULL
vat_treatment                   enum NOT NULL
                                  ('Standard_20','Reverse_Charge','Zero_Rated','Exempt')
                                  -- Reverse_Charge is the CIS reverse charge VAT regime since 2021
retention_rate_pct              decimal(5,2) NOT NULL DEFAULT 5
retention_release_at_pc_pct     decimal(5,2) NOT NULL DEFAULT 50    -- % of retention released at PC
retention_release_at_dlp_pct    decimal(5,2) NOT NULL DEFAULT 50    -- % at DLP end
dlp_months                      int NOT NULL DEFAULT 12
payment_terms_days              int NOT NULL DEFAULT 30  -- net X days from valuation date
valuation_cycle                 enum NOT NULL DEFAULT 'Monthly'
                                  ('Monthly','Stage','One_Off')
valuation_day_of_month          int                -- if Monthly, day to value (e.g. 25)
contract_start_date             date NOT NULL
contract_practical_completion_date  date
actual_practical_completion_date    date
dlp_end_date                    date              -- computed: PC + dlp_months
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Issued','Active','Practically_Complete','In_DLP','Final_Account_Agreed','Closed','Terminated')
total_certified_to_date         decimal(14,2) NOT NULL DEFAULT 0   -- cached from valuations
total_paid_to_date              decimal(14,2) NOT NULL DEFAULT 0   -- cached from actuals
total_retention_held            decimal(14,2) NOT NULL DEFAULT 0   -- cached
total_variations_approved       decimal(14,2) NOT NULL DEFAULT 0   -- cached
revised_contract_sum            decimal(14,2) NOT NULL             -- = contract_sum + total_variations_approved
contract_document_id            uuid    -- FK to documents (5.2)
notes                           text
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
issued_at                       timestamp
issued_by_user_id               uuid FK→users.id
terminated_at                   timestamp
terminated_by_user_id           uuid FK→users.id
termination_reason              text

Indexes:
- UNIQUE (tenant_id, subcontract_ref)
- INDEX (project_id, status)
- INDEX (subcontractor_id)
- INDEX (commitment_id)
- INDEX (status) WHERE status IN ('Active','Practically_Complete','In_DLP')
```

### Build `subcontract_milestones`

For stage-payment subcontracts (mostly LOIs and bespoke contracts).

```
subcontract_milestones
─────────────────────────────────────────────
id                              uuid PK
subcontract_id                  uuid NOT NULL FK→subcontracts.id ON DELETE CASCADE
sequence                        int NOT NULL
description                     varchar(255) NOT NULL
target_date                     date
stage_value_excl_vat            decimal(14,2) NOT NULL
status                          enum NOT NULL DEFAULT 'Pending'
                                  ('Pending','Achieved','Certified','Paid')
achieved_date                   date
certified_in_valuation_id       uuid    -- FK to subcontract_valuations (2.8b)
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (subcontract_id, sequence)
- INDEX (subcontract_id, status)
```

### Build `subcontract_variations`

```
subcontract_variations
─────────────────────────────────────────────
id                              uuid PK
subcontract_id                  uuid NOT NULL FK→subcontracts.id ON DELETE RESTRICT
variation_ref                   varchar(40) NOT NULL    -- e.g. VO-001 within the subcontract
title                           varchar(255) NOT NULL
description                     text NOT NULL
raised_by_user_id               uuid NOT NULL FK→users.id   -- internal user OR portal subcontractor user
raised_at                       timestamp NOT NULL DEFAULT now()
raised_via                      enum NOT NULL DEFAULT 'Internal'
                                  ('Internal','Portal_Subcontractor')
instruction_source              enum
                                  ('Site_Instruction','Architect_Instruction','Client_Change','Discovered_Condition','Compliance','Other')
estimated_value_excl_vat        decimal(14,2)         -- subcontractor estimate at submission
agreed_value_excl_vat           decimal(14,2)         -- after negotiation
time_impact_days                int                   -- variance to programme (negative for accelerations)
status                          enum NOT NULL DEFAULT 'Submitted'
                                  ('Draft','Submitted','Under_Review','Costed','Approved','Rejected','Withdrawn')
approved_by_user_id             uuid FK→users.id
approved_at                     timestamp
rejection_reason                text
linked_bcr_id                   uuid    -- FK to budget_change_requests (2.6); set on approval
linked_programme_task_ids       jsonb DEFAULT '[]'    -- which tasks affected (3.4)
supporting_documents            jsonb DEFAULT '[]'    -- list of document IDs from 5.2
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (subcontract_id, variation_ref)
- INDEX (subcontract_id, status)
- INDEX (status) WHERE status IN ('Submitted','Under_Review','Costed')
- INDEX (raised_at DESC)
```

### Build `subcontract_variation_lines`

Line-level cost breakdown of a variation. Mirrors the commitment_lines pattern.

```
subcontract_variation_lines
─────────────────────────────────────────────
id                              uuid PK
variation_id                    uuid NOT NULL FK→subcontract_variations.id ON DELETE CASCADE
sequence                        int NOT NULL
description                     varchar(500) NOT NULL
cost_code_id                    uuid NOT NULL FK→cost_codes.id
line_type                       enum NOT NULL
                                  ('Labour','Materials','Plant','Subcontract','Preliminaries','Other')
quantity                        decimal(14,4) NOT NULL DEFAULT 1
unit                            varchar(20)             -- m2, m3, item, hour, day
unit_rate_excl_vat              decimal(14,4) NOT NULL
line_total_excl_vat             decimal(14,2) NOT NULL  -- = quantity × unit_rate
notes                           text

Indexes:
- INDEX (variation_id)
- INDEX (cost_code_id)
```

### Business logic

**Subcontract creation flow:**

```
Trigger: User creates a commitment of type=Subcontract in 2.5 → option to "Create subcontract record" button.
Or: User creates subcontract directly, which auto-creates the linked commitment.

On Issue:
  - subcontracts.status = Issued
  - commitment.status = Issued (if not already)
  - PDF subcontract document generated from form-of-contract template (5.2 templates)
  - Subcontractor notified via portal (2.9) or email
  
On Counter-sign (subcontractor accepts):
  - subcontracts.status = Active
  - commitment.status = Confirmed
  - Audit log: "[user] confirmed subcontract [ref] on behalf of [subcontractor]"

revised_contract_sum cache:
  revised_contract_sum = contract_sum_excl_vat + sum(approved variations.agreed_value_excl_vat)
  Recalc on variation status → Approved or → Rejected (rolling back)
```

**Variation workflow state machine:**

```
Draft → (submit) → Submitted
Submitted → (CM reviews) → Under_Review
Under_Review → (CM costs and posts) → Costed
Costed → (director or finance approves) → Approved
Costed → (rejected) → Rejected
Submitted | Under_Review | Costed → (raiser withdraws) → Withdrawn

Approval gate:
  - If agreed_value < 0: any director approves
  - If agreed_value < config.budget.variation_director_threshold (default £5,000): one director
  - If above: two-director approval required (uses generic approval workflow from 1.7)

On Approved:
  - Generate BCR via 2.6 with source_type=Variation, lines mirroring variation_lines.
  - BCR follows its own approval flow (typically auto-approved if variation has been director-approved).
  - subcontracts.total_variations_approved += agreed_value
  - subcontracts.revised_contract_sum recalculated.
  - If linked_programme_task_ids set, programme tasks (3.4) flagged with variation impact.
```

**Programme integration:**
- Variations with `time_impact_days != 0` create a notification to the project lead suggesting programme update.
- Approved variation links don't auto-modify task durations — too risky. CM updates programme manually.

### UI

**Subcontracts list** (`/projects/:id/commercial/subcontracts`):
- Table: Ref, Subcontractor, Trade, Sum, Variations approved, Certified, Paid, Status.
- Filters: status, subcontractor, trade.
- Actions: New subcontract, Issue, View.

**Subcontract detail** (`/subcontracts/:id`):
- Header strip: ref, subcontractor, contract sum, revised sum, certified, paid, retention held.
- Tabs: Overview, Variations, Valuations (read-only summary, links to 2.8b), Milestones (if stage), Documents, Activity.
- Variations tab: list of variations with status pills, "Raise variation" button.

**Variation form** (`/subcontracts/:id/variations/new`):
- Multi-line entry similar to PO.
- Cost code per line. Auto-aggregates total.
- Supporting documents drag-drop.
- "Submit" → goes to Submitted state.

**Variation review (CM view):**
- Status tracker at top.
- "Cost this variation" — CM can edit `agreed_value_excl_vat` and rationalise per-line.
- "Approve" or "Reject" actions with director sign-off requirement enforced.

### Permissions

- `subcontracts.view` — finance, director, contracts manager, project lead
- `subcontracts.create` — contracts manager, director
- `subcontracts.issue` — contracts manager, director
- `subcontracts.terminate` — director only
- `subcontract_variations.view` — finance, director, CM, project lead, **subcontractor portal user (own variations only)**
- `subcontract_variations.create` — CM, director, **subcontractor portal user**
- `subcontract_variations.cost` — CM (assign costs)
- `subcontract_variations.approve` — director (per threshold rules)

### Acceptance criteria

- [ ] Subcontract can be created from a commitment, or directly creating a commitment underneath
- [ ] One subcontract = one commitment (1:1 enforced by UNIQUE constraint)
- [ ] Issue generates a PDF using the relevant form-of-contract template
- [ ] Counter-sign moves status to Active and commitment to Confirmed
- [ ] revised_contract_sum cache refreshes correctly when variations approved/rejected
- [ ] Variation state machine enforced; invalid transitions rejected
- [ ] Approved variation generates a BCR via 2.6 with correct source_type and line items
- [ ] Two-director approval enforced for variations above threshold
- [ ] Variation can be raised by a subcontractor portal user (2.9) and routed to CM for review
- [ ] Programme task variation flag set when linked_programme_task_ids populated
- [ ] Time impact stored (days) — does NOT auto-modify task durations
- [ ] Stage-payment milestones can be created and tracked
- [ ] All transitions audit-logged

### Out of scope

- Auto-update of programme task durations from variations — manual update only (CM judgement required).
- Variation valuation (the *value* of work-in-progress on a variation) lives in 2.8b.
- Final account agreement workflow — 7.3 handles final account close-out.
- Disputes / adjudication / contract claims tracking — Future Tasks Phase 5.

---

## Prompt 2.8b — Subcontract Valuations and Payment Notices

**Dependencies:** 2.5, 2.7, 2.8a
**Tables in this prompt:** `subcontract_valuations`, `subcontract_valuation_lines`, `payment_notices`
**Estimated hours:** 10h
**Status:** NEW — second half of skeleton's Prompt 2.8 (split per "Changes versus skeleton" above).

The monthly operating cycle on top of the subcontract structure built in 2.8a. Subcontractor submits a valuation; CM/QS reviews and certifies; payment notice generated under HGCRA / Construction Act timing rules; actual posted on payment.

### Build `subcontract_valuations`

```
subcontract_valuations
─────────────────────────────────────────────
id                              uuid PK
subcontract_id                  uuid NOT NULL FK→subcontracts.id ON DELETE RESTRICT
valuation_number                int NOT NULL    -- 1, 2, 3 within a subcontract
valuation_date                  date NOT NULL    -- the "as at" date
submitted_at                    timestamp        -- when subcontractor submitted
submitted_by_user_id            uuid FK→users.id
submitted_via                   enum NOT NULL DEFAULT 'Internal'
                                  ('Internal','Portal_Subcontractor')

-- Submitted (subcontractor's claim)
gross_applied_excl_vat          decimal(14,2) NOT NULL
                                  -- cumulative work-done value claimed by subcontractor
sub_claim_breakdown_attached    boolean NOT NULL DEFAULT false  -- usually a spreadsheet attached

-- Certified (after CM/QS review)
gross_certified_excl_vat        decimal(14,2)
                                  -- cumulative agreed value, may differ from applied
previous_certified_excl_vat     decimal(14,2) NOT NULL DEFAULT 0
                                  -- cumulative from prior valuations
this_valuation_excl_vat         decimal(14,2)
                                  -- = certified - previous_certified
retention_rate_pct              decimal(5,2) NOT NULL    -- snapshot from subcontract at time of valuation
retention_this_valuation        decimal(14,2)
                                  -- = this_valuation × retention_rate_pct / 100
cumulative_retention            decimal(14,2)

-- CIS
is_cis_applicable               boolean NOT NULL DEFAULT false
cis_status_at_valuation         enum
                                  ('Gross','Net_20','Net_30','Not_Applicable')
                                  -- snapshot from subcontractor.cis_status at certification time
labour_amount                   decimal(14,2)
materials_amount                decimal(14,2)
cis_deduction_pct               decimal(5,2)
cis_deduction_amount            decimal(14,2)
                                  -- = labour_amount × cis_deduction_pct / 100

-- VAT
vat_treatment                   enum NOT NULL    -- snapshot from subcontract
                                  ('Standard_20','Reverse_Charge','Zero_Rated','Exempt')
vat_rate_pct                    decimal(5,2) NOT NULL DEFAULT 20
                                  -- 0 if Reverse_Charge or Zero_Rated; 20 if Standard
vat_amount                      decimal(14,2)
                                  -- = (this_valuation - retention) × vat_rate / 100, only if Standard_20

-- Net to pay
net_payable_excl_vat            decimal(14,2)    -- this_valuation - retention - cis_deduction
gross_payable_incl_vat          decimal(14,2)    -- net_payable + vat

-- State
status                          enum NOT NULL DEFAULT 'Submitted'
                                  ('Draft','Submitted','Under_Review','Certified','Disputed','Paid','Void')
certified_by_user_id            uuid FK→users.id
certified_at                    timestamp
dispute_reason                  text
notes_to_subcontractor          text             -- shown on payment notice

-- Linked records
linked_actual_id                uuid             -- FK to actuals (2.5); set when payment posted
linked_payment_notice_id        uuid             -- FK to payment_notices below

created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
voided_at                       timestamp
voided_by_user_id               uuid FK→users.id
void_reason                     text

Indexes:
- UNIQUE (subcontract_id, valuation_number)
- INDEX (subcontract_id, valuation_date DESC)
- INDEX (status) WHERE status IN ('Submitted','Under_Review','Certified')
- INDEX (certified_at) WHERE status = 'Certified'
```

### Build `subcontract_valuation_lines`

Line-level breakdown of certified value, useful for audit and dispute resolution.

```
subcontract_valuation_lines
─────────────────────────────────────────────
id                              uuid PK
valuation_id                    uuid NOT NULL FK→subcontract_valuations.id ON DELETE CASCADE
sequence                        int NOT NULL
description                     varchar(500) NOT NULL
cost_code_id                    uuid FK→cost_codes.id
work_section                    varchar(100)            -- e.g. "Substructure", "Frame"
contract_value_excl_vat         decimal(14,2)           -- planned value of this line
percent_complete_applied        decimal(5,2)            -- subcontractor's claim
percent_complete_certified      decimal(5,2)            -- CM/QS certified
applied_value_excl_vat          decimal(14,2)
certified_value_excl_vat        decimal(14,2)
notes                           text

Indexes:
- INDEX (valuation_id)
- INDEX (cost_code_id) WHERE cost_code_id IS NOT NULL
```

### Build `payment_notices`

UK Construction Act (Housing Grants, Construction and Regeneration Act 1996, as amended) requires statutory payment notices with specific timing:
- **Payment notice** issued within 5 days of payment due date — states sum to be paid.
- **Pay less notice** issued within prescribed period before final date for payment — required if payer wants to pay less than the certified amount.
- The platform issues a payment notice automatically with each certified valuation. Pay-less notices are issued explicitly when needed.

```
payment_notices
─────────────────────────────────────────────
id                              uuid PK
notice_type                     enum NOT NULL
                                  ('Payment_Notice','Pay_Less_Notice')
valuation_id                    uuid NOT NULL FK→subcontract_valuations.id
subcontract_id                  uuid NOT NULL FK→subcontracts.id     -- denormalised for query
notice_number                   int NOT NULL    -- sequential within subcontract
notice_date                     date NOT NULL    -- date issued
due_date                        date NOT NULL    -- final date for payment (notice_date + payment_terms_days)
sum_notified_excl_vat           decimal(14,2) NOT NULL
sum_notified_incl_vat           decimal(14,2) NOT NULL
basis                           text NOT NULL    -- legally required: how the sum was calculated
                                                  -- Pay_Less requires this to detail why less than certified
issued_by_user_id               uuid NOT NULL FK→users.id
issued_at                       timestamp NOT NULL DEFAULT now()
delivery_method                 enum NOT NULL
                                  ('Email','Portal','Post','Hand_Delivered')
delivered_at                    timestamp
recipient_email                 varchar(255)
recipient_name                  varchar(255)
notice_pdf_document_id          uuid FK→documents.id    -- generated PDF
status                          enum NOT NULL DEFAULT 'Issued'
                                  ('Draft','Issued','Acknowledged','Paid','Withdrawn')
acknowledged_at                 timestamp        -- subcontractor acknowledges receipt via portal
paid_actual_id                  uuid FK→actuals.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
withdrawn_at                    timestamp
withdrawn_by_user_id            uuid FK→users.id
withdrawal_reason               text

Indexes:
- UNIQUE (subcontract_id, notice_type, notice_number)
- INDEX (due_date) WHERE status IN ('Issued','Acknowledged')
- INDEX (valuation_id)
```

### Business logic

**Valuation cycle (monthly default):**

```
On the valuation_day_of_month for each Active subcontract:
  Notification to subcontractor: "Submit valuation [number] for [subcontract] by [valuation_date + 5 days]"
  
Subcontractor (via portal 2.9 or internally):
  Submits gross_applied_excl_vat with optional line breakdown and supporting docs.
  Status: Submitted.

CM / QS review:
  Reviews vs site progress, programme (3.4), QA records (4.5).
  Either:
    - Certifies as-applied: gross_certified = gross_applied → status Certified.
    - Adjusts: gross_certified < gross_applied, with line-level rationale → status Certified (with notes).
    - Disputes: status Disputed with reason. Subcontractor can revise and resubmit.

On Certified:
  - this_valuation = gross_certified - previous_certified (where previous_certified is sum of prior certified).
  - retention_this_valuation = this_valuation × retention_rate_pct / 100.
  - If subcontractor.is_cis_applicable AND vat_treatment != 'Reverse_Charge':
      cis_deduction_amount = labour_amount × cis_deduction_pct / 100
      labour_amount defaults from subcontractor.default_labour_ratio_pct × this_valuation
  - VAT: 
      if vat_treatment = Standard_20: vat = (this_valuation - retention) × 20%
      if vat_treatment = Reverse_Charge: vat = 0; statement "VAT reverse charge applies — customer to account for VAT"
      if vat_treatment = Zero_Rated / Exempt: vat = 0
  - net_payable = this_valuation - retention - cis_deduction
  - gross_payable = net_payable + vat
  - subcontracts.total_certified_to_date += this_valuation
  - subcontracts.total_retention_held += retention_this_valuation
  - Generate payment_notice with notice_type=Payment_Notice (see below).
```

**Payment notice generation:**

```
Auto on Certified valuation:
  notice_date = today
  due_date = notice_date + subcontract.payment_terms_days
  notice_number = max(notice_number for this subcontract) + 1
  sum_notified_excl_vat = valuation.net_payable_excl_vat
  sum_notified_incl_vat = valuation.gross_payable_incl_vat
  basis = templated text including:
    "Gross certified: £X cumulative"
    "Less previously certified: £Y"
    "This valuation: £Z"
    "Less retention at N%: £A"
    "Less CIS at M%: £B" (if applicable)
    "Plus VAT at 20%: £C" or "VAT reverse charge applies"
    "Sum due: £D"
  PDF generated using payment notice template, includes statutory wording.
  Delivered to subcontractor via portal (2.9) or email.
  
Pay Less Notice (manual action by finance / director):
  Trigger: finance/director decides to pay less than certified within statutory window.
  Required: basis (text, why paying less — e.g. defective work, set-off).
  notice_type = Pay_Less_Notice
  sum_notified can be lower than the corresponding payment notice.
  Generated PDF includes statutory wording for Pay Less.
  Subcontractor notified.
  When actual is posted, it matches the Pay Less amount, not the original Payment Notice amount.
```

**Payment posting:**

```
On payment day:
  Finance: "Post payment for valuation [N]" action.
  Creates an actual in 2.5 with:
    related_subcontract_id = subcontract_id
    net_amount = valuation.net_payable_excl_vat (or pay-less if applicable)
    vat_amount = valuation.vat_amount
    cis_deduction_amount = valuation.cis_deduction_amount
    retention_amount = valuation.retention_this_valuation
    description = "Subcontract valuation [N] — [subcontractor]"
    cost code distribution can be derived from valuation_lines (sum by cost_code).
  Sets valuation.linked_actual_id and payment_notice.paid_actual_id.
  Sets valuation.status = Paid, payment_notice.status = Paid.
  Updates subcontracts.total_paid_to_date.
```

**Statutory time-window enforcement:**

The Construction Act has strict timing. The platform doesn't *enforce* timing (it's a legal matter, not a hard system constraint), but it *warns*:
- Payment notice must be issued within 5 days of payment due date — if certified > 5 days ago and no notice issued, alert finance.
- Pay less notice must be issued not later than 7 days (or contract-specified) before final date for payment — if user attempts to issue pay-less inside the prohibited window, warn explicitly with link to contract terms.

**CIS reverse charge VAT:**
Since 1 March 2021, most subcontract construction services use the VAT reverse charge. Default `vat_treatment = Reverse_Charge` for subcontractors flagged `is_subcontractor = true`. Override at subcontract level if needed. Payment notice and actual generation handle the difference: no VAT charged by subcontractor, customer (SY Homes ConstructionCo) accounts for VAT on its own VAT return.

### UI

**Valuations list** (`/projects/:id/commercial/valuations`):
- Table: Subcontract, Valuation #, Date, Applied, Certified, Net Payable, Status, Due Date.
- Filters: status, overdue (status=Issued and due_date < today), this month.

**Valuation detail** (`/valuations/:id`):
- Top: subcontract context, valuation summary tile.
- Sections: Application (subcontractor's claim), Certification (CM-edited), Calculation (retention, CIS, VAT, net), Notes, Documents, Activity.
- Status-driven actions: Certify, Adjust, Dispute, Issue Payment Notice, Issue Pay Less, Post Payment.

**Subcontractor portal valuation form** (in 2.9, but referenced here):
- Mobile-friendly. "Submit valuation" prominent on portal home for any subcontract with valuation due.
- Free-text breakdown attachment supported.
- Line-by-line entry optional but encouraged.

**Payment notice PDF template:**
- Entity letterhead.
- Statutory wording per HGCRA s.110A.
- Basis section enumerating calculation.
- "Final date for payment: [date]" — visible.

### Permissions

- `subcontract_valuations.view` — finance, director, CM, project lead, **subcontractor portal user (own only)**
- `subcontract_valuations.submit` — CM, director, **subcontractor portal user**
- `subcontract_valuations.certify` — CM, director (requires CM in default policy; configurable)
- `subcontract_valuations.dispute` — CM, director
- `subcontract_valuations.post_payment` — finance, director
- `payment_notices.issue` — automatic on certify; manual issuance director / finance only
- `payment_notices.issue_pay_less` — director, finance (with reason)

### Acceptance criteria

- [ ] Valuation can be submitted by subcontractor via portal (2.9) or internally
- [ ] Certified valuation calculates retention, CIS, VAT correctly across all CIS and VAT regimes (Standard, Reverse Charge, Zero, Exempt; Gross / Net 20 / Net 30)
- [ ] CIS reverse charge VAT defaults correctly for subcontractor-flagged suppliers
- [ ] Pay-less notice required to be issued within statutory window — warning if outside
- [ ] Payment notice auto-generated as PDF on certify
- [ ] Payment notice PDF includes statutory s.110A wording
- [ ] `previous_certified_excl_vat` correctly accumulates from prior valuations
- [ ] Posting payment creates an actual (2.5) linked to the subcontract with correct distribution
- [ ] subcontracts.total_certified_to_date / total_paid_to_date / total_retention_held caches refresh
- [ ] Valuation status machine correctly enforced
- [ ] Voided valuation rolls back caches
- [ ] Disputed valuation can be revised by subcontractor and resubmitted
- [ ] Retention held in this valuation flows to retention release schedule (linked forward to 7.3)
- [ ] Audit log captures all transitions including certification adjustments

### Out of scope

- Adjudication / dispute resolution module — Future Tasks Phase 5.
- Final account reconciliation (after PC, before retention release) — handled in 7.3.
- Direct payment to subcontractor's bank — uses Xero or manual bank transfer; out of scope.
- Multi-currency valuations — GBP only.
- Sub-subcontractor (lower-tier) tracking — out of scope.

---

## Prompt 2.9 — Supplier and Subcontractor Portal

**Dependencies:** 1.2, 1.3, 2.5, 2.7, 2.8a, 2.8b
**Tables in this prompt:** No new tables — uses existing 2.5/2.7/2.8 tables with `is_portal_user` flag added to `users`.
**Estimated hours:** 12h
**Status:** NEW.

The first external-facing surface in the platform. Suppliers confirm POs and schedule deliveries; subcontractors submit valuations, raise variations, upload required documents. Single portal, two distinct UI flavours by user type.

### Schema delta

```
users (extension)
─────────────────────────────────────────────
is_portal_user                  boolean NOT NULL DEFAULT false
portal_user_type                enum
                                  ('Supplier','Subcontractor','Labourer')   -- Labourer reserved for 4.7
linked_supplier_id              uuid FK→suppliers.id
linked_subcontractor_id         uuid FK→subcontractors.id
last_portal_login_at            timestamp
```

A portal user is a `users` row with `is_portal_user = true` and a link to either `suppliers` or `subcontractors`. They use a portal-scoped role (seeded in 1.2) with permission strictly limited.

### Authentication and session policy

- Portal users authenticate via the same flow as internal users (Argon2id + JWT) but on a separate URL (`portal.sy-homes.co.uk` or `/portal` path under main app — pick during build).
- **Shorter session timeout for portal users:** 8 hours (vs 12h default for internal). Configurable in 1.7.
- **MFA optional but encouraged.** Not mandatory for portal users to keep onboarding friction low. Internal MFA-required-roles config from 1.7 doesn't extend to portal.
- **Rate limiting per portal user:** 60 requests/min (vs 600/min for internal). Throttle triggers HTTP 429.
- Portal session forced re-auth after sensitive actions: valuation submission, variation submission, PO confirmation. Brief re-prompt for password.

### Field allowlists per portal endpoint

This is the key to safety. Portal endpoints don't return entity records — they return a portal DTO with explicit field allowlists. No accidental exposure.

**Supplier portal — allowed reads:**
- Own supplier record: `display_name`, `supplier_code`, contact info, billing/delivery addresses.
- Own POs (commitments where supplier_id matches): ref, line items, total value, status, expected delivery dates.
- Own delivery notes (uploaded). Documents requested by SY Homes (insurance certificates etc.).
- Their own portal user activity (last login, recent actions).
- **Forbidden:** other suppliers, project budgets, internal cost codes, ratings, internal notes, internal users.

**Supplier portal — allowed writes:**
- Confirm a PO (status Issued → Confirmed).
- Schedule delivery date for a PO line.
- Upload delivery note attachment.
- Upload supplier documents (insurance certificates, accreditations).
- Update own contact info (subject to internal review before propagating to master record).

**Subcontractor portal — allowed reads:**
- Own subcontractor record + linked supplier record (subset of fields).
- Own subcontracts: ref, contract sum, status, retention held, certified to date, paid to date.
- Own variations and valuations history.
- Own payment notices (PDFs downloadable).
- QA submission requests (links forward to 4.5 — placeholder in 2.9, full in 4.5).
- Own programme tasks (their work only — not the full programme).

**Subcontractor portal — allowed writes:**
- Submit valuation (creates 2.8b row with submitted_via=Portal_Subcontractor).
- Raise variation (creates 2.8a row with raised_via=Portal_Subcontractor).
- Acknowledge payment notice receipt.
- Upload supporting documents (linked to a valuation, variation, or required general docs).
- Update own contact info.

### Business logic

**Invitation flow:**

```
Internal user (CM or finance) on supplier or subcontractor detail:
  Action: "Invite to portal"
  Form: contact name, email
  System: 
    - creates users row with is_portal_user=true, status=Invited, links to supplier/subcontractor
    - sends invitation email with one-time link (expires 14 days)
    - link → set password + optional MFA → first login
  Audit: invitation logged.

Re-send invitation: yes, regenerates token.
Revoke portal access: archives user row, all sessions invalidated.
```

**Portal home (supplier):**
- Pending POs to confirm (count + list, top 5 latest).
- Upcoming deliveries this week.
- Documents expiring within 60 days (read warning).
- Recent activity.

**Portal home (subcontractor):**
- Active subcontracts (with quick metrics: certified vs revised contract sum).
- Valuations due this week (red flag if any past their valuation_day_of_month).
- Variations awaiting your action (Costed status — needs your acceptance) — forward-looking; not in 2.8a v1 but reserved.
- Payment notices to acknowledge.
- Documents expiring.

**PO confirmation flow (supplier):**
```
Portal user views PO.
Confirms: writes commitment.status = Confirmed (with portal_confirmed_by_user_id, portal_confirmed_at).
Notification to internal CM: "[supplier] confirmed PO [ref]".
Schedule delivery: writes commitment_lines.expected_delivery_date.
```

**Valuation submission flow (subcontractor):**
```
Portal user navigates to subcontract → "Submit valuation".
Form pre-populates with subcontract context.
Required: gross_applied_excl_vat, valuation_date.
Optional: line breakdown, notes, supporting docs.
On submit: 2.8b row created with status=Submitted, submitted_via=Portal_Subcontractor.
Notification to internal CM: "[subcontractor] submitted valuation [N]".
```

**Variation submission flow (subcontractor):**
```
Portal user navigates to subcontract → "Raise variation".
Form: title, description, proposed value, time impact, supporting docs.
On submit: 2.8a variation row created with status=Submitted, raised_via=Portal_Subcontractor.
Notification to internal CM and project lead.
```

### UI

**Mobile-first.** Most portal use happens on a phone — supplier confirming a PO from a yard, subcontractor submitting a valuation from a van. Big tap targets, minimal nesting, top-level actions visible.

**Branding:** SY Homes branded, but visually distinct from internal portal — clearly "external" so portal users don't confuse with internal SY Homes app. Header bar has a different colour. "You are using the SY Homes Supplier Portal" footer.

**Notifications:** portal users get email by default. SMS for critical notifications only (payment notice issued — Future Tasks if needed).

**Portal homepage** patterns:
- 3 columns max on desktop, single column mobile.
- Action cards (e.g. "2 POs awaiting confirmation") tap into a focused view.
- "Need help?" link → contact details for SY Homes commercial team.

### Permissions (portal-specific roles)

Two new system roles seeded:

- **Supplier Portal User** — minimal scope:
  - `commitments.view_own` (where supplier_id = linked_supplier_id)
  - `commitments.confirm_own`
  - `supplier_documents.upload_own`
  - `supplier.update_own_contact`
  
- **Subcontractor Portal User** — extends Supplier Portal User with:
  - `subcontracts.view_own` (where subcontractor_id = linked_subcontractor_id)
  - `subcontract_valuations.view_own` / `submit_own`
  - `subcontract_variations.view_own` / `raise_own`
  - `payment_notices.acknowledge_own`

The `_own` suffix indicates row-level filter applied at API layer based on the user's `linked_supplier_id` / `linked_subcontractor_id`. **Hard-constraint check (RBAC #8):** enforced at API middleware, not just UI — every portal endpoint runs through a scope check that filters returned rows to the user's linked entity.

### Acceptance criteria

- [ ] Portal user can be invited from internal supplier/subcontractor detail page
- [ ] Invitation email sends one-time link with 14-day expiry
- [ ] Portal user can set password and optional MFA on first login
- [ ] Portal session timeout enforced at 8h (configurable in 1.7)
- [ ] Portal session re-auth required for sensitive actions (valuation, variation, PO confirm)
- [ ] Portal user only sees own commitments / subcontracts (server-side filter, attempted access to other supplier's record returns 404)
- [ ] Portal API endpoints return only allowlisted fields (verified via API test suite)
- [ ] Internal user data (other suppliers, internal users, project budgets, ratings, notes) not exposed in any portal endpoint
- [ ] Rate limit of 60 req/min per portal user enforced; 429 returned over limit
- [ ] Mobile UX tested on iOS Safari and Android Chrome — all key flows usable
- [ ] PO confirmation, valuation submission, variation raising all work end-to-end
- [ ] Notifications sent to internal team on portal-driven events
- [ ] Revoking portal access invalidates all active sessions
- [ ] Audit log captures portal logins and all portal actions with user identity

### Out of scope

- Self-onboarding (subcontractor signs themselves up without invitation) — explicit invitation only.
- Customer-facing buyer portal — Future Tasks Phase 3.
- Labourer portal — separate prompt (4.7).
- Public read-only data feed (e.g. plot availability for marketing site) — Prompt 7.4.
- Portal-to-portal messaging between supplier and SY Homes — uses chat (4.3) once that lands; portal in 2.9 has notifications only.
- White-labelling the portal for any commercial sale — explicitly rejected per Project Instructions.

---

# Track 3 — Real-time + Offline + Programme

**Goal:** Lay the real-time and offline-sync infrastructure that all of Track 4 (Site Ops) and parts of Tracks 6, 7 depend on. Then deliver the programme/CPM module, taking advantage of the new infra. State-of-the-art programme module is in scope (CPM, baselines, dependency types, calendars, real-time updates); programme stretch features (weather-aware, predictive completion, cross-project resource view) confirmed deferred per Chat 5.

**Duration:** ~9 weeks at 25 hrs/week
**Prompts:** 5
**Tables added:** ~15
**Audit checkpoint:** End of Track 3 — self-audit + Rhys review, plus performance baseline measurement (real-time latency, offline sync timing, CPM compute on a 100-task programme).

---

## Prompt 3.1 — Real-time Infrastructure

**Dependencies:** 1.2, 1.4
**Tables in this prompt:** `realtime_channels`, `realtime_subscriptions`, `realtime_events`
**Estimated hours:** 14h
**Status:** NEW. Foundation infrastructure for chat, activity streams, programme updates, dashboard live metrics.

### Technology choice — locked

**WebSockets** (not SSE).

Reasoning:
- Chat (4.3) requires bidirectional messaging.
- Presence tracking (who's online) is bidirectional.
- FastAPI + Starlette ASGI handles WebSockets cleanly with `websockets` library; no additional infrastructure.
- SSE wins primarily when proxy / firewall constraints block long-lived connections — not the case for SY Homes (cloud-hosted on Emergent).
- WebSocket upgrade is a one-time HTTP handshake that survives the same proxy paths as regular HTTP.

Implementation: `websockets` library on backend; native `WebSocket` in browser; `react-use-websocket` for the React client wrapper. Single connection per browser tab, multiplexed channels.

### Build `realtime_channels`

```
realtime_channels
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
channel_type                    enum NOT NULL
                                  ('Project','User_Direct','Role_Scoped','System_Broadcast','Entity')
channel_key                     varchar(255) NOT NULL UNIQUE
                                  -- e.g. "project:abc-123", "user:def-456", "role:site_managers", "entity:spv"
display_name                    varchar(255)
description                     text
is_archived                     boolean NOT NULL DEFAULT false
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
last_event_at                   timestamp

Indexes:
- UNIQUE (tenant_id, channel_key)
- INDEX (channel_type, is_archived)
```

### Build `realtime_subscriptions`

Tracks who is currently subscribed to which channels. Used for presence (who's online for this project) and broadcast targeting.

```
realtime_subscriptions
─────────────────────────────────────────────
id                              uuid PK
channel_id                      uuid NOT NULL FK→realtime_channels.id ON DELETE CASCADE
user_id                         uuid NOT NULL FK→users.id ON DELETE CASCADE
session_id                      varchar(100) NOT NULL    -- WS connection ID
subscribed_at                   timestamp NOT NULL DEFAULT now()
last_pinged_at                  timestamp NOT NULL DEFAULT now()
client_info                     jsonb        -- { user_agent, ip, app_version }

Indexes:
- INDEX (channel_id, user_id)
- INDEX (session_id)
- INDEX (last_pinged_at)
```

Subscriptions are ephemeral. Cleanup job removes rows where `last_pinged_at < now() - 90 seconds` (heartbeat is every 30s; 3 missed pings = stale).

### Build `realtime_events`

Append-only log of every broadcast. Used for replay on reconnect (so a user who lost signal for 30 seconds can catch up without losing chat messages or activity events).

```
realtime_events
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
channel_id                      uuid NOT NULL FK→realtime_channels.id
event_type                      varchar(100) NOT NULL
                                  -- e.g. "chat.message", "task.updated", "snag.created", "presence.joined"
event_payload                   jsonb NOT NULL
emitted_by_user_id              uuid FK→users.id
emitted_at                      timestamp NOT NULL DEFAULT now()
sequence_number                 bigint NOT NULL    -- monotonic per channel; used for ordering + replay
ttl_seconds                     int NOT NULL DEFAULT 86400    -- default 24h retention

Indexes:
- UNIQUE (channel_id, sequence_number)
- INDEX (channel_id, emitted_at DESC)
- INDEX (emitted_at) -- for cleanup
```

Cleanup job removes rows where `emitted_at + ttl_seconds < now()`. Retention default 24h; chat events override to 30 days; system broadcasts to 7 days.

### Business logic — server-side broadcast hook

```python
# Pseudocode — generic broadcast API
def broadcast(channel_key: str, event_type: str, payload: dict, user_id: uuid):
    channel = get_or_create_channel(channel_key)
    sequence_number = next_sequence(channel.id)
    
    # Persist
    insert realtime_events(
        channel_id=channel.id,
        event_type=event_type,
        event_payload=payload,
        emitted_by_user_id=user_id,
        sequence_number=sequence_number
    )
    
    # Push to live subscribers
    subscribers = realtime_subscriptions where channel_id = channel.id
    for sub in subscribers:
        if sub.session_id is connected:
            send WS message {
                "channel": channel_key,
                "event_type": event_type,
                "payload": payload,
                "sequence": sequence_number,
                "emitted_at": now()
            }
    
    # Update channel
    channel.last_event_at = now()
```

Modules in Tracks 4–7 import this `broadcast()` function. They don't manage WS connections themselves.

### Business logic — client-side subscription manager

```javascript
// Pseudocode
const ws = new WebSocket(`wss://app.sy-homes.co.uk/ws?token=${jwt}`);

ws.onopen = () => {
  // Subscribe to channels relevant to this user/page
  send({ type: "subscribe", channels: ["project:abc-123", "user:my-id"] });
  // Heartbeat every 30s
  setInterval(() => send({ type: "ping" }), 30000);
};

ws.onmessage = (msg) => {
  const event = JSON.parse(msg.data);
  // Track last seen sequence per channel
  lastSeen[event.channel] = event.sequence;
  // Dispatch to relevant React reducer (chat, activity, programme, etc.)
  dispatch(event);
};

ws.onclose = () => {
  // Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)
  setTimeout(reconnect, currentBackoff());
};

function reconnect() {
  // On reconnect, request replay of missed events
  send({ type: "replay", channels: lastSeen });
  // Server returns events with sequence > lastSeen for each channel
}
```

### Business logic — auth handshake

WebSocket upgrade includes JWT token via query string or first message. Server validates JWT, derives user_id, then validates subscription requests against user's permissions:
- User can subscribe to `user:{own_id}` always.
- User can subscribe to `project:{id}` only if they're on `project_team_members` for that project.
- User can subscribe to `role:site_managers` only if they have role=site_manager.
- Subscribe attempts to forbidden channels: WS message returns `{ "type": "error", "code": "forbidden" }`; subscription not created.

### Business logic — ordering and delivery guarantees

- **In-order per channel:** sequence_number is monotonic per channel. Client uses this for ordering, ignores out-of-order arrivals (though TCP usually ensures order anyway).
- **At-least-once delivery:** events persist before push. Client handles idempotency by tracking sequence numbers — duplicate events with same sequence dropped.
- **No cross-channel ordering guarantee:** events on different channels may arrive interleaved, but each channel's sequence is preserved.

### Performance budget

- WebSocket connection establishment: <500ms p95.
- Broadcast latency (server publish → client receive): <200ms p95 within UK region.
- Concurrent connections supported: 100 (well above SY Homes's expected concurrent peak of ~25).
- Heartbeat overhead: <1KB / 30s per connection.

### UI — real-time status surface

A subtle connection status indicator in the app shell (top-right):
- Green dot: connected.
- Yellow dot: reconnecting.
- Red dot: disconnected (with retry button).
- Tooltip shows last successful sync time.

For development / debugging, a `/admin/realtime` page shows:
- Active channel count, active subscriber count.
- Recent events (last 50) as a debug feed.
- Stale subscription cleanup metrics.

### Permissions

- `realtime.subscribe.project` — project_team_members of that project, plus director, super_admin.
- `realtime.subscribe.user` — only the user themselves.
- `realtime.subscribe.role` — anyone with that role.
- `realtime.subscribe.entity` — director, finance, super_admin.
- `realtime.broadcast.system` — super_admin only.
- `realtime.admin` — super_admin (debug feed access).

### Acceptance criteria

- [ ] WebSocket connection establishes with JWT auth
- [ ] Forbidden subscription attempts rejected with explicit error
- [ ] Broadcasts received by all connected subscribers within p95 200ms
- [ ] Sequence numbers monotonic per channel
- [ ] Reconnect-with-replay returns missed events correctly
- [ ] Heartbeat / stale subscription cleanup runs and removes dead sessions
- [ ] Generic `broadcast()` API callable from any module
- [ ] Channel auto-create on first publish
- [ ] Event persistence respects TTL (24h default)
- [ ] Connection survives Emergent platform restart with auto-reconnect
- [ ] Load test: 100 concurrent connections sustained for 30 minutes without leak
- [ ] No memory leaks on long-lived connections (validated by 24h soak test)
- [ ] Audit log records subscription / broadcast counts (aggregate, not per-event)

### Out of scope

- Push notifications to mobile devices when WS not connected — handled by per-module notification system already built in 1.7.
- Federated WebSocket across multiple regions — single-region single-tenant.
- Voice / video — not in scope for this platform.
- WebSocket-to-WebSocket relay between users — server is always intermediary.

---

## Prompt 3.2 — Offline-First Sync Infrastructure

**Dependencies:** 3.1
**Tables in this prompt:** `offline_outbox`, `sync_conflicts`
**Estimated hours:** 12h
**Status:** NEW. Generic offline-write framework. Site-ops modules (4.1, 4.2, 4.5, 4.7) plug into it.

### Conflict resolution policy — locked

**Last-write-wins, with overwrite toast for the loser.**

Reasoning:
- Site-team offline writes are non-financial: daily logs, clock events, QA checklist completions, task completions. None of these have multi-user merge semantics that need careful resolution.
- Financial creation (actuals, valuations, payment notices) happens with connectivity in office or via portal; not offline.
- Two-user simultaneous-edit conflicts on the same record are rare in this domain (one labourer doesn't usually fill in another's clock event). Where they do happen (e.g. two site managers updating same daily log), the second writer's data wins, but both see a toast: "Your earlier entry was overwritten by [user]. View original?"

This avoids a complicated merge UI for low-collision data. Hard cases — daily log editing collision — are visible (toast) and recoverable (`sync_conflicts` table holds the loser's version for 30 days).

### Build `offline_outbox`

Server-side audit / debugging tool. The actual outbox lives in IndexedDB on the client; this table records sync events on the server side.

```
offline_outbox
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
user_id                         uuid NOT NULL FK→users.id
device_id                       varchar(100) NOT NULL    -- client-generated, persistent per device
client_idempotency_key          varchar(100) NOT NULL    -- per-write unique key from client
target_resource                 varchar(100) NOT NULL    -- e.g. "daily_logs", "clock_events"
target_resource_id              uuid                     -- if updating existing
operation                       enum NOT NULL ('CREATE','UPDATE','DELETE')
payload                         jsonb NOT NULL           -- the write payload
client_created_at               timestamp NOT NULL       -- when written offline on client
client_synced_at                timestamp NOT NULL       -- when sent to server
server_received_at              timestamp NOT NULL DEFAULT now()
server_applied_at               timestamp
sync_status                     enum NOT NULL DEFAULT 'Received'
                                  ('Received','Applied','Failed','Conflicted')
error_message                   text
result_resource_id              uuid    -- the actual resource id created/updated
sequence_on_device              bigint NOT NULL    -- client-side sequence for ordering replay

Indexes:
- UNIQUE (device_id, client_idempotency_key)
- INDEX (user_id, server_received_at DESC)
- INDEX (sync_status) WHERE sync_status IN ('Received','Failed')
- INDEX (target_resource, target_resource_id)
```

UNIQUE on (device_id, client_idempotency_key) makes the sync idempotent — replay of an outbox entry returns the same result, doesn't create duplicates.

### Build `sync_conflicts`

Records of last-write-wins overwrites. Surfaces in the toast and is queryable in audit.

```
sync_conflicts
─────────────────────────────────────────────
id                              uuid PK
target_resource                 varchar(100) NOT NULL
target_resource_id              uuid NOT NULL
loser_outbox_id                 uuid NOT NULL FK→offline_outbox.id
loser_user_id                   uuid NOT NULL FK→users.id
loser_payload                   jsonb NOT NULL    -- the version that was overwritten
winner_user_id                  uuid NOT NULL FK→users.id
winner_applied_at               timestamp NOT NULL
detected_at                     timestamp NOT NULL DEFAULT now()
loser_notified_at               timestamp
loser_acknowledged_at           timestamp
expires_at                      timestamp NOT NULL    -- 30 days; cleanup job

Indexes:
- INDEX (loser_user_id, loser_acknowledged_at)
- INDEX (target_resource, target_resource_id)
- INDEX (expires_at)
```

### Client-side outbox (IndexedDB)

Schema mirrors `offline_outbox` plus client state. Client API:

```javascript
// Pseudocode — outbox API in client SDK
outbox.write({
  resource: "daily_logs",
  operation: "CREATE",
  payload: { project_id, date, weather, notes },
  // Returns immediately — write is queued
}); 

// Reading: combines server data + outbox pending writes for instant UI feedback.
outbox.list("daily_logs", { project_id }) 
// Returns: [...server-fetched logs, ...pending-create logs from outbox]

// Sync: runs when online
outbox.sync() 
// Posts each entry to server with idempotency key.
// On 200: marks entry as synced, removes from outbox.
// On 4xx: marks failed with error, surfaces in UI.
// On 5xx: retries with backoff.
```

Sync triggers:
- App startup if online.
- Network reconnection (browser `online` event).
- Manual "sync now" button.
- Periodic (every 60s when app open).

### Business logic — server-side sync handler

```python
# Pseudocode
def receive_sync_batch(user_id, device_id, entries):
    results = []
    for entry in entries:
        # Idempotency check
        existing = offline_outbox where device_id = X and client_idempotency_key = Y
        if existing and existing.sync_status = 'Applied':
            results.append({ key: Y, status: 'AlreadyApplied', resource_id: existing.result_resource_id })
            continue
        
        # Persist outbox row
        outbox_id = insert_offline_outbox(entry)
        
        # Apply to target resource
        try:
            if entry.operation == 'CREATE':
                resource_id = create_resource(entry.target_resource, entry.payload)
            elif entry.operation == 'UPDATE':
                # Last-write-wins detection
                current = read_resource(entry.target_resource, entry.target_resource_id)
                if current.updated_at > entry.client_created_at:
                    # Conflict: someone else updated in the meantime
                    loser_payload_pre_overwrite = current_state
                    update_resource(entry.target_resource, entry.target_resource_id, entry.payload)
                    insert_sync_conflict(
                        target_resource=entry.target_resource,
                        target_resource_id=entry.target_resource_id,
                        loser_user_id=user_id,
                        loser_outbox_id=outbox_id,
                        loser_payload=loser_payload_pre_overwrite,
                        winner_user_id=user_id,  # the offline user IS the winner here, replacing
                        winner_applied_at=now()
                    )
                    # Wait — actually:
                    # If client write was earlier (client_created_at < server.updated_at):
                    #   Server's later write wins; client's is the loser.
                    # Reverse the policy: server keeps current state, client gets sync_conflict notification.
                else:
                    update_resource(entry.target_resource, entry.target_resource_id, entry.payload)
                resource_id = entry.target_resource_id
            elif entry.operation == 'DELETE':
                soft_delete(entry.target_resource, entry.target_resource_id)
                resource_id = entry.target_resource_id
            
            update_outbox(outbox_id, sync_status='Applied', server_applied_at=now(), result_resource_id=resource_id)
            results.append({ key: Y, status: 'Applied', resource_id })
        except ValidationError as e:
            update_outbox(outbox_id, sync_status='Failed', error_message=str(e))
            results.append({ key: Y, status: 'Failed', error: str(e) })
    
    return results
```

The server is the authoritative arbiter. The client's outbox payload contains `client_created_at` so the server can compare timestamps.

**Last-write-wins direction clarification:**
- If client's offline write timestamp < server's current `updated_at`: client write is the loser. Server keeps current state. Client gets `sync_conflict` notification — toast: "Your earlier offline edit to [resource] was overwritten by [user]'s later edit. View your version?"
- If client's offline write timestamp >= server's current `updated_at`: client write wins. Server applies. Previous state recorded as loser if it differs.

### Business logic — module integration pattern

A module wanting offline support adopts this pattern:

```javascript
// Module declares its offline schema
registerOfflineResource({
  resource: 'daily_logs',
  fields: { project_id, date, weather, work_completed_text, photo_ids },
  validates: { ...client-side validation },
});

// In React component:
const { data, isOffline, pendingCount } = useOfflineList('daily_logs', { project_id });
const { create, update, remove } = useOfflineMutations('daily_logs');

// UI shows "[N] entries pending sync" badge if pendingCount > 0
// Pending entries display with a subtle "syncing..." indicator
```

Modules adopting offline in Phase 2: 4.1 (daily logs), 4.2 (clock events), 4.5 (QA checklists), 4.7 (labourer task completions). Programme task updates (3.5) also adopt for site-driven updates.

### UI — sync status surface

App shell shows a sync indicator next to the realtime indicator (3.1):
- Green: synced, no pending writes.
- Yellow: pending writes ([N] entries).
- Red: sync failed (with retry button).
- Tap: opens sync detail panel showing pending and failed writes, manual retry per entry.

Conflict toast pattern:
- Triangle icon, neutral colour.
- "Your edit was overwritten. View?"
- Tap → modal showing your version vs current version, with "Keep mine" / "Discard mine" actions.
- Keeping yours triggers a new write (which becomes the new winner).
- Discarding marks `sync_conflicts.loser_acknowledged_at` and dismisses.

### Permissions

- `offline_outbox.view_own` — every user can see their own outbox via API.
- `offline_outbox.admin` — super_admin only (cross-user audit).
- `sync_conflicts.view_own` — every user.
- `sync_conflicts.admin` — super_admin (audit).

### Acceptance criteria

- [ ] Client outbox persists writes to IndexedDB when offline
- [ ] Sync runs on reconnect, posts batch to server with idempotency keys
- [ ] Server applies writes idempotently — duplicate sync of same key returns same result
- [ ] Last-write-wins resolution applied correctly per timestamp comparison
- [ ] Conflict detection records `sync_conflicts` row with loser payload
- [ ] Conflict toast shows on client when own write was overwritten
- [ ] Conflict toast modal shows both versions; "Keep mine" creates fresh write
- [ ] Sync indicator in app shell shows pending count accurately
- [ ] Manual sync trigger works
- [ ] Failed writes (validation errors) surfaced to user with actionable message
- [ ] 30-day TTL on `sync_conflicts` table; cleanup job runs daily
- [ ] Module registration pattern works for daily_logs (smoke test in 3.2; full integration in 4.1)
- [ ] Audit log records sync batches with counts (not individual writes — those are in outbox)
- [ ] Performance: outbox sync of 50 pending entries completes in <5s on 4G

### Out of scope

- Per-field merge UI (CRDTs / OT) — explicit non-goal; last-write-wins.
- Offline-capable financial writes — financial creation requires connectivity.
- Cross-device outbox (a write on phone visible on tablet before sync) — outbox is per-device.
- Outbox encryption at rest in IndexedDB — relies on browser's existing security; if the device is compromised, the user's session is compromised anyway.

---

## Prompt 3.3 — Programme Templates and Calendars

**Dependencies:** 1.5
**Tables in this prompt:** `programme_templates`, `programme_template_tasks`, `programme_calendars`, `programme_calendar_exceptions`
**Estimated hours:** 8h
**Status:** Carried forward from Phase 1 unchanged.

Reference Phase 1 brief Prompt 3.1 in full. Six seeded programme templates (Pure Dev, D&B Small/Medium/Large, D&B Contract, Main Contract). Calendars with working days, bank holidays, standard shutdowns. Project picks a calendar; CPM in 3.4 uses calendar dates.

### Phase 2 deltas
- **Calendars use JSONB for working_days, bank_holidays, standard_shutdowns** — confirmed retained from Phase 1 audit fix (was a remediation in CHANGELOG).
- No other deltas.

### Out of scope (unchanged from Phase 1)
- Multi-calendar per project (different calendars for groundworks vs MEP) — Phase 5 enhancement.
- Resource calendars per supplier — Phase 5.

---

## Prompt 3.4 — Programmes, Tasks, CPM Engine

**Dependencies:** 3.3
**Tables in this prompt:** `programmes`, `programme_tasks`, `programme_task_dependencies`, `programme_task_constraints`
**Estimated hours:** 16h
**Status:** Carried forward from Phase 1 with real-time hooks added.

Reference Phase 1 brief Prompt 3.2 in full. Programme records, tasks with predecessors (FS / SS / FF / SF + lag), CPM engine (forward + backward pass, total float, free float, critical path identification), task constraints (start no earlier than, must finish by). Gantt UI with dependencies visible.

### Phase 2 deltas
- **Real-time hook integration:** programme task updates broadcast via 3.1 to channel `project:{project_id}` with event type `programme.task_updated`. Other users' Gantt views update without refresh.
- **Real-time hook for CPM recompute:** when CPM recompute triggers (after a task update), broadcast `programme.cpm_recomputed` so dependent UI (critical path highlighting) refreshes.
- **Drag-and-drop on Gantt:** locked in scope per Chat 5 "state of the art programme" framing — Gantt UI supports drag-to-reschedule, drag-to-link-dependency, with optimistic UI and broadcast on confirm.
- **Resource levelling:** in scope per Chat 5 — resources defined on tasks, calendar-aware allocation, simple level-loading algorithm (no complex priority rules — those stay deferred). Implemented at the simple end: warn when resource over-allocated; "auto-level" button shifts non-critical tasks within float to ease conflicts.

### Out of scope (unchanged from Phase 1, plus stretch deferrals from Chat 5)
- Weather-aware shifts — Future Tasks Phase 3.
- Predictive completion based on velocity — Future Tasks Phase 3.
- Cross-project resource view — Future Tasks Phase 3.
- Monte Carlo schedule simulation — Future Tasks Phase 5.

---

## Prompt 3.5 — Task Updates, Baselines, Alerts, Weekly Reports

**Dependencies:** 3.1, 3.2, 3.4
**Tables in this prompt:** `programme_task_updates`, `programme_baselines`, `programme_baseline_tasks`, `programme_alerts`, `programme_alert_rules`
**Estimated hours:** 12h
**Status:** Carried forward from Phase 1, with offline support added.

Reference Phase 1 brief Prompt 3.3 in full. Site-driven task updates (mobile, photo, GPS), baselines (Original, Revised, Re-Baselined snapshots), variance vs baseline, weekly programme report PDF, alert rules (e.g. "task slipping > 5 days notifies CM"), scheduled report job.

### Phase 2 deltas
- **Offline support added:** task updates can be submitted offline on site (uses 3.2). Updates queue in client outbox, sync when back in signal.
- **Real-time broadcast:** task updates broadcast via 3.1 to project channel — `programme.task_updated` event.
- **Alert deduplication / acknowledge / snooze workflow** confirmed retained from Phase 1.
- **Weekly report scheduling unchanged from Phase 1** — runs Fridays 17:00 local time, generates PDF, emails project team.

### Out of scope (unchanged from Phase 1)
- Automated narrative generation (AI summary) — Future Tasks.
- Programme variance prediction — Future Tasks Phase 3.

---

# Locked decisions from this session (for the open-questions log)

Updating skeleton's "Open questions for sessions 3-4" section:

1. **Real-time choice: WebSockets** — locked. Reasoning in 3.1.
2. **Offline conflict resolution UX: last-write-wins with overwrite toast** — locked. Reasoning in 3.2.
3. **Chat replace WhatsApp or coexist** — still open; this is operational, addressed in Track 4 detail (session 4).
4. **Public API auth model** — still open; addressed in Track 7 detail (session 4).
5. **Designer engagement timing** — still open; addressed in Track 8 detail (session 4).
6. **Cutover plan for Buildertrend retirement** — still open; addressed in Track 8 detail (session 4) with reference to a separate cutover document.
7. **Whether Prompt 4.6 (snag + activity) really should split** — still open; resolved in session 4.
8. **Whether Prompt 2.8 should split** — **resolved: yes, split into 2.8a and 2.8b**. Track 2 is now 10 prompts. Total brief 44 prompts.

---

# Updates required to skeleton document

When merging this session's output into `SY_Homes_Emergent_Brief_Phase2.md`:

1. Replace lines ~166-251 (Track 2 + Track 3 sections) with the content of this document, sections starting at "# Track 2 — Commercial Engine + Subcontractors" through end of Track 3.
2. Update Track Summary table (skeleton ~line 56-67):
   - Track 2: 9 → **10** prompts (was: ~30 tables added; now ~30 tables added across 10 prompts).
   - Total prompts: 43 → **44**.
3. Update Hours estimate table (skeleton ~line 507-518):
   - Add Prompt 2.8a (10h) and 2.8b (10h); remove single 2.8 (16h).
   - T2 total: 108h → **112h** (108 + 4 net for the split — extra 4h is overhead of having two prompts with their own setup).
   - Track totals adjusted: T2 112h, total prompt work 416h → **420h**, grand total 568h → **572h**.
4. Update cumulative milestone calendar (skeleton ~lines 543-555):
   - End Track 2 milestone: 108 → **112** cumulative hours.
   - Subsequent rows shift by +4 each.
5. Update Cross-reference matrix Buildertrend section (skeleton ~lines 76-100):
   - Row "Change Orders | Prompts 2.6, 2.8" → "Change Orders | Prompts 2.6, 2.8a"
   - Add row implicitly: payment notices captured under 2.8b.
6. Update Cross-reference matrix Future Tasks absorbed (skeleton ~lines 117-128):
   - "Subcontracts and variations | Prompt 2.8" → "Subcontracts and variations | Prompt 2.8a"
   - Add row: "Subcontract valuations and payment notices | Prompt 2.8b"
7. Update Open Questions section (skeleton ~lines 645-665):
   - Mark questions 1, 2, 8 as resolved with cross-reference to this session.
   - Note T2 prompt count update (43 → 44).

---

_Session 3 of v2 brief re-spec complete. Tracks 4, 5, 6, 7, 8 detail follows in session 4 (Chat 8). Closing summary for Chat 7 to follow in standard format._
