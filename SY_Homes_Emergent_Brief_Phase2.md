<!-- ================================================================
     SY HOMES PLATFORM — PHASE 2 EMERGENT BRIEF (SKELETON)
     ================================================================
     Version: 2.0-skeleton
     Date: April 2026
     Status: Skeleton only — prompt-level detail added in sessions 3–4
     Supersedes (from Track 2 onwards): SY_Homes_Emergent_Brief_Phase1.md
     Companion: SY_Homes_Data_Model.xlsx (v1 — v2 model to follow)
     ================================================================ -->

# SY Homes Platform — Phase 2 Emergent Brief

**Version:** 2.0-skeleton
**Date:** April 2026
**Scope:** Full company OS — supersedes the original Tracks 2–5 from Phase 1 brief

This is the skeleton. It locks the track structure, the prompt list, dependencies, hours, data model delta, and the cross-reference matrix that proves nothing has been silently dropped. Per-prompt detail (table schemas, business logic, UI, acceptance criteria, permissions, out-of-scope blocks) lands in sessions 3–4, one track at a time.

---

## What changed since Phase 1 brief

The Phase 1 brief specified a 25-prompt build of a property-development financial-control platform. After Foundation completed (Prompts 1.1–1.7, Track 1 of Phase 1) we expanded scope to a full company operating system covering daily logs, clocking, chat, RFIs, QA with mandatory photos, snagging, supplier/subcontractor/labourer portals, sales, post-completion, real-time updates, and offline-capable site operations. The original Track 5 (Xero) is also re-shaped: Xero becomes an optional connector rather than a required integration, with CSV import/export as a first-class fallback so the platform is fully usable without Xero.

The framing decisions from Chat 5 are carried into this skeleton unchanged:

- 7 build tracks plus 1 polish track
- Track 2: Commercial Engine + Subcontractors, Xero-independent
- Track 3: Real-time + offline infrastructure + state-of-the-art Programme (core CPM in scope; weather / predictive / cross-project programme features deferred)
- Track 4: Site Ops — daily logs, clocking, chat, RFIs (formal), QA, unified snagging
- Track 5: Documents & Compliance
- Track 6: Xero connector (optional bidirectional) + CSV import/export
- Track 7: Sales + Post-Completion + Reporting + read-only public-data API
- Track 8: Portal hardening + mobile pass + designer
- Portals embedded per module, not standalone tracks
- Audit checkpoints: end T2, end T3, mid T4 (with team), pre-launch

Items absorbed from Future Tasks: subcontractor database & CIS, subcontracts & variations, plot management, buyer pipeline, post-completion. Items confirmed deferred: tender, customer aftercare, historical actuals importer, programme stretch features.

---

## Honest framing (read before sign-off)

Three things to know before this becomes a working brief:

**1. The prompt count will probably grow during sessions 3–4.** Target was ~37–43 prompts, this skeleton lands at 43. Once we draft acceptance criteria and table schemas, two or three prompts marked below as "candidate split" will probably split, taking us to 44–46. That's expected, not a failure of this session. The track structure is the thing that matters and is stable.

**2. Hours per prompt will average higher than Foundation pace suggests.** Foundation prompts averaged ~6h of Rhys's time end-to-end. The remaining 36 prompts are heavier — Track 2 has commercial calculation, Track 3.1/3.2 is genuine infrastructure work, Track 6 is third-party integration with the most subtle bugs. Honest average across remaining prompts is 10–12h. The 10–14 month timeline holds, but the upper end is more likely.

**3. The data model grows substantially.** Phase 1 ended at 77 tables / 1,288 fields. Phase 2 adds approximately 50 tables across site ops, sales, real-time infra, subcontractors, post-completion. Estimated end state: 120–130 tables / 1,800–2,200 fields. The data model XLSX needs a v2 — flagged as a separate deliverable after session 4.

---

## Track summary

| Track | Name | Prompts | Tables added (est.) | Status |
|---|---|---:|---:|---|
| 1 | Foundation | 7 | 0 (built) | DONE |
| 2 | Commercial Engine + Subcontractors | 9 | ~30 | To build |
| 3 | Real-time + Offline + Programme | 5 | ~15 | To build |
| 4 | Site Ops | 7 | ~25 | To build |
| 5 | Documents & Compliance | 3 | ~10 | To build |
| 6 | Xero + CSV Import/Export | 5 | ~17 | To build |
| 7 | Sales + Post-Completion + Reporting + Public API | 4 | ~12 | To build |
| 8 | Polish | 3 | 0 | To build |
| | **Total** | **43** | **~109 + Track 1's 23 = ~132 tables** | |

Note: ~30 of the new tables in T2 reflect the Phase 1 commercial-engine tables we kept (appraisals, budgets, cash flow — 22 tables) plus ~8 new for subcontractor/subcontract/variation/portal. Real net new beyond Phase 1 spec is ~50 tables.

---

# Cross-reference matrix

This matrix exists so nothing from prior thinking gets silently dropped. Every Buildertrend module, every Future Tasks item, every scope-expansion item, and every Project-Instructions hard constraint is mapped to either a prompt or an explicit deferral.

## A. Buildertrend Company Settings modules (14)

| Buildertrend module | Mapped to | Notes |
|---|---|---|
| Schedule | Prompts 3.3–3.5 | Programmes / Gantt / CPM |
| Daily Logs | Prompt 4.1 | Site diary, weather, attendance, photos |
| Time Clock | Prompt 4.2 | Clocking + timesheets |
| Bills / POs / Budget | Prompts 2.4–2.5 | Budget + Actuals + Commitments |
| Invoices | Prompts 2.5, 6.4 | Local + Xero mirror |
| Estimates / Bids | Prompts 2.2–2.3 | Appraisals (different shape, same purpose) |
| Change Orders | Prompts 2.6, 2.8 | Budget change control + variations |
| Files | Prompts 5.1–5.2 | Versioned document store with approvals |
| Subs / Vendors | Prompt 2.7 | Supplier + subcontractor records |
| Client contacts | Prompt 7.2 | Buyer pipeline |
| Accounting | Prompts 6.1–6.5 | Xero + CSV |
| Taxes | Prompt 2.5 | UK VAT/CIS per-line |
| Warranty | Prompt 7.3 | Folded into post-completion (DLP) |
| Sales / Lead Generation | OUT OF SCOPE | Per Project Instructions — not a CRM |
| Surveys | OUT OF SCOPE | Use Typeform |
| RFIs | Prompt 4.4 | Formal RFI workflow (not folded into chat) |
| Client Updates | Prompt 7.2 | Folded into buyer pipeline notifications |
| Gusto / payroll | OUT OF SCOPE | |
| HubSpot / Salesforce / Pipedrive | OUT OF SCOPE | CRM stack |

