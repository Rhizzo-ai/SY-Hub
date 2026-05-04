# SY Hub — Scope Expansion Memo

**Date:** April 2026  
**Author:** Rhys, with Claude  
**Purpose:** Document the expansion of SY Hub's scope from "property development financial control platform" to "full company operating system". Written in plain English so it can be shared, referenced, and sense-checked without wading through specification documents.

---

## What changed

The original 25-prompt build specification was scoped as a **property development financial control platform** — a tool for directors, PMs, and finance to manage appraisals, budgets, cash flow, compliance, and Xero integration. Site operations were included but secondary.

The revised scope is a **full company operating system** — everyone in SY Homes, from directors down to labourers on site, logs in and does their work in one place. The financial control layer stays; a substantial operational layer joins it.

This memo documents what that means and what it doesn't mean.

---

## The new vision in one paragraph

SY Hub is the single place where SY Homes operates. The office uses it for appraisals, budgets, cash flow, compliance, and document management. The finance team uses it for bill approval, Xero integration, and reporting. Site managers use it for daily logs, task updates, programme tracking, and QA. Labourers use it for clocking in and out, viewing today's tasks, and submitting end-of-day summaries. Contractors use it for payment applications, variations, and QA submissions. Suppliers use it for PO confirmations and deliveries. Everyone chats to each other in project-scoped threads. Photos and files live with the records they relate to. Directors see dashboards showing the state of the business in real time. The platform replaces spreadsheets, WhatsApp groups, Buildertrend, email chains, and phone calls — all of it — with one integrated system of record.

---

## What's in scope

### Already in the specification (being built)

These are in the original 25-prompt brief and will be built as the Emergent plan progresses:

- **Entities** — multi-entity group structure (Parent, SPV, ConstructionCo) with VAT, CIS, insurance tracking
- **Users, roles, permissions** — 10 role types, ~90 permissions, scope-based access
- **Sessions, MFA, SSO, API keys** — proper auth infrastructure
- **Audit log** — append-only forensic trail of all significant actions
- **Projects** — central project records with stage management
- **Cost codes** — ~120 codes, 792 subcategories, entity-aware mapping
- **System config and notifications** — tunable settings and in-app alerts
- **Appraisals** — SDLT engine, RLV solver, finance interest modelling, scenarios
- **Budgets** — line-item budgets from approved appraisals, change control, forecasts
- **Actuals and commitments** — bills, purchase orders, subcontracts, invoices
- **Cash flow** — forecast vs actual by entity, peak funding calculation, VAT/CIS scheduling
- **Programme** — Gantt with proper CPM, baselines, calendars, weekly reports
- **Documents** — versioned document store with approvals and access control
- **Compliance registers** — CDM, BSA, Part L/O/Q, Fire Safety, GDPR, Planning, Building Control, Insurance, Certificates, Contract
- **Xero integration** — bidirectional sync, tracking categories, OAuth, webhooks, reconciliation

### New additions (scope expansion)

These are **not yet in the spec** and need to be specified and added to the build plan:

#### 1. Daily logs
Site managers write daily entries per project: weather, attendance, work completed, deliveries received, issues, delays, visitors. Searchable, exportable, linked to programme tasks. Photos embedded. Replaces site diaries and WhatsApp updates.

#### 2. Clocking in and out
Labourers and contractors clock in at the start of the day and out at the end. Geolocation (optional) to verify on-site. Timesheet reporting. Links to payroll data (for reporting only — not processing payroll itself).

#### 3. Team chat
Real-time messaging within the platform. Project-scoped channels. Direct messages between users. Threaded replies. File attachments. Notifications integrated with the existing notifications table. Read receipts. Search.

#### 4. QA checklists with photo requirements
Contractors submit quality assurance against checklists tied to task completion. Photos are mandatory on specified items. Checklists linked to cost codes and programme tasks. Approval workflow for sign-off. Defect management.

#### 5. Supplier and contractor portals
External users (suppliers, subcontractors) get scoped portal access. Suppliers confirm POs, schedule deliveries, submit delivery notes. Subcontractors submit payment applications, variations, QA. Minimal UI, focused on what each role needs. Mobile-friendly.

#### 6. Labourer portal
Minimal mobile interface for labourers: clock in/out, see today's tasks, mark tasks complete, submit end-of-day summary, access safety briefings. Fast, simple, forgiving. No expectation of tech skill.

#### 7. Real-time features beyond notifications
Live dashboards that update without refresh. Task status changes visible immediately to other users. Programme updates propagate in real-time. Chat is instant. WebSocket-based infrastructure.

#### 8. Offline capability for site operations
Daily logs, clocking, task updates, QA submissions must queue when offline and sync when connection returns. Construction sites have patchy signal — this is a hard requirement, not nice-to-have.

