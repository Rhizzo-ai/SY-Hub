# SY Homes Platform — Future Tasks

Running list of deferred items surfaced during Phase 1 specification. Each is either out-of-scope for Phase 1 (to be picked up in Phase 2+) or a worthwhile enhancement that can be added once the core platform is stable.

Organised by theme. Priorities are my recommendation based on business impact and effort — Rhys to confirm final ordering.

---

## Phase 2 — Operational Modules

These are the next-biggest blocks of functionality after Phase 1 is live. Priority order reflects business value.

### Deal Pipeline (High)
Module for managing sites from "first look" through to appraisal. Tracks lead source, initial view, shortlist rationale, offer/counter-offer history, option/conditional contract tracking, SearchLand integration. The bridge between site discovery and the appraisal module.

### Planning Management (High)
Structured planning application tracking — pre-app, submission, LA correspondence, consultee responses, committee dates, decision, conditions, discharge tracking. Conditions register with responsible party, due dates, and evidence requirements. Ties into the existing document_registers (CDM, Planning Discharge types).

### Subcontractor Database and CIS (High)
Full subcontractor records — name, trades, preferred status, rates, insurance status, CIS verification history, payment history, performance ratings. Enables the subcontract valuation workflow and CIS300 generation natively (rather than via Xero's CIS module).

### Subcontracts and Variations (High)
Formal subcontract records linking to commitments. Variation instructions with approval workflow. Subcontract valuations with retention, CIS, and payment notice generation. Integration with commitments → actuals pipeline.

### Tender Module (Medium)
For main contracting projects — tender package creation, supplier invitations, return scoring matrix, award workflow. Consumes the estimating data (cost codes, subcategories, rates) and creates a budget on award.

---

## Phase 3 — Sales & Post-Completion

### Plot Management (High)
Individual plot records per scheme — plot number, house type, position, GIA, sale price, sale stage (available / reserved / exchanged / completed), buyer details. Links to sales module.

### Buyer Pipeline (Medium)
Buyer contact records, viewing history, reservation management, solicitor tracking, exchange/completion tracking. Integrates with Land Registry and conveyancing workflows.

### Post-Completion (High — was a big pain point)
Structured tracking of retentions (release at 6/12/24 months), defects period management, DLP (defects liability period) tracking, final accounts closure. Prevents the "fizzle out" problem where post-completion obligations get forgotten.

### Customer Handover and Aftercare (Medium)
Handover pack generation, home demonstrations, snag list management, 7-day/6-month/12-month inspection workflows, warranty call routing.

---

## Phase 4 — Advanced Integrations

### Buildertrend Integration (Medium)
If SY Homes continues using Buildertrend for estimating, a bidirectional sync lets estimates populate appraisal_cost_lines and actual progress update budget_lines without double entry.

### Bank Feed Integration (Medium)
Direct bank feed sync (via Open Banking / Plaid / TrueLayer) for true cash reconciliation. Complements Xero bank transaction sync with real-time visibility.

### Electronic Signatures (Medium)
DocuSign / Adobe Sign integration for subcontract orders, variations, payment notices. Removes print/sign/scan workflow.

### ISO 19650 / CDE Integration (Low for now — depends on HA work growth)
Common Data Environment integration for projects working to BIM Level 2 / ISO 19650 standards. Aconex, BIM 360, Asite integrations.

### HMRC CIS Direct Submission (Low)
Direct integration with HMRC CIS online service for CIS300 submission, verification, and contractor statements. Currently routed via Xero's CIS module.

### MTD for Corporation Tax (Medium — when mandatory)
HMRC's Making Tax Digital roadmap extends to Corporation Tax. When mandatory, the platform's audit trail and computations should export in the required format.

### Intercompany Billing Automation (Medium)
Currently intercompany transactions are modelled but posting is manual. Phase 2: semi-automated (draft invoices generated, Louise reviews and authorises in Xero). Phase 3: fully automated with defined rules per cost code type.

---

## Phase 5 — Platform Enhancements

### Dashboard: Committed as % of FFC (Low effort, high value)
Widget showing, per project, how much of the forecast final cost is already contractually committed. Indicates risk exposure — a project that's 90% committed is locked in; 40% is exposed to market volatility.

### Unit Mix Library (Medium)
Reusable library of house types with standard GIA, build cost per unit, typical finishes. New appraisals select from library rather than re-entering. Version-controlled so historical appraisals preserve original assumptions.

### Scotland/Wales SDLT Equivalents (Low until first site there)
Scotland uses LBTT (Land and Buildings Transaction Tax), Wales uses LTT (Land Transaction Tax). Different rates and bands. Low priority until SY Homes operates outside England; current engine handles England only.

### Historical Actuals CSV Importer (Medium)
Bulk import tool for loading historical project actuals from Excel/CSV. Needed for populating completed/legacy projects for group-level reporting.

### Contingency Usage Analyser (Low, insight-driven)
Report showing, per project and per cost section, what the contingency was drawn down for. Over time, this builds an empirical picture of where risk materialises most — feeding future appraisal contingency sizing.

### Cash Runway Alerting (Medium)
Group-level alert when forecast cumulative cash position trends toward zero or below a threshold within a 3/6/12-month horizon. Prevents surprise cash crunches.

### Scenario-driven Cash Flow (Medium)
Ability to model "what if we slow sales by 3 months" or "what if build runs 10% over" without changing the live forecast. Compares scenarios side-by-side.

### AI Document Ingestion (Low)
Auto-extract data from uploaded PDFs — invoices, bank statements, contract pages. Uses LLM to parse and populate matching records for review. Low priority until volume justifies it.

### BIM Module (Low)
Link to BIM models stored externally with drawing register integration. Relevant only if moving to more BIM-intensive delivery.

---

## Phase 6 — Security Hardening

### MFA Enforcement for All Roles (Medium)
Phase 1 enforces MFA only for super_admin, director, finance. Phase 6: extend to all internal users as company policy. Portal users (subcontractor, consultant) remain optional.

### Second Super-Admin Approval for Impersonation of Super-Admins (Low)
Currently super_admin can impersonate any user including other super_admins (logged in audit_log). Harden by requiring second super_admin approval when impersonating another super_admin. Prevents a single compromised super_admin account from accessing another.

### API Call Anomaly Detection (Low)
Machine learning or rules-based detection of unusual API key usage patterns — volume spikes, unusual IPs, off-hours access. Triggers alerts to owner and security.

### External Audit Log Export (Medium)
Scheduled or on-demand export of audit_log to an external immutable store (AWS CloudTrail, Azure Log Analytics, or dedicated SIEM). Protects against the scenario where platform itself is compromised.

### Penetration Testing (High — at least annually once live)
Annual third-party pen test covering auth, session management, permission boundaries, injection attacks, data exposure. Report findings addressed per risk rating.

---

## Phase 7 — Data and Reporting

### Build Cost Rate Defaults Learning from Actuals (Medium)
Over time, the platform learns empirical build cost rates from completed projects (£/sq ft by house type, by location). These replace or supplement the manual defaults in appraisal_default_settings. Improves appraisal accuracy as the dataset grows.

### Cross-Project Benchmarking (Low)
Anonymous benchmarking across SY Homes's portfolio — programme durations per phase, cost per sq ft by region/type, variance patterns. Insight tool for future appraisals.

### Investor Reporting Pack Generator (Medium)
Quarterly/annual investor pack auto-generated: group financials, per-project status, cash runway, pipeline, risk register. PDF output with consistent layout. Saves Director time.

### Executive KPI Dashboard (Medium)
Single group-level dashboard surfacing the 8-12 KPIs that matter to the board: units in pipeline, units on-site, units sold, average margin realised, average margin forecast, cash runway, peak funding required, variance status across active projects, red-flag list.

### Board Pack Generator (Medium)
Monthly board pack auto-compiled from existing data — project-by-project summary, financial headlines, programme status, cash position, pipeline, risk register. Approx 15-20 pages, exported as PDF.

---

## Workflow Enhancements

### Automated Email Templates (Medium — Phase 2)
Standard emails (payment notice issued, valuation approved, variation issued, alert escalated) generated from templates with merge fields. Reduces email friction for repetitive communications.

### Explicit Folder Structure for Documents (Medium)
Phase 1 uses virtual folder paths (folder_path text field). Phase 2: add a formal folders table with hierarchical structure, folder permissions, and drag-drop reorganisation.

### File Attachments Polymorphic (Medium)
Phase 1 handles attachments via the documents table with related_* FKs. Phase 2+: a polymorphic file_attachments table for smaller attachments (photos in task updates, screenshots on comments) that don't warrant full document records.

### Customer-Facing Buyer Portal (Medium — once Plot Management is live)
Buyers log in to view their plot details, reservation status, choice selections, build progress, completion dates, handover information. Reduces sales team phone time.

### Xero Project Archival Workflow (Medium)
When a project closes in the platform, the linked Xero tracking options are archived to stay under Xero's 100-option limit. Currently manual — Phase 2 automates this.

### Bank Feed Enablement Guidance (Low)
Onboarding guide and setup wizard for enabling bank feeds per entity. Currently left for Louise to configure manually.

### Intercompany Reconciliation Workflow (Medium)
Monthly reconciliation screen showing, for each intercompany cost code flow, whether the equivalent transaction has been posted in the paired entity. Flags mismatches for investigation.

---

## Priority Summary for Phase 2 Kickoff

If planning Phase 2 now, recommend these in this order:

1. **Subcontractor database + CIS + subcontracts + variations** (most days-per-month saved for the team).
2. **Deal pipeline** (most business value — better deal flow tracking).
3. **Planning management** (compliance risk mitigation).
4. **Plot management + post-completion** (operational quality improvement).
5. **Tender module** (enables growth of main contracting work).
6. **Automated email templates** (quality-of-life).
7. **Historical actuals importer** (unlocks group-level reporting).
8. **Cash runway alerting** (capital protection).

Other items in this document fit into Phase 3 onwards as capacity and business priorities allow.

---

_Document version 1.0 · April 2026 · Maintained alongside SY_Homes_Data_Model.xlsx and SY_Homes_Platform_Spec_v2.docx_


---

## Microsoft 365 Ecosystem Integration (Strategic — needs decision before Track 4)

SY Homes operates on Microsoft 365: Outlook for email, Word/Excel for documents, 
ToDo for tasks, SharePoint/OneDrive for file storage, Teams for communication. The 
platform should integrate with this ecosystem rather than compete with it. Several 
integration points identified:

### SharePoint / OneDrive as Document Backend (High — affects Track 4 architecture)
**Decision needed before Prompt 4.2.** Options:
- (A) Native file store in the platform (simpler to build, duplicates storage SY 
  Homes already pays for, files locked behind platform auth)
- (B) SharePoint/OneDrive as the backend — platform stores metadata and 
  SharePoint document IDs, actual files live in SharePoint. Users get native 
  co-authoring, version history, offline sync, and Office apps open files 
  natively. Access control via SharePoint permissions.
- (C) Hybrid — native store for platform-internal docs (QA checklists, generated 
  reports), SharePoint for user-uploaded files (drawings, contracts, 
  specifications).

Recommendation: (C) hybrid, with SharePoint as the default for user uploads. 
Revisit when Track 4 is specced.

### Microsoft Graph API (High — the single gateway)
One API covers calendar, mail, tasks, SharePoint, OneDrive, Teams, Users. Using 
Graph means OAuth once, then all of the above are available. Already half-built 
into 1.3 via Microsoft SSO — extending it adds massive leverage.

### Outlook Calendar Sync (Medium)
- Programme milestones → Outlook calendar entries on assignees' calendars
- Delivery schedule → site manager's calendar
- Meeting scheduling for approvals, site visits, inspections
- Two-way sync: platform reschedule updates calendar; calendar change prompts 
  programme update

### Microsoft ToDo Sync (Medium)
- Platform tasks assigned to users appear in their ToDo list
- Two-way sync: ticking in ToDo marks complete in platform
- Works naturally on mobile (ToDo app on phone, no separate platform app needed 
  for task-only users)

### Excel Integration (Medium-High)
- Export any grid (budgets, actuals, programme, reports) to Excel with one click
- Import templates for bulk entry (historical actuals, programme tasks)
- Excel add-in: live platform data in spreadsheets for finance director's models
- Consider Excel Online embed for certain read-only views

### Outlook Add-in (Medium)
- Email → platform record conversion. Drag supplier invoice email → creates 
  draft actual. Drag subcontractor query email → creates RFI. Attachments go 
  to linked document record.
- Saves the finance team's time on email triage.

### Teams Integration (Lower priority)
- Auto-create Teams channel per project
- Platform notifications post to project Teams channel
- File sharing via SharePoint already covered by document integration
- Consider whether to do this or keep chat native to the platform (site users 
  probably don't have Teams; office staff do)

### Word Integration (Lower)
- Generate contracts, RFIs, variations as Word documents from platform templates
- Track changes back into the platform record

---

**Build order implication:** Microsoft Graph auth and the SharePoint/OneDrive 
decision belong in or before Track 4. Calendar, ToDo, Excel add-in, Outlook 
add-in can come later as standalone prompts once the Graph foundation is in.