(15 listed because Buildertrend itself groups some sub-modules; total mapped = every BT capability that's not explicitly out of scope.)

## B. Scope-expansion items from SY_Hub_Scope_Expansion_Memo.md (10)

| # | Item | Mapped to |
|---|---|---|
| 1 | Daily logs | Prompt 4.1 |
| 2 | Clocking in/out | Prompt 4.2 |
| 3 | Team chat | Prompt 4.3 |
| 4 | QA checklists with photos | Prompt 4.5 |
| 5 | Supplier and contractor portals | Prompts 2.9 (commercial portal), 4.7 (labourer portal) |
| 6 | Labourer portal | Prompt 4.7 |
| 7 | Real-time features | Prompt 3.1 (infra) — applied across T3–T7 |
| 8 | Offline capability | Prompt 3.2 (infra) — applied across T4 |
| 9 | Activity streams | Prompt 4.6 (folded with snagging in skeleton — see notes) |
| 10 | Sales integration | Prompts 7.1–7.2 |

## C. Future Tasks status

**Absorbed into Phase 2 (no longer deferred):**

| Future Task | Now in |
|---|---|
| Subcontractor database + CIS | Prompt 2.7 |
| Subcontracts and variations | Prompt 2.8 |
| Plot management | Prompt 7.1 |
| Buyer pipeline | Prompt 7.2 |
| Post-completion (retentions, DLP, final accounts) | Prompt 7.3 |

**Still deferred (will remain in updated Future Tasks):**

| Future Task | Reason for deferral |
|---|---|
| Deal pipeline | Phase 3 — not bottleneck |
| Planning management | Phase 3 — handled informally for now |
| Tender module | Confirmed deferred per Chat 5 |
| Customer handover & aftercare | Confirmed deferred per Chat 5 — Phase 3 |
| Historical actuals CSV importer | Confirmed deferred per Chat 5; CSV framework in 6.1 enables later |
| Programme stretch (weather, predictive, cross-project) | Confirmed deferred per Chat 5 |
| Buildertrend integration | Phase 4 — only if SY Homes keeps using BT for estimating |
| Bank feed integration | Phase 4 — Xero gives sufficient coverage initially |
| Electronic signatures | Phase 4 |
| ISO 19650 / CDE | Phase 4 |
| HMRC CIS direct submission | Phase 4 — Xero CIS module covers Phase 2 |
| MTD for Corporation Tax | When mandatory |
| Intercompany billing automation | Phase 4 |
| Phase 5 enhancements (8 items) | All Phase 5 |
| Phase 6 security hardening (5 items) | Phase 6 — pen test annually post-launch |
| Phase 7 reporting (5 items) | Some basic reporting in 7.4; full BI Phase 7 |
| Workflow enhancements (most) | Various phases |

## D. Project Instructions hard constraints (8) — coverage check

| Constraint | Where addressed |
|---|---|
| 1. Platform must be fast | Prompt 8.3 (perf/launch readiness) + per-prompt acceptance criteria |
| 2. Xero integration must work properly | Prompts 6.2–6.5 |
| 3. Mobile-first for site users | Prompt 8.2 (mobile pass) + every Track 4 prompt mobile-first by default |
| 4. Offline-capable for site operations | Prompt 3.2 (infra) + applied in 4.1, 4.2, 4.5, 4.7 |
| 5. Must never lose financial data | Continued from Phase 1 (audit log, append-only); reinforced in 2.5 (actuals) and 6.4 (Xero mirrors) |
| 6. Multi-entity preserved | Continued from Phase 1; explicit checks per prompt |
| 7. Real-time where it matters | Prompt 3.1 (infra) + applied in 4.3 (chat), 4.6 (activity), 7.4 (dashboards) |
| 8. RBAC enforced server-side | Continued from Phase 1; per-prompt permission lists |

---

# Track 2 — Commercial Engine + Subcontractors

**Goal:** Build the appraisal-to-budget-to-actuals-to-payment-notice pipeline, fully Xero-independent (Xero connector layered on later in Track 6). Add native subcontractor records, formal subcontracts, variations, and an embedded supplier/subcontractor portal so external commercial parties can confirm POs, submit valuations, raise variations.
**Duration:** ~12 weeks at 25 hrs/week
**Prompts:** 9
**Tables added:** ~30 (22 from kept Phase 1 commercial engine + ~8 new)

## Prompt 2.1 — Reference Data: SDLT Bands, Appraisal Defaults
**Dependencies:** 1.1, 1.2, 1.4
**Hours estimate:** 6h
Carried forward from Phase 1 unchanged. Two reference tables: `sdlt_rate_bands` (England, current rates effective April 2025; Scotland LBTT and Wales LTT remain Future Tasks) and `appraisal_default_settings` (build cost per sq ft defaults, finance assumptions, hurdle rate). Read-only seed data with admin-only edit. SDLT calculator used by 2.2 — must be built first.

## Prompt 2.2 — Appraisals Core
**Dependencies:** 1.1, 1.2, 1.4, 1.5, 1.6, 2.1
**Hours estimate:** 16h
Carried forward from Phase 1, unchanged in shape. Tables for appraisal header, units, cost lines, finance model. Engines: SDLT calculator (uses 2.1 bands), RLV solver (residual land value via iterative search), finance model (interest cost over construction period, peak debt). UI: appraisal builder with three views (units, costs, finance), summary tile (GDV, total cost, profit, margin %, RLV), revision-aware. Heaviest single prompt in Track 2.

## Prompt 2.3 — Appraisal Governance: Revisions, Scenarios, Decision Log
**Dependencies:** 2.2
**Hours estimate:** 10h
Carried forward from Phase 1 unchanged. Revision history (immutable snapshots), scenario branching (e.g. "what if build cost +10%"), decision log capturing approvals/rejections at director level, locked vs draft states. Underpins the audit story for any appraisal that becomes a budget.

## Prompt 2.4 — Budgets Core
**Dependencies:** 1.6, 2.3
**Hours estimate:** 12h
Carried forward from Phase 1 unchanged. Budget header per project + entity, budget lines keyed to cost codes, opening budget locked from approved appraisal, separate "live budget" with change control wired in 2.6. Forecast final cost (FFC) derived from budget + actuals + commitments + change orders.

## Prompt 2.5 — Actuals and Commitments (Xero-independent)
**Dependencies:** 2.4
**Hours estimate:** 14h
**Modified from Phase 1.** Actuals (bills, invoices, payments, credit notes) and commitments (purchase orders, subcontract orders) created natively in the platform — Xero is not a prerequisite. Each actual carries entity, cost code, VAT line, CIS treatment, and source enum (`Manual` / `Xero` / `CSV_Import`). Posting an actual updates budget line `actuals_to_date`. PO confirmation flow with status machine (`Draft` → `Issued` → `Confirmed` → `Goods_Received` → `Closed`). Append-only — voiding leaves a void record, never deletes.

## Prompt 2.6 — Budget Change Control and Forecasts
**Dependencies:** 2.4, 2.5
**Hours estimate:** 10h
Carried forward from Phase 1 unchanged. Budget change requests (BCRs) with approval workflow, transfer between cost lines, contingency drawdown, automatic FFC recalc, change log per budget. Variation impact on budget posts via this surface (variations approved in 2.8 generate BCRs).

## Prompt 2.7 — Suppliers and Subcontractors (NEW — absorbed from Future Tasks)
**Dependencies:** 1.1, 1.2, 1.4, 1.5
**Hours estimate:** 12h
Native records for both supplier types: suppliers (materials/plant/services) and subcontractors (labour-and-plant or labour-only with CIS implications). Tables for `suppliers`, `subcontractors`, `subcontractor_cis_verifications` (HMRC verification number history, gross/net status, expiry), `supplier_documents` (insurance, accreditations with expiry tracking). Ratings per project. Replaces supplier records held in spreadsheets and Buildertrend's Subs/Vendors module.

## Prompt 2.8 — Subcontracts, Variations, Valuations, Payment Notices (NEW — absorbed from Future Tasks)
**Dependencies:** 2.5, 2.7
**Hours estimate:** 16h
Formal subcontract records linking to a commitment. Variation instruction workflow (raise → cost → approve → issue) with the variation either covered within contract sum or generating a BCR via 2.6. Subcontract valuations (typically monthly): gross applied, less previous, less retention, less CIS, net payable, payment notice generated. Retention release schedule (50% at PC, 50% at DLP end — links forward to 7.3). Probably the most complex prompt in T2. **Candidate split** if sessions 3–4 detail shows it.

## Prompt 2.9 — Supplier & Subcontractor Portal (NEW)
**Dependencies:** 1.2, 1.3, 2.5, 2.7, 2.8
**Hours estimate:** 12h
Embedded portal — separate URL, scoped role, minimal UI. Supplier features: confirm POs, schedule deliveries, upload delivery notes, exchange documents. Subcontractor features: submit valuations, raise variations, submit QA evidence (the QA submission piece previews into Track 4.5), upload required documents. Mobile-friendly — much portal access happens from a phone in a yard or on site. Builds on the existing 1.2 RBAC scoping.

---

# Track 3 — Real-time + Offline + Programme

**Goal:** Lay the real-time and offline infrastructure that all Site Ops (Track 4) depends on, and deliver the programme/CPM module that uses it. Real-time first so chat, activity streams, and live dashboards land naturally on top.
**Duration:** ~9 weeks
**Prompts:** 5
**Tables added:** ~15

## Prompt 3.1 — Real-time Infrastructure (NEW)
**Dependencies:** 1.2, 1.4
**Hours estimate:** 14h
WebSocket (or SSE if simpler) connection management, channel system (project-scoped, user-scoped, role-scoped), presence tracking (who's online), server-side broadcast hooks that any module can publish into, client-side subscription manager. Tables: `realtime_channels`, `realtime_subscriptions`, `realtime_events` (audit-style log of broadcasts). Auth handshake uses existing JWT. Reconnect logic, backoff, message ordering guarantees. This is real infrastructure work — most failure modes only show under load. **Candidate split** into infra-build + infra-test if sessions 3–4 detail explodes it.

## Prompt 3.2 — Offline-First Sync Infrastructure (NEW)
**Dependencies:** 3.1
**Hours estimate:** 12h
Outbox pattern on the client (IndexedDB), sync queue with retry, conflict resolution policy (last-write-wins for non-financial; explicit conflict UI for financial — but financial isn't usually offline anyway), idempotency keys per write, sync status indicator in the UI. Tables: `offline_outbox` (server-side audit of synced writes), `sync_conflicts` (rare, but logged). Generic — every offline-capable module (4.1, 4.2, 4.5, 4.7) plugs in. Without this, "offline-capable" means "ad-hoc per module" which doesn't work.

## Prompt 3.3 — Programme Templates and Calendars
**Dependencies:** 1.5
**Hours estimate:** 8h
Carried forward from Phase 1 unchanged. Six seeded programme templates (Pure Dev, D&B Small/Medium/Large, D&B Contract, Main Contract). Calendar tables with JSONB working_days / bank_holidays / standard_shutdowns (post-audit fix from Phase 1). Project picks a calendar; CPM in 3.4 uses calendar dates.

## Prompt 3.4 — Programmes, Tasks, CPM Engine
**Dependencies:** 3.3
**Hours estimate:** 16h
Carried forward from Phase 1. Programme records, tasks with predecessors (FS/SS/FF/SF + lag), CPM engine (forward + backward pass, total float, free float, critical path identification), task constraints (start no earlier than, must finish by). Gantt UI with dependencies visible. Real-time hook: programme changes broadcast via 3.1 so other users' Gantt views update without refresh.

## Prompt 3.5 — Task Updates, Baselines, Alerts, Weekly Reports
**Dependencies:** 3.1, 3.2, 3.4
**Hours estimate:** 12h
Carried forward from Phase 1, with offline support added (tasks can be progressed offline on site and sync when back in signal — uses 3.2). Baselines (snapshots), variance vs baseline, weekly programme report PDF, alert rules (e.g. "task slipping > 5 days notifies CM"). Updates broadcast via 3.1.

---

# Track 4 — Site Operations

**Goal:** The on-site experience — what site managers, contractors, and labourers actually do. Mobile-first throughout, offline-capable for the parts that need it, real-time where it matters. This is where the platform replaces WhatsApp, paper diaries, and clipboard QA.
**Duration:** ~14 weeks
**Prompts:** 7
**Tables added:** ~25

## Prompt 4.1 — Daily Logs (NEW)
**Dependencies:** 1.5, 3.1, 3.2
**Hours estimate:** 10h
Site managers create daily entries per project: weather (auto-pulled from a weather API for the project site, editable), attendance (free-text with optional clock-in cross-reference from 4.2), work completed (linked to programme tasks from 3.4), deliveries received, issues, delays, visitors, photos. Searchable, exportable to PDF for monthly reports. Offline-capable. Fast on a phone — designed for end-of-day entry, three minutes max.

## Prompt 4.2 — Clocking In/Out + Timesheets (NEW)
**Dependencies:** 1.2, 1.5, 3.2
**Hours estimate:** 10h
Labourers and contractors clock in at start of shift, out at end. Optional geofence verification (project site polygon). Tables for `clock_events`, `geofences`, `timesheets`, `timesheet_entries`. Timesheet view per user per week, approval by site manager, CSV export for payroll system (no payroll processing — payroll is out of scope per Project Instructions). Offline-capable (clock events queue and sync). Late-clock and missing-clock-out handling.

## Prompt 4.3 — Chat / Messaging (NEW)
**Dependencies:** 3.1
**Hours estimate:** 14h
Real-time messaging built on 3.1. Project-scoped channels, role-scoped channels (e.g. "all site managers"), direct messages, threaded replies, file attachments (links to 5.2 documents for substantial files; inline photos for casual), @mentions tied to notifications, read receipts, search across messages. Mobile push notifications. Replaces WhatsApp groups for project comms — hard problem because WhatsApp is convenient and the bar is high.

## Prompt 4.4 — RFIs (Formal Workflow) (NEW)
**Dependencies:** 1.5, 4.3
**Hours estimate:** 8h
Per Chat 5 framing — RFIs stay as a formal workflow rather than collapsing into chat. Tables for `rfis`, `rfi_responses`, `rfi_attachments`. Status machine (`Open` → `Awaiting_Response` → `Answered` → `Closed`). Response SLA tracking (default 5 working days, configurable per project). Designer or external consultant assigned. Linked back to programme tasks (an RFI on a task may pause it). Chat (4.3) is the conversational layer; RFIs are the formal record.

## Prompt 4.5 — QA Checklists with Mandatory Photos (NEW)
**Dependencies:** 1.5, 1.6, 3.2, 3.4
**Hours estimate:** 12h
QA checklist templates per cost code or per task type. Items can be flagged "photo required" — checklist can't be marked complete without the photo. Workflow: contractor submits, site manager reviews and approves or returns, defects (failures) feed into 4.6 snagging. Tables: `qa_checklist_templates`, `qa_checklists`, `qa_items`, `qa_photos`, `qa_signoffs`. Offline-capable (huge for site use).

## Prompt 4.6 — Snagging + Activity Streams (NEW)
**Dependencies:** 1.5, 4.5
**Hours estimate:** 10h
Unified snagging module per Chat 5 — pre-handover snags (during build) and post-handover defects use the same table with a stage flag. Tables: `snags`, `snag_photos`, `snag_assignments`. Status, severity, assigned-to, photo evidence, sign-off. Activity streams piggyback on the same surface (per-project feed of significant events: documents uploaded, tasks completed, snags raised/closed, bills posted, messages flagged) — table `activity_events` filterable by type. Folded together because both are "what happened" surfaces; **candidate split** if sessions 3–4 detail shows snagging needs more space.

## Prompt 4.7 — Labourer Portal (NEW)
**Dependencies:** 1.2, 4.1, 4.2, 4.5
**Hours estimate:** 8h
Minimal mobile UI for labourers — separate app shell, large tap targets, almost no nesting. Features: clock in/out (4.2), view today's tasks (3.4), mark tasks complete (3.5), end-of-day summary into daily log (4.1), submit QA checklist evidence (4.5), receive safety briefings (read-and-acknowledge). No appraisals, no documents browser, no chat clutter. Forgiving of low tech literacy. Offline-capable.

---

# Track 5 — Documents & Compliance

**Goal:** Versioned document management with approvals and access control, plus the compliance registers (CDM, BSA, Part L/O/Q, Fire Safety, Insurance, Certificates, Contract). Carried forward from Phase 1 Track 4 with mobile and approval polish.
**Duration:** ~5 weeks
**Prompts:** 3
**Tables added:** ~10 (carried forward from Phase 1 Track 4)

## Prompt 5.1 — Document Types and Templates
**Dependencies:** 1.5, 1.6
**Hours estimate:** 8h
Carried forward from Phase 1 unchanged. Document types catalogue (Drawing, Specification, Survey, Insurance Certificate, etc.) with approval-required flag, version control flag, retention period. Document templates seed list per type. Sets up 5.2.

## Prompt 5.2 — Documents, Approvals, Access Log
**Dependencies:** 5.1
**Hours estimate:** 12h
Carried forward from Phase 1 with mobile-friendly upload flows. Versioned document store, approval workflow (single or multi-approver per type), access log per document (who viewed, who downloaded — important for compliance audit), polymorphic links to projects/entities/subcontracts. Soft delete only for documents with audit history.

## Prompt 5.3 — Compliance Registers, Certificates & Permits
**Dependencies:** 5.2
**Hours estimate:** 10h
Carried forward from Phase 1 unchanged. Compliance register types (13 seeded — CDM, BSA, Part L/O/Q, Fire Safety, Warranty, GDPR, Planning Discharge, Building Control, Insurance, Certificates, Contract), per-register entries with due dates, evidence document links, responsible party, notification on approaching expiry. Critical for the BSA / Building Safety Regulator and CDM duties.

---

# Track 6 — Xero + CSV Import/Export

**Goal:** Make Xero an optional connector while ensuring the platform is fully usable without it. CSV import/export covers the case where SY Homes wants to onboard data from elsewhere or work in Xero-disconnected mode. Xero connector itself carried forward from Phase 1 Track 5 with the optional-not-required reframe.
**Duration:** ~10 weeks
**Prompts:** 5
**Tables added:** ~17 (15 from Phase 1 + 2 for CSV framework)

## Prompt 6.1 — CSV Import/Export Framework (NEW)
**Dependencies:** 2.5, 2.7
**Hours estimate:** 12h
Generic schema-driven CSV import framework. Handles actuals (bills/invoices/payments), suppliers, subcontractors, plot data, basic project metadata. Tables: `import_jobs` (status, file, mapping, errors), `import_errors`. Per-import column mapping, validation pass before commit, dry-run preview, partial-success (commit valid rows, error log for invalid). Export side: same shape, every list view gets a "Download CSV" action with the filter applied. Critical for the "platform without Xero" mode and for migrating historical data later (Future Tasks historical actuals importer would build on this framework).

## Prompt 6.2 — Xero Connections (OAuth + Token Management)
**Dependencies:** 1.1, 1.2
**Hours estimate:** 14h
Carried forward from Phase 1 Track 5.1. OAuth 2.0 connection flow per entity, token storage (encrypted refresh tokens), token refresh background job, connection status dashboard, disconnect flow. Three connections (Parent, SPV, ConstructionCo). Webhook subscription setup. The "you must connect Xero" framing relaxes — entities can operate without a Xero connection.

## Prompt 6.3 — Reference Sync: Tracking Categories, COA, Tax Rates, Contacts
**Dependencies:** 6.2
**Hours estimate:** 10h
Carried forward from Phase 1 Track 5.2 unchanged. Sync Xero tracking categories (used for project/cost-code dimension tagging), chart of accounts, tax rates, contacts. Mapping UI to map platform cost codes to Xero accounts and tracking options. Required before financial mirrors in 6.4 because every bill needs the right account/tracking on push.

## Prompt 6.4 — Financial Mirrors: Bills, Invoices, Payments, Credit Notes
**Dependencies:** 6.3, 2.5
**Hours estimate:** 16h
Carried forward from Phase 1 Track 5.3, lightly modified for the optional-Xero frame. Bidirectional mirror: bills/invoices/payments created in platform sync to Xero (push); created in Xero sync into platform (pull via webhooks + delta). Idempotency via external_id. VAT/CIS preserved. Voids handled. The most subtle prompt in T6 — most Xero integration bugs hide here.

## Prompt 6.5 — Sync Queue, Webhooks, Bank Transactions, Manual Journals, Reconciler
**Dependencies:** 6.4
**Hours estimate:** 14h
Combines Phase 1 Tracks 5.4 and 5.5. Sync queue (job-based async sync), webhook receiver, bank transaction sync, manual journal sync, nightly reconciler (orphan detection, amount reconciliation, VAT reconciliation, mapping health metrics), sync events log, dashboard. Scaled-back compared to Phase 1's two-prompt split because the optional-Xero framing means we accept slightly less polish here than Phase 1 envisioned.

---

# Track 7 — Sales + Post-Completion + Reporting + Public API

**Goal:** Plot management and buyer pipeline (so the sales side of the business runs in the platform), post-completion (retentions, DLP, final accounts — was a big pain point per Future Tasks), reporting and dashboards, and a read-only public API surface for an eventual marketing-site integration.
**Duration:** ~8 weeks
**Prompts:** 4
**Tables added:** ~12

## Prompt 7.1 — Plot Management (NEW — absorbed from Future Tasks)
**Dependencies:** 1.5
**Hours estimate:** 10h
Per-scheme plot records: plot number, house type (with reusable house type library — Future Tasks "unit mix library" stays deferred but a basic house-types table goes here), GIA, sale price, sale stage (`Available` / `Reserved` / `Exchanged` / `Completed`), buyer link (set after 7.2). Plot status board view. Links to programme tasks (e.g. "plot 12 ready for handover when these tasks complete").

## Prompt 7.2 — Buyer Pipeline (NEW — absorbed from Future Tasks)
**Dependencies:** 7.1
**Hours estimate:** 10h
Buyer records, viewing log, reservation (reservation fee tracking, reservation expiry), exchange and completion milestone tracking, solicitor records, conveyancing milestones (search ordered, contract issued, exchange, completion). Notifications to sales (and director on significant events). Not a CRM — no lead scoring, no sequence automation. **Customer-facing buyer portal stays in Future Tasks** (Phase 3+).

## Prompt 7.3 — Post-Completion: Retentions, DLP, Final Accounts (NEW — absorbed from Future Tasks)
**Dependencies:** 2.8, 5.3
**Hours estimate:** 10h
The "fizzle out" problem. Tables: `retentions` (amounts held per subcontract), `retention_releases` (scheduled — typically 50% PC + 50% DLP end), `dlp_periods` (defects liability period per project, default 12 months configurable), final account reconciliation per subcontract. Notifications when retention release due and when DLP ending. Folds in the "warranty" Buildertrend module (warranty period = DLP from a different angle). Defect/snag during DLP creates a snag (4.6) flagged DLP.

## Prompt 7.4 — Reporting, Dashboards, Public-Data API
**Dependencies:** Most of T2, T4, T7.1–7.3
**Hours estimate:** 12h
Director dashboard (project status grid, cash position, pipeline, red-flag list — basic version of Future Tasks executive dashboard), board pack scaffold (PDF export of project summaries), per-project dashboard (financials, programme, recent activity, open snags, open RFIs). Read-only public API surface (rate-limited, no auth) for the eventual marketing site to consume — endpoints for available plots, completed schemes gallery. Basic — full BI/board pack/investor pack stays in Future Tasks Phase 7. **Candidate split** if reporting and the public API both need real depth.

---

# Track 8 — Polish

**Goal:** Pre-launch hardening across security, mobile UX, visual design, performance. Designer engagement during this track per Project Instructions.
**Duration:** ~5 weeks
**Prompts:** 3
**Tables added:** 0

## Prompt 8.1 — Portal Hardening
**Dependencies:** 2.9, 4.7
**Hours estimate:** 10h
Security audit of all portal surfaces (supplier, subcontractor, labourer). Data exfiltration tests, auth boundary tests, scope leakage tests, rate limiting per portal user, session policy review (shorter timeout for portal users), explicit allowlist of fields exposed via portal endpoints (no accidental exposure of internal data). Annual pen test framework setup (Future Tasks Phase 6 picks up annual external pen testing).

## Prompt 8.2 — Mobile UX Pass + Designer Pass
**Dependencies:** All site-ops prompts complete
**Hours estimate:** 14h (designer time on top — see cost section)
Comprehensive mobile audit across all site-facing screens (4.1, 4.2, 4.3, 4.5, 4.7) plus the supplier/subcontractor portal (2.9) and key director-on-the-go views. Designer engaged for 1–2 weeks during this prompt for visual polish, typography, iconography, micro-interactions. Performance budget enforced (every screen under 2s on a mid-range Android on 4G).

## Prompt 8.3 — Performance + Launch Readiness
**Dependencies:** 8.1, 8.2
**Hours estimate:** 12h
Load testing (50 concurrent users, realistic traffic mix), query tuning (slow query log review, missing index audit), cache warming where useful, end-to-end smoke testing covering full user journeys (director → site manager → labourer → supplier → subcontractor), launch checklist (backups verified, audit log working, Xero reconciliation clean, rollback procedure documented), final acceptance review with MD/Louise. **Cutover plan** finalised here — migrate active project data, train users role by role, retire Buildertrend and spreadsheet workflows.

---

# Dependencies graph

Visual representation of the prompt dependency lattice. Each prompt depends on its predecessors plus selected cross-track items.

```
Track 1 (DONE)        Track 2                  Track 3                Track 4              Track 5         Track 6              Track 7              Track 8
                      ─────────                ─────────              ─────────            ─────────       ─────────            ─────────            ─────────
1.1 Entities          2.1 Ref Data ←┐                                                                                                                              
       │                  │         │                                                                                                                              
1.2 Users ────────────┐   │   2.2 Appraisals ←─ depends on 1.1, 1.2, 1.4, 1.5, 1.6, 2.1                                                                                                            
       │              │   │         │                                                                                                                              
1.3 Sessions          │   │   2.3 Governance                                                                                                                       
       │              │   │         │                                                                                                                              
1.4 Audit ────────────┤   │   2.4 Budgets ←──── depends on 1.6, 2.3                                                                                                
       │              │   │         │                                                                                                                              
1.5 Projects ─────────┤   │   2.5 Actuals ←──── depends on 2.4                                                                                                     
       │              │   │         │                                                                                                                              
1.6 Cost Codes ───────┤   │   2.6 BCRs ←─────── depends on 2.4, 2.5                                                                                                
       │              │   │         │                                                                                                                              
1.7 Config            │   │   2.7 Suppliers/Subs ←─ depends on 1.1, 1.2, 1.4, 1.5                                                                                  
                      │   │         │                                                                                                                              
                      │   │   2.8 Subcontracts ←─ depends on 2.5, 2.7                                                                                              
                      │   │         │                                                                                                                              
                      │   │   2.9 Portal ←──── depends on 1.2, 1.3, 2.5, 2.7, 2.8                                                                                  
                      │   │                                                                                                                                        
                      │   └─────────────────── 3.1 Real-time Infra ←── 1.2, 1.4                                                                                    
                      │                                │                                                                                                            
                      │                          3.2 Offline Infra ←── 3.1                                                                                          
                      │                                │                                                                                                            
                      │                          3.3 Programme Templates ←── 1.5                                                                                    
                      │                                │                                                                                                            
                      │                          3.4 Programmes + CPM ←── 3.3                                                                                       
                      │                                │                                                                                                            
                      │                          3.5 Task Updates ←── 3.1, 3.2, 3.4                                                                                  
                      │                                                                                                                                            
                      │                                            4.1 Daily Logs ←── 1.5, 3.1, 3.2                                                                
                      │                                                  │                                                                                          
                      │                                            4.2 Clocking ←── 1.2, 1.5, 3.2                                                                  
                      │                                                  │                                                                                          
                      │                                            4.3 Chat ←──── 3.1                                                                              
                      │                                                  │                                                                                          
                      │                                            4.4 RFIs ←──── 1.5, 4.3                                                                         
                      │                                                  │                                                                                          
                      │                                            4.5 QA ←────── 1.5, 1.6, 3.2, 3.4                                                               
                      │                                                  │                                                                                          
                      │                                            4.6 Snag/Activity ←── 1.5, 4.5                                                                  
                      │                                                  │                                                                                          
                      │                                            4.7 Labourer Portal ←── 1.2, 4.1, 4.2, 4.5                                                      
                      │                                                                                                                                            
                      │                                                                  5.1 Doc Types ←── 1.5, 1.6                                                
                      │                                                                        │                                                                    
                      │                                                                  5.2 Documents ←── 5.1                                                     
                      │                                                                        │                                                                    
                      │                                                                  5.3 Compliance ←── 5.2                                                    
                      │                                                                                                                                            
                      └────────────────────────── 6.1 CSV Framework ←── 2.5, 2.7                                                                                   
                                                       │                                                                                                            
                                                 6.2 Xero OAuth ←── 1.1, 1.2                                                                                       
                                                       │                                                                                                            
                                                 6.3 Reference Sync ←── 6.2                                                                                        
                                                       │                                                                                                            
                                                 6.4 Financial Mirrors ←── 6.3, 2.5                                                                                
                                                       │                                                                                                            
                                                 6.5 Sync Queue + Reconciler ←── 6.4                                                                               
                                                                                                                                                                    
                                                                                            7.1 Plots ←── 1.5                                                       
                                                                                                  │                                                                 
                                                                                            7.2 Buyers ←── 7.1                                                      
                                                                                                  │                                                                 
                                                                                            7.3 Post-Completion ←── 2.8, 5.3                                        
                                                                                                  │                                                                 
                                                                                            7.4 Reporting + API ←── most of T2, T4, T7.1–7.3                        
                                                                                                                                                                    
                                                                                                                              8.1 Portal Hardening ←── 2.9, 4.7      
                                                                                                                                    │                               
                                                                                                                              8.2 Mobile + Designer ←── all site ops 
                                                                                                                                    │                               
                                                                                                                              8.3 Perf + Launch ←── 8.1, 8.2         
```

**Critical path** (longest dependency chain through the graph):

1.1/1.2/1.4/1.5/1.6 → 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.7 → 2.8 → 6.4 → 6.5 → 7.3 → 7.4 → 8.1/8.2 → 8.3

That's 14 prompts on the critical path. Many other prompts can in principle be parallelised (Track 3, Track 4, Track 5 don't strictly block each other once 3.1/3.2 land), but Project Instructions specify sequential build with one prompt at a time, so the practical timeline is the sum of all 36 remaining prompts.

**Audit checkpoints (inserted into timeline, not part of prompt count):**
- After 2.9 (end T2): self-audit + Rhys review, log deviations
- After 3.5 (end T3): self-audit + Rhys review, plus performance baseline measured
- During T4 (after 4.3 chat lands): bring MD, Louise, team in for directional feedback — this is the "mid T4 with team" review
- After 8.3 (pre-launch): full audit, cutover sign-off

---

# Hours estimate and timeline

**Per-prompt hours (Rhys's time end-to-end including verify/fix/commit, excluding Emergent compute time which runs in parallel):**

| Prompt | Hours | | Prompt | Hours | | Prompt | Hours | | Prompt | Hours |
|---|---:|---|---|---:|---|---|---:|---|---|---:|
| 2.1 | 6 | | 3.1 | 14 | | 4.1 | 10 | | 5.1 | 8 |
| 2.2 | 16 | | 3.2 | 12 | | 4.2 | 10 | | 5.2 | 12 |
| 2.3 | 10 | | 3.3 | 8 | | 4.3 | 14 | | 5.3 | 10 |
| 2.4 | 12 | | 3.4 | 16 | | 4.4 | 8 | | | |
| 2.5 | 14 | | 3.5 | 12 | | 4.5 | 12 | | 6.1 | 12 |
| 2.6 | 10 | | | | | 4.6 | 10 | | 6.2 | 14 |
| 2.7 | 12 | | | | | 4.7 | 8 | | 6.3 | 10 |
| 2.8 | 16 | | | | | | | | 6.4 | 16 |
| 2.9 | 12 | | | | | | | | 6.5 | 14 |
| **T2** | **108** | | **T3** | **62** | | **T4** | **72** | | **T5** | **30** | | **T6** | **66** |

| Prompt | Hours | | Prompt | Hours |
|---|---:|---|---|---:|
| 7.1 | 10 | | 8.1 | 10 |
| 7.2 | 10 | | 8.2 | 14 (+ designer) |
| 7.3 | 10 | | 8.3 | 12 |
| 7.4 | 12 | | | |
| **T7** | **42** | | **T8** | **36 (+ designer ~40)** |

**Track totals:** T2 108h, T3 62h, T4 72h, T5 30h, T6 66h, T7 42h, T8 36h = **416 hours** of Rhys's time across 36 remaining prompts. Designer engagement during T8 adds ~40 hours of *external* time on top.

**Average per remaining prompt:** ~11.5 hours — broadly the "10–12h" estimate flagged in Honest Framing.

**At 25 hrs/week, sustained:**
- 416 / 25 = 16.6 weeks of pure prompt work.
- Reality: also re-spec sessions (3 more sessions of this brief work, ~8h each = 24h), audit checkpoints (4 × ~6h = 24h), unforeseen patches and remediation (estimate ~15% overhead = 62h), holidays / illness / business travel (estimate ~10% = 42h).
- Honest total: 416 + 24 + 24 + 62 + 42 = **568 hours** = 22–23 weeks at 25 hrs/week sustained = **~5.5 calendar months from end of Foundation if pace holds**.

**At 20 hrs/week (more realistic given other obligations):** 568 / 20 = 28 weeks ≈ **~7 calendar months**.

**At 15 hrs/week (if life intervenes):** 568 / 15 = 38 weeks ≈ **~9 calendar months**.

The 10–14 month range from Project Instructions covers all three of these scenarios with margin for genuine schedule slip. **Lower end of the range (10 months) requires sustained 25 hrs/week which has historically been hard. 12–14 months is the planning assumption.**

**Cumulative milestone calendar (assuming 22 hrs/week average):**

| Milestone | Cumulative hours | Calendar weeks | From now |
|---|---:|---:|---|
| End Track 2 (commercial engine + portals live) | 108 | 5 | ~1.5 months |
| End Track 3 (programme + real-time/offline infra live) | 170 | 8 | ~2 months |
| End Track 4 (full site ops live) | 242 | 11 | ~3 months |
| End Track 5 (documents + compliance live) | 272 | 12 | ~3.5 months |
| End Track 6 (Xero + CSV — platform integration-complete) | 338 | 15 | ~4.5 months |
| End Track 7 (sales + post-completion + reporting) | 380 | 17 | ~5 months |
| End Track 8 (polish + launch readiness) | 416 | 19 | ~5.5 months prompt time |
| Plus overhead | +152 | 7 | |
| **Total** | **568** | **26** | **~6 months minimum, 12–14 months realistic** |

---

# Data model delta estimate

**Phase 1 final state:** 77 tables / 1,288 fields / 10 modules.

**Phase 2 estimated additions** (50 new tables, ~700 fields):

| Track | New tables (rough) |
|---|---|
| Track 2 (subcontractors + portal) | ~8: suppliers, subcontractors, subcontractor_cis_verifications, supplier_documents, subcontracts, subcontract_variations, subcontract_valuations, payment_notices |
| Track 3 (real-time + offline) | ~5: realtime_channels, realtime_subscriptions, realtime_events, offline_outbox, sync_conflicts |
| Track 4 (site ops) | ~22: daily_logs, daily_log_entries, daily_log_photos, clock_events, geofences, timesheets, timesheet_entries, chat_channels, chat_messages, chat_threads, chat_attachments, chat_reads, chat_mentions, rfis, rfi_responses, rfi_attachments, qa_checklist_templates, qa_checklists, qa_items, qa_photos, qa_signoffs, snags, snag_photos, snag_assignments, activity_events |
| Track 6 (CSV) | ~2: import_jobs, import_errors |
| Track 7 (sales + post-completion + reporting) | ~13: plots, house_types, buyers, buyer_viewings, reservations, conveyancing_milestones, retentions, retention_releases, dlp_periods, final_accounts, report_definitions, report_runs, public_api_endpoints |

**Phase 2 final state estimate: 127 tables / ~2,000 fields / 13 modules.** Within the 110–130 range from Chat 5 framing.

The data model XLSX needs a v2 reflecting this. Flagged as a separate deliverable — to be produced after session 4 of brief work, before Track 2 build starts.

Some Phase 1 tables get extended in Phase 2 (e.g. `actuals` gets a `source` enum extension to include `CSV_Import`, `users` gets an `is_portal_user` flag). These extensions are noted in the per-prompt detail in sessions 3–4, not counted as new tables.

---

# Updated Future Tasks list (post-absorption)

The following items were in `SY_Homes_Future_Tasks.md` v1 and are now **absorbed into Phase 2**, so they are removed from Future Tasks v2:

- Subcontractor Database and CIS → Prompt 2.7
- Subcontracts and Variations → Prompt 2.8
- Plot Management → Prompt 7.1
- Buyer Pipeline → Prompt 7.2
- Post-Completion → Prompt 7.3

The following items remain in **Future Tasks v2**, organised by phase. The priority ordering is unchanged from v1 except where noted.

**Phase 3 — Operational follow-on (post Phase 2 launch):**
- Deal Pipeline (high)
- Planning Management (high)
- Tender Module (medium) — confirmed deferred per Chat 5
- Customer Handover and Aftercare (medium) — confirmed deferred per Chat 5
- Customer-facing Buyer Portal (medium) — depends on plot mgmt being live
- Programme stretch features: weather integration, predictive completion, cross-project resource view (medium) — confirmed deferred per Chat 5

**Phase 4 — Advanced integrations:**
- Buildertrend Integration (medium — only if SY Homes keeps using BT)
- Bank Feed Integration (medium)
- Electronic Signatures (medium)
- ISO 19650 / CDE Integration (low)
- HMRC CIS Direct Submission (low)
- MTD for Corporation Tax (medium — when mandatory)
- Intercompany Billing Automation (medium)

**Phase 5 — Platform enhancements (8 items unchanged from v1):**
- Dashboard widget: Committed as % of FFC
- Unit Mix Library (a basic house_types table arrives in Prompt 7.1; full library is more)
- Scotland/Wales SDLT equivalents (LBTT / LTT)
- Historical Actuals CSV importer (CSV framework lands in 6.1; this is the operational layer on top)
- Contingency Usage Analyser
- Cash Runway Alerting
- Scenario-driven Cash Flow
- AI Document Ingestion
- BIM Module

**Phase 6 — Security hardening (5 items unchanged from v1):**
- MFA enforcement for all roles
- Second super-admin approval for super-admin impersonation
- API call anomaly detection
- External audit log export (to SIEM)
- Annual external pen testing

**Phase 7 — Data and reporting (5 items, partial overlap with Track 7.4):**
- Build cost rate defaults learning from actuals
- Cross-project benchmarking
- Investor Reporting Pack Generator
- Executive KPI Dashboard (basic version in 7.4)
- Board Pack Generator (basic version in 7.4)

**Workflow enhancements:**
- Automated Email Templates (Phase 3)
- Explicit Folder Structure for Documents (Phase 3) — Phase 2 uses virtual paths
- File Attachments Polymorphic (Phase 3)
- Xero Project Archival Workflow (Phase 3)
- Bank Feed Enablement Guidance (Phase 4)
- Intercompany Reconciliation Workflow (Phase 3)

---

# Open questions for sessions 3–4

These are the design decisions that should be locked in detail rather than at skeleton level. Surfacing now so they aren't surprises.

1. **Real-time choice: WebSockets vs SSE.** Both work. WebSocket is bidirectional and lower-latency; SSE is simpler and works through more proxies. Decision in Prompt 3.1 detail.

2. **Offline conflict resolution UX.** Last-write-wins for non-financial, conflict UI for financial — but financial isn't usually offline. Probably last-write-wins everywhere with a "this was overwritten" toast for the loser. Decision in 3.2.

3. **Chat — replace WhatsApp or coexist?** Hard problem. Coexistence seems likely in early months ("it's not chat for everything yet"). Chat (4.3) needs to be good enough that the team chooses it for project comms. Decision is operational not technical.

4. **Public API auth model.** Read-only with rate limit but no auth is simplest for a marketing site feed. If the marketing site needs personalised data (buyer-specific) that's a different authenticated surface and stays in Phase 3. Decision in 7.4.

5. **Designer engagement timing within T8.** Designer for 1–2 weeks during 8.2 — find designer in advance, brief in advance. Lead time matters; this isn't "decide on the day".

6. **Cutover plan for Buildertrend retirement.** Not a prompt, but a real plan needed before 8.3 launch readiness. Probably a separate document drafted during T6/T7.

7. **Whether Prompt 4.6 (snag + activity) really should be split.** Snagging is a meaningful module on its own; activity streams are a generic surface. Folded together for skeleton because both are "what happened" feeds, but they're conceptually distinct. Sessions 3–4 detail will tell.

8. **Whether Prompt 2.8 (subcontracts + variations + valuations + payment notices) should split.** Probably the most overloaded prompt in the skeleton. Could be 2.8a Subcontracts + Variations, 2.8b Valuations + Payment Notices.

If 4.6 and 2.8 both split, prompt count goes from 43 to 45. Within the honest range flagged at the top.

---

# Next sessions

- **Session 3:** Prompt-level detail for Tracks 2 and 3 (table schemas, business logic, UI specs, acceptance criteria, permissions, out-of-scope blocks per prompt). Estimated 6–8 hours.
- **Session 4:** Prompt-level detail for Tracks 4, 5, 6, 7, 8. Estimated 8–10 hours. Likely splits into 4a (T4–T5) and 4b (T6–T8) if it runs long.
- **After session 4:** v2 of `SY_Homes_Data_Model.xlsx` reflecting the ~50 new tables. Estimated 3–4 hours.
- **After data model v2:** Project Instructions update — track count, prompt count, timeline, Future Tasks ordering. Edit-in-place per existing convention.

Then: build resumes with Prompt 2.1 in Emergent.

---

_Version 2.0-skeleton, April 2026. To be refined into 2.0-full across sessions 3–4._