#### 9. Activity streams
Every project has an activity feed showing what's happened recently: documents uploaded, tasks completed, bills posted, messages sent. Filterable. Catches users up when they come back to a project.

#### 10. Sales integration (future phase)
Plot records, buyer pipeline, reservation tracking, deposit management, legal completion workflow. Possibly links to a public-facing website showing available plots. This is a later phase — probably months 8-12 of the build — but in scope.

### What's different about how things already in scope are built

The scope expansion also changes how some existing items get built:

- **Mobile-first design from day one.** The current spec is desktop-oriented in places. Every UI needs to work well on phones for site users.
- **Role-based UI divergence.** A labourer's experience of "Projects" is completely different from a director's. Not just hidden fields — entirely different screens.
- **Performance budget.** "Slow and shit" is the failure mode. Pages under 2 seconds, interactions feel immediate. No more forgiving than a consumer app.
- **Real-time architecture.** WebSockets or similar must be baked in, not bolted on.

---

## What's NOT in scope

Some boundaries that hold regardless of how things evolve:

### Not a CRM
No lead scoring, no marketing automation, no email campaigns, no prospect pipeline management (beyond the sales module, which is about actual buyers of actual plots).

### Not a payroll system
No HMRC RTI submissions, no PAYE calculations, no pension admin. Clocking provides data for payroll; payroll happens elsewhere.

### Not a replacement for Xero
Xero remains the book of record for accounting. SY Hub mirrors relevant data bidirectionally but doesn't become the ledger.

### Not a public-facing marketing website
If there's eventual website integration, it's for things like "show available plots" — a read-only surface driven by the platform data. Not a marketing CMS.

### Not a design / BIM / CAD tool
Design files are stored, versioned, shared, approved. They're not authored or edited in-platform.

### Not a construction contract-drafting system
Contracts are documents. They get uploaded, approved, tracked. The platform doesn't have a clause library, risk-allocation wizard, or JCT-form-builder.

### Not a general-purpose SaaS
Designed for SY Homes. Commercialisation is a future option that, if taken, means a meaningful rebuild.

---

## What this means for the build

### Timeline

Original 25-prompt plan was sized for the narrower scope at 4-6 months.

Expanded scope realistically requires **35-40 prompts** and **10-14 months** at 20-25 hours per week.

### Cost

Emergent credits probably £3-8k for the full build (up from £2-4k in the original plan). Possible additional spend on a designer (£2-4k for polish) and possibly a developer for the Xero integration if needed (£3-5k). **Total plausible cash: £8-15k**, plus Rhys's time.

### Sequence

1. **Finish Foundation track** (Prompts 1.3 through 1.7) as originally specced. Foundation is robust to scope changes — users, roles, audit, projects, cost codes, config, notifications all serve the expanded vision.

2. **Pause and re-spec Tracks 2-5** with the expanded scope. This will probably produce a new brief document replacing the current Emergent brief from Prompt 2.1 onwards.

3. **Build against the expanded brief.** One prompt at a time, with verification, same discipline as current.

4. **Review point:** after Commercial Engine (Track 2) complete and before Xero (Track 5), bring MD / Louise / team in for directional feedback. Adjust as needed.

5. **Launch planning:** when the platform is genuinely usable end-to-end, plan the cutover. Migrate active project data, train users role by role, retire Buildertrend and spreadsheet-based workflows.

### Review triggers

Scope drift happens naturally during long builds. Check this memo quarterly and ask:

- Has anything new been asked for that belongs in scope?
- Has anything turned out to not be needed that we can cut?
- Have the "not in scope" boundaries held, or have we drifted?
- Is the timeline still realistic given the pace we're actually going?

---

## One honest reflection

Building this is ambitious. Not every small property developer would — most would stitch together Buildertrend + Xero + a CRM and live with the friction. SY Homes is choosing the harder path because:

1. The commercial alternatives each solve part of the problem; none solves all
2. Licensing 3-4 products plus integrating them approaches the cost of custom
3. Owning the platform means it fits how SY Homes actually works, not the other way round
4. If SY Homes grows, the platform grows with it without escalating licensing costs
5. The platform becomes a company asset rather than a monthly expense

The risk is that it becomes a long, expensive project that over-promises and under-delivers — "slow and shit", in the explicit failure-mode framing. The mitigation is process discipline: build one prompt at a time, verify each before moving on, log every deviation, course-correct regularly.

If this is still the right call in 12 months when the platform is live and working, it was worth doing. If by month 6 the build is bogged down and the team's losing faith, we pivot — finish Phase 1 as originally specced and accept the narrower tool. That's a legitimate outcome too.

For now: eyes open, full commitment, 20-25 hours a week, one prompt at a time.

---

_Version 1.0, April 2026. Updates as scope evolves._
