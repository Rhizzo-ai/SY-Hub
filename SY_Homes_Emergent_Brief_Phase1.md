<!-- ================================================================
     SY HOMES PLATFORM — PHASE 1 EMERGENT BRIEF
     ================================================================
     Version: 1.0
     Date: April 2026
     Companion: SY_Homes_Data_Model.xlsx, SY_Homes_Platform_Spec_v2.docx
     ================================================================ -->

# Table of Contents

## How to use this brief
- Global conventions
- Workflow recommendations

## Track 1 — Foundation (7 prompts)
- Prompt 1.1 — Entities
- Prompt 1.2 — Users, Roles, Permissions
- Prompt 1.3 — Sessions, Login History, Invitations, SSO, API Keys
- Prompt 1.4 — Audit Log
- Prompt 1.5 — Projects, Project Team Members
- Prompt 1.6 — Cost Codes
- Prompt 1.7 — System Config, Notifications

## Track 2 — Commercial Engine (7 prompts)
- Prompt 2.1 — Reference Data: SDLT Bands, Appraisal Default Settings
- Prompt 2.2 — Appraisals Core: Header, Units, Cost Lines, Finance Model
- Prompt 2.3 — Appraisal Governance: Revisions, Scenarios, Decision Log
- Prompt 2.4 — Budgets Core
- Prompt 2.5 — Actuals and Commitments
- Prompt 2.6 — Budget Change Control and Forecasts
- Prompt 2.7 — Cash Flow

## Track 3 — Programme (3 prompts)
- Prompt 3.1 — Programme Templates and Calendars
- Prompt 3.2 — Programmes, Tasks, CPM Engine
- Prompt 3.3 — Task Updates, Baselines, Alerts, Weekly Reports

## Track 4 — QA & Documents (3 prompts)
- Prompt 4.1 — Document Types and Templates
- Prompt 4.2 — Documents, Approvals, Access Log
- Prompt 4.3 — Compliance Registers, Certificates & Permits

## Track 5 — Xero Integration (5 prompts)
- Prompt 5.1 — Xero Connections (OAuth + Token Management)
- Prompt 5.2 — Reference Sync
- Prompt 5.3 — Financial Mirrors
- Prompt 5.4 — Sync Queue, Webhooks, Bank Transactions, Manual Journals
- Prompt 5.5 — Reconciler, Sync Events, Delta Sync

---

# SY Homes Platform — Phase 1 Emergent Brief

**Version:** 1.0  
**Date:** April 2026  
**Scope:** Phase 1 Foundation — Emergent build prompts for 77 tables across 10 modules  
**Companion documents:**
- `SY_Homes_Data_Model.xlsx` — complete schema reference
- `SY_Homes_Platform_Spec_v2.docx` — narrative specification
- `SY_Homes_Future_Tasks.md` — deferred items

---

## How to use this brief

Each prompt below is a self-contained build instruction for Emergent. Work through them in order — each prompt lists its dependencies (what must be built before it can be attempted).

**Recommended workflow:**

1. Open one prompt at a time.
2. Paste into Emergent.
3. Review what Emergent generates against the Acceptance Criteria.
4. Fix gaps, validate, commit, move to next prompt.
5. Do not skip ahead — dependencies matter.

**Target pace:** One prompt every 1-3 days with testing. Full Phase 1 in 4-6 months.

---

## Global conventions (applies to every prompt)

These apply to every table built. Emergent should treat these as implicit defaults.

### Naming
- Tables: `plural_snake_case` (e.g. `cost_code_sections`)
- Fields: `snake_case`
- Foreign keys: `_id` suffix (e.g. `project_id`)
- Timestamps: `_at` suffix (UTC, always)
- Dates: `_date` suffix
- Percentages: `_pct` suffix (stored 0–100, not 0–1)
- Booleans: `is_` or `has_` prefix
- Enums: `PascalCase_With_Underscores` values

### Data types
- IDs: UUID v4, generated at insert
- Money: DECIMAL(14,2) — never FLOAT
- Percentages: DECIMAL(6,3)
- Text (short): VARCHAR(255)
- Text (long): TEXT
- JSONB for flexible structured data
- Timestamps: always timezone-aware, stored as UTC

### Standard audit fields (add to every table)
```
created_at     timestamp  NOT NULL  DEFAULT now()
updated_at     timestamp  NOT NULL  DEFAULT now()
```
Most tables also need `created_by_user_id uuid` (becomes available after Prompt 1.2).

### Updated_at trigger
Apply an `updated_at` trigger to every table that updates the timestamp on any row modification. Built once in Prompt 1.1, reused throughout.

### Delete behaviour
- Default: `ON DELETE RESTRICT` for `_id` FKs
- Junction tables (M2M): `ON DELETE CASCADE`
- Optional FKs (e.g. `linked_programme_task_id`): `ON DELETE SET NULL`
- Soft delete via `status` field for records with financial/audit history — never physically delete these

### Audit logging
Every significant write (create / update / delete / approve / stage_change / status_change) creates an `audit_log` entry. Wired via application layer, not DB trigger, so the actor user context is available. Built in Prompt 1.4.

### Permission enforcement
Every endpoint checks the user's effective permissions against the required permission for that action. Built in Prompt 1.2 (roles/permissions) and applied from Prompt 1.5 onwards.

### Cached field refresh pattern
Cached rollup fields (e.g. `projects.gdv_actual`, `budget_lines.actuals_to_date`) are recomputed on source writes. Pattern:
1. Source write (e.g. posting an actual) triggers recalc queue job.
2. Job recomputes affected cached fields.
3. Cached fields updated with timestamp.
4. If job fails, retry with exponential backoff; after 3 fails, alert.

### UI conventions
- List views: sortable columns, filterable, paginated (50 per page default).
- Detail views: two-column layout, section headers for field groups.
- Forms: inline validation on blur, submit disabled until valid.
- Tables with lots of fields: collapse uncommon fields into "Advanced" section.
- Dates: pickers default to project timezone (Europe/London).
- Money: formatted with thousand separators, 2 decimal places.
- Percentages: formatted as "12.5%", stored as 12.5.

---

# Track 1 — Foundation

**Goal:** Build the core tables everything else depends on — entities, users/permissions, audit, projects, cost codes, config.  
**Duration:** 3-4 weeks  
**Prompts:** 7  
**Tables:** 23 (21 + 2 cross-cutting)

---

## Prompt 1.1 — Entities

**Dependencies:** None  
**Tables in this prompt:** `entities`  
**Estimated build time:** 1-2 days

### Build this table

```
entities
─────────────────────────────────────────────
id                              uuid PK DEFAULT gen_random_uuid()
name                            varchar(255) NOT NULL
legal_name                      varchar(255) NOT NULL
entity_type                     enum NOT NULL  ('Parent','SPV','ConstructionCo','JV_Vehicle','Other')
parent_entity_id                uuid FK→entities.id ON DELETE RESTRICT
companies_house_number          varchar(10)
vat_number                      varchar(15)
vat_scheme                      enum NOT NULL DEFAULT 'Standard_Quarterly'  
                                  ('Standard_Quarterly','Standard_Monthly','Cash_Accounting','Flat_Rate','Not_Registered')
vat_return_period               enum NOT NULL DEFAULT 'Mar_Jun_Sep_Dec'
                                  ('Jan_Apr_Jul_Oct','Feb_May_Aug_Nov','Mar_Jun_Sep_Dec','Monthly')
utr                             varchar(13)
cis_status                      enum DEFAULT 'None'  ('Contractor','Subcontractor','Both','None')
registered_address              text NOT NULL
trading_address                 text
xero_org_id                     varchar(100)    -- populated in Prompt 5.1
xero_org_name                   varchar(255)    -- populated in Prompt 5.1
default_currency                varchar(3) NOT NULL DEFAULT 'GBP'
incorporation_date              date
year_end                        varchar(5)    -- MM-DD format, e.g. "03-31"
el_insurance_expires            date
pl_insurance_expires            date
pi_insurance_expires            date
all_risks_insurance_expires     date
bank_name                       varchar(255)
bank_account_name               varchar(255)
bank_account_number_masked      varchar(10)    -- last 4 digits only
status                          enum NOT NULL DEFAULT 'Active'  ('Active','Dormant','Struck_off')
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (companies_house_number) WHERE companies_house_number IS NOT NULL
- UNIQUE (vat_number) WHERE vat_number IS NOT NULL
- INDEX (entity_type, status)
- INDEX (xero_org_id) WHERE xero_org_id IS NOT NULL
```

### UI

**List view** (`/entities`):
- Columns: Name, Type, Companies House #, VAT #, Status, Year End
- Filter: Type, Status
- Search: Name, Legal Name
- Action: "+ New Entity" button

**Detail view** (`/entities/:id`):
- Section: Identity (name, legal_name, type, companies_house_number, incorporation_date, year_end, status)
- Section: Tax (vat_number, vat_scheme, vat_return_period, utr, cis_status, default_currency)
- Section: Addresses (registered_address, trading_address)
- Section: Insurance (el_insurance_expires, pl_insurance_expires, pi_insurance_expires, all_risks_insurance_expires) — highlight dates <60 days in amber, <14 days in red, past in red with "EXPIRED"
- Section: Banking (bank_name, bank_account_name, bank_account_number_masked — entered as full 8 digits, only last 4 stored)
- Section: Xero (xero_org_id, xero_org_name — read-only until Prompt 5.1)
- Section: Notes (free text)

**Create form** (`/entities/new`):
- Same fields as detail view
- Validation: companies_house_number must be 8 characters if provided; vat_number format validated loosely (digits only).

### Business logic

**Insurance expiry alerts:**
- Scheduled job runs daily at 06:00 UTC.
- For each entity with non-null insurance dates, compute days until expiry.
- Create a notification (see Prompt 1.7) at days: 60, 30, 14, 7, 0.
- Notification type: `Insurance_Expiry`.
- Recipient: all users with `director` role who have access to this entity.

**Group hierarchy:**
- Detail view shows parent (if set) and children (entities where parent_entity_id = this id).
- Prevent cycles: cannot set parent_entity_id to self, and prevent circular chains.

**Deletion blocked:**
- Deletion blocked if any other row references this entity (will apply once projects/users etc. exist).
- Use `status = Struck_off` for retired entities instead.

### Permissions

For now (until Prompt 1.2 adds roles), hardcode all actions as superuser-only.

Permissions to register (used from Prompt 1.2):
- `entities.view`
- `entities.create`
- `entities.edit`
- `entities.delete`
- `entities.view_sensitive` (reveals banking + xero details)

### Seed data

On first system setup, create three entities:

```yaml
- name: SY Homes Ltd
  legal_name: SY Homes Limited
  entity_type: Parent
  parent_entity_id: null
  status: Active
  default_currency: GBP

- name: SY Homes (Shrewsbury) Ltd
  legal_name: SY Homes (Shrewsbury) Limited
  entity_type: SPV
  parent_entity_id: (id of SY Homes Ltd)
  status: Active
  default_currency: GBP

- name: SY Homes (Construction) Ltd
  legal_name: SY Homes (Construction) Limited
  entity_type: ConstructionCo
  parent_entity_id: (id of SY Homes Ltd)
  cis_status: Contractor
  status: Active
  default_currency: GBP
```

The Companies House number, VAT number, incorporation date, year end, addresses, and insurance expiries are entered manually by the admin after setup — not hardcoded.

### Acceptance criteria

- [ ] Three seeded entities visible in list view
- [ ] Can create a new entity (e.g. a new SPV) with all fields
- [ ] Parent-child hierarchy displays correctly
- [ ] Cannot create circular parent chain
- [ ] Insurance expiry alerts fire correctly at 60/30/14/7/0 days (test by setting a date)
- [ ] Companies House number and VAT number unique constraints enforced
- [ ] `updated_at` refreshed on every save
- [ ] Status = Struck_off hides entity from active filters but remains queryable

### Out of scope

- Xero organisation connection (Prompt 5.1 handles the OAuth flow that populates xero_org_id)
- Insurance document uploads (Prompt 4.2 handles documents)
- Bank feed integration (deferred — see Future Tasks)
- Group consolidation reporting (Phase 2+)

---

## Prompt 1.2 — Users, Roles, Permissions

**Dependencies:** Prompt 1.1 (entities)  
**Tables in this prompt:** `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, `user_role_entities`, `user_role_projects`  
**Estimated build time:** 3-5 days

This is the permission backbone. Get this right; everything else depends on it.

### Build these tables

**`users`** — every human and service account.
```
id                              uuid PK
email                           varchar(255) NOT NULL  -- lowercased
email_verified                  boolean NOT NULL DEFAULT false
email_verified_at               timestamp
password_hash                   text                   -- argon2id; null for SSO/service
password_algorithm              enum DEFAULT 'argon2id'  ('argon2id','bcrypt')
password_changed_at             timestamp
password_history                jsonb DEFAULT '[]'     -- last 5 hashes
first_name                      varchar(100) NOT NULL
last_name                       varchar(100) NOT NULL
display_name                    varchar(255)           -- defaults to "First Last"
job_title                       varchar(255)
phone                           varchar(20)            -- E.164
phone_verified                  boolean NOT NULL DEFAULT false
avatar_url                      text
user_type                       enum NOT NULL DEFAULT 'Internal'
                                  ('Internal','External_Subcontractor','External_Consultant','External_Funder','Service_Account')
primary_entity_id               uuid FK→entities.id ON DELETE SET NULL  -- display only
timezone                        varchar(50) NOT NULL DEFAULT 'Europe/London'
locale                          varchar(10) NOT NULL DEFAULT 'en-GB'
mfa_enabled                     boolean NOT NULL DEFAULT false
mfa_method                      enum  ('TOTP','SMS','Email')
mfa_secret_encrypted            text
mfa_backup_codes_encrypted      text                   -- 10 single-use, hashed
mfa_enforced_at                 timestamp
last_login_at                   timestamp
last_login_ip                   varchar(45)
failed_login_attempts           int NOT NULL DEFAULT 0
locked_until                    timestamp
password_reset_token_hash       text
password_reset_expires_at       timestamp
status                          enum NOT NULL DEFAULT 'Pending_Invitation'
                                  ('Pending_Invitation','Active','Suspended','Archived')
suspended_reason                text
archived_at                     timestamp
invitation_sent_at              timestamp
invitation_accepted_at          timestamp
invited_by_user_id              uuid FK→users.id
admin_notes                     text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (LOWER(email))
- INDEX (status, created_at)
- INDEX (user_type)
```

**`roles`** — named permission bundles.
```
id                  uuid PK
code                varchar(50) NOT NULL UNIQUE    -- e.g. "super_admin"
name                varchar(100) NOT NULL
description         text NOT NULL
is_system_role      boolean NOT NULL DEFAULT false
priority            int NOT NULL DEFAULT 50
created_at          timestamp NOT NULL DEFAULT now()
updated_at          timestamp NOT NULL DEFAULT now()
```

**`permissions`** — atomic grants.
```
id              uuid PK
code            varchar(100) NOT NULL UNIQUE   -- e.g. "projects.view_financials"
resource        enum NOT NULL                  -- see Resources list below
action          enum NOT NULL                  ('view','view_sensitive','create','edit','delete','approve','reopen','export','admin')
description     text NOT NULL
is_sensitive    boolean NOT NULL DEFAULT false
created_at      timestamp NOT NULL DEFAULT now()
```

Resources enum (for the `resource` field):
```
entities, projects, users, roles, audit, cost_codes, appraisals, budgets, actuals, 
commitments, budget_changes, cash_flow, programmes, programme_tasks, documents, 
document_registers, certificates, xero_connections, xero_bills, xero_invoices, 
xero_sync, system_config, notifications, reports
```

**`role_permissions`** — junction.
```
role_id         uuid FK→roles.id ON DELETE CASCADE
permission_id   uuid FK→permissions.id ON DELETE CASCADE
created_at      timestamp NOT NULL DEFAULT now()
PK (role_id, permission_id)
```

**`user_roles`** — assignment with scope.
```
id                      uuid PK
user_id                 uuid NOT NULL FK→users.id ON DELETE RESTRICT
role_id                 uuid NOT NULL FK→roles.id ON DELETE RESTRICT
entity_scope            enum NOT NULL DEFAULT 'All'  ('All','Specific')
project_scope           enum NOT NULL DEFAULT 'All'  ('All','Specific','None')
view_overrides          jsonb DEFAULT '[]'   -- array of permission codes to REMOVE
assigned_by_user_id     uuid NOT NULL FK→users.id
assigned_at             timestamp NOT NULL DEFAULT now()
expires_at              timestamp            -- for temp access
revoked_at              timestamp
revoked_by_user_id      uuid FK→users.id
revoked_reason          text
status                  enum NOT NULL DEFAULT 'Active'  ('Active','Expired','Revoked')
created_at              timestamp NOT NULL DEFAULT now()
updated_at              timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (user_id, status)
- INDEX (role_id)
- INDEX (expires_at) WHERE expires_at IS NOT NULL
```

**`user_role_entities`** — resolves "Specific" entity scope.
```
user_role_id    uuid FK→user_roles.id ON DELETE CASCADE
entity_id       uuid FK→entities.id ON DELETE CASCADE
created_at      timestamp NOT NULL DEFAULT now()
PK (user_role_id, entity_id)
```

**`user_role_projects`** — resolves "Specific" project scope (projects table built in Prompt 1.5; FK can be added then).
```
user_role_id    uuid FK→user_roles.id ON DELETE CASCADE
project_id      uuid   -- FK added in Prompt 1.5
created_at      timestamp NOT NULL DEFAULT now()
PK (user_role_id, project_id)
```

### UI

**`/users` list:**
- Columns: Name (avatar + display_name), Email, User Type, Status, MFA, Last Login, Roles (count)
- Filters: User Type, Status, Role
- Action: "+ Invite User" (handled in Prompt 1.3)

**`/users/:id` detail:**
- Section: Identity (name, email, phone, job title, avatar)
- Section: Access (user_type, primary_entity_id, status, roles — see below)
- Section: Security (MFA status, password changed date, last login, failed attempts, locked until)
- Section: Admin (admin_notes, invited by, invitation dates)
- Role assignments table (from user_roles): role, entity scope, project scope, expires, status, actions (revoke)

**Role assignment modal** ("+ Add Role"):
- Select role
- Select entity_scope (All / Specific — if Specific, multi-select entities)
- Select project_scope (All / Specific / None — if Specific, multi-select projects after Prompt 1.5)
- Optional expiry date
- Optional view_overrides (multi-select from role's permissions, which ones to REMOVE for this assignment)
- Submit → creates user_role row + cascading user_role_entities and user_role_projects rows

**`/roles` list:**
- Columns: Name, Code, Description, Permissions count, Users count, System
- Action: "+ New Role" (only non-system roles can be created/edited/deleted)

**`/roles/:id` detail:**
- Section: Identity (name, code, description, priority, is_system_role)
- Section: Permissions — checkbox matrix of all permissions, grouped by resource. Disabled for is_system_role=true.
- Section: Users holding this role (read-only list)

**`/permissions` list (admin-only):**
- Read-only. Grouped by resource. Shows code, action, description, is_sensitive.

### Business logic

**Password hashing:**
- argon2id with memory=64MB, iterations=3, parallelism=4.
- On password change: save old hash to `password_history` (keep last 5), reject if new matches any in history.
- Minimum 12 characters; complexity rules per NIST 800-63B (no composition rules, just length and breach check).

**MFA:**
- Required at login for super_admin, director, finance roles.
- Voluntary for all others.
- On MFA enrolment: generate TOTP secret (encrypted), display QR, user confirms, generate 10 backup codes (hashed), show once.
- Backup code use: marks as used; once all used, prompt regeneration.

**Account lockout:**
- 5 failed login attempts within 15 min → lock for 15 min.
- Repeated lockouts → escalating durations (15 → 30 → 60 min).
- Super-admin can unlock manually.

**Effective permissions computation:**
For a user, effective permissions = union of all active user_roles:
```
foreach user_role where status = Active AND (expires_at IS NULL OR expires_at > now()):
    role_perms = permissions granted to user_role.role_id
    effective_perms += role_perms - user_role.view_overrides
```
Scope applied on access:
- If entity_scope = Specific: only permissions apply to listed entities
- If project_scope = Specific: only permissions apply to listed projects

**Cached permission computation:**
- Cache user's effective permissions on login (refresh on role change or every 15 min).
- Store in user session context — don't recompute on every request.

**Self-approval detection (applies to all approval actions built later):**
- If submitter_user_id == approver_user_id on any approval:
  - Show confirmation modal: "You are approving your own submission. This will be logged. Continue?"
  - On confirm: proceed with approval, but write `metadata.self_approval = true` into the audit_log entry.

**Expiry scheduler:**
- Daily job: set `user_roles.status = Expired` WHERE `expires_at < now()` AND `status = Active`.

**User archive:**
- `status = Archived` hides from active lists but preserves all FK links.
- Archived users cannot log in.
- PII scrub on "Delete user data" action (replaces first_name, last_name, email with "[Deleted User X]" where X is user ID — preserves FK integrity for audit trail).

### Permissions

Self-registered permissions (this module creates its own permissions):
```
users.view, users.view_sensitive, users.create, users.edit, users.delete, users.admin
roles.view, roles.edit, roles.admin
```

Access control bootstrapping:
- First user created during initial setup is granted super_admin role automatically with entity_scope=All, project_scope=All.
- After that, super_admin can grant roles to others.

### Seed data

**Roles (10 seeded):**
```yaml
- code: super_admin
  name: Super Administrator
  description: Full system access including security and impersonation.
  is_system_role: true
  priority: 1

- code: director
  name: Director
  description: Full group access except super-admin-only actions.
  is_system_role: true
  priority: 10

- code: project_manager
  name: Project Manager
  description: Full operational control on assigned projects.
  is_system_role: true
  priority: 20

- code: finance
  name: Finance
  description: Financial records, Xero sync, reporting access.
  is_system_role: true
  priority: 20

- code: site_manager
  name: Site Manager
  description: Programme and document access on assigned projects.
  is_system_role: true
  priority: 30

- code: sales
  name: Sales
  description: Plot and buyer records, sales reporting.
  is_system_role: true
  priority: 30

- code: read_only
  name: Read Only
  description: Can view assigned records; no edit/approve.
  is_system_role: true
  priority: 50

- code: investor_read_only
  name: Investor
  description: Dashboard and report access only; no individual record detail.
  is_system_role: true
  priority: 50

- code: subcontractor_portal
  name: Subcontractor Portal
  description: External — scoped portal access.
  is_system_role: true
  priority: 70

- code: consultant_portal
  name: Consultant Portal
  description: External — scoped portal access.
  is_system_role: true
  priority: 70
```

**Permissions (~90 seeded):**

Generate by cross-product: for each resource × each action, create a permission if the combination makes sense. See the full list in `SY_Homes_Data_Model.xlsx` → Enums Reference tab.

Example entries:
```
entities.view               resource=entities,    action=view,            sensitive=false
entities.view_sensitive     resource=entities,    action=view_sensitive,  sensitive=true  (banking, Xero IDs)
entities.create             resource=entities,    action=create,          sensitive=false
entities.edit               resource=entities,    action=edit,            sensitive=false
entities.delete             resource=entities,    action=delete,          sensitive=false
entities.admin              resource=entities,    action=admin,           sensitive=true  (grants all entity ops)

projects.view               resource=projects,    action=view,            sensitive=false
projects.view_financials    resource=projects,    action=view_sensitive,  sensitive=true
projects.create             resource=projects,    action=create,          sensitive=false
...
```

Full matrix enumerated in a seed file — do not hardcode in application.

**Role-permission mapping (seeded JSON file):**

```yaml
super_admin: [all permissions]

director:
  - all permissions EXCEPT:
    - users.admin (cannot grant super_admin role)
    - roles.admin (cannot edit system roles)
    - audit.admin (cannot delete audit entries — nobody can, but this makes it explicit)

project_manager:
  - projects.view, projects.view_financials, projects.edit
  - appraisals.view, appraisals.create, appraisals.edit, appraisals.approve (with threshold)
  - budgets.view, budgets.view_sensitive, budgets.edit
  - actuals.view, actuals.create, actuals.edit
  - commitments.view, commitments.create, commitments.edit
  - budget_changes.view, budget_changes.create, budget_changes.approve (≤£5k)
  - cash_flow.view, cash_flow.edit
  - programmes.view, programmes.edit
  - programme_tasks.view, programme_tasks.create, programme_tasks.edit
  - documents.view, documents.create, documents.edit
  - document_registers.view, document_registers.edit
  - certificates.view
  - reports.view, reports.export

finance:
  - entities.view, entities.view_sensitive, entities.edit
  - projects.view, projects.view_financials
  - appraisals.view
  - budgets.view, budgets.view_sensitive
  - actuals.view, actuals.view_sensitive, actuals.create, actuals.edit, actuals.approve
  - commitments.view, commitments.view_sensitive
  - budget_changes.view, budget_changes.approve (≤£25k with PM)
  - cash_flow.view, cash_flow.view_sensitive, cash_flow.edit
  - xero_connections.view, xero_connections.admin
  - xero_bills.view, xero_invoices.view, xero_sync.admin
  - reports.view, reports.export

site_manager:
  - projects.view
  - programmes.view
  - programme_tasks.view, programme_tasks.edit  (only assigned)
  - documents.view, documents.create
  - document_registers.view, document_registers.edit
  - certificates.view

sales:
  - projects.view
  - reports.view (sales reports only)
  # Phase 5: plots.view/edit, buyers.view/edit

read_only:
  - entities.view
  - projects.view
  - appraisals.view
  - budgets.view
  - programmes.view
  - documents.view
  - reports.view

investor_read_only:
  - projects.view (project list + high-level stats only, no detail)
  - reports.view (investor reports only)

subcontractor_portal:
  - documents.view  (scoped: only docs tagged to their subcontract)
  - documents.create (scoped: uploads into their folder)
  # Phase 4: subcontract_valuations.view/create

consultant_portal:
  - documents.view  (scoped: only docs shared with them)
  - documents.create
```

### Acceptance criteria

- [ ] Can create first super_admin user during initial setup
- [ ] 10 roles seeded and visible on /roles list
- [ ] ~90 permissions seeded and visible on /permissions list
- [ ] Can assign a role to a user with entity/project scope
- [ ] User with `director` role can view all entities
- [ ] User with `project_manager` role scoped to Entity A can view Entity A but not Entity B
- [ ] view_overrides correctly removes specific permissions from an assignment
- [ ] Expired user_roles status changes to Expired via scheduled job
- [ ] Password change rejects reuse of last 5 passwords
- [ ] MFA flow works end-to-end (TOTP enrolment, login prompt, backup codes)
- [ ] Account locks after 5 failed attempts, unlocks after 15 min
- [ ] Super-admin can manually unlock account
- [ ] Self-approval modal shows when submitter = approver (test once approval workflows exist in later prompts)
- [ ] Archived users cannot log in but remain in FK references

### Out of scope

- Session management and login history (Prompt 1.3)
- Password reset flow (Prompt 1.3)
- SSO integration (Prompt 1.3)
- API keys (Prompt 1.3)
- Audit logging of role changes (Prompt 1.4 — wired retroactively)
- Project scope FK to projects (Prompt 1.5 adds the FK)

---

## Prompt 1.3 — Sessions, Login History, Invitations, SSO, API Keys

**Dependencies:** Prompts 1.1, 1.2  
**Tables in this prompt:** `user_sessions`, `user_login_history`, `user_invitations`, `external_identity_providers`, `api_keys`  
**Estimated build time:** 2-3 days

### Build these tables

**`user_sessions`** — active sessions with revocation support.
```
id                          uuid PK
user_id                     uuid NOT NULL FK→users.id ON DELETE CASCADE
access_token_hash           text NOT NULL           -- SHA-256; 15 min TTL
refresh_token_hash          text NOT NULL           -- SHA-256; 30d (90d "remember me")
ip_address                  varchar(45) NOT NULL
user_agent                  text NOT NULL
device_fingerprint          text
device_name                 varchar(100)            -- user-editable
location_country            varchar(50)
location_city               varchar(100)
impersonator_user_id        uuid FK→users.id        -- if super_admin impersonating
last_active_at              timestamp NOT NULL DEFAULT now()
expires_at                  timestamp NOT NULL
revoked_at                  timestamp
revoked_reason              enum  ('Logout','Password_Change','Admin_Revoke','Suspicious_Activity','Expiry')
created_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (user_id, revoked_at)
- INDEX (expires_at)
```

**`user_login_history`** — forensic trail (append-only, 2+ year retention).
```
id                  uuid PK
user_id             uuid FK→users.id  -- nullable (unknown email)
email_attempted     varchar(255) NOT NULL
event_type          enum NOT NULL   ('Login_Success','Login_Failed','Logout','Password_Change','Password_Reset_Requested','Password_Reset_Completed','MFA_Success','MFA_Failed','MFA_Enrolled','MFA_Disabled','Account_Locked','Account_Unlocked')
failure_reason      enum   ('Invalid_Password','Unknown_Email','MFA_Invalid','Account_Locked','Account_Suspended','Invitation_Expired')
ip_address          varchar(45) NOT NULL
user_agent          text NOT NULL
location_country    varchar(50)
session_id          uuid FK→user_sessions.id
created_at          timestamp NOT NULL DEFAULT now()  -- immutable

Indexes:
- INDEX (user_id, created_at DESC)
- INDEX (email_attempted, created_at DESC)
- INDEX (event_type)
```

**`user_invitations`** — invitation flow.
```
id                              uuid PK
email                           varchar(255) NOT NULL
invitation_token_hash           text NOT NULL        -- SHA-256 of raw token
invited_by_user_id              uuid NOT NULL FK→users.id
pre_assigned_role_id            uuid NOT NULL FK→roles.id
pre_assigned_entity_scope       enum NOT NULL DEFAULT 'All'
pre_assigned_project_scope      enum NOT NULL DEFAULT 'All'
pre_assigned_entities           jsonb DEFAULT '[]'
pre_assigned_projects           jsonb DEFAULT '[]'
expires_at                      timestamp NOT NULL DEFAULT (now() + interval '7 days')
accepted_at                     timestamp
accepted_user_id                uuid FK→users.id
status                          enum NOT NULL DEFAULT 'Pending'  ('Pending','Accepted','Expired','Revoked')
personal_message                text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (invitation_token_hash)
- INDEX (email, status)
```

**`external_identity_providers`** — SSO links.
```
id                          uuid PK
user_id                     uuid NOT NULL FK→users.id ON DELETE CASCADE
provider                    enum NOT NULL  ('Google','Microsoft','Apple')
provider_user_id            varchar(255) NOT NULL
provider_email              varchar(255) NOT NULL
access_token_encrypted      text
refresh_token_encrypted     text
scopes_granted              jsonb DEFAULT '[]'
linked_at                   timestamp NOT NULL DEFAULT now()
last_used_at                timestamp
unlinked_at                 timestamp
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (provider, provider_user_id)
- INDEX (user_id)
```

**`api_keys`** — service-to-service auth.
```
id                  uuid PK
owning_user_id      uuid NOT NULL FK→users.id  -- must be user_type=Service_Account
name                varchar(255) NOT NULL
key_prefix          varchar(10) NOT NULL       -- first 8 chars for display
key_hash            text NOT NULL              -- SHA-256
scopes              jsonb NOT NULL DEFAULT '[]' -- permission codes
last_used_at        timestamp
last_used_ip        varchar(45)
expires_at          timestamp
revoked_at          timestamp
created_at          timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (key_hash)
- INDEX (owning_user_id)
```

### UI

**`/profile/sessions`** (user's own sessions):
- List active sessions: device, location, last active, current session indicator.
- "Revoke" button on each.
- "Revoke all other sessions" button.

**`/users/:id/sessions`** (admin):
- Same view but for any user.

**`/users/:id/login-history`** (admin):
- Paginated list with filters: event type, date range.
- Shows user_id (if resolved), email_attempted, event_type, failure_reason, IP, UA, country, timestamp.

**`/invitations`** (admin):
- List: email, role, status, expires, invited by, sent.
- "+ Invite User" button.

**Invitation flow:**
1. Admin fills form (email, role, entity/project scope, optional message).
2. System generates token (cryptographically random 32 bytes), stores SHA-256 hash.
3. Email sent to invitee with link `/accept-invite?token={raw_token}`.
4. Invitee clicks → lands on acceptance form: set password, MFA enrolment (if required by role).
5. On submit: create user, create user_roles from pre_assigned_*, mark invitation Accepted.

**`/api-keys`** (admin):
- List existing keys (name, prefix, scopes, last used, expires, status).
- "+ New API Key" → form: name, scopes (multi-select), expiry date.
- On create: show key **once** in modal with copy button; after closing, only hash stored.

**Login page:**
- Email + password.
- "Sign in with Google / Microsoft / Apple" (if SSO providers configured).
- MFA challenge if required.
- "Forgot password" link.

**SSO link flow (in profile):**
- "Link Google account" button → OAuth flow.
- Shows linked providers; "Unlink" action (soft — sets unlinked_at, doesn't delete for audit).

### Business logic

**Session management:**
- Access token: short-lived (15 min), stored as signed JWT or opaque with hash in DB.
- Refresh token: 30 days default, 90 days if user ticks "Remember me".
- Rotation: on every refresh, old refresh token revoked, new one issued.
- Idle timeout: 60 min without activity forces re-auth.
- New-country detection: if `location_country` differs from user's recent logins, email alert.

**Suspicious activity detection:**
- Impossible travel: two logins from distant geographies within short time window → flag session, email user.
- Unusual time: login outside user's typical hours → lower severity flag.

**Password reset:**
- Request: user enters email → generate token, store hash, email raw token with link expiring in 1 hour.
- Complete: validate token, check expiry, require MFA if enabled, set new password.
- On completion: revoke all user's sessions (force re-login).

**Invitation expiry:**
- Daily job: set status=Expired on invitations past expires_at.
- Expired invitations cannot be accepted; require new invitation.

**API key usage:**
- On each API request: hash provided key, look up by hash, check revoked_at/expires_at, update last_used_at/last_used_ip.
- Key prefix displayed for debugging ("Which key made this request?") without exposing full key.

### Permissions

- `users.admin` — required to manage other users' sessions, see login history, send invitations, manage API keys.
- Users can always view/manage their **own** sessions without this permission.

### Seed data

**Service account for Xero webhooks** (populated on first Xero connection, Prompt 5.1):
```yaml
user:
  email: xero-webhook@sy-homes.internal
  user_type: Service_Account
  status: Active
  first_name: Xero
  last_name: Webhook Receiver
api_key:
  name: Xero Webhook Receiver
  scopes: [xero_sync.admin]
  expires_at: null
```

### Acceptance criteria

- [ ] Login creates user_session row with hashed tokens
- [ ] Refresh flow rotates tokens correctly
- [ ] Logout revokes session
- [ ] Failed login creates user_login_history row with failure_reason
- [ ] Idle timeout forces re-auth after 60 min
- [ ] New-country login sends email alert
- [ ] Password reset flow works end-to-end
- [ ] Invitation flow: admin sends → email received with link → invitee accepts → user created with pre-assigned role
- [ ] Expired invitations cannot be used
- [ ] SSO link/unlink flow works for Google (primary test provider)
- [ ] API key created shows raw key once, never again
- [ ] API key auth works on request with SHA-256 hash lookup
- [ ] User can view and revoke their own sessions
- [ ] Admin can view any user's sessions and login history

### Out of scope

- WebAuthn / FIDO2 security keys (Future Tasks)
- API call anomaly detection (Future Tasks)
- Password breach detection via Have I Been Pwned (Future Tasks)
- IP allow-listing for sensitive roles (Future Tasks)

---

## Prompt 1.4 — Audit Log

**Dependencies:** Prompts 1.1, 1.2, 1.3  
**Tables in this prompt:** `audit_log`  
**Estimated build time:** 1-2 days

This is the append-only forensic spine. Wire it into every write operation from this point forward.

### Build this table

```
audit_log
─────────────────────────────────────────────
id                          uuid PK
actor_user_id               uuid FK→users.id           -- null for system actions
impersonator_user_id        uuid FK→users.id           -- set under impersonation
action                      enum NOT NULL
                              ('Create','Update','Delete','Approve','Reject','Reopen',
                               'Login','Logout','Export','Permission_Change',
                               'Stage_Change','Status_Change')
resource_type               varchar(100) NOT NULL       -- table name
resource_id                 uuid NOT NULL
entity_id                   uuid FK→entities.id         -- for entity filter
project_id                  uuid                        -- FK added in Prompt 1.5
field_changes               jsonb     -- array: [{field, old, new}] — sensitive fields REDACTED
metadata                    jsonb     -- context-specific (self_approval, reasons, etc.)
ip_address                  varchar(45)
user_agent                  text
session_id                  uuid FK→user_sessions.id
created_at                  timestamp NOT NULL DEFAULT now()   -- immutable

Indexes:
- INDEX (actor_user_id, created_at DESC)
- INDEX (resource_type, resource_id)
- INDEX (entity_id, created_at DESC)
- INDEX (project_id, created_at DESC)
- INDEX (created_at DESC)
```

### Enforce append-only

At database level, add triggers preventing UPDATE and DELETE:

```sql
CREATE OR REPLACE FUNCTION audit_log_no_modify()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_block_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify();

CREATE TRIGGER audit_log_block_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify();
```

### Build the audit middleware

Every write to a significant table should go through an audit middleware that:

1. Captures the current session context (actor_user_id, impersonator_user_id, session_id, IP, UA).
2. Records the pre-change state of affected fields.
3. Performs the write.
4. Records the post-change state.
5. Writes an audit_log entry with the diff.

**Sensitive fields auto-redacted** (substituted with "[REDACTED]" in field_changes):
```
password_hash, password_history, mfa_secret_encrypted, mfa_backup_codes_encrypted,
password_reset_token_hash, access_token_encrypted, refresh_token_encrypted,
access_token_hash, refresh_token_hash, invitation_token_hash, key_hash
```

### UI

**`/audit`** (admin):
- Paginated list: timestamp, actor (name + avatar), action, resource_type, resource_id (linked to record), summary.
- Filters: date range, actor, resource_type, action, entity, project.
- Detail modal on click: full field_changes, metadata, IP, UA, session ID.
- Export CSV / JSON.

**On any record detail page** (projects, users, budgets, etc.):
- "Audit Trail" tab showing audit_log entries for this resource_id.
- Same filters as global /audit but scoped.

### Business logic

**Retention:**
- Financial / contractual writes (actuals, budget_changes, invoices, contracts, valuations): indefinite retention.
- Authentication events (login, logout, password_change): 2+ years.
- Other: 7+ years minimum (UK statute of limitations baseline).
- Scheduled purge job runs monthly for records past their retention date — but with explicit allow-list by resource_type.

**Self-approval detection:**
When an approval action fires, check if `actor_user_id == record.submitted_by_user_id` (or equivalent). If so, set `metadata.self_approval = true`.

**Impersonation tracking:**
If a super_admin impersonates another user, both IDs appear: `actor_user_id` = the impersonated user (what they did), `impersonator_user_id` = the super_admin (who was really behind it).

### Permissions

- `audit.view` — view audit log (scoped by entity/project per user_role)
- `audit.export` — export audit log
- `audit.admin` — view all audit log across all entities/projects
- No action grants the ability to modify audit_log.

### Acceptance criteria

- [ ] Creating an entity writes an audit_log row with action=Create, field_changes showing new values
- [ ] Updating a user writes action=Update, field_changes showing only changed fields with old/new
- [ ] Password change records audit_log entry with password_hash field REDACTED in field_changes
- [ ] Impersonated action has impersonator_user_id set; actor_user_id = impersonated user
- [ ] DB-level UPDATE on audit_log raises error
- [ ] DB-level DELETE on audit_log raises error
- [ ] Global /audit page loads with pagination and filters
- [ ] Record detail audit tab shows only that record's history
- [ ] Export CSV produces structured file with all visible fields
- [ ] Retention purge job respects resource_type allow-list

### Out of scope

- External audit log export (to CloudTrail / SIEM) — Future Tasks
- Real-time anomaly detection on audit patterns — Future Tasks

---

## Prompt 1.5 — Projects, Project Team Members

**Dependencies:** Prompts 1.1, 1.2, 1.3, 1.4  
**Tables in this prompt:** `projects`, `project_team_members`  
**Estimated build time:** 2-3 days

The central record. Everything from here on hangs off a project.

### Build `projects`

```
projects
─────────────────────────────────────────────
id                              uuid PK
project_code                    varchar(20) NOT NULL UNIQUE  -- auto-generated, immutable
name                            varchar(255) NOT NULL
project_type                    enum NOT NULL
                                  ('Pure_Dev','Dev_Build','DB_Contract','JV','Main_Contract')
parent_project_id               uuid FK→projects.id ON DELETE SET NULL  -- phased schemes
primary_entity_id               uuid NOT NULL FK→entities.id ON DELETE RESTRICT
construction_entity_id          uuid FK→entities.id ON DELETE RESTRICT
land_ownership_method           enum NOT NULL
                                  ('Direct_Purchase','Option','Conditional_Contract','JV_Contribution','Existing_Holding')
site_address                    text NOT NULL
site_postcode                   varchar(10) NOT NULL
local_authority                 varchar(100)
site_area_ha                    decimal(10,4)
site_area_acres                 decimal(10,4)      -- auto-calc from ha × 2.47105
tenure                          enum NOT NULL DEFAULT 'Freehold'
                                  ('Freehold','Leasehold','Long_Leasehold','Option','Conditional','Other')
lease_years_remaining           int
land_type                       enum  ('Greenfield','Brownfield','Mixed','Urban_Infill','Garden_Land')
planning_ref                    varchar(50)
planning_type                   enum  ('Full','Outline','Reserved_Matters','Hybrid','Permitted_Dev','Prior_Approval')
planning_status                 enum  ('Pre_App','Submitted','Approved','Refused','Appeal','Not_Required')
planning_approval_date          date
planning_expiry_date            date           -- auto-calc on approval_date change; editable
implementation_required         boolean NOT NULL DEFAULT true
s106_required                   boolean DEFAULT false
cil_required                    boolean DEFAULT false
vat_opt_to_tax                  boolean DEFAULT false
vat_opt_to_tax_date             date
units_target                    int
units_actual                    int            -- auto-populated from plots (Phase 5)
affordable_housing_pct          decimal(5,2) DEFAULT 0
target_start_date               date
target_pc_date                  date
actual_start_date               date
actual_pc_date                  date
current_stage                   enum NOT NULL DEFAULT 'Lead'
                                  ('Lead','Appraisal','Deal_Pipeline','Planning','Pre_Con','Construction','Sales','Post_Completion','Closed','Dead')
stage_entered_at                timestamp NOT NULL DEFAULT now()
status                          enum NOT NULL DEFAULT 'Active'
                                  ('Active','On_Hold','Dead','Complete')
dead_reason                     text
gdv_actual                      decimal(14,2) DEFAULT 0    -- cached
build_cost_actual               decimal(14,2) DEFAULT 0    -- cached
all_in_cost_actual              decimal(14,2) DEFAULT 0    -- cached
profit_actual                   decimal(14,2) DEFAULT 0    -- cached
margin_actual_pct               decimal(6,3) DEFAULT 0     -- cached
financials_refreshed_at         timestamp
project_lead_user_id            uuid NOT NULL FK→users.id ON DELETE RESTRICT
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (project_code)
- INDEX (primary_entity_id, status)
- INDEX (current_stage, status)
- INDEX (project_lead_user_id)
- INDEX (parent_project_id) WHERE parent_project_id IS NOT NULL
```

### Build `project_team_members`

```
project_team_members
─────────────────────────────────────────────
id                  uuid PK
project_id          uuid NOT NULL FK→projects.id ON DELETE CASCADE
user_id             uuid NOT NULL FK→users.id ON DELETE RESTRICT
role_on_project     enum NOT NULL
                      ('Project_Lead','Site_Manager','Sales_Lead','QS','Design_Lead','Commercial_Lead','Other')
assigned_at         timestamp NOT NULL DEFAULT now()
unassigned_at       timestamp
is_primary          boolean NOT NULL DEFAULT false
notes               text
created_at          timestamp NOT NULL DEFAULT now()
updated_at          timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (project_id, role_on_project) WHERE is_primary = true
- INDEX (project_id)
- INDEX (user_id)
```

### Now add `project_id` FK to `user_role_projects` and `audit_log`

```sql
ALTER TABLE user_role_projects
    ADD CONSTRAINT fk_user_role_projects_project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE audit_log
    ADD CONSTRAINT fk_audit_log_project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
```

### Project code generation

On creation:
1. Take first 3 letters of project name, uppercase (strip spaces/special chars). If <3 letters, pad with X.
2. Find highest sequence for that prefix + 1.
3. Format: `{PREFIX}-{SEQ:03d}` e.g. "GAR-001", "NEW-042".
4. Allow override at create time (validated unique), but immutable after.

### UI

**`/projects` list:**
- Columns: Project Code, Name, Type, Primary Entity, Stage, Status, Target PC, Margin %, Project Lead
- Filters: Type, Stage, Status, Entity, Lead
- Search: Name, Code, Address, Postcode
- Grouping toggle: by Entity, by Stage, by Type
- Action: "+ New Project"

**`/projects/:id` detail:**
- Header: Project code badge, name, status badge (colored by stage), project lead avatar
- Tabs: Overview | Appraisal | Budget | Cash Flow | Programme | Documents | Xero | Team | Audit
- Overview tab sections:
  - Identity: project_type, parent_project, primary_entity, construction_entity, land_ownership_method
  - Location: site_address, site_postcode, local_authority, site_area_ha (with auto-computed acres)
  - Tenure: tenure, lease_years_remaining (if leasehold)
  - Planning: planning_ref, planning_type, planning_status, approval_date, expiry_date (with countdown), implementation_required, s106_required, cil_required
  - VAT: vat_opt_to_tax, vat_opt_to_tax_date
  - Schedule: target_start_date, target_pc_date, actual_start_date, actual_pc_date
  - Stage: current_stage with history dropdown, stage_entered_at
  - Commercials (cached): units_target, units_actual, affordable_housing_pct, gdv_actual, build_cost_actual, all_in_cost_actual, profit_actual, margin_actual_pct, financials_refreshed_at
  - Team: project_lead, other team members (link to Team tab)

**Team tab:**
- List of project_team_members with role_on_project, assigned_at, primary flag.
- "+ Add Team Member" action.

**Stage change action:**
- Button on detail view: "Move to next stage" → dropdown showing valid next stages.
- On change: audit_log entry with action=Stage_Change, old and new stage in field_changes.
- Non-sequential allowed (e.g. Construction → Sales skipping Post_Completion) but flagged for review in audit.

**Status change action:**
- Mark Dead: requires dead_reason text; sets status=Dead, stage=Dead.
- Mark Complete: auto on final plot completion (Phase 5); manually allowed.
- Put On Hold: toggle, no reason required but appears in audit.

### Business logic

**Planning expiry auto-calc:**
- On change to planning_approval_date OR planning_type:
  - If planning_type in [Full, Outline, Hybrid, Permitted_Dev, Prior_Approval]: expiry = approval + 3 years.
  - If planning_type = Reserved_Matters: expiry = approval + 2 years.
  - User can override; audit tracks manual change.

**Planning expiry alerts:**
- Scheduled daily: for projects where implementation_required=true AND actual_start_date IS NULL:
  - Alert at 12 months / 6 months / 3 months / 1 month to expiry.
  - Notification type: `Deadline_Approaching`.
  - Recipients: project lead, directors with scope.

**Stage history:**
- Stage changes captured in audit_log. Detail view can query audit_log to show stage progression timeline.

**Site area conversion:**
- Entering ha auto-fills acres (ha × 2.47105).
- Entering acres auto-fills ha (acres × 0.404686).

**Cached financials refresh:**
- Triggered on actuals/commitments/sales writes (once those tables exist).
- Async job computes: gdv_actual, build_cost_actual, all_in_cost_actual, profit_actual, margin_actual_pct.
- Sets financials_refreshed_at.
- Showed as stale if refreshed_at > 15 min ago with a "Refresh now" button.

**Delete vs archive:**
- Delete blocked once ANY financial or contractual record exists for the project.
- Use status=Dead or Complete to archive.

**Team management:**
- Assigning a user to a project does NOT grant them access — access is via user_roles with project_scope.
- Team membership is purely informational.
- One primary per (project, role_on_project) — validated.
- Assigning a team member with role=Project_Lead also updates projects.project_lead_user_id (and vice versa).

### Permissions

Self-registered:
```
projects.view, projects.view_financials, projects.create, projects.edit, projects.delete, projects.approve
```

- `projects.view_financials` — required to see gdv/cost/profit/margin fields
- `projects.delete` — blocked if financial records exist

### Seed data

None. Projects are created per site.

### Acceptance criteria

- [ ] Can create a project with all required fields
- [ ] Project code auto-generated in "PFX-NNN" format
- [ ] Project code immutable after creation (edit UI disables the field)
- [ ] Land area ha ↔ acres conversion works both ways
- [ ] Planning expiry auto-calculates from approval date + planning type
- [ ] Planning expiry alerts fire at 12/6/3/1 months
- [ ] Stage change recorded in audit_log with Stage_Change action
- [ ] Non-sequential stage changes allowed but flagged in audit metadata
- [ ] project_team_members can be added/removed
- [ ] Only one primary per (project, role) enforced
- [ ] Setting a team member as Project_Lead role updates projects.project_lead_user_id
- [ ] User with project_scope=Specific sees only assigned projects
- [ ] Delete blocked once any dependent record exists (test once actuals exist in later prompt)
- [ ] Cached financials show stale indicator after 15 min
- [ ] audit_log.project_id FK wired correctly (historical audits can now link to projects)
- [ ] user_role_projects.project_id FK wired correctly

### Out of scope

- Appraisal tab content (Prompt 2.2)
- Budget tab content (Prompt 2.4)
- Cash flow tab content (Prompt 2.7)
- Programme tab content (Prompt 3.2)
- Documents tab content (Prompt 4.2)
- Xero tab content (Prompt 5.2)
- Related plot records (Phase 5)
- Phase 2 stages: Deal_Pipeline workflow, Planning conditions management

---

## Prompt 1.6 — Cost Codes

**Dependencies:** Prompts 1.1, 1.2, 1.4, 1.5  
**Tables in this prompt:** `cost_code_sections`, `cost_codes`, `cost_code_subcategories`, `cost_code_entity_mapping`, `project_cost_codes`  
**Estimated build time:** 2-3 days

The classification system. Seed this early and well — every financial record uses it.

### Build these tables

**`cost_code_sections`** — 11 top-level groupings.
```
id                              uuid PK
code                            varchar(30) NOT NULL UNIQUE     -- slug: "acquisition"
name                            varchar(100) NOT NULL
display_order                   int NOT NULL
is_direct_cost                  boolean NOT NULL DEFAULT true    -- COS vs Overhead
default_p_and_l_category        enum NOT NULL DEFAULT 'COS'    ('COS','Overhead','Finance','Tax')
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
```

**`cost_codes`** — 19 prefixes × sequences (~120 codes total).
```
id                              uuid PK
code                            varchar(10) NOT NULL UNIQUE     -- "SUB-03", immutable
prefix                          varchar(3) NOT NULL            -- 3 letters
sequence                        int NOT NULL                   -- 2-digit number
name                            varchar(255) NOT NULL          -- e.g. "Piling"
description                     text
section_id                      uuid NOT NULL FK→cost_code_sections.id
nrm_reference                   varchar(20)                    -- NRM2 ref
applies_to_parent               boolean NOT NULL DEFAULT false
applies_to_spv                  boolean NOT NULL DEFAULT true
applies_to_construction_co      boolean NOT NULL DEFAULT false
default_entity                  enum NOT NULL DEFAULT 'SPV'
                                  ('Parent','SPV','Construction_Co','Context_Dependent')
entity_rule_notes               text
xero_nominal_code               varchar(10)
xero_nominal_name               varchar(255)
is_vattable                     boolean NOT NULL DEFAULT true
vat_treatment                   enum NOT NULL DEFAULT 'Standard'
                                  ('Standard','Reduced','Zero_New_Build','Exempt','Reverse_Charge','Mixed')
is_cis_applicable               boolean NOT NULL DEFAULT false
is_retention_applicable         boolean NOT NULL DEFAULT false
is_capitalisable                boolean NOT NULL DEFAULT true
status                          enum NOT NULL DEFAULT 'Active' ('Active','Retired')
retired_at                      timestamp
retired_reason                  text
replaced_by_code_id             uuid FK→cost_codes.id    -- self-ref for code evolution
display_order                   int NOT NULL
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (code)
- UNIQUE (prefix, sequence)
- INDEX (section_id)
- INDEX (status)
```

**`cost_code_subcategories`** — granular detail under cost codes (~792 rows).
```
id                      uuid PK
cost_code_id            uuid NOT NULL FK→cost_codes.id ON DELETE RESTRICT
code                    varchar(15) NOT NULL UNIQUE    -- "SUB-03.01"
name                    varchar(255) NOT NULL
description             text
default_unit            enum  ('each','m','m²','m³','tonnes','sum','hours','day','week')
display_order           int NOT NULL
status                  enum NOT NULL DEFAULT 'Active' ('Active','Retired')
created_at              timestamp NOT NULL DEFAULT now()
updated_at              timestamp NOT NULL DEFAULT now()
```

**`cost_code_entity_mapping`** — per-entity overrides.
```
id                                  uuid PK
cost_code_id                        uuid NOT NULL FK→cost_codes.id ON DELETE CASCADE
entity_id                           uuid NOT NULL FK→entities.id ON DELETE CASCADE
is_allowed                          boolean NOT NULL DEFAULT true
xero_nominal_code_override          varchar(10)
notes                               text
created_at                          timestamp NOT NULL DEFAULT now()
updated_at                          timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (cost_code_id, entity_id)
```

**`project_cost_codes`** — which codes enabled per project.
```
id                          uuid PK
project_id                  uuid NOT NULL FK→projects.id ON DELETE CASCADE
cost_code_id                uuid NOT NULL FK→cost_codes.id ON DELETE RESTRICT
is_enabled                  boolean NOT NULL DEFAULT true
project_override_name       varchar(255)
notes                       text
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (project_id, cost_code_id)
- INDEX (project_id)
```

### UI

**`/cost-codes`** (admin):
- Tree view: sections → cost codes → subcategories.
- Expand/collapse sections.
- Action: "+ New Cost Code", "+ New Subcategory".

**`/cost-codes/:id`** (admin):
- Section: Identity (code, prefix, sequence, name, description, section)
- Section: Entity Applicability (default_entity, applies_to_* booleans, entity_rule_notes)
- Section: Xero Mapping (xero_nominal_code, xero_nominal_name)
- Section: Tax Treatment (is_vattable, vat_treatment, is_cis_applicable, is_retention_applicable, is_capitalisable)
- Section: Lifecycle (status, retired_at, retired_reason, replaced_by)
- Entity Overrides tab: cost_code_entity_mapping rows per entity with allow/deny and nominal override.

**`/projects/:id/cost-codes`** (project team):
- Tree view: sections → enabled/disabled cost codes for this project.
- Toggle per code to enable/disable.
- Override name field per enabled code.

### Business logic

**Auto-populate `project_cost_codes` on project creation:**

When a project is created, populate `project_cost_codes` based on `project_type`:

```
Pure_Dev:
  enabled: ACQ, PLN, DES, FAC, SAL, FIN, OHD, ACC, CTG
  disabled: SUB, SUP, INT, FIT, SER, PRE, EXB, EXT, PRL, MCP

Dev_Build:
  enabled: ALL active cost codes

DB_Contract:
  enabled: ALL except SAL (HA client pays directly)

JV:
  enabled: ALL active cost codes

Main_Contract:
  enabled: ALL active cost codes
```

**Cost code retirement:**
- Cannot delete a code with any actuals/budget/appraisal references.
- Set status=Retired instead; set replaced_by_code_id to guide users to the successor.
- New transactions cannot select Retired codes; existing references remain.

**Entity mapping resolution:**
- When selecting a cost code on a transaction for a given entity:
  - Check cost_code_entity_mapping for (cost_code_id, entity_id). If exists and is_allowed=false → block.
  - If exists and is_allowed=true → use xero_nominal_code_override if set, else cost_code.xero_nominal_code.
  - If no row → fall back to cost_code.applies_to_* flags for the entity's type.

### Permissions

- `cost_codes.view` — everyone
- `cost_codes.admin` — super_admin, director, finance (manage cost code master)
- Project-level project_cost_codes enabling/disabling: project_manager + director

### Seed data

**11 cost code sections:**
```yaml
- code: acquisition        order: 1   is_direct_cost: true    p_and_l: COS
- code: planning           order: 2   is_direct_cost: true    p_and_l: COS
- code: design             order: 3   is_direct_cost: true    p_and_l: COS
- code: construction       order: 4   is_direct_cost: true    p_and_l: COS
- code: preliminaries      order: 5   is_direct_cost: true    p_and_l: COS
- code: contractor_oh      order: 6   is_direct_cost: true    p_and_l: COS
- code: sales_marketing    order: 7   is_direct_cost: false   p_and_l: Overhead
- code: finance            order: 8   is_direct_cost: false   p_and_l: Finance
- code: company_overheads  order: 9   is_direct_cost: false   p_and_l: Overhead
- code: accounting         order: 10  is_direct_cost: false   p_and_l: Tax
- code: contingency        order: 11  is_direct_cost: true    p_and_l: COS
```

**19 cost code prefixes** (~120 codes, see full list in `SY_Homes_Cost_Codes_Final.xlsx`):

Prefix summary:
- ACQ — Acquisition (ACQ-01 Purchase price, ACQ-02 Legal, ACQ-03 SDLT, ACQ-04 Valuation fees, ...)
- PLN — Planning (PLN-01 Application fee, PLN-02 Planning consultant, PLN-03 s106, ...)
- DES — Design & Consultants (DES-01 Architect, DES-02 Structural, DES-03 M&E, DES-04 QS, DES-05 Acoustic, DES-06 Thermal, DES-07 Fire, DES-08 Principal Designer, ...)
- FAC — Factual Surveys (FAC-01 Topographical, FAC-02 Geotechnical, FAC-03 Ecological, FAC-04 Arboricultural, FAC-05 Utilities, FAC-06 Measured building, ...)
- SUB — Substructure (SUB-01 Site clearance, SUB-02 Excavation, SUB-03 Piling, SUB-04 Foundations, SUB-05 Ground beams, SUB-06 Slab, SUB-07 Drainage below slab, ...)
- SUP — Superstructure (SUP-01 Frame, SUP-02 Upper floors, SUP-03 Roof, SUP-04 External walls, SUP-05 Windows, SUP-06 External doors, ...)
- INT — Internal (INT-01 Internal walls, INT-02 Internal doors, INT-03 Wall finishes, INT-04 Floor finishes, INT-05 Ceiling finishes, ...)
- FIT — Fit-out (FIT-01 Kitchens, FIT-02 Sanitaryware, FIT-03 Built-in furniture, FIT-04 Appliances, ...)
- SER — Services (SER-01 Electrical, SER-02 Plumbing, SER-03 Heating, SER-04 Ventilation, SER-05 Renewables, SER-06 Lifts, SER-07 Fire alarm, SER-08 Security, ...)
- PRE — Prefab/MMC (PRE-01 Modular units, PRE-02 Offsite frame, ...)
- EXB — Existing Buildings (EXB-01 Demolition, EXB-02 Strip-out, EXB-03 Structural alterations, EXB-04 Asbestos removal, ...)
- EXT — External Works (EXT-01 Landscaping, EXT-02 Paving, EXT-03 Driveways, EXT-04 Boundary walls, EXT-05 Drainage external, EXT-06 Service connections, ...)
- PRL — Preliminaries (PRL-01 Site establishment, PRL-02 Site management, PRL-03 Welfare, PRL-04 Temporary works, PRL-05 Plant hire, PRL-06 Waste management, ...)
- MCP — Main Contractor OH&P (MCP-01 Head office overhead, MCP-02 Site overhead, MCP-03 Profit)
- SAL — Sales & Marketing (SAL-01 Marketing, SAL-02 Sales agents, SAL-03 Legal on sale, SAL-04 CGIs, SAL-05 Show home, ...)
- FIN — Finance (FIN-01 Senior debt interest, FIN-02 Arrangement fees, FIN-03 Exit fees, FIN-04 Monitoring surveyor, FIN-05 Mezz interest, FIN-06 Bridge, ...)
- OHD — Company Overheads (OHD-01 Allocated head office cost, OHD-02 Project management time, OHD-03 Company insurances, ...)
- ACC — Accounting & Tax (ACC-01 Corporation tax, ACC-02 Accountancy fees, ACC-03 Audit, ACC-04 VAT irrecoverable, ...)
- CTG — Contingency (CTG-01 Design contingency, CTG-02 Construction contingency, CTG-03 Market contingency)

Each seeded with:
- `section_id`: appropriate section
- `default_entity`: sensible default (ACQ→SPV, SUB/SUP/INT/FIT/SER/PRE/EXB/EXT/PRL→ConstructionCo in D&B, etc.)
- `vat_treatment`: Standard for most; Reverse_Charge for SUB-SUP-INT-FIT-SER-PRE-EXB-EXT-PRL between CIS contractors; Zero_New_Build for new residential sales; Exempt for ACC-01 Corp tax etc.
- `is_cis_applicable`: true for SUB-SUP-INT-FIT-SER-PRE-EXB-EXT-PRL-MCP
- `is_retention_applicable`: true for SUB-SUP-INT-FIT-SER-PRE-EXB-EXT-PRL
- `xero_nominal_code`: matched to SY Homes's Xero chart (populated on first Xero connection — pre-seed with sensible guesses, user updates)

**Subcategories:** ~792 rows — detailed breakdown under construction codes per SY_Homes_Cost_Codes_Final.xlsx.

**Entity mapping:** Seeded for each (cost_code, entity) combination per SY Homes's structure.

### Acceptance criteria

- [ ] 11 sections seeded
- [ ] ~120 cost codes seeded with full metadata
- [ ] ~792 subcategories seeded
- [ ] Entity mapping seeded for all three entities
- [ ] Cost code tree view displays correctly
- [ ] Creating a new Dev_Build project auto-populates project_cost_codes with all active codes enabled
- [ ] Creating a new Pure_Dev project auto-populates with only acquisition/planning/design/sales/finance/overhead codes enabled
- [ ] Retiring a cost code with no references works; with references blocks and shows dependents
- [ ] Entity mapping correctly resolves on transaction (is_allowed=false blocks, override nominal used if set)
- [ ] Cost code uniqueness enforced at (code) and (prefix, sequence)
- [ ] Project-level override name displays in appraisal/budget UIs

### Out of scope

- Xero nominal code validation against actual Xero COA (Prompt 5.2)
- Cost code recommendations based on project type beyond initial enable/disable (future ML enhancement)

---

## Prompt 1.7 — System Config, Notifications

**Dependencies:** Prompts 1.1, 1.2, 1.4, 1.5  
**Tables in this prompt:** `system_config`, `notifications`  
**Estimated build time:** 1-2 days

### Build `system_config`

```
system_config
─────────────────────────────────────────────
id                          uuid PK
config_key                  varchar(100) NOT NULL UNIQUE
config_value                text NOT NULL
value_type                  enum NOT NULL  ('String','Integer','Decimal','Boolean','JSON','Date')
category                    enum NOT NULL
                              ('Finance','Appraisal','Budget','CashFlow','Programme',
                               'Document','Security','Integration','Notification','Reporting')
description                 text NOT NULL
is_system_locked            boolean NOT NULL DEFAULT false
minimum_role_to_edit        uuid NOT NULL FK→roles.id
last_changed_by_user_id     uuid FK→users.id
last_changed_at             timestamp
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()
```

### Build `notifications`

```
notifications
─────────────────────────────────────────────
id                          uuid PK
recipient_user_id           uuid NOT NULL FK→users.id ON DELETE CASCADE
notification_type           enum NOT NULL
                              ('Approval_Requested','Approval_Decision','Budget_Variance',
                               'Programme_Alert','Document_Shared','Mention','Assignment',
                               'System_Announcement','Integration_Error','Security_Alert',
                               'Deadline_Approaching','Task_Overdue','Xero_Sync_Error',
                               'Insurance_Expiry','Certificate_Expiry')
priority                    enum NOT NULL DEFAULT 'Normal' ('Low','Normal','High','Critical')
title                       varchar(255) NOT NULL
body                        text NOT NULL      -- markdown supported
related_resource_type       varchar(100)
related_resource_id         uuid
action_url                  text
action_label                varchar(50)
is_read                     boolean NOT NULL DEFAULT false
read_at                     timestamp
is_dismissed                boolean NOT NULL DEFAULT false
dismissed_at                timestamp
email_sent                  boolean NOT NULL DEFAULT false
email_sent_at               timestamp
sms_sent                    boolean NOT NULL DEFAULT false
sms_sent_at                 timestamp
expires_at                  timestamp
created_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (recipient_user_id, is_read, created_at DESC)
- INDEX (related_resource_type, related_resource_id)
- INDEX (expires_at) WHERE expires_at IS NOT NULL
```

### UI

**`/config`** (super_admin):
- Grouped by category.
- Each row: key, current value (editable inline), description, last changed by, last changed at.
- is_system_locked rows are read-only (highlighted).
- "Restore to default" action per row.

**Notification bell icon in navbar:**
- Shows unread count badge.
- Click opens panel: list of unread notifications by priority + recent.
- Each notification: title, body, timestamp, action button (if action_url set).
- "Mark all as read" action.
- "Settings" link → `/profile/notifications`.

**`/profile/notifications`** (user):
- Notification preferences: which types to receive via email, SMS (phone must be verified), in-app only.
- Digest options: immediate / hourly / daily / weekly.
- Do Not Disturb hours (timezone-aware).

**`/notifications`** (full inbox):
- Paginated list with filters: type, priority, read/unread.
- Bulk actions: mark read, dismiss.

### Business logic

**Notification dispatch:**

When a notification is created:
1. Insert into notifications table.
2. If recipient_user's preferences allow email for this type: queue email send; set email_sent=true on send.
3. If priority=Critical AND phone verified AND prefs allow SMS for this type: queue SMS; set sms_sent=true.
4. Push to active WebSocket if recipient is online (real-time bell update).

**Notification grouping:**
- If 3+ notifications of same type arrive within 1 hour for same recipient: collapse into one summary.
- Summary links to a filtered /notifications view.

**Auto-expire:**
- expires_at defaults to created_at + 30 days if not set.
- Scheduled job dismisses expired notifications.

**System config read API:**
- Provide a singleton service `SystemConfig.get(key)` accessible from all modules.
- Caches config in memory; invalidates on config write.
- All modules use this service rather than hardcoding defaults.

### Permissions

- `system_config.view` — all authenticated users (to read config)
- `system_config.admin` — super_admin only for edit
- notifications.* — users manage their own notifications only; admin cannot manage others'

### Seed data

**system_config (~40 keys):**

```yaml
# Finance
- key: finance.default_hurdle_on_cost_pct
  value: 20
  type: Decimal
  category: Finance
  description: Default minimum profit on cost for go/no-go.
  minimum_role: director

- key: finance.default_hurdle_on_gdv_pct
  value: 17
  type: Decimal
  category: Finance
  description: Default minimum profit on GDV as alternative hurdle.
  minimum_role: director

- key: finance.build_cost_inflation_pct_pa
  value: 3.0
  type: Decimal
  category: Finance
  description: Annual build cost inflation assumption for appraisals.
  minimum_role: director

# Appraisal
- key: appraisal.default_contingency_pct
  value: 5
  type: Decimal
  category: Appraisal
  description: Default design+construction contingency as % of build.
  minimum_role: director

- key: appraisal.default_architect_fee_pct
  value: 6
  type: Decimal
  category: Appraisal
  description: Default architect fee as % of build cost.
  minimum_role: director

- key: appraisal.default_structural_fee_pct
  value: 1.5
  type: Decimal
  category: Appraisal

- key: appraisal.default_qs_fee_pct
  value: 1.0
  type: Decimal
  category: Appraisal

- key: appraisal.default_selling_agents_pct
  value: 1.5
  type: Decimal
  category: Appraisal
  description: Selling agents as % of GDV.

- key: appraisal.default_legal_on_sale_pct
  value: 0.25
  type: Decimal
  category: Appraisal

- key: appraisal.default_prelims_pct
  value: 12
  type: Decimal
  category: Appraisal
  description: Preliminaries as % of build cost.

- key: appraisal.default_mc_oh_p_pct
  value: 5
  type: Decimal
  category: Appraisal
  description: Main contractor OH&P as % of build cost.

# Budget
- key: budget.variance_threshold_amber_pct
  value: 5
  type: Decimal
  category: Budget

- key: budget.variance_threshold_red_pct
  value: 10
  type: Decimal
  category: Budget

- key: budget.approval_threshold_pm_gbp
  value: 5000
  type: Integer
  category: Budget

- key: budget.approval_threshold_finance_gbp
  value: 25000
  type: Integer
  category: Budget

- key: budget.approval_threshold_director_gbp
  value: 100000
  type: Integer
  category: Budget

# Security
- key: security.session_idle_timeout_minutes
  value: 60
  type: Integer
  category: Security

- key: security.password_min_length
  value: 12
  type: Integer
  category: Security

- key: security.lockout_attempts
  value: 5
  type: Integer
  category: Security

- key: security.lockout_duration_minutes
  value: 15
  type: Integer
  category: Security

- key: security.refresh_token_days
  value: 30
  type: Integer
  category: Security

- key: security.refresh_token_days_remember_me
  value: 90
  type: Integer
  category: Security

- key: security.mfa_required_roles
  value: ["super_admin","director","finance"]
  type: JSON
  category: Security

# Integration
- key: xero.sync_interval_minutes
  value: 15
  type: Integer
  category: Integration

- key: xero.rate_limit_per_minute
  value: 60
  type: Integer
  category: Integration

# Notification
- key: notification.digest_time
  value: "08:00"
  type: String
  category: Notification

- key: notification.email_from_address
  value: platform@sy-homes.co.uk
  type: String
  category: Notification

# Programme
- key: programme.alert_task_starting_lookahead_days
  value: 7
  type: Integer
  category: Programme

- key: programme.alert_milestone_lookahead_days
  value: [30,14,7]
  type: JSON
  category: Programme

- key: programme.alert_no_update_threshold_days
  value: 14
  type: Integer
  category: Programme

- key: programme.alert_duration_overrun_threshold_pct
  value: 110
  type: Decimal
  category: Programme

# Reporting
- key: reporting.weekly_report_day
  value: "Friday"
  type: String
  category: Reporting

- key: reporting.weekly_report_time
  value: "17:00"
  type: String
  category: Reporting
```

### Acceptance criteria

- [ ] All ~40 config keys seeded
- [ ] /config page displays grouped by category with inline edit
- [ ] is_system_locked rows read-only
- [ ] Changing a value writes to audit_log with old/new value
- [ ] Notification bell shows unread count
- [ ] Creating a notification dispatches email (if prefs allow), SMS (if Critical + phone verified), WebSocket push
- [ ] Grouping collapses 3+ similar notifications within 1 hour
- [ ] User can customise prefs per notification type
- [ ] Do Not Disturb hours respected
- [ ] expires_at auto-dismiss job runs daily

### Out of scope

- Email template library (Future Tasks)
- Per-entity config overrides (could be Phase 2 if needed)
- Config change approval workflow (currently direct edit; Future Tasks if needed)

---
# Track 2 — Commercial Engine

**Goal:** Build the appraisal-to-budget-to-actuals pipeline. This is the biggest-value block of Phase 1.  
**Duration:** 6-8 weeks  
**Prompts:** 7  
**Tables:** 22 (Appraisal 9, Budget 8, Cash Flow 5)

**Split recommendation:** Prompts 2.1-2.4 first (reference data, appraisal, budget core), then 2.5-2.7 (actuals, commitments, change control, cash flow). This lets the team test the appraisal-to-budget handoff before adding complexity.

---

## Prompt 2.1 — Reference Data: SDLT Bands, Appraisal Default Settings

**Dependencies:** Prompts 1.1, 1.2, 1.4  
**Tables in this prompt:** `sdlt_rate_bands`, `appraisal_default_settings`  
**Estimated build time:** 1 day

Reference tables. Build before appraisal module so the engine has values to reference.

### Build `sdlt_rate_bands`

```
sdlt_rate_bands
─────────────────────────────────────────────
id                  uuid PK
effective_from      date NOT NULL
effective_to        date                -- null = current
category            enum NOT NULL  ('Residential_Standard','Residential_Surcharge','Non_Residential','Corporate_Flat_Rate')
band_lower          decimal(14,2) NOT NULL DEFAULT 0
band_upper          decimal(14,2)       -- null = no upper
rate_pct            decimal(6,3) NOT NULL
notes               text

Indexes:
- INDEX (category, effective_from, effective_to)
```

### Build `appraisal_default_settings`

```
appraisal_default_settings
─────────────────────────────────────────────
id                          uuid PK
setting_key                 varchar(100) NOT NULL
setting_value               decimal(14,4) NOT NULL
setting_type                enum NOT NULL  ('Percentage','Absolute','Boolean')
applies_to_project_type     enum  (null = all types)
description                 text NOT NULL
updated_by_user_id          uuid NOT NULL FK→users.id
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (setting_key, applies_to_project_type)
```

### UI

**`/settings/sdlt-rates`** (super_admin + director):
- List current active bands grouped by category.
- "+ New rate structure" action: creates a new version with effective_from date; previous version's effective_to auto-set to day before.
- Historical bands viewable via date picker.
- Band editor: table of (band_lower, band_upper, rate_pct) rows with add/remove.

**`/settings/appraisal-defaults`** (super_admin + director):
- Grouped by project type (null = "All types").
- Each key editable inline with description.
- Change log visible via audit_log link.

### Business logic

**SDLT rate versioning:**
- Bands are append-only — new rates = new effective_from rows, old rows get effective_to set.
- An appraisal built in 2024 references 2024-effective bands; a 2026 appraisal references 2026 bands.
- SDLT engine (Prompt 2.2) always uses the rates effective for `appraisal.created_at`.

**Default settings application:**
- New appraisal inherits these defaults; user can override on a per-appraisal basis.
- Changing a default setting applies only to new appraisals, not existing.

### Permissions

- `system_config.view` — read
- `system_config.admin` — edit (super_admin only)

### Seed data

**sdlt_rate_bands (effective from 1 April 2025, current):**

```yaml
# Residential Standard
- category: Residential_Standard
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 0
  band_upper: 125000
  rate_pct: 0.00

- category: Residential_Standard
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 125000
  band_upper: 250000
  rate_pct: 2.00

- category: Residential_Standard
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 250000
  band_upper: 925000
  rate_pct: 5.00

- category: Residential_Standard
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 925000
  band_upper: 1500000
  rate_pct: 10.00

- category: Residential_Standard
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 1500000
  band_upper: null
  rate_pct: 12.00

# Residential Surcharge (+5% per band for additional dwelling / company)
- category: Residential_Surcharge
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 0
  band_upper: 125000
  rate_pct: 5.00

- category: Residential_Surcharge
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 125000
  band_upper: 250000
  rate_pct: 7.00

- category: Residential_Surcharge
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 250000
  band_upper: 925000
  rate_pct: 10.00

- category: Residential_Surcharge
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 925000
  band_upper: 1500000
  rate_pct: 15.00

- category: Residential_Surcharge
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 1500000
  band_upper: null
  rate_pct: 17.00

# Non-Residential
- category: Non_Residential
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 0
  band_upper: 150000
  rate_pct: 0.00

- category: Non_Residential
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 150000
  band_upper: 250000
  rate_pct: 2.00

- category: Non_Residential
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 250000
  band_upper: null
  rate_pct: 5.00

# Corporate Flat Rate (>£500k dwellings)
- category: Corporate_Flat_Rate
  effective_from: 2025-04-01
  effective_to: null
  band_lower: 500000
  band_upper: null
  rate_pct: 17.00
  notes: Applies to companies buying dwellings >£500k. Developer relief may apply — see developer_relief flag on appraisal.
```

**appraisal_default_settings (~10 keys):**

```yaml
- setting_key: default_hurdle_on_cost_pct
  setting_value: 20.00
  setting_type: Percentage
  applies_to_project_type: null
  description: Target minimum profit on total cost

- setting_key: default_hurdle_on_gdv_pct
  setting_value: 17.00
  setting_type: Percentage
  applies_to_project_type: null
  description: Alternative target — profit on GDV

- setting_key: default_contingency_pct
  setting_value: 5.00
  setting_type: Percentage
  applies_to_project_type: null
  description: Design+construction contingency as % of build

- setting_key: default_architect_fee_pct
  setting_value: 6.00
  setting_type: Percentage
  applies_to_project_type: null
  description: Architect fee as % of build

- setting_key: default_structural_fee_pct
  setting_value: 1.50
  setting_type: Percentage
  applies_to_project_type: null

- setting_key: default_qs_fee_pct
  setting_value: 1.00
  setting_type: Percentage
  applies_to_project_type: null

- setting_key: default_selling_agents_pct
  setting_value: 1.50
  setting_type: Percentage
  applies_to_project_type: null
  description: Selling agents as % of GDV

- setting_key: default_legal_on_sale_pct
  setting_value: 0.25
  setting_type: Percentage
  applies_to_project_type: null

- setting_key: default_prelims_pct
  setting_value: 12.00
  setting_type: Percentage
  applies_to_project_type: Dev_Build
  description: Prelims as % of build for Dev_Build

- setting_key: default_mc_oh_p_pct
  setting_value: 5.00
  setting_type: Percentage
  applies_to_project_type: Dev_Build
  description: MC OH&P as % of build for Dev_Build
```

### Acceptance criteria

- [ ] SDLT bands seeded for all four categories effective 2025-04-01
- [ ] Appraisal defaults seeded (~10 keys)
- [ ] SDLT calc on a test value (£500k residential standard) returns correct amount using bands
- [ ] Changing a default setting updates new appraisals only, not existing
- [ ] Historical band query works (pick a date, see bands effective then)
- [ ] Creating new SDLT structure sets effective_to on previous active rows correctly

### Out of scope

- Scotland LBTT / Wales LTT bands (Future Tasks)
- Commercial lease SDLT (NPV calculation)
- SDLT refund tracking (if sold within 3 years, etc.)

---

## Prompt 2.2 — Appraisals Core: Header, Units, Cost Lines, Finance Model

**Dependencies:** Prompts 1.1, 1.2, 1.4, 1.5, 1.6, 2.1  
**Tables in this prompt:** `appraisals`, `appraisal_units`, `appraisal_cost_lines`, `appraisal_finance_model`  
**Estimated build time:** 5-7 days (largest single prompt)

The appraisal engine. The SDLT, RLV, and finance interest engines are significant calculation logic — budget extra time.

### Build `appraisals`

```
appraisals
─────────────────────────────────────────────
id                                  uuid PK
project_id                          uuid NOT NULL FK→projects.id ON DELETE RESTRICT
version_number                      int NOT NULL DEFAULT 1
is_current                          boolean NOT NULL DEFAULT true
status                              enum NOT NULL DEFAULT 'Draft'
                                      ('Draft','Submitted','Approved','Rejected','Superseded','Withdrawn')
scenario                            enum NOT NULL DEFAULT 'Base'
                                      ('Base','Upside','Downside')
appraisal_group_id                  uuid    -- groups scenarios together
project_type                        enum NOT NULL  -- copied from project at creation
gdv_basis                           enum NOT NULL DEFAULT 'Per_Unit'
                                      ('Per_Unit','Per_Sq_Ft','Per_Sq_M','Lump_Sum')
gdv_total                           decimal(14,2) NOT NULL DEFAULT 0  -- cached
total_cost                          decimal(14,2) NOT NULL DEFAULT 0  -- cached
profit_total                        decimal(14,2) NOT NULL DEFAULT 0  -- cached
margin_on_gdv_pct                   decimal(6,3) NOT NULL DEFAULT 0
margin_on_cost_pct                  decimal(6,3) NOT NULL DEFAULT 0
residual_land_value                 decimal(14,2) NOT NULL DEFAULT 0
residual_land_value_net             decimal(14,2) DEFAULT 0  -- after SDLT+legal+agent
irr_pct                             decimal(6,3)
roce_pct                            decimal(6,3)
assumed_start_date                  date NOT NULL
assumed_pc_date                     date NOT NULL
assumed_sales_period_months         int NOT NULL DEFAULT 12
assumed_total_programme_months      int NOT NULL
minimum_profit_on_cost_pct          decimal(6,3) NOT NULL DEFAULT 20
minimum_profit_on_gdv_pct           decimal(6,3) NOT NULL DEFAULT 17
passes_hurdle                       boolean NOT NULL DEFAULT false
sdlt_property_classification        enum NOT NULL DEFAULT 'Residential_Land_With_Consent'
                                      ('Residential_With_Dwelling','Residential_Land_With_Consent','Non_Residential','Mixed_Use','Six_Plus_Dwellings_Election')
sdlt_developer_relief_claimed       boolean NOT NULL DEFAULT true
sdlt_developer_relief_rationale     text
submitted_at                        timestamp
submitted_by_user_id                uuid FK→users.id
approved_at                         timestamp
approved_by_user_id                 uuid FK→users.id
rejected_at                         timestamp
rejected_by_user_id                 uuid FK→users.id
rejection_reason                    text
assumptions_notes                   text
risks_notes                         text
opportunities_notes                 text
created_by_user_id                  uuid NOT NULL FK→users.id
created_at                          timestamp NOT NULL DEFAULT now()
updated_at                          timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, is_current)
- INDEX (project_id, version_number)
- INDEX (status)
```

### Build `appraisal_units`

```
appraisal_units
─────────────────────────────────────────────
id                              uuid PK
appraisal_id                    uuid NOT NULL FK→appraisals.id ON DELETE CASCADE
unit_type                       varchar(255) NOT NULL    -- "3-bed semi"
description                     text
quantity                        int NOT NULL
gia_sq_ft                       decimal(10,2)
gia_sq_m                        decimal(10,2)    -- auto-calc from sq_ft ÷ 10.764
plot_size_sq_m                  decimal(10,2)
gdv_per_unit                    decimal(14,2) NOT NULL
gdv_per_sq_ft                   decimal(10,2)    -- auto-calc from gdv_per_unit ÷ gia_sq_ft
gdv_total_for_type              decimal(14,2) NOT NULL  -- auto-calc: quantity × gdv_per_unit
build_cost_basis                enum NOT NULL DEFAULT 'Per_Unit' ('Per_Unit','Per_Sq_Ft','Per_Sq_M')
build_cost_rate                 decimal(14,2) NOT NULL
build_cost_per_unit             decimal(14,2) NOT NULL  -- auto-calc
build_cost_total_for_type       decimal(14,2) NOT NULL  -- auto-calc
is_affordable                   boolean NOT NULL DEFAULT false
affordable_tenure               enum   ('Shared_Ownership','Social_Rent','Affordable_Rent','First_Homes')
affordable_discount_pct         decimal(5,2)
display_order                   int NOT NULL
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (appraisal_id)
```

### Build `appraisal_cost_lines`

```
appraisal_cost_lines
─────────────────────────────────────────────
id                          uuid PK
appraisal_id                uuid NOT NULL FK→appraisals.id ON DELETE CASCADE
cost_code_id                uuid NOT NULL FK→cost_codes.id
line_description            varchar(255) NOT NULL
input_basis                 enum NOT NULL DEFAULT 'Lump_Sum'
                              ('Lump_Sum','Per_Unit','Percentage_Of_GDV','Percentage_Of_Build_Cost','Percentage_Of_Land','Per_Sq_Ft','Rate_And_Qty')
input_rate                  decimal(14,4)
input_quantity              decimal(14,4)
input_unit                  varchar(20)
calculated_value            decimal(14,2) NOT NULL DEFAULT 0
manual_override_value       decimal(14,2)
effective_value             decimal(14,2) NOT NULL DEFAULT 0
timing_basis                enum NOT NULL DEFAULT 'Evenly_Over_Build'
                              ('Upfront','On_Planning','On_Start','Evenly_Over_Build','On_PC','On_Sale','Custom_Schedule')
custom_schedule             jsonb DEFAULT '[]'   -- [{month_offset, percentage}]
entity_id                   uuid NOT NULL FK→entities.id
is_vat_recoverable          boolean NOT NULL DEFAULT true
vat_rate_pct                decimal(5,2) NOT NULL DEFAULT 20
display_order               int NOT NULL
notes                       text
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (appraisal_id)
- INDEX (cost_code_id)
```

### Build `appraisal_finance_model`

```
appraisal_finance_model
─────────────────────────────────────────────
id                              uuid PK
appraisal_id                    uuid NOT NULL FK→appraisals.id ON DELETE CASCADE
facility_type                   enum NOT NULL
                                  ('Senior_Debt','Mezz','Bridge','JV_Equity','Private_Lender','HA_Drawdown','Director_Loan')
lender_name                     varchar(255)
facility_amount                 decimal(14,2) NOT NULL
loan_to_cost_pct                decimal(5,2)
loan_to_gdv_pct                 decimal(5,2)
interest_rate_pct               decimal(6,3) NOT NULL
interest_type                   enum NOT NULL DEFAULT 'Fixed'
                                  ('Fixed','Variable_Over_SONIA','Variable_Over_Base')
margin_over_reference_pct       decimal(5,2)
interest_calc_method            enum NOT NULL DEFAULT 'Compound_Monthly'
                                  ('Simple','Compound_Monthly','Compound_Quarterly')
is_rolled_up                    boolean NOT NULL DEFAULT true
arrangement_fee_pct             decimal(5,2)
exit_fee_pct                    decimal(5,2)
monitoring_surveyor_fee_pa      decimal(10,2)
drawdown_schedule               jsonb NOT NULL DEFAULT '[]'  -- [{month_offset, amount}]
repayment_source                enum NOT NULL DEFAULT 'Sales_Proceeds'
                                  ('Sales_Proceeds','Refinance','Equity_Exit','HA_Drawdown')
repayment_schedule              jsonb NOT NULL DEFAULT '[]'
facility_end_month              int NOT NULL
display_order                   int NOT NULL
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (appraisal_id)
```

### UI

**`/projects/:id/appraisal`** (Appraisal tab on project):
- If no current appraisal: "Create new appraisal" button.
- If exists: show current appraisal with tabs: Summary | Units | Costs | Finance | Decisions

**Summary tab:**
- Top card: Status badge, version number, created date.
- KPI tiles: GDV, Total Cost, Profit, Margin on GDV, Margin on Cost, RLV, passes_hurdle (green/red).
- Assumptions section: start date, PC date, sales period, programme months, hurdle rates.
- SDLT section: classification, developer relief claimed/rationale, computed SDLT.
- Free-text sections: Assumptions, Risks, Opportunities.

**Units tab:**
- Editable table with rows per unit type.
- Columns: Type, Qty, GIA (ft²/m²), Plot m², GDV/unit, GDV/ft², GDV total, Build rate, Build/unit, Build total, Affordable (checkbox), Tenure, Discount.
- Auto-calc cells update live as user types.
- "+ Add unit type" button.
- Footer row: totals.

**Costs tab:**
- Editable table grouped by cost code section (collapsible).
- Per row: cost code (dropdown of enabled codes for project), description, input_basis, input_rate, input_quantity, calculated_value, manual_override, effective_value, timing_basis, entity.
- Timing_basis = Custom_Schedule opens a sub-editor for the jsonb.
- "+ Add cost line" within each section.
- Footer: total cost, total cost as % of GDV.

**Finance tab:**
- Facilities listed vertically, each as a card.
- Per facility: type, lender, amount, rate, drawdown schedule (mini table), repayment schedule, fees.
- Computed monthly balance chart showing rolled-up balance over programme.
- Total interest feeds into FIN-01 cost line automatically.

**Decisions tab:**
- See Prompt 2.3.

### Business logic

**SDLT calculation engine:**

Input: land_price (from appraisal_cost_lines where cost_code.prefix='ACQ' and is first ACQ-01 or override), sdlt_property_classification, appraisal.created_at.

Algorithm:
```
1. Determine category:
   - Residential_With_Dwelling + no surcharge: Residential_Standard
   - Residential_With_Dwelling + surcharge applicable: Residential_Surcharge
   - Residential_Land_With_Consent: Residential_Standard (SDLT on land with consent = residential rates)
   - Non_Residential: Non_Residential
   - Mixed_Use: Non_Residential (commercial-weighted)
   - Six_Plus_Dwellings_Election: Non_Residential (dwellings elected as non-residential)
   
   If developer_relief_claimed=true AND category is Residential_Surcharge:
     → may shift to Residential_Standard (developer relief for companies buying
        for redevelopment). Store rationale.

2. Fetch active sdlt_rate_bands for category at appraisal.created_at.
3. Apply banded rates:
   foreach band in bands:
     applicable = min(land_price, band.band_upper) - band.band_lower
     if applicable > 0:
       tax += applicable × (band.rate_pct / 100)
4. For Corporate_Flat_Rate category (if applicable):
   if land_price > 500000:
     flat_tax = land_price × 0.17
     tax = max(tax, flat_tax)  -- whichever is higher

Return: total SDLT.
```

**RLV (Residual Land Value) solver:**

Input: target_margin_on_cost_pct (from appraisal.minimum_profit_on_cost_pct).

Iteratively solve:
```
1. Initial guess: land_price = GDV × 0.25 (rough starter)
2. Loop (max 50 iterations):
   a. Compute SDLT on land_price using SDLT engine
   b. Compute total_cost = land_price + SDLT + other_acquisition_costs + 
                          build + fees + prelims + MC_OHP + finance + 
                          sales + overheads + contingency + tax
   c. Compute profit = GDV - total_cost
   d. Compute margin_on_cost_pct = profit / total_cost × 100
   e. If abs(margin_on_cost_pct - target) < 0.01: break
   f. Adjust land_price up/down by 10% of delta, with damping
3. Return land_price (= RLV)
4. Also return RLV_net = land_price - SDLT - legal - agent (what actually hits the seller)
```

Converges in 8-12 iterations typically.

**Finance interest engine:**

For each appraisal_finance_model row:
```
Build monthly ledger for facility:
  For month m in 1..facility_end_month:
    drawdown_m = drawdowns scheduled for m
    repayment_m = repayments scheduled for m
    opening_balance_m = closing_balance_{m-1} (or 0 if m=1)
    balance_before_interest = opening_balance_m + drawdown_m - repayment_m
    
    interest_m = balance_before_interest × (interest_rate_pct/12/100)
    (or quarterly-compounded if method = Compound_Quarterly; divide by 3 for quarter)
    
    If is_rolled_up:
      closing_balance = balance_before_interest + interest_m
    Else:
      closing_balance = balance_before_interest
      (interest paid in cash month m — reflected in cash flow)

Total interest = sum(interest_m) over all months
Total facility cost = total_interest + arrangement_fee + exit_fee + monitoring_fees
```

Total interest from all facilities populates FIN-01 (senior) + FIN-05 (mezz) + FIN-06 (bridge) lines automatically. These cost lines are marked as "auto from finance model" — user cannot override manually.

**Unit auto-calculations:**

On save of appraisal_units row:
```
- gia_sq_m = gia_sq_ft ÷ 10.764 (if gia_sq_ft set)
- gdv_per_sq_ft = gdv_per_unit ÷ gia_sq_ft (if gia_sq_ft set)
- gdv_total_for_type = quantity × gdv_per_unit
- build_cost_per_unit:
    - basis = Per_Unit: rate
    - basis = Per_Sq_Ft: rate × gia_sq_ft
    - basis = Per_Sq_M: rate × gia_sq_m
- build_cost_total_for_type = quantity × build_cost_per_unit
```

**Cost line calculations:**

On save of appraisal_cost_line:
```
Depending on input_basis:
  - Lump_Sum: calculated_value = input_rate
  - Per_Unit: calculated_value = input_rate × (sum of quantity from appraisal_units)
  - Percentage_Of_GDV: calculated_value = appraisal.gdv_total × input_rate / 100
  - Percentage_Of_Build_Cost: calculated_value = sum(build_cost_total_for_type) × input_rate / 100
  - Percentage_Of_Land: calculated_value = ACQ-01 value × input_rate / 100
  - Per_Sq_Ft: calculated_value = sum(gia_sq_ft × quantity) × input_rate
  - Rate_And_Qty: calculated_value = input_rate × input_quantity

effective_value = manual_override_value IF NOT NULL ELSE calculated_value
```

**Header cached field recomputation:**

Triggered by any write to appraisal_units, appraisal_cost_lines, appraisal_finance_model:

```
gdv_total = sum(appraisal_units.gdv_total_for_type)

total_cost = 
  sum(appraisal_cost_lines.effective_value) 
  + sum(appraisal_units.build_cost_total_for_type)  -- building costs go to units, not lines
  + total_finance_cost_from_model                    -- auto-pushed to FIN lines but double-check

profit_total = gdv_total - total_cost
margin_on_gdv_pct = profit_total / gdv_total × 100  (if gdv_total > 0)
margin_on_cost_pct = profit_total / total_cost × 100  (if total_cost > 0)

passes_hurdle = margin_on_cost_pct >= minimum_profit_on_cost_pct
  OR margin_on_gdv_pct >= minimum_profit_on_gdv_pct
```

**Seed cost lines on appraisal creation:**

When a new appraisal is created, pre-populate appraisal_cost_lines with a template set based on project_type. ~30 standard lines per type. Examples:

**Pure_Dev template lines:**
```yaml
- ACQ-01 "Land purchase"              Lump_Sum, entity=SPV
- ACQ-02 "Legal on purchase"          Percentage_Of_Land 0.5%, entity=SPV
- ACQ-03 "SDLT"                       (computed by SDLT engine, read-only)
- ACQ-04 "Valuation fees"             Lump_Sum £2000, entity=SPV
- PLN-01 "Planning application fee"   Lump_Sum, entity=SPV
- PLN-02 "Planning consultant"        Lump_Sum, entity=SPV
- DES-01 "Architect"                  Percentage_Of_Build_Cost 6%, entity=SPV (Pure_Dev doesn't build but fees at this stage)
- SAL-01 "Marketing"                  Percentage_Of_GDV 0.5%, entity=SPV
- SAL-02 "Selling agents"             Percentage_Of_GDV 1.5%, entity=SPV
- SAL-03 "Legal on sale"              Percentage_Of_GDV 0.25%, entity=SPV
- FIN-01 "Senior debt interest"       (auto from finance model)
- OHD-01 "Company overhead allocation" Lump_Sum, entity=Parent
- CTG-02 "Construction contingency"   Percentage_Of_Build_Cost 5%, entity=SPV
```

**Dev_Build template lines** add the full construction cost codes: SUB, SUP, INT, FIT, SER, PRL, MCP etc., typically as Per_Unit or Per_Sq_Ft rates. Values seeded from recent project averages (user overrides).

Full template lists maintained in a seed file per project_type.

### Versioning

**New version:**
- Action button on detail view: "Create new version".
- Clones all units, cost lines, finance model into new appraisal row.
- Increments version_number.
- Sets previous version: is_current=false, status=Superseded.
- Sets new version: is_current=true, status=Draft.
- Records appraisal_revisions row (built in Prompt 2.3).

**Approval:**
- Submit action: status Draft → Submitted.
- Approve action: status Submitted → Approved.
- Reject action: status Submitted → Rejected with rejection_reason.
- Approved appraisal locks cost breakdown — edits create new version.
- Self-approval soft-enforced (confirmation modal + audit flag).

### Permissions

- `appraisals.view` — project team
- `appraisals.view_financials` — director, finance, PM
- `appraisals.create` — PM+
- `appraisals.edit` — PM+ (creators can edit Draft; approvals locked)
- `appraisals.approve` — director
- `appraisals.reopen` — director

### Acceptance criteria

- [ ] Create a new appraisal on a project — inherits defaults from appraisal_default_settings
- [ ] Cost lines pre-populated from template for project_type
- [ ] Unit auto-calcs work (gia, gdv per sq ft, totals)
- [ ] Cost line auto-calcs work for all input_basis options
- [ ] SDLT engine returns correct values for test cases:
    - £500k residential standard → £15,000
    - £500k residential surcharge → £40,000 (12.5% from surcharge bands on total)
    - £2m residential standard → £153,750
    - £250k non-residential → £2,000
- [ ] RLV solver converges within 50 iterations and returns correct RLV for test scenarios
- [ ] Finance engine correctly computes monthly balance and total interest
- [ ] Finance interest auto-populates FIN cost lines (read-only in UI)
- [ ] Header cached fields (gdv_total, total_cost, profit, margins) refresh on any detail change
- [ ] passes_hurdle flag correctly reflects margin vs threshold
- [ ] Create new version clones all detail correctly, supersedes previous
- [ ] Submit → Approve workflow works with notifications
- [ ] Self-approval modal shows and records in audit

### Out of scope

- Unit mix library (reusable house types) — Future Tasks
- Appraisal comparison view (side-by-side scenarios) — Prompt 2.3
- Sensitivity analysis (what if GDV -5%) — Future Tasks
- Scotland/Wales SDLT — Future Tasks

---

## Prompt 2.3 — Appraisal Governance: Revisions, Scenarios, Decision Log

**Dependencies:** Prompt 2.2  
**Tables in this prompt:** `appraisal_revisions`, `appraisal_scenarios`, `appraisal_decision_log`  
**Estimated build time:** 2 days

### Build `appraisal_revisions`

```
appraisal_revisions
─────────────────────────────────────────────
id                      uuid PK
from_version            int NOT NULL
to_version              int NOT NULL
appraisal_id_from       uuid NOT NULL FK→appraisals.id
appraisal_id_to         uuid NOT NULL FK→appraisals.id
revision_reason         enum NOT NULL
                          ('GDV_Updated','Costs_Updated','Planning_Change','Finance_Terms_Change','Market_Change','Scope_Change','Error_Correction','Other')
summary_of_changes      text NOT NULL
delta_gdv               decimal(14,2) DEFAULT 0
delta_total_cost        decimal(14,2) DEFAULT 0
delta_profit            decimal(14,2) DEFAULT 0
revised_by_user_id      uuid NOT NULL FK→users.id
created_at              timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (appraisal_id_from)
- INDEX (appraisal_id_to)
```

### Build `appraisal_scenarios`

```
appraisal_scenarios
─────────────────────────────────────────────
id                                  uuid PK
appraisal_group_id                  uuid NOT NULL
parent_scenario_appraisal_id        uuid FK→appraisals.id   -- points to Base
scenario_label                      enum NOT NULL
                                      ('Base','Upside','Downside','Sensitivity')
scenario_description                text NOT NULL
created_at                          timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (appraisal_group_id)
```

### Build `appraisal_decision_log`

```
appraisal_decision_log
─────────────────────────────────────────────
id                                  uuid PK
appraisal_id                        uuid NOT NULL FK→appraisals.id
appraisal_version                   int NOT NULL   -- version at decision time
decision_type                       enum NOT NULL
                                      ('Go','No_Go','Defer','Request_Revision','Conditional_Go','Correction')
decision_maker_user_id              uuid NOT NULL FK→users.id
decision_date                       date NOT NULL
decision_rationale                  text NOT NULL
conditions                          text                    -- for Conditional_Go
key_assumptions_challenged          text
supporting_documents                jsonb DEFAULT '[]'      -- document IDs
created_at                          timestamp NOT NULL DEFAULT now()  -- immutable

Indexes:
- INDEX (appraisal_id)
- INDEX (decision_date DESC)
```

### UI

**Revision history (on appraisal Summary tab):**
- Timeline view of all versions for this project.
- Each row: version_number, created_at, status, created_by, revision_reason, delta_gdv/cost/profit.
- Click to view specific version (read-only if superseded).

**Revision creation modal** (when "Create new version" clicked):
- Dropdown: revision_reason
- Text: summary_of_changes (mandatory)
- After save, user is taken to new version in edit mode.
- Deltas auto-calculated from old vs new totals on save.

**Scenarios panel** (Summary tab):
- Card per scenario in group: label, description, KPIs (GDV, cost, profit, margin).
- "+ Create upside/downside scenario" action:
  - Clones Base appraisal.
  - Shows side-by-side comparison editor.
  - User adjusts inputs (GDV +10%, build +5%, etc.) and sees impact.

**Decisions tab:**
- Chronological log of all decisions on this appraisal.
- Each row: date, decision_type (badge colored by type), maker, rationale excerpt.
- "+ Log decision" action:
  - Form: decision_type, rationale, conditions (if Conditional_Go), key_assumptions_challenged, supporting documents multi-select.
  - Submit creates append-only row.
- Dashboard nudge on project: "Go decision logged by only 1 of 3 decision-makers — log your decision."

### Business logic

**Revision creation:**
- Automatic on any "Create new version" action.
- delta_* computed from current totals of old vs new.

**Scenario grouping:**
- appraisal_group_id is a UUID shared by all scenarios in a group.
- Base scenario created first; Upside/Downside clone from Base and share group_id.
- All scenarios in a group share the same project_id.

**Decision log immutability:**
- No UPDATE/DELETE allowed (like audit_log).
- Corrections via new row with decision_type=Correction and reference to original in rationale.

**Nudge logic:**
- If project has an Approved appraisal AND <3 distinct decision_maker_user_ids have logged Go/No_Go/Defer on latest version:
  - Show banner on project detail: "Only N of 3 board members have recorded their decision. Log yours."
- Configurable threshold (default 3) in system_config.

### Permissions

- `appraisals.view` — required to see decision log
- `appraisals.approve` — required to log a decision

### Acceptance criteria

- [ ] New version creates appraisal_revisions row with deltas
- [ ] Scenarios grouped correctly under appraisal_group_id
- [ ] Side-by-side comparison view shows Base vs Upside/Downside
- [ ] Decision log append-only (UPDATE/DELETE blocked)
- [ ] Correction decision type creates new row referencing original
- [ ] Dashboard nudge appears when <3 decisions logged
- [ ] Supporting documents link to documents table (once Prompt 4.2 built)

### Out of scope

- Decision document auto-generation (PDF of appraisal + decision) — Future Tasks
- Automated decision recording via e-signature — Future Tasks

---

## Prompt 2.4 — Budgets Core

**Dependencies:** Prompts 1.1–1.7, 2.1–2.3  
**Tables in this prompt:** `budgets`, `budget_lines`, `budget_line_items`  
**Estimated build time:** 3-4 days

### Build `budgets`

```
budgets
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
source_appraisal_id             uuid NOT NULL FK→appraisals.id
version_number                  int NOT NULL DEFAULT 1
version_label                   varchar(50) NOT NULL DEFAULT 'Original'
is_current                      boolean NOT NULL DEFAULT true
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Active','Locked','Superseded','Closed')
created_from_appraisal_at       timestamp NOT NULL DEFAULT now()
locked_at                       timestamp
locked_by_user_id               uuid FK→users.id
closed_at                       timestamp
closed_by_user_id               uuid FK→users.id
total_budget                    decimal(14,2) NOT NULL DEFAULT 0  -- cached
total_actuals                   decimal(14,2) NOT NULL DEFAULT 0  -- cached
total_committed_not_invoiced    decimal(14,2) NOT NULL DEFAULT 0  -- cached
total_forecast_to_complete      decimal(14,2) NOT NULL DEFAULT 0  -- cached
forecast_final_cost             decimal(14,2) NOT NULL DEFAULT 0  -- cached
variance_vs_budget              decimal(14,2) NOT NULL DEFAULT 0  -- cached
variance_pct                    decimal(6,3) NOT NULL DEFAULT 0   -- cached
summary_refreshed_at            timestamp NOT NULL DEFAULT now()
notes                           text
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, is_current)
- INDEX (status)
```

### Build `budget_lines`

```
budget_lines
─────────────────────────────────────────────
id                              uuid PK
budget_id                       uuid NOT NULL FK→budgets.id ON DELETE CASCADE
cost_code_id                    uuid NOT NULL FK→cost_codes.id
cost_code_subcategory_id        uuid FK→cost_code_subcategories.id
line_description                varchar(255) NOT NULL
entity_id                       uuid NOT NULL FK→entities.id
original_budget                 decimal(14,2) NOT NULL DEFAULT 0
approved_changes                decimal(14,2) NOT NULL DEFAULT 0  -- cached sum from approved budget_changes
current_budget                  decimal(14,2) NOT NULL DEFAULT 0  -- cached: original + approved_changes
actuals_to_date                 decimal(14,2) NOT NULL DEFAULT 0  -- cached
actuals_this_period             decimal(14,2) DEFAULT 0           -- current month
last_actual_posted_at           timestamp
committed_value                 decimal(14,2) NOT NULL DEFAULT 0  -- cached
invoiced_against_commitment     decimal(14,2) NOT NULL DEFAULT 0
committed_not_invoiced          decimal(14,2) NOT NULL DEFAULT 0  -- cached
forecast_to_complete            decimal(14,2) NOT NULL DEFAULT 0
ftc_method                      enum NOT NULL DEFAULT 'Budget_Remaining'
                                  ('Manual','Budget_Remaining','Committed_Only','Percentage_Complete')
forecast_final_cost             decimal(14,2) NOT NULL DEFAULT 0  -- cached
variance_value                  decimal(14,2) NOT NULL DEFAULT 0  -- cached
variance_pct                    decimal(6,3) NOT NULL DEFAULT 0   -- cached
variance_status                 enum NOT NULL DEFAULT 'Green' ('Green','Amber','Red')
percentage_complete             decimal(5,2) DEFAULT 0
linked_programme_task_id        uuid    -- FK added in Prompt 3.2
is_locked                       boolean NOT NULL DEFAULT false
requires_attention              boolean NOT NULL DEFAULT false
display_order                   int NOT NULL
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (budget_id, cost_code_id, cost_code_subcategory_id)
- INDEX (budget_id)
- INDEX (cost_code_id)
```

### Build `budget_line_items`

Optional line-item granularity.

```
budget_line_items
─────────────────────────────────────────────
id                  uuid PK
budget_line_id      uuid NOT NULL FK→budget_lines.id ON DELETE CASCADE
description         varchar(255) NOT NULL
quantity            decimal(14,4)
unit                varchar(20)
rate                decimal(14,4)
amount              decimal(14,2) NOT NULL
notes               text
display_order       int NOT NULL
created_at          timestamp NOT NULL DEFAULT now()
updated_at          timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (budget_line_id)
```

### UI

**`/projects/:id/budget`** (Budget tab on project):
- If no current budget: "Create budget from approved appraisal" button (disabled if no approved appraisal).
- If exists: show the budget grid.

**Budget grid:**
- Hierarchical view grouped by cost code section (collapsible).
- Columns: Cost code, Description, Entity, Original, Approved Changes, Current, Actuals, Committed, FTC, FFC, Variance £, Variance %, Status.
- Variance status shown with color chip: Green / Amber / Red.
- Inline edit on description, FTC, percentage_complete, notes.
- Click cost code → expand to show budget_line_items.
- Footer row per section: subtotal.
- Grand total row at bottom.

**Budget line detail drawer:**
- Opens from right when a row is clicked.
- Tabs: Summary | Actuals | Commitments | Changes | Items
- Summary: all fields of the line.
- Actuals: list of actuals posted against this line (built in Prompt 2.5).
- Commitments: list of commitments against this line (built in Prompt 2.5).
- Changes: list of approved budget_changes affecting this line (built in Prompt 2.6).
- Items: editable list of budget_line_items.

**Budget actions:**
- "Lock budget" (Draft → Locked via Active): baseline set, direct line edits blocked.
- "Close budget" (on project completion).
- "Create new version": clones to new budget_id, previous set Superseded.

### Business logic

**Budget creation from appraisal:**

When "Create budget from approved appraisal" is clicked:
1. Validate source appraisal is Approved.
2. Create budgets row with version_number=1, version_label="Original", status=Draft.
3. For each appraisal_cost_line, create a budget_lines row:
   - cost_code_id = appraisal_cost_line.cost_code_id
   - entity_id = appraisal_cost_line.entity_id
   - line_description = appraisal_cost_line.line_description
   - original_budget = appraisal_cost_line.effective_value
   - current_budget = original_budget (no changes yet)
   - All other cached fields initialised to 0
4. Also create budget_lines from appraisal_units build costs (aggregated per cost code if applicable).
5. Display the new budget.

**current_budget computation:**
- `current_budget = original_budget + approved_changes` (cached, refreshed on budget_changes approval).

**FTC computation (depends on ftc_method):**
```
Manual:
  FTC = whatever the user entered

Budget_Remaining:
  FTC = max(0, current_budget − actuals_to_date − committed_value)

Committed_Only:
  FTC = 0
  (assumes full scope committed; any cost beyond actuals+committed is a variance)

Percentage_Complete:
  if percentage_complete > 0:
    FTC = (current_budget × (100 − percentage_complete) / 100) − committed_not_invoiced
    (remaining physical work × budget rate minus already-committed)
  else:
    fall back to Budget_Remaining
```

**FFC and variance:**
```
FFC = actuals_to_date + committed_value + FTC
     (note: committed includes both invoiced and not-invoiced; don't double count)
     More precisely:
     FFC = actuals_to_date + committed_not_invoiced + FTC
     
variance_value = FFC − current_budget
variance_pct = variance_value / current_budget × 100   (if current_budget > 0)

variance_status:
  |variance_pct| < amber_threshold (default 5%) → Green
  |variance_pct| < red_threshold (default 10%) → Amber
  else → Red
```

Thresholds from system_config.

**Budget status transitions:**
- Draft → Active: admin action; enables actuals posting against lines.
- Active → Locked: admin action; baseline taken, direct line edits blocked (only via budget_changes).
- Any → Superseded: when new version created.
- Any → Closed: when project complete.

**Requires attention flag:**
- Scheduled daily: set budget_lines.requires_attention = true WHERE:
  - variance_status = Red, OR
  - last_actual_posted_at < now() - 30 days AND actuals_to_date > 0 AND ftc_method != 'Committed_Only' (stale line), OR
  - percentage_complete < 100 AND linked_programme_task.status = Complete (under-billed against complete task)

**Cached refresh triggers:**
- On any actual post (Prompt 2.5): refresh actuals_to_date, actuals_this_period, last_actual_posted_at.
- On any commitment change (Prompt 2.5): refresh committed_value, invoiced_against_commitment, committed_not_invoiced.
- On any approved budget_change (Prompt 2.6): refresh approved_changes, current_budget.
- On any of the above: recompute FFC, variance, variance_status for that line.
- Roll up to budget header cached fields.

### Permissions

- `budgets.view` — project team
- `budgets.view_sensitive` — director, finance, PM
- `budgets.create` — PM+ (requires approved appraisal)
- `budgets.edit` — PM+ on Draft/Active; no direct edits when Locked (only via budget_changes)
- `budgets.admin` — director (can force unlock)

### Acceptance criteria

- [ ] Cannot create budget on project without Approved appraisal
- [ ] Budget creation clones appraisal cost lines into budget lines correctly
- [ ] Original_budget total matches appraisal total_cost
- [ ] Manual FTC override works
- [ ] Budget_Remaining FTC auto-calculates correctly
- [ ] Committed_Only FTC returns 0
- [ ] Percentage_Complete FTC calculates correctly when % comp set
- [ ] FFC = actuals + committed_not_invoiced + FTC
- [ ] Variance_status Green/Amber/Red colors reflect thresholds
- [ ] Lock → edits to original_budget disabled in UI
- [ ] Lock → can still edit FTC, percentage_complete, notes
- [ ] Unlock (director) re-enables direct edits
- [ ] Budget line item sums validate against line but non-blocking
- [ ] Cached header fields refresh on any line change
- [ ] requires_attention flag set correctly by scheduled job

### Out of scope

- Actuals posting (Prompt 2.5)
- Commitments tracking (Prompt 2.5)
- Budget change workflow (Prompt 2.6)
- Programme link (Prompt 3.2 adds linked_programme_task_id FK)

---

## Prompt 2.5 — Actuals and Commitments

**Dependencies:** Prompts 1.1–1.7, 2.4  
**Tables in this prompt:** `actuals`, `commitments`  
**Estimated build time:** 3-4 days

### Build `actuals`

```
actuals
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
budget_line_id                  uuid NOT NULL FK→budget_lines.id
entity_id                       uuid NOT NULL FK→entities.id
source_type                     enum NOT NULL
                                  ('Xero_Bill','Xero_Credit_Note','Manual_Entry','SC_Valuation',
                                   'Day_Rate_Timesheet','Expense_Claim','Journal','Internal_Recharge')
source_reference                varchar(100)    -- Xero bill ID, valuation no, etc.
external_id                     varchar(100)    -- for dedup (e.g. Xero invoice+line ID)
transaction_date                date NOT NULL
posting_date                    date NOT NULL
description                     varchar(500) NOT NULL
net_amount                      decimal(14,2) NOT NULL
vat_amount                      decimal(14,2) NOT NULL DEFAULT 0
gross_amount                    decimal(14,2) NOT NULL   -- net + vat
vat_rate_pct                    decimal(5,2) NOT NULL DEFAULT 20
is_vat_recoverable              boolean NOT NULL DEFAULT true
currency                        varchar(3) NOT NULL DEFAULT 'GBP'
exchange_rate                   decimal(10,6)
supplier_id                     uuid           -- FK added in Phase 4 (subcontractors table)
supplier_name_snapshot          varchar(255) NOT NULL
supplier_invoice_ref            varchar(100)
is_cis_applicable               boolean NOT NULL DEFAULT false
cis_deduction_rate_pct          decimal(5,2)
cis_labour_amount               decimal(14,2)
cis_materials_amount            decimal(14,2)
cis_deduction_amount            decimal(14,2)    -- auto-calc
cis_reported_to_hmrc            boolean DEFAULT false
retention_rate_pct              decimal(5,2)
retention_amount                decimal(14,2)
retention_released              boolean NOT NULL DEFAULT false
retention_release_date          date
related_subcontract_id          uuid    -- FK added in Phase 4
is_reconciled_to_xero           boolean NOT NULL DEFAULT false
reconciled_at                   timestamp
reconciliation_variance         decimal(14,2)
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Posted','Paid','Void','Disputed')
paid_date                       date
payment_reference               varchar(100)
document_ids                    jsonb DEFAULT '[]'
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
voided_at                       timestamp
voided_by_user_id               uuid FK→users.id
void_reason                     text

Indexes:
- INDEX (project_id, transaction_date DESC)
- INDEX (budget_line_id)
- UNIQUE (external_id, source_type) WHERE external_id IS NOT NULL
- INDEX (transaction_date, status)
- INDEX (supplier_id) WHERE supplier_id IS NOT NULL
```

### Build `commitments`

```
commitments
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
budget_line_id                  uuid NOT NULL FK→budget_lines.id
commitment_type                 enum NOT NULL
                                  ('Subcontract','Purchase_Order','Consultant_Appointment','Service_Agreement')
source_reference                varchar(100) NOT NULL   -- "SC-0042", "PO-0101"
source_subcontract_id           uuid    -- FK added in Phase 4
supplier_id                     uuid
supplier_name_snapshot          varchar(255) NOT NULL
description                     varchar(500) NOT NULL
original_commitment_value       decimal(14,2) NOT NULL
approved_variations_value       decimal(14,2) NOT NULL DEFAULT 0   -- cached
current_commitment_value        decimal(14,2) NOT NULL DEFAULT 0   -- cached: orig + variations
invoiced_to_date                decimal(14,2) NOT NULL DEFAULT 0   -- cached from actuals
remaining_commitment            decimal(14,2) NOT NULL DEFAULT 0   -- cached: current - invoiced
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Committed','Partially_Invoiced','Fully_Invoiced','Cancelled')
signed_date                     date
cancelled_date                  date
cancellation_reason             text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id)
- INDEX (budget_line_id)
- INDEX (status)
```

### UI

**Budget line detail drawer — Actuals tab:**
- Paginated list of actuals posted against this line.
- Columns: Transaction date, Source type (badge), Description, Supplier, Net, VAT, Gross, Status, Actions.
- "+ Add manual actual" button (if user has actuals.create permission).
- Bulk actions: void selected (with reason), mark paid.

**Budget line detail drawer — Commitments tab:**
- List of commitments against this line.
- Columns: Reference, Supplier, Description, Original £, Variations £, Current £, Invoiced £, Remaining £, Status.
- "+ Add commitment" button.
- Click commitment → detail panel showing: terms, variations history, linked actuals, invoice run-down.

**`/actuals` (project or global scope):**
- Paginated list with strong filters: entity, project, cost code, supplier, date range, status.
- Export to CSV / XLSX.

**Manual actual entry form:**
- Fields: entity, project, cost code (from project_cost_codes where enabled), budget line (auto-suggested), supplier name, invoice ref, transaction date, net, VAT rate, VAT recoverable, gross (auto), CIS applicable, retention applicable, description, document attachments.
- Validation:
  - gross = net + vat (must match)
  - cost code must be enabled for (project, entity) combo
  - transaction date cannot be future-dated more than 7 days
- Submit creates Draft actual; requires approval (director/finance) to Post.

**Void action:**
- Requires void_reason.
- Sets status=Void, voided_at, voided_by_user_id.
- Triggers cache recompute on budget_line.
- Writes audit_log entry.

### Business logic

**Actuals cache refresh:**

On actual Post or Void:
```
For affected budget_line:
  actuals_to_date = sum(actuals.net_amount WHERE budget_line_id = X AND status IN ('Posted','Paid'))
  
  (Note: we use net_amount for recoverable VAT; gross for non-recoverable.
   Actually: if is_vat_recoverable → use net; else use gross.
   Implementation: actuals_to_date_sum = sum(CASE WHEN is_vat_recoverable THEN net_amount ELSE gross_amount END))
  
  actuals_this_period = same sum filtered by transaction_date in current month
  last_actual_posted_at = max(posting_date)
  
  FFC recalculated, variance recalculated.
  
  Project.gdv_actual and .build_cost_actual etc. recalculated by separate async job.
```

**CIS auto-calc:**

On manual actual entry with CIS flags:
```
if is_cis_applicable:
  cis_deduction_amount = (cis_labour_amount or net_amount × default_labour_ratio) × cis_deduction_rate_pct / 100
  
  Default labour_ratio per cost code (stored in cost_codes, or Phase 4 subcontractor table):
    - Labour-heavy trades (carpentry, plastering, decorating): 80%
    - Plant + labour (groundworks, roofing): 60%
    - Materials-heavy (cladding supply): 30%
    
  User can override labour/materials split on the actual.
```

**Retention auto-calc:**

```
if cost_code.is_retention_applicable AND retention_rate_pct > 0:
  retention_amount = net_amount × retention_rate_pct / 100
```

**Dedup on Xero sync:**
When Xero sync creates an actual (Prompt 5.3):
- external_id = xero_bill_id + "_" + line_id
- UNIQUE constraint prevents duplicates.
- If re-sync occurs with matching external_id: update the existing row, don't create new.

**Posted immutability:**
- Posted actuals cannot be edited except via Void + new correction.
- Void requires reason and is audit-logged.

**Commitments cache refresh:**

On actual post linked to a commitment:
```
If actual.source_reference matches a commitment.source_reference:
  commitment.invoiced_to_date += actual.net_amount
  commitment.remaining_commitment = current - invoiced
  
  if invoiced >= current:
    commitment.status = Fully_Invoiced
  else if invoiced > 0:
    commitment.status = Partially_Invoiced
```

**Variations (Phase 4 will add formal variation tracking):**
- For now, approved_variations_value is manually entered on commitment.
- Phase 4 introduces variations table that rolls up automatically.

### Permissions

- `actuals.view` — project team
- `actuals.view_sensitive` — director, finance (shows CIS/retention detail)
- `actuals.create` — PM, finance
- `actuals.edit` — PM (Draft only), finance (Draft only)
- `actuals.approve` — finance, director (to Post status)
- `actuals.delete` — nobody directly; use Void action
- `commitments.view` — project team
- `commitments.create` — PM+
- `commitments.edit` — PM+ (before fully invoiced)

### Acceptance criteria

- [ ] Can post manual actual against a budget line
- [ ] Gross = net + VAT validation works
- [ ] CIS auto-calc produces correct deduction amounts
- [ ] Retention auto-calc correct
- [ ] budget_line.actuals_to_date refreshes after post
- [ ] Variance recalculation correct after post
- [ ] Void action works with reason, triggers cache refresh
- [ ] Dedup via external_id prevents duplicate Xero-sourced actuals
- [ ] Commitment created, then actual posted referencing it, correctly updates invoiced_to_date
- [ ] commitment.status auto-transitions (Draft → Committed on signed_date set → Partially_Invoiced → Fully_Invoiced)
- [ ] Cannot edit Posted actuals directly

### Out of scope

- Subcontractor master data (Phase 4)
- Formal variations workflow (Phase 4)
- Expense claims and timesheets (Phase 4)
- Xero bill sync — feeds actuals automatically (Prompt 5.3)

---

## Prompt 2.6 — Budget Change Control and Forecasts

**Dependencies:** Prompts 1.1–1.7, 2.4, 2.5  
**Tables in this prompt:** `budget_changes`, `budget_change_lines`, `budget_forecasts`  
**Estimated build time:** 2-3 days

### Build `budget_changes`

```
budget_changes
─────────────────────────────────────────────
id                          uuid PK
budget_id                   uuid NOT NULL FK→budgets.id
change_number               varchar(20) NOT NULL UNIQUE    -- auto: BC-001
change_type                 enum NOT NULL
                              ('Transfer','Addition','Reduction','Scope_Change','Contingency_Release')
reason                      enum NOT NULL
                              ('Design_Development','Client_Variation','Market_Movement',
                               'Error_Correction','Risk_Materialised','Saving_Realised',
                               'Contingency_Drawdown','Other')
reason_detail               text NOT NULL
net_change_value            decimal(14,2) NOT NULL DEFAULT 0
status                      enum NOT NULL DEFAULT 'Draft'
                              ('Draft','Submitted','Approved','Rejected','Withdrawn')
submitted_by_user_id        uuid FK→users.id
submitted_at                timestamp
approved_by_user_id         uuid FK→users.id
approved_at                 timestamp
rejection_reason            text
effective_date              date NOT NULL
supporting_documents        jsonb DEFAULT '[]'
related_variation_id        uuid    -- Phase 4
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (change_number)
- INDEX (budget_id)
- INDEX (status)
```

### Build `budget_change_lines`

```
budget_change_lines
─────────────────────────────────────────────
id                      uuid PK
budget_change_id        uuid NOT NULL FK→budget_changes.id ON DELETE CASCADE
budget_line_id          uuid NOT NULL FK→budget_lines.id
change_value            decimal(14,2) NOT NULL    -- signed: + increase, − decrease
rationale               text
display_order           int NOT NULL
created_at              timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (budget_change_id)
- INDEX (budget_line_id)
```

### Build `budget_forecasts`

```
budget_forecasts
─────────────────────────────────────────────
id                                  uuid PK
budget_id                           uuid NOT NULL FK→budgets.id
snapshot_date                       date NOT NULL
snapshot_type                       enum NOT NULL DEFAULT 'Month_End_Auto'
                                      ('Month_End_Auto','Ad_Hoc_Manual','Pre_Board_Meeting')
total_budget_at_snapshot            decimal(14,2) NOT NULL DEFAULT 0
total_actuals_at_snapshot           decimal(14,2) NOT NULL DEFAULT 0
total_committed_at_snapshot         decimal(14,2) NOT NULL DEFAULT 0
total_ftc_at_snapshot               decimal(14,2) NOT NULL DEFAULT 0
ffc_at_snapshot                     decimal(14,2) NOT NULL DEFAULT 0
variance_at_snapshot                decimal(14,2) NOT NULL DEFAULT 0
programme_pct_complete              decimal(5,2)
notes                               text
created_by_user_id                  uuid NOT NULL FK→users.id
created_at                          timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (budget_id, snapshot_date DESC)
```

### UI

**`/projects/:id/budget` — Changes tab:**
- List of all budget_changes for the project's current budget.
- Columns: Change #, Type, Reason, Net £, Status, Submitted, Approved.
- "+ New Change" action.

**Change creation form:**
- Step 1: Header (change_type, reason, reason_detail, effective_date, supporting documents).
- Step 2: Lines (multi-row editor — pick budget_line, enter signed amount, optional rationale).
- Running total shown. For Transfer type, warn if sum ≠ 0.
- Step 3: Preview impact (before/after on affected budget lines).
- Submit sends for approval per threshold rules.

**Approval UI:**
- Pending approvals appear in approver's inbox.
- Shows requester, type, reason, net value, lines impacted, supporting docs.
- Approve / Reject (with reason) buttons.
- Self-approval modal if approver = submitter.

**`/projects/:id/budget` — Forecasts tab:**
- Timeline chart: FFC, budget, variance over time.
- Table of monthly snapshots with KPIs.
- "Take ad-hoc snapshot" action (for pre-board meeting).

### Business logic

**Change number generation:**
- Auto-generated on submit (not create): `BC-{NNN}` scoped to project. Highest existing + 1.

**Approval threshold routing:**

On Submit, determine required approver role based on net_change_value:
```
abs(net_change_value):
  ≤ £5,000      → project_manager (already the typical creator; still needs PM sign-off)
  ≤ £25,000     → finance
  ≤ £100,000    → director
  > £100,000    → director AND MD (two approvals required; two-stage workflow)
  
change_type = Scope_Change → director required regardless of value
```

Thresholds configurable in system_config.

**Transfer validation:**
```
if change_type = Transfer:
  sum(budget_change_lines.change_value) must equal 0 (± £0.01 for rounding)
  net_change_value = 0
```

**Addition / Reduction:**
```
sum(lines) = net_change_value
Addition: sum > 0
Reduction: sum < 0
```

**Scope_Change:**
- Net value can be anything.
- Must include affected budget_lines.
- Must include supporting documents.

**Contingency_Release:**
- From budget line where cost_code.prefix = 'CTG'.
- Drawn down to target lines.
- Sum = 0 (pure transfer from contingency).

**On approval:**

```
For each budget_change_line:
  budget_line.approved_changes += change_value  (cached)
  budget_line.current_budget = original_budget + approved_changes  (cached)
  
  Recompute FFC, variance, variance_status for affected line.
  Roll up to budget header.
```

**On rejection:**
- Status → Rejected with reason.
- No changes applied to budget_lines.
- Requester notified.

**Withdrawal:**
- Requester can withdraw Draft or Submitted changes (not Approved).
- Status → Withdrawn; no effect on budget.

**Monthly forecast snapshot (automated):**

Scheduled job on last calendar day of each month:
```
For each active budget:
  Create budget_forecasts row:
    snapshot_date = last day of month
    snapshot_type = Month_End_Auto
    total_budget_at_snapshot = budgets.total_budget
    total_actuals_at_snapshot = budgets.total_actuals
    total_committed_at_snapshot = budgets.total_committed_not_invoiced
    total_ftc_at_snapshot = budgets.total_forecast_to_complete
    ffc_at_snapshot = budgets.forecast_final_cost
    variance_at_snapshot = budgets.variance_vs_budget
    programme_pct_complete = programme.percentage_complete (if programme exists)
    created_by_user_id = system user
```

**Ad-hoc snapshot:**
- Director or PM can create via "Take snapshot now" action.
- snapshot_type = Ad_Hoc_Manual or Pre_Board_Meeting.
- Optional notes explaining context.

### Permissions

- `budget_changes.view` — project team
- `budget_changes.create` — PM+
- `budget_changes.approve` — threshold-based (see routing above)
- `budget_changes.delete` — only Draft; admin only

### Acceptance criteria

- [ ] Create Addition change — approval routed to finance at ≤£25k
- [ ] Create Addition change £50k — approval routed to director
- [ ] Create Scope_Change £1k — approval routed to director (type-based override)
- [ ] Create Transfer with unbalanced lines → validation error
- [ ] Approve change — budget_line.approved_changes and current_budget update
- [ ] Approve change — variance recalculation correct
- [ ] Reject change — no effect on budget
- [ ] Self-approval modal shows and records in audit
- [ ] Monthly scheduled job creates Month_End_Auto forecast snapshot
- [ ] Ad-hoc snapshot via button works
- [ ] Forecast trend chart shows historical FFC over time

### Out of scope

- Two-stage approval workflow for >£100k (basic pattern — extend in Phase 2 if needed)
- Variation linkage (Phase 4)
- Automated email for approval requests (email notifications handled via existing notifications table)

---

## Prompt 2.7 — Cash Flow

**Dependencies:** Prompts 1.1–1.7, 2.2, 2.4  
**Tables in this prompt:** `cash_flow_periods`, `cash_flow_lines`, `cash_flow_entries`, `cash_flow_summaries`, `cash_flow_variance_entries`  
**Estimated build time:** 3-4 days

### Build `cash_flow_periods`

```
cash_flow_periods
─────────────────────────────────────────────
id                          uuid PK
project_id                  uuid NOT NULL FK→projects.id ON DELETE CASCADE
period_type                 enum NOT NULL DEFAULT 'Month' ('Month','Quarter')
period_start_date           date NOT NULL
period_end_date             date NOT NULL
period_label                varchar(20) NOT NULL    -- "Apr 2026"
period_offset               int NOT NULL            -- months from project start
is_pre_start                boolean NOT NULL DEFAULT false
is_construction             boolean NOT NULL DEFAULT false
is_sales                    boolean NOT NULL DEFAULT false
is_post_completion          boolean NOT NULL DEFAULT false
is_actual                   boolean NOT NULL DEFAULT false
is_current                  boolean NOT NULL DEFAULT false
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (project_id, period_start_date, period_type)
```

### Build `cash_flow_lines`

```
cash_flow_lines
─────────────────────────────────────────────
id                          uuid PK
project_id                  uuid NOT NULL FK→projects.id ON DELETE CASCADE
line_type                   enum NOT NULL
                              ('Cost_Outflow','Sales_Income','Land_Sale','Deposit_Received',
                               'Finance_Drawdown','Finance_Repayment','Equity_In','Equity_Out',
                               'VAT_Payment','VAT_Reclaim','CIS_Payment','Intercompany','Tax')
cost_code_id                uuid FK→cost_codes.id
budget_line_id              uuid FK→budget_lines.id
entity_id                   uuid NOT NULL FK→entities.id
line_description            varchar(255) NOT NULL
is_vat_inclusive            boolean NOT NULL DEFAULT true
is_intercompany             boolean NOT NULL DEFAULT false
display_order               int NOT NULL
display_section             enum NOT NULL
                              ('Inflow','Outflow_Acquisition','Outflow_Construction',
                               'Outflow_Fees','Outflow_Finance','Outflow_Sales',
                               'Outflow_Overhead','Finance','Tax')
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id)
- INDEX (entity_id)
```

### Build `cash_flow_entries`

```
cash_flow_entries
─────────────────────────────────────────────
id                              uuid PK
cash_flow_line_id               uuid NOT NULL FK→cash_flow_lines.id ON DELETE CASCADE
cash_flow_period_id             uuid NOT NULL FK→cash_flow_periods.id ON DELETE CASCADE
forecast_amount                 decimal(14,2) NOT NULL DEFAULT 0
forecast_method                 enum NOT NULL DEFAULT 'From_Budget_Timing'
                                  ('From_Budget_Timing','Manual','Formula_Driven')
forecast_source_reference       varchar(255)
actual_amount                   decimal(14,2) NOT NULL DEFAULT 0
actual_source                   enum  ('Xero_Bank','Actuals_Derived','Manual')
vat_amount                      decimal(14,2) DEFAULT 0
vat_quarter                     varchar(10)
notes                           text
is_locked                       boolean NOT NULL DEFAULT false
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (cash_flow_line_id, cash_flow_period_id)
```

### Build `cash_flow_summaries`

```
cash_flow_summaries
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL FK→projects.id
cash_flow_period_id             uuid NOT NULL FK→cash_flow_periods.id
entity_id                       uuid FK→entities.id    -- null = project total
total_inflows_forecast          decimal(14,2) NOT NULL DEFAULT 0
total_inflows_actual            decimal(14,2) NOT NULL DEFAULT 0
total_outflows_forecast         decimal(14,2) NOT NULL DEFAULT 0
total_outflows_actual           decimal(14,2) NOT NULL DEFAULT 0
net_forecast                    decimal(14,2) NOT NULL DEFAULT 0
net_actual                      decimal(14,2) NOT NULL DEFAULT 0
cumulative_net_forecast         decimal(14,2) NOT NULL DEFAULT 0
cumulative_net_actual           decimal(14,2) NOT NULL DEFAULT 0
peak_funding_required           decimal(14,2) NOT NULL DEFAULT 0
peak_funding_period_id          uuid FK→cash_flow_periods.id
refreshed_at                    timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, cash_flow_period_id)
```

### Build `cash_flow_variance_entries`

```
cash_flow_variance_entries
─────────────────────────────────────────────
id                              uuid PK
cash_flow_entry_id              uuid NOT NULL FK→cash_flow_entries.id ON DELETE CASCADE
variance_type                   enum NOT NULL
                                  ('Timing_Only','Amount_Under','Amount_Over','Missed_Entirely','Bonus_Income')
variance_amount                 decimal(14,2) NOT NULL
explanation                     text NOT NULL
linked_budget_change_id         uuid FK→budget_changes.id
logged_by_user_id               uuid NOT NULL FK→users.id
logged_at                       timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (cash_flow_entry_id)
```

### UI

**`/projects/:id/cash-flow`** (Cash Flow tab on project):
- Matrix view: rows = cash_flow_lines grouped by display_section, columns = periods, cells = forecast/actual amounts.
- Top bar: entity filter (All / specific entity), period range (12 months default), forecast/actual toggle, VAT inclusive/exclusive toggle.
- Footer rows per section: subtotal forecast/actual.
- Grand total rows: Total Inflow, Total Outflow, Net, Cumulative Net.
- Peak funding callout: "Peak funding required: £X in Month Y".

**Cell interaction:**
- Click cell → drawer with forecast + actual + variance + explanations.
- Edit forecast inline if manually set.
- Actual auto-populated from derived sources (see business logic).
- Variance explanation form if abs(forecast - actual) > threshold.

**Variance alert indicator:**
- Cells with explained variance: small icon.
- Cells with unexplained variance above threshold: red border.

### Business logic

**Period generation:**

On project creation or appraisal start date change:
```
start = project.target_start_date - (months for pre-construction activity, derived from assumed_total_programme_months)
end = start + assumed_total_programme_months + some buffer

Create cash_flow_periods rows month-by-month:
  For each month m from start to end:
    period_start_date = 1st of month
    period_end_date = last day of month
    period_label = "MMM YYYY"
    period_offset = months from project start
    
    Flags based on project schedule:
      is_pre_start = period_end < actual_start_date (or target_start_date)
      is_construction = period_start >= start AND period_end <= target_pc_date
      is_sales = period within sales period
      is_post_completion = period_start > target_pc_date + sales_period
    
    is_actual = period_end < current date
    is_current = period contains today
```

**Line seeding:**

On project creation, seed cash_flow_lines:
- One line per enabled project_cost_code, line_type=Cost_Outflow, display_section based on cost code section
- One line per appraisal_unit type, line_type=Sales_Income
- One line per finance facility, line_type=Finance_Drawdown + Finance_Repayment
- Special lines: VAT_Payment (per entity), VAT_Reclaim (per entity), CIS_Payment (per entity with is_cis=Contractor)

**Forecast derivation (From_Budget_Timing):**

For each Cost_Outflow line:
```
Find matching appraisal_cost_line (via cost_code_id).
Get timing_basis and custom_schedule.

Based on timing_basis, distribute effective_value across cash_flow_entries:
  Upfront: 100% in period before start
  On_Planning: 100% in period planning approval expected
  On_Start: 100% in period 1 of construction (first is_construction period)
  Evenly_Over_Build: distribute across construction periods (working-day weighted)
  On_PC: 100% in period containing target_pc_date
  On_Sale: distribute across sales periods weighted by expected absorption
  Custom_Schedule: read jsonb — [{month_offset, percentage}] → distribute accordingly

Write forecast_amount per period, with forecast_method = From_Budget_Timing.
```

For Sales_Income lines:
```
Get total GDV from appraisal.
Distribute across sales periods using S-curve (early-front-loaded):
  Default: 30% in months 1-3, 40% in months 4-6, 20% in months 7-9, 10% in months 10-12 of sales period.
  Configurable via system_config (sales_absorption_curve).
```

For Finance_Drawdown / Finance_Repayment:
```
Read appraisal_finance_model.drawdown_schedule and .repayment_schedule jsonb.
Write amounts per matching period offset.
```

For VAT_Payment / VAT_Reclaim:
```
Based on entity.vat_return_period:
  Quarterly (Jan/Apr/Jul/Oct):
    - For each quarter, sum output VAT (from sales lines) - input VAT recoverable (from cost lines where is_vat_recoverable=true).
    - Net positive: VAT_Payment in month following quarter end + 7 days grace → payment due 7th of 2nd month.
    - Net negative: VAT_Reclaim in month following quarter end.
  Monthly:
    - Same logic month-by-month.
```

For CIS_Payment:
```
For entities with cis_status=Contractor:
  Sum of CIS deductions from actuals (or forecast from cost lines with is_cis_applicable) per month.
  Paid to HMRC by 22nd of following month.
  Write as CIS_Payment in following period.
```

**Manual override:**
- User can change any cell to forecast_method=Manual.
- Manual values preserved across From_Budget_Timing refresh.
- Visual indicator (e.g. orange dot) shows manually-set cells.

**Actual derivation:**
```
For each cash_flow_entry where period is_actual=true:
  Sum matching actuals/sales by transaction_date within period:
    Cost_Outflow: sum(actuals.gross where budget_line_id matches, posting_date in period)
    Sales_Income: (Phase 5 from plot completions) or manual
    Finance_Drawdown: (manual or from Xero bank transactions matching drawdown description)
    etc.
```

**Lock historical periods:**
- When a period moves from current to past: cash_flow_entries.is_locked = true.
- Locked entries' forecast cannot be edited (actual still editable).

**Summary cache:**

On any cash_flow_entries change:
```
For affected project + period:
  Recompute cash_flow_summaries:
    total_inflows = sum(entries where line.line_type in [Sales_Income, Land_Sale, Deposit_Received, Finance_Drawdown, Equity_In, VAT_Reclaim])
    total_outflows = sum(entries where line.line_type in [Cost_Outflow, Finance_Repayment, Equity_Out, VAT_Payment, CIS_Payment, Tax])
    Compute both forecast and actual columns.
    net = inflows - outflows
    
  Also compute per-entity summaries (entity_id set).
  
Recompute cumulative:
  order periods by start_date
  cumulative_net[i] = cumulative_net[i-1] + net[i]
  
peak_funding_required = min(cumulative_net across all periods) -- most negative
peak_funding_period_id = period where min occurred
```

**Intercompany netting:**
- cash_flow_lines.is_intercompany=true: shown in per-entity view but EXCLUDED from project-level totals (cancelling out SPV ↔ ConstructionCo flows for group reporting).

**Variance logging:**
- When user updates actual and it differs from forecast above threshold (default 10% or £5k):
  - Prompt for variance explanation.
  - Creates cash_flow_variance_entries row.
  - variance_type chosen from enum.

### Permissions

- `cash_flow.view` — project team
- `cash_flow.view_sensitive` — director, finance (shows per-entity)
- `cash_flow.edit` — PM, finance (can manually adjust forecast)
- `cash_flow.admin` — director (can unlock historical)

### Acceptance criteria

- [ ] Periods generated correctly on project creation
- [ ] Cash flow lines seeded from project cost codes and appraisal
- [ ] Forecast derivation from budget timing works for all timing_basis values
- [ ] VAT quarter scheduling correct for entity on Mar/Jun/Sep/Dec returns (payment in 2nd month following quarter end)
- [ ] CIS payment scheduling correct (22nd of following month)
- [ ] Finance drawdown/repayment schedules populate correctly
- [ ] Intercompany lines excluded from project total
- [ ] Cached summaries refresh on entry changes
- [ ] Peak funding period correctly identified
- [ ] Historical periods lock after current-month roll
- [ ] Variance prompt appears on material divergence
- [ ] Variance entry saves correctly with explanation

### Out of scope

- Scenario-driven cash flow (what-if sales slow 3 months) — Future Tasks
- Cash runway alerting at group level — Future Tasks
- Direct bank feed integration — Future Tasks
- Sales forecasting from plot-level data — Phase 5

---
# Track 3 — Programme

**Goal:** Build template-driven project schedules with critical path analysis, baselines, alerting, and weekly reporting.  
**Duration:** 4-5 weeks  
**Prompts:** 3  
**Tables:** 10

**Independence note:** Track 3 is independent of Track 2 (except FKs for optional cost-code and budget-line linking). Can be built in parallel by a second team.

---

## Prompt 3.1 — Programme Templates and Calendars

**Dependencies:** Prompts 1.1, 1.2, 1.4  
**Tables in this prompt:** `programme_calendars`, `programme_calendar_exceptions` (partial — exceptions table built fully in 3.2), `programme_templates`, `programme_template_tasks`  
**Estimated build time:** 3-4 days

Reference data for programme generation. Build before programmes themselves.

### Build `programme_calendars`

```
programme_calendars
─────────────────────────────────────────────
id                              uuid PK
name                            varchar(100) NOT NULL UNIQUE
description                     text
is_default                      boolean NOT NULL DEFAULT false
working_days                    jsonb NOT NULL DEFAULT '["Mon","Tue","Wed","Thu","Fri"]'
working_hours_per_day           decimal(4,2) NOT NULL DEFAULT 8.0
bank_holidays                   jsonb NOT NULL DEFAULT '[]'   -- array of dates
standard_shutdowns              jsonb NOT NULL DEFAULT '[]'   -- [{start_date, end_date, name}]
timezone                        varchar(50) NOT NULL DEFAULT 'Europe/London'
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
```

### Build `programme_calendar_exceptions` (initial structure)

```
programme_calendar_exceptions
─────────────────────────────────────────────
id                              uuid PK
calendar_id                     uuid NOT NULL FK→programme_calendars.id ON DELETE CASCADE
applies_to_programme_id         uuid                        -- FK added in 3.2
exception_date                  date NOT NULL
exception_type                  enum NOT NULL
                                  ('Non_Working','Working_Day_Added','Partial_Day')
partial_day_hours               decimal(4,2)
reason                          varchar(255) NOT NULL
logged_by_user_id               uuid NOT NULL FK→users.id
logged_at                       timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (calendar_id, exception_date)
```

### Build `programme_templates`

```
programme_templates
─────────────────────────────────────────────
id                              uuid PK
name                            varchar(255) NOT NULL UNIQUE
description                     text
applies_to_project_type         enum        -- null = all types
typical_duration_weeks          int
typical_unit_count              varchar(50)         -- e.g. "<10", "10-30", "30+"
task_count                      int NOT NULL DEFAULT 0   -- cached
is_active                       boolean NOT NULL DEFAULT true
is_system_template              boolean NOT NULL DEFAULT false    -- seeded vs custom
version                         int NOT NULL DEFAULT 1
created_by_user_id              uuid FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (applies_to_project_type, is_active)
```

### Build `programme_template_tasks`

```
programme_template_tasks
─────────────────────────────────────────────
id                              uuid PK
programme_template_id           uuid NOT NULL FK→programme_templates.id ON DELETE CASCADE
parent_task_id                  uuid FK→programme_template_tasks.id ON DELETE CASCADE   -- phase/subtask
task_code                       varchar(20)
task_name                       varchar(255) NOT NULL
task_description                text
task_type                       enum NOT NULL DEFAULT 'Task'
                                  ('Phase','Task','Milestone','Hammock')
duration_days                   int NOT NULL DEFAULT 1
duration_basis                  enum NOT NULL DEFAULT 'Working_Days'
                                  ('Working_Days','Calendar_Days')
predecessor_codes               jsonb DEFAULT '[]'
                                  -- [{predecessor_task_code, link_type, lag_days}]
link_type                       enum DEFAULT 'FS'  ('FS','SS','FF','SF')
is_critical_default             boolean NOT NULL DEFAULT false
linked_cost_code_prefix         varchar(3)
display_order                   int NOT NULL
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (programme_template_id)
- INDEX (parent_task_id)
- UNIQUE (programme_template_id, task_code) WHERE task_code IS NOT NULL
```

### UI

**`/settings/calendars`** (super_admin + director):
- List of calendars.
- Default indicator.
- Create/edit calendar: working_days checkboxes, working_hours, bank_holidays (date picker list), standard_shutdowns (date range list).

**`/settings/programme-templates`** (super_admin + director):
- List of templates with project_type filter.
- Click template → tree view of tasks.

**Template editor:**
- Tree view: phases → tasks → subtasks.
- Per task: code, name, duration_days, duration_basis, predecessors (picker from other tasks in same template), link_type, lag_days, is_critical_default flag, linked_cost_code_prefix dropdown.
- Drag-and-drop reordering.
- Clone template button (for creating project-specific variants).

### Business logic

**Calendar default enforcement:**
- Only one is_default = true allowed.
- Setting another as default auto-clears the previous.

**Template validation:**
- task_code unique within template (where set).
- Predecessor codes must reference existing task_codes in same template.
- No cyclic dependencies (cycle detection on save).
- Parent task must not be a Task (only Phase or Hammock can have children).
- Milestones have duration 0 days (auto-enforced on save).

**task_count cache:**
- On template task create/delete: recount task_count on template.

**Seed bank holidays:**
Populate programme_calendars.bank_holidays for "Standard Construction UK" with England & Wales bank holidays through end of 2028:

```
2026: 01-Jan (New Year), 03-Apr (Good Friday), 06-Apr (Easter Mon), 04-May (Early May), 25-May (Spring), 31-Aug (Summer), 25-Dec, 28-Dec (Boxing obs)
2027: 01-Jan, 26-Mar (Good Friday), 29-Mar (Easter Mon), 03-May, 31-May, 30-Aug, 27-Dec (Xmas obs), 28-Dec (Boxing obs)
2028: 03-Jan (NYD obs), 14-Apr (Good Friday), 17-Apr (Easter Mon), 01-May, 29-May, 28-Aug, 25-Dec, 26-Dec
```

Scheduled reminder for admin in December each year to add next year's dates if not already seeded.

### Permissions

- `programmes.view` — users with programme access see templates read-only.
- `programmes.admin` — super_admin and director manage templates and calendars.

### Seed data

**Calendars (1 default seeded):**
```yaml
- name: Standard Construction UK
  description: UK working calendar — Mon-Fri, 8h/day, England & Wales bank holidays, Christmas shutdown
  is_default: true
  working_days: [Mon, Tue, Wed, Thu, Fri]
  working_hours_per_day: 8.0
  bank_holidays: [list through 2028 per above]
  standard_shutdowns:
    - start_date: 2026-12-24
      end_date: 2027-01-02
      name: Christmas 2026
    - start_date: 2027-12-24
      end_date: 2028-01-03
      name: Christmas 2027
  timezone: Europe/London
```

**Programme templates (6 seeded):**

Template 1 — Pure Development (12 weeks):
```yaml
name: Pure Development
applies_to_project_type: Pure_Dev
typical_duration_weeks: 12
tasks:
  Phase: Pre-Acquisition
    - DUE-01 Due diligence kick-off              1d,  milestone, critical
    - DUE-02 Site visit and photo survey          2d
    - DUE-03 Desktop searches                     5d,  pred: DUE-01
    - DUE-04 Planning history review              3d,  pred: DUE-01
    - DUE-05 Title investigation                  10d, pred: DUE-01
    - DUE-06 Access and services review           5d,  pred: DUE-02
    - DUE-07 Comparable sales analysis            5d
    - DUE-08 Initial appraisal draft              5d,  pred: DUE-03, DUE-04, DUE-05, DUE-07
  Phase: Legal Completion
    - LEG-01 Heads of terms                       3d,  pred: DUE-08
    - LEG-02 Solicitor instructed                 1d,  pred: LEG-01
    - LEG-03 Contract exchange                    14d, pred: LEG-02
    - LEG-04 Completion                           14d, pred: LEG-03, milestone
  Phase: Marketing & Sale
    - MKT-01 Marketing pack prep                  5d,  pred: LEG-04
    - MKT-02 Listing live                         1d,  pred: MKT-01, milestone
    - MKT-03 Offer period                         21d, pred: MKT-02
    - MKT-04 Offer accepted                       1d,  pred: MKT-03, milestone
    - MKT-05 Buyer legal                          28d, pred: MKT-04
    - MKT-06 Exchange                             1d,  pred: MKT-05, milestone
    - MKT-07 Sale completion                      14d, pred: MKT-06, milestone, critical
```

Template 2 — Dev & Build Small (<10 units, ~40 weeks):
```yaml
name: Dev & Build Small (<10 units)
applies_to_project_type: Dev_Build
typical_unit_count: <10
typical_duration_weeks: 40
tasks:
  Phase: Mobilisation (6 weeks)
    - MOB-01 Pre-con meeting                      1d, milestone, critical
    - MOB-02 CDM notification (F10)               3d
    - MOB-03 PD appointment                       2d
    - MOB-04 PC appointment                       2d
    - MOB-05 Site insurance active                3d
    - MOB-06 Welfare delivered                    5d
    - MOB-07 Site set-up complete                 10d, milestone
    - MOB-08 Hoarding & signage                   5d
    - MOB-09 Utility disconnection                14d
    - MOB-10 Enabling works permits               10d
  Phase: Substructure (10 weeks)
    - SUB-01 Site clearance                       10d, pred: MOB-07
    - SUB-02 Setting out                          3d, pred: SUB-01
    - SUB-03 Foundations dug & poured             30d, pred: SUB-02, critical, linked_cost_code=SUB
    - SUB-04 Below-ground drainage                10d, pred: SUB-03
    - SUB-05 Slabs laid                           15d, pred: SUB-04, critical
    - SUB-06 Damp-proofing                        5d, pred: SUB-05
    - SUB-07 Substructure complete                0d, pred: SUB-06, milestone
  Phase: Superstructure (12 weeks)
    - SUP-01 First lift                           5d, pred: SUB-07, critical, linked_cost_code=SUP
    - SUP-02 First floor                          15d, pred: SUP-01, critical
    - SUP-03 Roof structure                       10d, pred: SUP-02, critical
    - SUP-04 Roof covering                        10d, pred: SUP-03, critical
    - SUP-05 Watertight                           0d, pred: SUP-04, milestone, critical
    - SUP-06 External walls                       20d, pred: SUP-05
    - SUP-07 Windows & external doors             10d, pred: SUP-05, SUP-06
  Phase: Internal & Services (12 weeks)
    - INT-01 First-fix plumbing                   15d, pred: SUP-07, linked_cost_code=SER
    - INT-02 First-fix electrical                 15d, pred: SUP-07
    - INT-03 Insulation & plasterboard            15d, pred: INT-01, INT-02
    - INT-04 Plastering                           15d, pred: INT-03
    - INT-05 Second-fix electrical                10d, pred: INT-04
    - INT-06 Second-fix plumbing                  10d, pred: INT-04
    - INT-07 Kitchens                             10d, pred: INT-05, INT-06, linked_cost_code=FIT
    - INT-08 Bathrooms                            10d, pred: INT-05, INT-06
    - INT-09 Decoration                           15d, pred: INT-07, INT-08
    - INT-10 Floor finishes                       10d, pred: INT-09
  Phase: External & Completion (4 weeks)
    - EXT-01 Landscaping                          15d, pred: SUP-05, linked_cost_code=EXT
    - EXT-02 External drainage final              5d, pred: INT-10
    - EXT-03 Driveways & paving                   10d, pred: EXT-01, EXT-02
    - EXT-04 Fencing & boundaries                 5d, pred: EXT-01
    - COM-01 Commissioning                        10d, pred: INT-10
    - COM-02 Snagging                             10d, pred: COM-01
    - COM-03 Building Control final               5d, pred: COM-02
    - COM-04 Practical Completion                 0d, pred: COM-03, milestone, critical
  Phase: Post-Completion (until end of DLP - separate tracking)
    - PC-01 Handover to sales                     1d, pred: COM-04, milestone
```

Template 3 — Dev & Build Medium (10-30 units, ~65 weeks):
- Similar structure to Small but scaled up with more tasks.
- Adds: planning discharge tasks, plot-level detailing, phased handover.
- Total ~80 tasks.

Template 4 — Dev & Build Large (30+ units, ~100 weeks):
- Multi-phase delivery structure.
- Adds: showhome build and fit-out first, marketing suite, phased plot handover.
- Total ~120 tasks.

Template 5 — D&B Contract (50 weeks):
- HA-scheme oriented.
- Adds: employer review/approval gates, monthly valuation dates, retention release stages.
- Total ~60 tasks.

Template 6 — Main Contract (variable, template baseline):
- Tender preparation tasks.
- Adds: tender query period, tender return, award, mobilisation.
- Construction section duration variable — user edits on project-specific version.

### Acceptance criteria

- [ ] 1 calendar seeded ("Standard Construction UK") with 2026-2028 bank holidays
- [ ] 6 programme templates seeded with correct project_type association
- [ ] Task trees render correctly in template editor
- [ ] Cyclic dependency detected and blocked on save
- [ ] Milestones auto-enforced to 0 days
- [ ] Task count cached correctly on template
- [ ] Cloning a template creates an editable copy with is_system_template=false
- [ ] Bank holiday list editable (can add 2029 dates)
- [ ] Calendar default enforcement works

### Out of scope

- Live programmes themselves (Prompt 3.2)
- Task progress / updates (Prompt 3.3)
- CPM calculation (Prompt 3.2)

---

## Prompt 3.2 — Programmes, Tasks, CPM Engine

**Dependencies:** Prompts 1.1–1.7, 2.4 (for budget_line linking), 3.1  
**Tables in this prompt:** `programmes`, `programme_tasks`, complete `programme_calendar_exceptions` FK  
**Estimated build time:** 7-10 days (largest single prompt — CPM engine is significant)

### Build `programmes`

```
programmes
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
source_template_id              uuid FK→programme_templates.id
calendar_id                     uuid NOT NULL FK→programme_calendars.id
name                            varchar(255) NOT NULL
description                     text
version_number                  int NOT NULL DEFAULT 1
is_current                      boolean NOT NULL DEFAULT true
status                          enum NOT NULL DEFAULT 'Draft' ('Draft','Active','Superseded','Closed')
project_start_date              date NOT NULL
project_end_date                date NOT NULL            -- cached: latest task end
target_pc_date                  date NOT NULL
actual_start_date               date
actual_pc_date                  date
total_tasks                     int NOT NULL DEFAULT 0   -- cached
tasks_complete                  int NOT NULL DEFAULT 0   -- cached
tasks_in_progress               int NOT NULL DEFAULT 0   -- cached
tasks_overdue                   int NOT NULL DEFAULT 0   -- cached
percentage_complete             decimal(5,2) NOT NULL DEFAULT 0   -- cached
critical_path_task_count        int NOT NULL DEFAULT 0   -- cached
has_critical_path_slippage      boolean NOT NULL DEFAULT false
critical_path_slippage_days     int NOT NULL DEFAULT 0
last_recalculated_at            timestamp NOT NULL DEFAULT now()
notes                           text
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, is_current)
- INDEX (status)
```

### Build `programme_tasks`

```
programme_tasks
─────────────────────────────────────────────
id                              uuid PK
programme_id                    uuid NOT NULL FK→programmes.id ON DELETE CASCADE
parent_task_id                  uuid FK→programme_tasks.id ON DELETE CASCADE
task_code                       varchar(20)
task_name                       varchar(255) NOT NULL
task_description                text
task_type                       enum NOT NULL DEFAULT 'Task'
                                  ('Phase','Task','Milestone','Hammock')
responsible_user_id             uuid FK→users.id
responsible_subcontractor       varchar(255)
planned_start_date              date NOT NULL
planned_end_date                date NOT NULL
duration_days                   int NOT NULL            -- working days (or calendar per basis)
duration_basis                  enum NOT NULL DEFAULT 'Working_Days'
                                  ('Working_Days','Calendar_Days')
actual_start_date               date
actual_end_date                 date
predecessors                    jsonb NOT NULL DEFAULT '[]'
                                  -- [{predecessor_task_id, link_type, lag_days}]
early_start_date                date     -- computed by CPM
early_end_date                  date     -- computed by CPM
late_start_date                 date     -- computed by CPM
late_end_date                   date     -- computed by CPM
total_float_days                int      -- computed: late_start - early_start
free_float_days                 int      -- computed
is_critical                     boolean NOT NULL DEFAULT false  -- total_float_days = 0
percentage_complete             decimal(5,2) NOT NULL DEFAULT 0
status                          enum NOT NULL DEFAULT 'Not_Started'
                                  ('Not_Started','In_Progress','Complete','On_Hold','Cancelled')
on_hold_reason                  text
linked_cost_code_id             uuid FK→cost_codes.id
linked_budget_line_id           uuid FK→budget_lines.id
display_order                   int NOT NULL
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (programme_id, display_order)
- INDEX (parent_task_id)
- INDEX (responsible_user_id)
- INDEX (is_critical, status) WHERE is_critical = true
- INDEX (planned_end_date) WHERE status IN ('Not_Started','In_Progress')
```

### Wire FKs

```sql
-- Complete the programme_calendar_exceptions FK from Prompt 3.1
ALTER TABLE programme_calendar_exceptions
    ADD CONSTRAINT fk_pce_programme
    FOREIGN KEY (applies_to_programme_id) REFERENCES programmes(id) ON DELETE CASCADE;

-- Wire budget_lines back to programme_tasks
ALTER TABLE budget_lines
    ADD CONSTRAINT fk_budget_line_programme_task
    FOREIGN KEY (linked_programme_task_id) REFERENCES programme_tasks(id) ON DELETE SET NULL;
```

### UI

**`/projects/:id/programme`** (Programme tab):
- If no programme: "Create programme from template" → dropdown of templates matching project_type.
- If exists: Gantt view is default.

**Gantt view:**
- Left panel: task list with code, name, duration, planned start/end, % complete, status, responsible.
- Right panel: bar chart per task.
- Critical path tasks shown in red.
- Milestones shown as diamonds.
- Today line (vertical).
- Baseline bars shown faintly behind current bars (if baseline taken — Prompt 3.3).
- Zoom: week / month / quarter.
- Expand/collapse phases.

**Task detail drawer** (click on task):
- Tabs: Details | Predecessors | Progress | Updates | Costs
- Details: all task fields editable (if Draft or Active, respecting status).
- Predecessors: list + editor (add/remove, pick task, link type, lag).
- Progress: percentage_complete slider, status dropdown, actual dates.
- Updates: list of programme_task_updates (Prompt 3.3).
- Costs: linked cost_code_id and budget_line_id with quick lookup.

**List view toggle** (alt to Gantt):
- Table with sortable/filterable columns.

**Calendar exception logging:**
- On programme detail: button "Log calendar exception" → form: date, type (non_working/partial), reason.
- Triggers CPM recalc for affected programme.

### Business logic

**Programme creation from template:**

When "Create programme from template" is selected:
```
1. Validate user has projects.edit and programmes.create on this project.
2. Clone programme_template header into programmes row:
   - source_template_id = template.id
   - calendar_id = default calendar (or user-selected)
   - project_start_date = project.target_start_date
   - target_pc_date = project.target_pc_date
3. For each programme_template_task, create programme_tasks:
   - Copy task_code, task_name, task_description, task_type, duration_days, duration_basis
   - Set parent_task_id from template's tree structure
   - predecessors = template.predecessor_codes resolved to new programme_tasks IDs
4. Set status = Draft. User can then refine.
5. Run initial CPM calculation.
6. Display programme in Gantt view.
```

**CPM algorithm — forward pass:**

```
Input: programme_tasks for a programme, calendar (with exceptions applied)

1. Topological sort tasks based on predecessor links.
2. For each task in topological order:
   
   if task has no predecessors:
     early_start = programme.project_start_date
   else:
     early_start = max across all predecessors of:
       predecessor_end + lag_days (for FS)
       predecessor_start + lag_days (for SS)
       predecessor_end - task_duration + lag_days (for FF — unusual)
       predecessor_start - task_duration + lag_days (for SF — unusual)
     
     Apply calendar: advance early_start to next working day if it falls on non-working.
   
   if duration_basis = Working_Days:
     early_end = add working_days(early_start, duration_days − 1)
     (using calendar + programme-specific exceptions)
   else:
     early_end = early_start + duration_days − 1 (calendar days)
   
   if task_type = Milestone:
     early_end = early_start  (duration 0)
   
   Store early_start_date, early_end_date.
```

**CPM algorithm — backward pass:**

```
1. Reverse topological order.
2. Find late PC date (programme.target_pc_date or latest task end).
3. For each task in reverse topological order:
   
   if task has no successors:
     late_end = programme.target_pc_date (or programme.project_end_date)
   else:
     late_end = min across all successors of:
       successor_late_start - lag_days - 1 (for FS)
       etc. based on link_type
   
   if duration_basis = Working_Days:
     late_start = subtract working_days(late_end, duration_days − 1)
   else:
     late_start = late_end − duration_days + 1
   
   Store late_start_date, late_end_date.
```

**Float calculation:**

```
For each task:
  total_float_days = working_days_between(early_start, late_start, calendar)
  
  free_float_days = 
    min across successors of (successor_early_start − task_early_end − lag)
    (if task has no successors: free_float = total_float)
  
  is_critical = (total_float_days = 0)
```

**Recalc trigger:**
- On any task create/delete/duration change/predecessor change/calendar exception: queue recalc job.
- Job runs CPM on affected programme.
- Updates task cached fields (early/late dates, float, is_critical).
- Updates programme cached fields (project_end_date, critical_path_task_count).
- Target: <2 seconds for programmes up to 200 tasks.
- Incremental — only recalc if affected task's early/late dates actually change.

**Actual start / end handling:**
- When actual_start_date is set on a task: freeze early_start at that date for downstream calc.
- When actual_end_date is set: mark task Complete, percentage_complete = 100.
- Downstream tasks' early_start recomputed based on actual end.

**Slippage detection:**
- On each CPM recalc, check if any critical task's current early_end > its original baseline end (once baseline exists — Prompt 3.3).
- Set programme.has_critical_path_slippage and critical_path_slippage_days.

**Percentage complete calculation:**

On any task update:
```
programme.tasks_complete = count(tasks where status = Complete)
programme.tasks_in_progress = count(tasks where status = In_Progress)
programme.tasks_overdue = count(tasks where status IN ('Not_Started','In_Progress') AND planned_end_date < today)
programme.percentage_complete = 
  weighted by duration_days:
    sum(task.percentage_complete × task.duration_days) / sum(task.duration_days)
  (excludes Cancelled tasks)
```

**Working-day calculator:**

```
function add_working_days(start_date, working_days, calendar, programme_id=null):
    current = start_date
    added = 0
    while added < working_days:
        current += 1 day
        if is_working_day(current, calendar, programme_id):
            added += 1
    return current

function is_working_day(date, calendar, programme_id=null):
    day_name = date.strftime('%a')  # Mon, Tue...
    
    # Check if weekday
    if day_name not in calendar.working_days:
        default = false
    else:
        default = true
    
    # Check bank holidays
    if date in calendar.bank_holidays:
        default = false
    
    # Check standard shutdowns
    for shutdown in calendar.standard_shutdowns:
        if shutdown.start_date <= date <= shutdown.end_date:
            default = false
    
    # Check exceptions (calendar-level, then programme-level)
    exceptions = programme_calendar_exceptions
                 where calendar_id = calendar.id
                 and exception_date = date
                 and (applies_to_programme_id IS NULL 
                      OR applies_to_programme_id = programme_id)
    for ex in exceptions:
        if ex.exception_type = 'Working_Day_Added':
            return true  # forces working
        elif ex.exception_type = 'Non_Working':
            return false  # forces non-working
        elif ex.exception_type = 'Partial_Day':
            return 'partial'  # handled separately for hours-based calcs
    
    return default
```

### Permissions

- `programmes.view` — project team
- `programmes.create` — PM+
- `programmes.edit` — PM+ (task-level edits)
- `programme_tasks.view` — project team (scoped)
- `programme_tasks.edit` — assigned user (own tasks) + PM (all)

### Acceptance criteria

- [ ] Create programme from Dev & Build Small template clones all tasks
- [ ] CPM forward pass calculates early_start/early_end correctly
- [ ] CPM backward pass calculates late_start/late_end correctly
- [ ] Float calculated correctly; zero-float tasks flagged critical
- [ ] Test case: task A 5d, task B 5d (A→B FS+0), project starts Mon → A=Mon-Fri, B=Mon-Fri week 2
- [ ] Test case with lag: A 5d, B 3d (A→B FS+2d) → B starts 2 working days after A ends
- [ ] Milestone tasks have 0 duration and no end offset
- [ ] Bank holiday in middle of task shifts end date appropriately
- [ ] Programme-specific exception (non-working day) added shifts downstream tasks
- [ ] Recalc completes in <2s for 200-task programme
- [ ] Actual_start freezes task's early_start for downstream calc
- [ ] Task completion rolls up to programme.percentage_complete correctly (duration-weighted)
- [ ] Cached programme fields (task counts, pct complete, critical path count) refresh
- [ ] Gantt chart renders correctly with critical path in red
- [ ] Budget line linked_programme_task_id FK wired — can select from list

### Out of scope

- Baselines and variance vs baseline (Prompt 3.3)
- Task progress updates from mobile (Prompt 3.3)
- Alerts (Prompt 3.3)
- Weekly reports (Prompt 3.3)
- Resource levelling (Phase 2+)

---

## Prompt 3.3 — Task Updates, Baselines, Alerts, Weekly Reports

**Dependencies:** Prompts 1.1–1.7, 3.1, 3.2  
**Tables in this prompt:** `programme_task_updates`, `programme_baselines`, `programme_alerts`, `programme_weekly_reports`  
**Estimated build time:** 4-5 days

### Build `programme_task_updates`

```
programme_task_updates
─────────────────────────────────────────────
id                              uuid PK
programme_task_id               uuid NOT NULL FK→programme_tasks.id ON DELETE CASCADE
update_type                     enum NOT NULL
                                  ('Started','Progress_Update','Completed','On_Hold','Resumed',
                                   'Cancelled','Date_Change','Duration_Change',
                                   'Responsibility_Change','Comment')
update_source                   enum NOT NULL DEFAULT 'Desktop'
                                  ('Desktop','Mobile','Email_Ingested','API','System')
previous_status                 enum
new_status                      enum
previous_percentage_complete    decimal(5,2)
new_percentage_complete         decimal(5,2)
previous_planned_start          date
new_planned_start               date
previous_planned_end            date
new_planned_end                 date
previous_duration_days          int
new_duration_days               int
previous_responsible_user_id    uuid
new_responsible_user_id         uuid
comment                         text
photo_urls                      jsonb DEFAULT '[]'
gps_latitude                    decimal(10,6)
gps_longitude                   decimal(10,6)
weather_notes                   text
submitted_by_user_id            uuid NOT NULL FK→users.id
submitted_at                    timestamp NOT NULL DEFAULT now()
ip_address                      varchar(45)

Indexes:
- INDEX (programme_task_id, submitted_at DESC)
- INDEX (submitted_by_user_id, submitted_at DESC)
```

### Build `programme_baselines`

```
programme_baselines
─────────────────────────────────────────────
id                          uuid PK
programme_id                uuid NOT NULL FK→programmes.id ON DELETE CASCADE
baseline_name               varchar(100) NOT NULL
baseline_type               enum NOT NULL DEFAULT 'Original'
                              ('Original','Contractual','Re_Baseline')
taken_at                    timestamp NOT NULL DEFAULT now()
taken_by                    uuid NOT NULL FK→users.id
approved_at                 timestamp
approved_by                 uuid FK→users.id
task_snapshot               jsonb NOT NULL    -- full task state at baseline
notes                       text
is_active                   boolean NOT NULL DEFAULT true
superseded_at               timestamp
created_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (programme_id, baseline_type, is_active)
```

### Build `programme_alerts`

```
programme_alerts
─────────────────────────────────────────────
id                          uuid PK
programme_id                uuid NOT NULL FK→programmes.id ON DELETE CASCADE
programme_task_id           uuid FK→programme_tasks.id ON DELETE CASCADE
alert_type                  enum NOT NULL
                              ('Task_Starting_Soon','Task_Overdue','Milestone_Approaching',
                               'Milestone_Missed','Critical_Path_Slipping','Baseline_Deviation',
                               'No_Updates','Duration_Overrun','Predecessor_Not_Complete')
severity                    enum NOT NULL DEFAULT 'Medium' ('Low','Medium','High','Critical')
message                     text NOT NULL
triggered_at                timestamp NOT NULL DEFAULT now()
status                      enum NOT NULL DEFAULT 'Active' ('Active','Acknowledged','Resolved','Snoozed')
acknowledged_at             timestamp
acknowledged_by_user_id     uuid FK→users.id
snoozed_until               timestamp
resolved_at                 timestamp
resolution_notes            text
notified_user_ids           jsonb DEFAULT '[]'
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (programme_id, status, triggered_at DESC)
- INDEX (programme_task_id)
- INDEX (status, severity)
```

### Build `programme_weekly_reports`

```
programme_weekly_reports
─────────────────────────────────────────────
id                              uuid PK
programme_id                    uuid NOT NULL FK→programmes.id ON DELETE CASCADE
report_period_start             date NOT NULL
report_period_end               date NOT NULL
percentage_complete             decimal(5,2) NOT NULL
critical_path_slippage_days     int NOT NULL DEFAULT 0
tasks_completed_this_period     jsonb DEFAULT '[]'     -- task IDs
tasks_started_this_period       jsonb DEFAULT '[]'
tasks_overdue                   jsonb DEFAULT '[]'
milestones_hit                  jsonb DEFAULT '[]'
milestones_missed               jsonb DEFAULT '[]'
two_week_lookahead              jsonb DEFAULT '[]'     -- upcoming task IDs
key_issues                      text                     -- manual narrative
weather_impact_days             decimal(4,2) DEFAULT 0
delivered_at                    timestamp NOT NULL DEFAULT now()
delivered_by_user_id            uuid FK→users.id         -- null for automated
report_pdf_url                  text
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (programme_id, report_period_start DESC)
```

### UI

**Task detail drawer — Updates tab:**
- Timeline of updates for the task: submitter avatar, update_type badge, details, timestamp.
- "+ Log update" button (for assigned user + PM).

**Update form:**
- Type dropdown: Started / Progress / Completed / On Hold / Comment / etc.
- Based on type, show relevant fields (percentage slider for Progress, reason text for On Hold).
- Photo upload (mobile takes via camera; web accepts files).
- Automatic timestamp, user, IP.
- Optional GPS capture (mobile).
- Submit → creates update, applies changes to task, recalcs CPM, potentially triggers alerts.

**Baseline UI:**
- "Take baseline" button on programme detail header.
- Modal: baseline_name, baseline_type, notes.
- On submit: snapshot current task state to task_snapshot, flag as active baseline.

**Baseline comparison view:**
- Toggle on Gantt: "Show baseline" overlays original bars behind current.
- Table view: Baseline vs Current for planned_start, planned_end, duration, float — with delta column.

**Alerts inbox:**
- `/projects/:id/programme/alerts`: list of active alerts.
- Columns: triggered date, type, task, message, severity.
- Actions: Acknowledge (adds to ack list but stays visible), Snooze (until date), Resolve (with notes).

**Weekly report:**
- `/projects/:id/programme/reports`: list of weekly reports.
- Click to view PDF.

### Business logic

**Update processing:**

When an update is submitted:
```
1. Create programme_task_updates row with previous_* and new_* snapshot.

2. Apply changes to programme_tasks based on update_type:
   Started: 
     status = In_Progress
     actual_start_date = today if null
     percentage_complete = 1 if null
     
   Progress_Update:
     percentage_complete = new value
     status unchanged (or In_Progress if Not_Started)
     
   Completed:
     status = Complete
     percentage_complete = 100
     actual_end_date = today if null
     
   On_Hold:
     status = On_Hold
     on_hold_reason = comment
     
   Resumed:
     status = In_Progress (from On_Hold)
     
   Cancelled:
     status = Cancelled
     (excluded from percentage_complete calc)
     
   Date_Change:
     planned_start_date and/or planned_end_date changed
     Recalc duration if both dates moved.
     
   Duration_Change:
     duration_days = new
     planned_end_date recalculated
     
3. Queue CPM recalc on programme.
4. Refresh cached fields on programme.
5. Evaluate alert rules against this task:
   - If actual_end > baseline_end on critical task → raise Critical_Path_Slipping alert
   - If task was flagged Overdue and now Complete → resolve Task_Overdue alert
   - If actual_duration > 110% of planned → Duration_Overrun alert
```

**Baseline creation:**

```
On "Take baseline":
  1. If baseline of this type already active and type != Re_Baseline:
       Block — "An {type} baseline already exists; take a re-baseline instead."
  2. If type = Re_Baseline: require director approval (flag as approved_by with pending state).
  3. Snapshot all programme_tasks to task_snapshot JSONB:
     [{id, task_code, planned_start, planned_end, duration, is_critical, total_float, ...}]
  4. Create programme_baselines row.
  5. On re-baseline: set previous re_baseline rows is_active=false, superseded_at=now.
```

**Baseline variance:**
- On demand calculation:
  ```
  For each task in current programme:
    baseline_task = lookup in baseline.task_snapshot
    If found:
      start_variance = task.planned_start - baseline.planned_start (days)
      end_variance = task.planned_end - baseline.planned_end (days)
      duration_variance = task.duration_days - baseline.duration_days (days)
    Else:
      task added after baseline (delta N/A)
  ```

**Alert rules (scheduled daily at 06:00 UTC):**

```
1. Task_Starting_Soon (severity Medium):
   SELECT tasks WHERE planned_start_date BETWEEN today AND today + N days
     AND status = Not_Started
     (N = config programme.alert_task_starting_lookahead_days, default 7)
   For each: create alert if not already active.
   Notify: responsible_user_id, project_lead.

2. Task_Overdue (severity High):
   SELECT tasks WHERE planned_end_date < today AND status IN (Not_Started, In_Progress)
   Alert + notify.

3. Milestone_Approaching:
   SELECT tasks WHERE task_type = Milestone AND planned_start_date BETWEEN today AND today + M days
     (M = multi-tier from config: 30/14/7 days → Low/Medium/High)
   Alert at each threshold once.

4. Milestone_Missed:
   SELECT tasks WHERE task_type = Milestone AND planned_start_date < today AND status != Complete.
   Severity Critical.

5. Critical_Path_Slipping:
   If programme.has_critical_path_slippage = true AND slippage > 5 days: raise alert.
   Severity scales with slippage (5d=Medium, 10d=High, 20d+=Critical).

6. Baseline_Deviation:
   If programme.percentage_complete − expected_at_today < X% (where expected comes from baseline's cumulative curve):
     Severity Medium.

7. No_Updates:
   SELECT tasks WHERE status = In_Progress AND last update > N days ago
     (N = config, default 14)
   Severity Medium.

8. Duration_Overrun:
   SELECT tasks WHERE status = In_Progress AND today − actual_start > duration_days × threshold / 100
     (threshold = config, default 110)

9. Predecessor_Not_Complete:
   For each task at planned_start_date = today + 1 where status = Not_Started:
     Check all predecessors status = Complete.
     If not: alert.
     Severity High.
```

**Alert deduplication:**
- Same alert_type + programme_task_id + status=Active: skip creation.
- When acknowledged: stays Active but excluded from "new alerts" notifications.
- When Resolved: auto-resolves on condition clearing (e.g. task completed → Task_Overdue → Resolved).
- When Snoozed: suppressed from notifications until snoozed_until.

**Weekly report generation:**

Scheduled: every Friday at 17:00 in programme timezone (default Europe/London).

```
For each active programme:
  report_period_end = today
  report_period_start = today - 7 days
  
  tasks_completed_this_period = tasks where status changed to Complete in period
  tasks_started_this_period = tasks where status changed to In_Progress in period
  tasks_overdue = tasks currently overdue
  milestones_hit = milestone tasks completed in period
  milestones_missed = milestone tasks that should have been completed but weren't
  two_week_lookahead = tasks with planned_start in next 14 days
  percentage_complete = programme.percentage_complete
  critical_path_slippage_days = programme.critical_path_slippage_days
  weather_impact_days = sum of partial-day calendar exceptions in period with weather-tagged reason
  key_issues = last narrative manually entered (if any)
  
  Generate PDF report with SY Homes branding.
  Store URL in report_pdf_url.
  
  Email to:
    - project_lead_user_id
    - project_team_members
    - directors (optional — configurable per-project)
```

### Permissions

- `programme_tasks.edit` — responsible user can update own task, PM+ can update any
- `programmes.admin` — director required for Re_Baseline
- `programme_alerts.view` — project team
- `programme_alerts.edit` — ack/snooze/resolve: project lead, PM

### Acceptance criteria

- [ ] Update submission creates programme_task_updates row with previous/new snapshots
- [ ] Mobile camera capture + GPS works on update submission
- [ ] Task status changes correctly per update_type
- [ ] CPM recalc triggered after update
- [ ] Baseline taken captures full task snapshot
- [ ] Cannot take 2nd Original baseline (blocked)
- [ ] Re_Baseline requires director approval
- [ ] Baseline comparison view shows deltas correctly
- [ ] Scheduled alert job runs daily at 06:00
- [ ] Each of 9 alert types triggers under correct conditions
- [ ] Deduplication prevents repeated alerts for same condition
- [ ] Acknowledge/snooze/resolve actions work
- [ ] Auto-resolution works when condition clears (task completed → overdue alert resolved)
- [ ] Weekly report job runs Fridays at 17:00 local
- [ ] Weekly report PDF generated with correct branding
- [ ] Weekly report email delivered to project team

### Out of scope

- Automated narrative generation (AI summary) — Future Tasks
- Weather API integration for automatic weather_impact_days — Future Tasks
- Resource allocation / levelling — Phase 2+
- Mobile app (uses mobile web interface for now) — separate track

---
# Track 4 — QA & Documents

**Goal:** Build the document store with versioning, approvals, access control, and compliance registers.  
**Duration:** 4-5 weeks  
**Prompts:** 3  
**Tables:** 7

**Independence note:** Track 4 is largely independent — can be built in parallel with Tracks 2 or 3.

---

## Prompt 4.1 — Document Types and Templates

**Dependencies:** Prompts 1.1, 1.2, 1.4  
**Tables in this prompt:** `document_types`, `document_templates`  
**Estimated build time:** 2 days

### Build `document_types`

```
document_types
─────────────────────────────────────────────
id                                  uuid PK
code                                varchar(10) NOT NULL UNIQUE      -- "DRW", "RAM"
name                                varchar(100) NOT NULL
description                         text
category                            enum NOT NULL
                                      ('Design','Construction','Safety','Quality','Commercial',
                                       'Legal','Statutory','Marketing','Completion','Handover')
requires_approval                   boolean NOT NULL DEFAULT false
typical_approval_workflow           enum DEFAULT 'None'
                                      ('None','Single_Approver','Two_Stage','Consultant_Signed')
retains_history                     boolean NOT NULL DEFAULT true
requires_expiry_tracking            boolean NOT NULL DEFAULT false
is_active                           boolean NOT NULL DEFAULT true
sort_order                          int NOT NULL DEFAULT 100
created_at                          timestamp NOT NULL DEFAULT now()
updated_at                          timestamp NOT NULL DEFAULT now()
```

### Build `document_templates`

```
document_templates
─────────────────────────────────────────────
id                              uuid PK
document_type_id                uuid NOT NULL FK→document_types.id
name                            varchar(255) NOT NULL
description                     text
template_file_url               text NOT NULL
placeholder_fields              jsonb NOT NULL DEFAULT '[]'
                                  -- [{name, label, source, required}]
                                  -- source e.g. "project.name", "entity.vat_number"
default_access_restriction      enum DEFAULT 'Project_Team'
                                  ('Public','Authenticated','Project_Team',
                                   'Project_Team_Plus_Consultants','Project_Team_Plus_Client',
                                   'Internal_Only','Restricted_Custom')
is_active                       boolean NOT NULL DEFAULT true
is_system_template              boolean NOT NULL DEFAULT false
created_by_user_id              uuid FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (document_type_id, is_active)
```

### UI

**`/settings/document-types`** (super_admin + director):
- List with filter by category.
- Create/edit form: code, name, description, category, requires_approval, workflow, etc.
- Deactivate action (not delete if any documents reference it).

**`/settings/document-templates`** (super_admin + director + PM):
- List grouped by document_type.
- Click to edit.
- Upload template file (docx, xlsx, pdf).
- Define placeholder_fields: mapping from a label to a data source path.

**Placeholder editor:**
```
Fields:
- name: "PROJECT_NAME" (how it appears in template file)
- label: "Project name"
- source: "project.name" (dot-path to data value)
- required: true/false
- default_value: (optional)

Example sources:
  project.name, project.project_code, project.site_address, project.site_postcode
  entity.name, entity.legal_name, entity.vat_number, entity.companies_house_number
  user.display_name, user.job_title
  budget.total_budget, budget.forecast_final_cost
  today (special — current date)
```

### Business logic

**Document type deactivation:**
- is_active = false hides from creation menus but preserves existing documents referencing it.

**Template usage:**
- When a user creates a document "from template":
  1. Open template file.
  2. For each placeholder_field, resolve source path against current context (project, entity, etc.).
  3. Replace placeholders with resolved values.
  4. Prompt user for any unresolved/manual fields.
  5. Save as new Document record (Prompt 4.2).

### Permissions

- `documents.view` — all authenticated users (to list types/templates)
- `document_types.admin` — super_admin + director (edit)
- `document_templates.admin` — super_admin + director + PM (can create project templates)

### Seed data

**Document types (20+ seeded):**

```yaml
- code: DRW
  name: Drawing
  category: Design
  requires_approval: true
  typical_approval_workflow: Consultant_Signed
  retains_history: true

- code: RAM
  name: RAMS (Risk Assessment Method Statement)
  category: Safety
  requires_approval: true
  typical_approval_workflow: Two_Stage

- code: CRT
  name: Certificate
  category: Quality
  retains_history: true
  requires_expiry_tracking: true

- code: CON
  name: Contract
  category: Legal
  requires_approval: true
  typical_approval_workflow: Two_Stage
  retains_history: true

- code: PGM
  name: Programme
  category: Construction
  retains_history: true

- code: VAL
  name: Valuation
  category: Commercial
  requires_approval: true
  typical_approval_workflow: Single_Approver

- code: PN
  name: Payment Notice
  category: Commercial
  requires_approval: true
  typical_approval_workflow: Single_Approver

- code: PLN
  name: Pay Less Notice
  category: Commercial
  requires_approval: true
  typical_approval_workflow: Single_Approver

- code: VI
  name: Variation Instruction
  category: Commercial
  requires_approval: true
  typical_approval_workflow: Single_Approver

- code: COM
  name: Commercial Record
  category: Commercial

- code: PHO
  name: Photograph
  category: Construction
  retains_history: false

- code: SUR
  name: Survey
  category: Design

- code: RPT
  name: Report
  category: Design

- code: MIN
  name: Meeting Minutes
  category: Construction

- code: HSF
  name: Health & Safety File
  category: Safety
  requires_approval: true

- code: CDM
  name: CDM Document
  category: Safety
  requires_approval: true

- code: WAR
  name: Warranty
  category: Handover
  retains_history: true
  requires_expiry_tracking: true

- code: INS
  name: Inspection Record
  category: Quality

- code: TST
  name: Test Certificate
  category: Quality
  retains_history: true

- code: HAN
  name: Handover Document
  category: Handover

- code: CW
  name: Collateral Warranty
  category: Legal
  requires_approval: true
  typical_approval_workflow: Two_Stage
  retains_history: true

- code: OM
  name: O&M Manual
  category: Handover
  retains_history: true
```

**Document templates (30+ seeded):** Per the Platform Spec document types list, create templates for:
- JCT Payment Notice
- JCT Pay Less Notice
- NEC4 Compensation Event Quotation
- Variation Instruction
- Consultant Appointment Letter
- Subcontract Order (JCT Sub-Contract)
- Collateral Warranty (Employer)
- Collateral Warranty (Funder)
- Tender Assessment Matrix
- H&S File Index
- CDM Pre-Construction Info
- Construction Phase Plan Template
- Part L Compliance Checklist
- Part O Overheating Assessment
- Part Q Security Assessment
- Fire Strategy Template
- Meeting Minutes Template
- Site Diary Template
- Snag List Template
- Handover Letter
- Practical Completion Certificate
- Defects Notification
- Final Account Agreement
- Retention Release Notice
- EPC Request Form
- NHBC Cover Note Request
- LABC Cover Note Request

Full template library maintained as versioned files in source control.

### Acceptance criteria

- [ ] 20+ document types seeded
- [ ] 30+ templates seeded with uploaded template files
- [ ] Placeholder resolution works for project + entity paths
- [ ] Deactivating type hides from creation menus but preserves existing docs
- [ ] Template usage creates a new Document (prompt 4.2) with resolved fields

### Out of scope

- Documents themselves (Prompt 4.2)
- Approval workflows (Prompt 4.2)
- Compliance registers (Prompt 4.3)

---

## Prompt 4.2 — Documents, Approvals, Access Log

**Dependencies:** Prompts 1.1–1.7, 4.1  
**Tables in this prompt:** `documents`, `document_approvals`, `document_access_log`  
**Estimated build time:** 4-5 days

### Build `documents`

```
documents
─────────────────────────────────────────────
id                              uuid PK
document_number                 varchar(30) NOT NULL UNIQUE     -- "GAR-001-DRW-0042"
document_type_id                uuid NOT NULL FK→document_types.id
title                           varchar(255) NOT NULL
description                     text
related_project_id              uuid FK→projects.id
related_entity_id               uuid FK→entities.id
related_subcontract_id          uuid                            -- Phase 4
related_plot_id                 uuid                            -- Phase 5
related_budget_change_id        uuid FK→budget_changes.id
related_valuation_id            uuid                            -- Phase 4
version                         int NOT NULL DEFAULT 1
supersedes_document_id          uuid FK→documents.id
superseded_by_document_id       uuid FK→documents.id
is_current                      boolean NOT NULL DEFAULT true
file_storage_backend            enum NOT NULL DEFAULT 'S3'
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text NOT NULL     -- path in backend
file_original_name              varchar(500) NOT NULL
file_mime_type                  varchar(100) NOT NULL
file_size_bytes                 bigint NOT NULL
file_sha256                     varchar(64) NOT NULL  -- integrity check
thumbnail_url                   text
page_count                      int
access_restriction              enum NOT NULL DEFAULT 'Project_Team'
                                  ('Public','Authenticated','Project_Team',
                                   'Project_Team_Plus_Consultants','Project_Team_Plus_Client',
                                   'Internal_Only','Restricted_Custom')
restricted_user_ids             jsonb DEFAULT '[]'    -- for Restricted_Custom
tags                            jsonb DEFAULT '[]'
folder_path                     text                   -- virtual folder path, e.g. "/Drawings/Architectural"
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Under_Review','Approved','Issued','Superseded','Archived')
approved_at                     timestamp
approved_by_user_id             uuid FK→users.id
issued_at                       timestamp
expiry_date                     date
uploaded_by_user_id             uuid NOT NULL FK→users.id
uploaded_via                    enum NOT NULL DEFAULT 'Web_Upload'
                                  ('Web_Upload','Mobile_Upload','Email_Ingested','Template_Generated','API','Portal_Upload')
content_searchable              boolean NOT NULL DEFAULT false
ocr_completed_at                timestamp
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (document_number)
- INDEX (related_project_id, is_current, document_type_id)
- INDEX (related_entity_id, is_current)
- INDEX (status)
- INDEX (expiry_date) WHERE expiry_date IS NOT NULL
- INDEX (uploaded_by_user_id)
- INDEX (tags) USING GIN
```

### Build `document_approvals`

```
document_approvals
─────────────────────────────────────────────
id                              uuid PK
document_id                     uuid NOT NULL FK→documents.id ON DELETE CASCADE
stage                           int NOT NULL          -- 1, 2, 3... for multi-stage
required_approver_role_id       uuid FK→roles.id      -- role required to approve
required_approver_user_id       uuid FK→users.id      -- OR specific user
actual_approver_user_id         uuid FK→users.id
status                          enum NOT NULL DEFAULT 'Pending'
                                  ('Pending','Approved','Rejected','Skipped','Withdrawn')
decided_at                      timestamp
decision_notes                  text
is_self_approval                boolean NOT NULL DEFAULT false
display_order                   int NOT NULL
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (document_id, stage)
- INDEX (status)
- INDEX (required_approver_user_id) WHERE status = 'Pending'
```

### Build `document_access_log`

```
document_access_log
─────────────────────────────────────────────
id                      uuid PK
document_id             uuid NOT NULL FK→documents.id ON DELETE CASCADE
user_id                 uuid FK→users.id    -- null for public access
action                  enum NOT NULL
                          ('Viewed','Downloaded','Shared','Printed','Emailed',
                           'Approval_Decision','Version_Uploaded','Deleted_Attempt')
ip_address              varchar(45)
user_agent              text
via                     varchar(50)          -- web, mobile, api, email, portal
meta                    jsonb DEFAULT '{}'   -- context: shared_with, print_dpi, etc.
created_at              timestamp NOT NULL DEFAULT now()   -- immutable

Indexes:
- INDEX (document_id, created_at DESC)
- INDEX (user_id, created_at DESC)
- INDEX (created_at)
```

### UI

**`/documents`** (global) or `/projects/:id/documents`:
- Tree view by folder_path (virtual folders).
- List view with columns: Document number, Title, Type, Project, Version, Status, Uploaded by, Uploaded at.
- Filters: type, status, folder, tags, uploaded range.
- Search: by title, document_number, tags, full-text (if OCR'd).
- Actions: "+ Upload", "+ From template", "+ New folder" (virtual).

**Upload flow:**
1. Select files (drag-drop or picker).
2. Per file: type, title (auto-filled from filename), project/entity link, folder_path, tags, access_restriction, expiry_date (if applicable).
3. Bulk upload: apply same metadata to all.
4. On submit:
   - Generate document_number: `{project_code}-{type_code}-{sequence}`.
   - Upload file to storage backend.
   - Compute SHA-256.
   - Store documents row.
   - If document_type.requires_approval: create document_approvals rows based on workflow.
   - Notify approvers if any.

**Document detail** (`/documents/:id`):
- Header: document_number, title, type badge, version, status.
- Preview pane: PDF/image inline; docx/xlsx link to download.
- Sidebar: metadata, related links, tags, access.
- Tabs: Versions | Approvals | Access Log | Notes
- Versions: timeline of supersedes chain (older → current → successor).
- Approvals: stage-by-stage list with approve/reject actions.
- Access log: who has viewed/downloaded.

**Approval flow:**
- Approvers see pending approvals in notifications + `/my/approvals` inbox.
- Each approval stage must Approve before next stage opens.
- Rejection at any stage → document status = Draft, requires re-upload or edit.
- Self-approval modal if approver = uploader.

**Share action:**
- Generate time-bound shareable link (signed URL with expiry).
- Optional: require auth (shared with specific user).
- Access logs the share event.

**New version upload:**
- On existing document: "Upload new version" action.
- Creates new documents row with supersedes_document_id = current.
- Sets previous: is_current=false, status=Superseded.
- Carries over metadata (tags, folder, access).
- Resets approval workflow if type requires it.

### Business logic

**Document number generation:**
```
On upload:
  project = documents.related_project_id → projects
  type_code = documents.document_type.code
  prefix = f"{project.project_code}-{type_code}-"
  existing_max = max(sequence) from documents where document_number starts with prefix
  new_sequence = existing_max + 1
  document_number = f"{prefix}{new_sequence:04d}"    # 4-digit zero-padded
```

**File integrity check:**
- On upload: compute SHA-256 hash, store.
- Scheduled weekly: re-fetch stored hash, compare. Mismatch triggers tamper alert.

**Expiry alerts:**
- Scheduled daily: for documents with expiry_date within 60/30/14/7 days, create notification (type: Certificate_Expiry — reused for any expiring doc).

**Approval workflow setup:**
On document creation with type.requires_approval=true:
```
Based on typical_approval_workflow:
  Single_Approver:
    Create 1 document_approvals row with stage=1, required role = typically 'director'
    
  Two_Stage:
    Create 2 document_approvals rows:
      stage=1, required role = typically 'project_manager' or 'finance'
      stage=2, required role = typically 'director'
      
  Consultant_Signed:
    Create 1 document_approvals row:
      stage=1, required_approver_user_id = specified user (design consultant)
```

Exact approver roles configurable per document_type.

**Stage progression:**
- Stage N cannot be Approved until Stage N-1 is Approved.
- Stage N Pending until Stage N-1 decision.
- On Stage N Approved and it's the last stage: document.status = Approved.
- On any stage Rejected: document.status = Draft with rejection feedback.

**Self-approval:**
- If actual_approver_user_id = document.uploaded_by_user_id:
  - Show confirmation modal.
  - Set is_self_approval = true on the approval row.
  - Audit log entry includes metadata.self_approval = true.

**Access control enforcement:**

On any document view/download:
```
Determine user's access level:
  If document.access_restriction = Public: allow.
  If Authenticated: allow if logged in.
  If Project_Team: allow if user has role scoped to related_project_id.
  If Project_Team_Plus_Consultants: 
    - Project team members allowed, OR
    - User is consultant_portal role with scope to this project.
  If Project_Team_Plus_Client:
    - Project team, OR
    - User is connected to the client (HA, joint_venturer) with scope to this project.
  If Internal_Only: allow if user_type = Internal.
  If Restricted_Custom: allow only if user.id in restricted_user_ids.

On any access: log to document_access_log.
```

**Supersede immutability:**
- Once a document is superseded: file content is immutable.
- Can update: tags, folder_path, notes, access_restriction.
- Cannot update: file content, title (reflects what was distributed at that version).

**OCR processing:**
- Async job on PDF/image upload: extract text, set content_searchable=true, ocr_completed_at.
- Adds to full-text search index.

### Permissions

- `documents.view` — project team (scoped by project)
- `documents.create` — PM+, site manager (for their projects)
- `documents.edit` — uploader + PM on Draft; no edit after Approved (upload new version)
- `documents.delete` — blocked; use archive status
- `documents.approve` — per approval workflow
- `documents.admin` — super_admin (can see all regardless of scope)

### Acceptance criteria

- [ ] Upload a document, document_number generated correctly
- [ ] SHA-256 hash stored and verifiable
- [ ] Document type with Two_Stage workflow creates 2 approval rows
- [ ] Stage 2 pending until Stage 1 approved
- [ ] Rejection at any stage resets document to Draft
- [ ] Self-approval modal shows and records correctly
- [ ] Access restriction enforced: user without project scope cannot view Project_Team docs
- [ ] New version upload creates supersedes chain correctly
- [ ] Expiry alerts fire at 60/30/14/7 days
- [ ] Access log records every view/download
- [ ] OCR processes PDFs and enables full-text search
- [ ] Time-bound share link expires correctly

### Out of scope

- Email ingestion for document filing (Future Tasks)
- Electronic signature integration (Future Tasks)
- Full CDE / ISO 19650 workflow (Future Tasks)
- BIM model integration (Future Tasks)

---

## Prompt 4.3 — Compliance Registers, Certificates & Permits

**Dependencies:** Prompts 1.1–1.7, 4.1, 4.2  
**Tables in this prompt:** `document_registers`, `certificates_and_permits`  
**Estimated build time:** 3-4 days

### Build `document_registers`

```
document_registers
─────────────────────────────────────────────
id                          uuid PK
project_id                  uuid NOT NULL FK→projects.id ON DELETE CASCADE
register_type               enum NOT NULL
                              ('CDM','BSA','Part_L','Part_O','Part_Q','Warranty','Fire_Safety',
                               'GDPR','Planning_Discharge','Building_Control','Insurance','Certificates','Contract')
register_item_code          varchar(30) NOT NULL    -- e.g. "CDM-01"
register_item_name          varchar(255) NOT NULL
description                 text
required_by_stage           enum NOT NULL
                              ('Pre_Con','Start_On_Site','Key_Milestone','Pre_PC','PC','Post_PC','Handover','Ongoing')
required_document_type_id   uuid FK→document_types.id
responsible_party           enum NOT NULL
                              ('SY_Homes','Principal_Contractor','Principal_Designer','Architect',
                               'Engineer','Subcontractor','HA_Client','Accountable_Person',
                               'BSR','Building_Control','Fire_Officer')
responsible_user_id         uuid FK→users.id
linked_document_id          uuid FK→documents.id
status                      enum NOT NULL DEFAULT 'Required'
                              ('Required','In_Progress','Submitted','Approved','Completed','Overdue','Not_Applicable','Waived')
waiver_reason               text
waived_at                   timestamp
waived_by_user_id           uuid FK→users.id
due_date                    date
completed_at                timestamp
is_blocker                  boolean NOT NULL DEFAULT false
                              -- true = blocks stage progression (pre-commencement conditions)
notes                       text
display_order               int NOT NULL
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, register_type, status)
- INDEX (responsible_user_id)
- INDEX (due_date) WHERE status IN ('Required','In_Progress')
- INDEX (linked_document_id) WHERE linked_document_id IS NOT NULL
```

### Build `certificates_and_permits`

```
certificates_and_permits
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid FK→projects.id
entity_id                       uuid FK→entities.id    -- for entity-level certs like EL/PL insurance
certificate_type                enum NOT NULL
                                  ('Building_Regs','Fire_Cert','Gas_Safe','Electrical','EPC',
                                   'Party_Wall','Planning_Permission','S106','CIL_Notice',
                                   'Contract','Collateral_Warranty','NHBC_Cover','LABC_Cover',
                                   'Insurance_EL','Insurance_PL','Insurance_PI','Insurance_CAR',
                                   'Site_Licence','Environmental_Permit','Road_Opening',
                                   'Scaffold_Inspection','Crane_Operator','Other')
certificate_number              varchar(100)
issuing_body                    varchar(255)
issued_to_name                  varchar(255)
issued_date                     date NOT NULL
effective_from                  date
expiry_date                     date
status                          enum NOT NULL DEFAULT 'Current'
                                  ('Current','Expiring_Soon','Expired','Renewed','Superseded','Cancelled')
renewal_required                boolean NOT NULL DEFAULT false
renewal_reminder_days           jsonb NOT NULL DEFAULT '[60,30,14,7]'
renewed_by_certificate_id       uuid FK→certificates_and_permits.id
linked_document_id              uuid FK→documents.id
coverage_details                text             -- for insurances: amount, scope
responsible_user_id             uuid FK→users.id
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, certificate_type, status)
- INDEX (entity_id, certificate_type, status)
- INDEX (expiry_date) WHERE status IN ('Current','Expiring_Soon')
- INDEX (linked_document_id) WHERE linked_document_id IS NOT NULL
```

### UI

**`/projects/:id/compliance`** (Compliance tab on project):
- Dashboard: status summary cards per register_type with counts (Required, In Progress, Complete, Overdue).
- Tabs per register: CDM | BSA | Part L | Fire | Warranty | GDPR | Planning | BC | Insurance | Certificates | Contract

**Per-register view:**
- Table of register items: code, name, stage, responsible, due date, status, linked doc.
- Filter by status.
- Link items to documents (picker from project's documents).
- Status update dropdown per row.
- Bulk operations: mark multiple Completed.

**Stage dashboard** (from overview):
- Group register items by required_by_stage.
- Highlight items where due_date approaching or status = Overdue.
- Blocker items (is_blocker=true) flagged prominently.
- Cannot move project to later stage if any blocker items in prior stages not Complete/Waived/Not_Applicable.

**Waiver action:**
- Set status=Waived with mandatory waiver_reason.
- Requires director approval (workflow).
- Logged in audit_log.

**`/projects/:id/certificates`** (Certificates tab):
- Register of time-bound certificates and permits.
- Columns: type, number, issuing_body, issued_date, expiry_date, status.
- Expiring_Soon highlighted amber; Expired red.
- Filter by type, status.
- "+ New certificate" action.

**Certificate detail:**
- All fields.
- Renewal section: shows predecessor and successor chain.
- "Renew this certificate" action → creates new cert with renewed_by_certificate_id back-link.

**Entity-level certs** (insurances, etc.):
- Also visible from `/entities/:id` — same certificates_and_permits table, filtered by entity_id.

### Business logic

**Register auto-seeding on project creation:**

When a project is created, seed document_registers rows based on project_type:

```
Pure_Dev:
  - GDPR register (5 items)
  - Planning Discharge register (items based on planning conditions)
  - Contract register (key contracts: land contract, sales contracts)

Dev_Build and JV:
  All of above, PLUS:
  - CDM register (18 items: F10 notification, PD appointment, PC appointment, 
    pre-con info, CPP, H&S file, ...)
  - BSA register (12 items — IF building >18m or 7+ storeys residential, trigger flag 
    on project)
  - Part L register (6 items: SAP calc, DER/TER check, as-built SAP, EPC, etc.)
  - Part O register (4 items: overheating risk assessment, mitigation measures, 
    compliance statement, commissioning)
  - Part Q register (5 items: security assessment, PAS 24 doors/windows, 
    boundary security, locks/hinges, certification)
  - Fire Safety register (8 items: fire strategy, RRO, fire door schedule, 
    evacuation plan, signage, alarm commissioning, fire risk assessment, 
    accountable person registration)
  - Warranty register (6 items: NHBC or LABC application, structural warranty 
    cover issued, 10-year cover, defect liability provisions, latent defects)
  - Building Control register (7 items: Initial Notice, Plans submitted, 
    inspections scheduled, interim certificates, final certificate, Part P, 
    SAP/EPC submission)
  - Insurance register (5 items: EL confirmed, PL confirmed, PI confirmed for 
    consultants, CAR in place, Product guarantee provisions)

DB_Contract (HA):
  - All Dev_Build items, PLUS:
  - Employer's Requirements compliance checklist
  - Monthly valuation schedule
  - HA-specific handover requirements

Main_Contract:
  - As D&B Contract based on what's in the contract.
```

Detailed seed lists maintained in a versioned seed file per register_type.

**Blocker enforcement:**
- Pre-commencement conditions (planning) flagged is_blocker=true auto-seeded.
- CDM: F10 notification, PD+PC appointments flagged as blockers before Start_On_Site.
- On project stage change attempt:
  - Check for is_blocker=true items in stages ≤ target stage with status NOT IN (Completed, Waived, Not_Applicable).
  - If any: block stage change with error listing blocker items.

**Waiver workflow:**
- Waiver requires: reason (mandatory), director approval.
- Sets status=Waived, waiver_reason, waived_at, waived_by_user_id.
- Audit log entry.

**Certificate expiry cron:**
- Daily scheduled job at 06:00 UTC:
  ```
  For each certificate where status = Current:
    days_to_expiry = expiry_date - today
    
    If days_to_expiry <= 0:
      status = Expired
      notify: responsible_user, project_lead, directors
    Else if days_to_expiry in renewal_reminder_days:
      status = Expiring_Soon (if not already)
      notification type = Certificate_Expiry
      notify: responsible_user, project_lead (and directors if no responsible_user)
  
  For each certificate where status = Expiring_Soon AND days_to_expiry <= 0:
    status = Expired
  ```

**Renewal:**
- Creating a new certificate with renewed_by_certificate_id set:
  - Sets previous cert status = Renewed.
  - Auto-links forward (previous.renewed_by_certificate_id set bidirectionally if supported).
  - Notifies interested parties.

**Linked document integrity:**
- If linked_document_id set and document is deleted: linked_document_id → NULL, status remains.
- If document superseded: linked_document_id updated to new version automatically.

### Permissions

- `document_registers.view` — project team
- `document_registers.edit` — PM+
- `document_registers.approve` — director (for waivers)
- `certificates.view` — project team (scoped)
- `certificates.edit` — PM+, finance (for entity-level)
- `certificates.admin` — super_admin (can override any status)

### Acceptance criteria

- [ ] Project creation auto-seeds correct register items based on project_type
- [ ] Dev_Build project with BSA flag creates 12 BSA items
- [ ] Blocker items prevent stage change until complete
- [ ] Blocker list shown clearly in error message
- [ ] Waiver workflow requires director approval + reason
- [ ] Waived items don't block stage change
- [ ] Certificate expiry cron runs daily and updates statuses
- [ ] Expiry notifications fire at [60,30,14,7] days (configurable per cert)
- [ ] Renewal creates bidirectional link between old and new certificate
- [ ] Linked document auto-updates to new version on supersede
- [ ] Entity-level certificates (insurances) visible on entity detail
- [ ] Compliance dashboard summary shows correct counts per register_type

### Out of scope

- BSR Gateway 2 and 3 automated submission — Future Tasks
- CDM F10 automated filing — Future Tasks
- EPC generation — uses external EPC provider, doc upload only
- Lessons learned register — Phase 4 Post-Completion

---
# Track 5 — Xero Integration

**Goal:** Build bidirectional Xero integration with OAuth, tracking category sync, financial document mirroring, webhooks, and reconciliation.  
**Duration:** 6-8 weeks  
**Prompts:** 5  
**Tables:** 15

**Architecture note:** Xero integration is technically the most complex Phase 1 component. Strongly consider implementing the sync engine, webhook receiver, and OAuth flow as a dedicated service (Python or Node) rather than fully within Emergent. Emergent can consume the service's outputs via API; the service handles OAuth token management, webhook HMAC validation, rate limiting, and retry logic — all of which are easier outside an app builder.

---

## Prompt 5.1 — Xero Connections (OAuth + Token Management)

**Dependencies:** Prompts 1.1, 1.2, 1.3, 1.4  
**Tables in this prompt:** `xero_connections`  
**Estimated build time:** 4-5 days (OAuth flow is significant)

### Build `xero_connections`

```
xero_connections
─────────────────────────────────────────────
id                                  uuid PK
entity_id                           uuid NOT NULL FK→entities.id ON DELETE RESTRICT
xero_tenant_id                      varchar(100) NOT NULL    -- Xero organisation UUID
xero_tenant_type                    enum NOT NULL DEFAULT 'ORGANISATION'
                                      ('ORGANISATION','PRACTICE')
xero_organisation_name              varchar(255) NOT NULL
xero_country_code                   varchar(2)
xero_base_currency                  varchar(3)
xero_timezone                       varchar(50)
xero_line_of_business               varchar(100)
xero_short_code                     varchar(20)
connected_by_user_id                uuid NOT NULL FK→users.id
connected_at                        timestamp NOT NULL DEFAULT now()
connection_status                   enum NOT NULL DEFAULT 'Active'
                                      ('Active','Expired','Revoked','Error','Disconnected')
access_token_encrypted              text NOT NULL
access_token_expires_at             timestamp NOT NULL
refresh_token_encrypted             text NOT NULL
refresh_token_expires_at            timestamp NOT NULL   -- 60-day rolling
scopes_granted                      jsonb NOT NULL DEFAULT '[]'
last_token_refresh_at               timestamp
token_refresh_count                 int NOT NULL DEFAULT 0
last_successful_sync_at             timestamp
last_failed_sync_at                 timestamp
last_sync_error_message             text
webhook_key                         text                 -- Xero webhook signing key
webhook_enabled                     boolean NOT NULL DEFAULT false
disconnected_at                     timestamp
disconnected_reason                 text
created_at                          timestamp NOT NULL DEFAULT now()
updated_at                          timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_tenant_id)
- UNIQUE (entity_id, connection_status) WHERE connection_status = 'Active'
- INDEX (connection_status)
- INDEX (access_token_expires_at) WHERE connection_status = 'Active'
```

### OAuth flow

**Setup prerequisites:**
- Register SY Homes app at developer.xero.com.
- Store `XERO_CLIENT_ID` and `XERO_CLIENT_SECRET` in cloud KMS.
- Redirect URI: `https://platform.sy-homes.co.uk/xero/callback`.
- Scopes required:
  ```
  openid profile email
  accounting.transactions
  accounting.transactions.read
  accounting.contacts
  accounting.contacts.read
  accounting.settings
  accounting.settings.read
  accounting.reports.read
  accounting.attachments
  accounting.attachments.read
  accounting.journals.read
  offline_access
  ```

**Connect flow (from `/entities/:id/xero/connect`):**
```
1. User clicks "Connect Xero" on entity detail.
2. Backend generates:
   - state = cryptographic random 32 bytes (base64)
   - code_verifier = random 64 bytes (PKCE)
   - code_challenge = SHA-256(code_verifier) base64 URL-encoded
3. Stash state + code_verifier + entity_id in session (5-min expiry).
4. Redirect user to:
   https://login.xero.com/identity/connect/authorize
     ?response_type=code
     &client_id=XERO_CLIENT_ID
     &redirect_uri=https://platform.sy-homes.co.uk/xero/callback
     &scope=openid profile email accounting.transactions ... offline_access
     &state={state}
     &code_challenge={code_challenge}
     &code_challenge_method=S256
5. User consents on Xero, selects organisation.
6. Xero redirects to /xero/callback?code=...&state=...
```

**Callback handling (`/xero/callback`):**
```
1. Validate state matches session (CSRF protection).
2. Retrieve code_verifier + entity_id from session.
3. Exchange code for tokens:
   POST https://identity.xero.com/connect/token
   Body:
     grant_type=authorization_code
     client_id=XERO_CLIENT_ID
     code={code}
     redirect_uri={redirect_uri}
     code_verifier={code_verifier}
4. Response contains:
   - access_token (30 min lifespan)
   - refresh_token (60 days, rotates on every use)
   - expires_in (seconds)
   - id_token (JWT for user identity)
5. GET https://api.xero.com/connections
   Authorization: Bearer {access_token}
   Returns array of tenants user consented to.
6. For each tenant the user selected:
   - Encrypt tokens using per-tenant key derived from master KMS key
   - Create xero_connections row
7. Kick off initial sync (Prompt 5.2, 5.3) via sync queue.
8. Redirect user to /entities/:id with success message.
```

**Token refresh:**
```
Scheduled job every 5 minutes:
  SELECT xero_connections WHERE connection_status = 'Active'
    AND access_token_expires_at < now() + interval '10 minutes'
  
  For each:
    POST https://identity.xero.com/connect/token
      grant_type=refresh_token
      client_id=XERO_CLIENT_ID
      refresh_token={decrypted_refresh_token}
    
    Response: new access_token + new refresh_token (rotation).
    
    Update xero_connections:
      access_token_encrypted = encrypt(new access_token)
      access_token_expires_at = now() + expires_in
      refresh_token_encrypted = encrypt(new refresh_token)
      refresh_token_expires_at = now() + 60 days
      token_refresh_count += 1
      last_token_refresh_at = now()
    
    On failure (refresh token expired, revoked, etc.):
      connection_status = 'Expired'
      last_sync_error_message = details
      Create notification to entity's finance team: 'Xero connection lost — reconnect.'
```

**Encryption:**
- Use AES-256-GCM.
- Master key in cloud KMS (AWS KMS / Azure Key Vault / GCP KMS) — NEVER in app config.
- Per-tenant key: `HKDF(master_key, "xero-tokens-" + tenant_id, 32 bytes)`.
- Store nonce + ciphertext + tag in encrypted field (base64).

**API client:**
- Centralised `XeroClient` service used by all sync code.
- Every call: acquire fresh access_token (auto-refresh if close to expiry).
- Rate limiting: per Xero API limits (60 calls/min, 5000 calls/day per tenant).
- Retry on 429 with exponential backoff honouring Retry-After header.
- Retry on 500/502/503/504 up to 3 times.
- Log every call to xero_sync_events (Prompt 5.5).

### UI

**`/entities/:id/xero`:**
- If no active connection: "Connect Xero" button.
- If connected: show connection card:
  - Organisation name, country, currency.
  - Connection status badge (Active / Expired / Error).
  - Connected at / connected by.
  - Last successful sync.
  - Scopes granted.
  - Actions: "Refresh tokens", "Disconnect", "View sync history".
- If Expired: "Reconnect" button to re-trigger OAuth.

**`/xero/connections`** (admin global view):
- List all connections across all entities.
- Status overview: count active / expired / error.

**Disconnect flow:**
- Confirmation modal: "Disconnecting will stop all sync from this organisation. Existing synced data remains. Continue?"
- On confirm:
  - Call Xero to revoke: `POST https://identity.xero.com/connect/revocation`.
  - Set connection_status = Disconnected.
  - Clear encrypted tokens (set to null or empty).
  - Preserve row for audit.

### Business logic

**Entity ↔ Xero tenant binding:**
- One active connection per entity.
- If user tries to connect a second Xero org to same entity: prompt "Disconnect existing first".
- If same Xero tenant already connected to different entity: block with error.

**Error handling:**
- Xero API errors → log with details.
- Classify: retry-able (timeouts, 5xx) vs non-retry-able (4xx auth issues).
- Non-retry → surface to finance team as notification.
- Circuit breaker: if >10 failures in 5 minutes → mark connection Error, suspend sync, notify.

### Permissions

- `xero_connections.view` — finance + director
- `xero_connections.admin` — director (connect/disconnect/reconnect)

### Seed data

None. Connections are created per entity by user action.

### Acceptance criteria

- [ ] OAuth flow completes end-to-end with real Xero sandbox
- [ ] State parameter validated (rejected if mismatch — CSRF protection)
- [ ] PKCE code_verifier works
- [ ] Tokens stored encrypted with AES-256-GCM
- [ ] Scheduled refresh job runs every 5 min
- [ ] Token refresh rotates refresh_token correctly
- [ ] Failed refresh flags connection as Expired
- [ ] Notification sent to finance team on connection loss
- [ ] Disconnect revokes tokens at Xero + clears locally
- [ ] Rate limiter honours 60/min
- [ ] 429 retry honours Retry-After
- [ ] Duplicate tenant connection blocked
- [ ] Circuit breaker triggers on repeated errors

### Out of scope

- Webhook receiver (Prompt 5.5)
- Reference sync (Prompt 5.2)
- Financial document sync (Prompt 5.3)
- Bank transactions / manual journals (Prompt 5.4)

---

## Prompt 5.2 — Reference Sync: Tracking Categories, COA, Tax Rates, Contacts

**Dependencies:** Prompts 1.1, 1.2, 1.4, 1.5, 1.6, 5.1  
**Tables in this prompt:** `xero_tracking_categories`, `xero_tracking_options`, `xero_chart_of_accounts`, `xero_tax_rates`, `xero_contacts`  
**Estimated build time:** 3-4 days

### Build `xero_tracking_categories`

```
xero_tracking_categories
─────────────────────────────────────────────
id                          uuid PK
xero_connection_id          uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_category_id            varchar(100) NOT NULL       -- Xero UUID
xero_category_name          varchar(100) NOT NULL
category_role               enum NOT NULL DEFAULT 'Other'  ('Project','Cost_Code','Other')
xero_status                 varchar(20)                 -- ACTIVE or ARCHIVED
last_synced_at              timestamp NOT NULL DEFAULT now()
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_connection_id, xero_category_id)
```

### Build `xero_tracking_options`

```
xero_tracking_options
─────────────────────────────────────────────
id                          uuid PK
xero_tracking_category_id   uuid NOT NULL FK→xero_tracking_categories.id ON DELETE CASCADE
xero_option_id              varchar(100) NOT NULL
xero_option_name            varchar(100) NOT NULL
xero_status                 varchar(20)
mapped_project_id           uuid FK→projects.id         -- if category.role = Project
mapped_cost_code_id         uuid FK→cost_codes.id       -- if category.role = Cost_Code
mapping_status              enum NOT NULL DEFAULT 'Unmapped'
                              ('Mapped','Unmapped','Ambiguous','Archived_In_Xero')
mapping_confidence          enum DEFAULT 'Unresolved'
                              ('Exact_Match','Fuzzy_Match','Manual','Unresolved')
mapping_notes               text
last_synced_at              timestamp NOT NULL DEFAULT now()
created_at                  timestamp NOT NULL DEFAULT now()
updated_at                  timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_tracking_category_id, xero_option_id)
- INDEX (mapped_project_id) WHERE mapped_project_id IS NOT NULL
- INDEX (mapped_cost_code_id) WHERE mapped_cost_code_id IS NOT NULL
- INDEX (mapping_status)
```

### Build `xero_chart_of_accounts`

```
xero_chart_of_accounts
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_account_id                 varchar(100) NOT NULL
account_code                    varchar(10) NOT NULL   -- "200", "7502"
account_name                    varchar(255) NOT NULL
account_type                    enum NOT NULL
                                  ('REVENUE','DIRECTCOSTS','EXPENSE','CURRENT','FIXED',
                                   'CURRLIAB','TERMLIAB','EQUITY','BANK','PREPAYMENT',
                                   'DEPRECIATN','DEPOSIT')
account_class                   enum NOT NULL
                                  ('ASSET','EQUITY','EXPENSE','LIABILITY','REVENUE')
tax_type                        varchar(20)            -- e.g. INPUT2, OUTPUT2, NONE
description                     text
is_enabled                      boolean NOT NULL DEFAULT true
is_bank_account                 boolean NOT NULL DEFAULT false
bank_account_number             varchar(30)
show_in_expense_claims          boolean DEFAULT false
xero_status                     varchar(20)            -- ACTIVE, ARCHIVED
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_connection_id, xero_account_id)
- UNIQUE (xero_connection_id, account_code)
- INDEX (account_type)
```

### Build `xero_tax_rates`

```
xero_tax_rates
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
tax_type                        varchar(20) NOT NULL   -- code e.g. INPUT2, DRCHARGE20
name                            varchar(100) NOT NULL
rate_pct                        decimal(6,3) NOT NULL
can_apply_to_assets             boolean DEFAULT false
can_apply_to_equity             boolean DEFAULT false
can_apply_to_expenses           boolean DEFAULT false
can_apply_to_liabilities        boolean DEFAULT false
can_apply_to_revenue            boolean DEFAULT false
is_display_tax_rate             boolean DEFAULT true
xero_status                     varchar(20)
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_connection_id, tax_type)
```

### Build `xero_contacts`

```
xero_contacts
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_contact_id                 varchar(100) NOT NULL
xero_contact_number             varchar(50)
name                            varchar(255) NOT NULL
first_name                      varchar(100)
last_name                       varchar(100)
email_address                   varchar(255)
contact_type                    enum DEFAULT 'None'  ('Supplier','Customer','Both','None')
is_supplier                     boolean NOT NULL DEFAULT false
is_customer                     boolean NOT NULL DEFAULT false
is_archived                     boolean NOT NULL DEFAULT false
default_currency                varchar(3)
tax_number                      varchar(50)
accounts_payable_tax_type       varchar(20)
accounts_receivable_tax_type    varchar(20)
phone_numbers                   jsonb DEFAULT '[]'
addresses                       jsonb DEFAULT '[]'
mapped_entity_id                uuid FK→entities.id
mapping_status                  enum DEFAULT 'Unmapped'
                                  ('Mapped','Unmapped','Ambiguous')
mapping_notes                   text
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_connection_id, xero_contact_id)
- INDEX (name)
- INDEX (mapped_entity_id) WHERE mapped_entity_id IS NOT NULL
```

### UI

**`/entities/:id/xero/setup`** (Setup wizard, run on first connection):

**Step 1 — Tracking Categories:**
- Show existing Xero tracking categories.
- Identify which is Project and which is Cost Code (user confirms role).
- If Project category missing: "Create 'Project' tracking category in Xero?" action.
- If Cost Code category missing: similar.
- Warnings if Xero already has 2 non-SY Homes categories (limit reached).

**Step 2 — Options auto-seeded:**
- For Project category: for each active project in platform, check if a matching tracking option exists in Xero. If not: create it (name = project_code + " " + project.name).
- For Cost Code category: same for each active cost code.
- Respect 100-option limit: if exceeded, prompt user to archive inactive projects/codes.

**Step 3 — Chart of Accounts mapping:**
- Import all Xero accounts.
- For each cost code, suggest Xero nominal code based on cost code section (e.g. construction codes → 7000s, overhead codes → 6000s).
- Show suggested mapping; user adjusts; save to cost_codes.xero_nominal_code.

**Step 4 — Contacts:**
- Import all Xero contacts.
- Auto-match to SY Homes entities where tax_number matches entity.vat_number or name contains entity.legal_name.
- For unmatched SY Homes entities: prompt user to select Xero contact.

**Step 5 — Review & Enable webhooks:**
- Summary of what was set up.
- Enable webhooks toggle (requires additional Xero setup — see Prompt 5.5).

**`/xero/mappings`** (ongoing admin view):
- Tabs: Tracking Categories | Options | Chart of Accounts | Tax Rates | Contacts.
- Per tab: list with mapping status, filter Unmapped / Ambiguous.
- Bulk edit for manual mapping.

### Business logic

**Initial sync on OAuth connection:**

Triggered by successful OAuth callback. Runs the following in sequence:

```
1. Fetch org details (GET /api.xro/2.0/Organisation):
   Update xero_connections with organisation name, country, currency, etc.

2. Fetch tracking categories (GET /api.xro/2.0/TrackingCategories):
   Upsert into xero_tracking_categories.
   
3. For each tracking category, fetch options (embedded in response):
   Upsert into xero_tracking_options.

4. Fetch chart of accounts (GET /api.xro/2.0/Accounts):
   Upsert into xero_chart_of_accounts.

5. Fetch tax rates (GET /api.xro/2.0/TaxRates):
   Upsert into xero_tax_rates.

6. Fetch contacts paginated (GET /api.xro/2.0/Contacts?page=1, 2, ...):
   Upsert into xero_contacts.
   
7. Run auto-mapping (see below).

8. Update xero_connections.last_successful_sync_at.
```

**Auto-mapping:**

```
For tracking options in Project category:
  For each option:
    # Exact match on project_code
    Try match option.name prefix or contains project.project_code.
    If found:
      mapped_project_id = project.id
      mapping_status = Mapped
      mapping_confidence = Exact_Match
      continue
    
    # Fuzzy match on project name
    Use Levenshtein distance < 3 or contains.
    If single candidate: 
      mapping_status = Mapped, confidence = Fuzzy_Match.
    If multiple candidates:
      mapping_status = Ambiguous, mapping_notes = "Multiple candidates: X, Y, Z"
    Else:
      mapping_status = Unmapped.

For tracking options in Cost_Code category:
  Same approach with cost_code.code (e.g. "SUB-03").

For Xero accounts:
  Suggest nominal code per cost code based on section:
    Section acquisition → typically asset (1xxx) or overhead (6xxx)
    Section construction → direct cost (7xxx)
    Section overheads → overhead (6xxx)
    Section finance → finance cost (8xxx)
    Section sales_marketing → overhead (6xxx)

For contacts:
  For each SY Homes entity, try to match:
    - tax_number = vat_number → Exact
    - name containing legal_name → Fuzzy
    - Otherwise: Unmapped.
```

**Delta sync:**

Scheduled every 15 min per active connection (configurable):
```
For reference data (tracking categories, COA, tax rates, contacts):
  GET endpoints with If-Modified-Since header or ModifiedAfter query param = last_synced_at.
  Upsert returned items.
  Flag any previously existing items not returned as potentially archived (separate check).
```

**Archive detection:**
```
For xero_tracking_options where Xero status changed to ARCHIVED:
  mapping_status = Archived_In_Xero
  Notify: this tracking option is archived in Xero; consider archiving mapped project/cost code in platform too.
```

**Push tracking options:**
- When a new project is created in platform: auto-create matching tracking option in Xero.
- When a cost code is added: auto-create matching cost code option.
- Push is idempotent (checks if option exists first).

### Permissions

- `xero_sync.view` — finance
- `xero_sync.admin` — director, finance (for manual mapping, force sync)

### Acceptance criteria

- [ ] On OAuth success, setup wizard runs automatically
- [ ] Tracking categories imported correctly
- [ ] Options imported with auto-matching to projects/cost codes
- [ ] Exact matches flagged confidence=Exact_Match
- [ ] Fuzzy matches flagged confidence=Fuzzy_Match
- [ ] Ambiguous matches highlighted for manual resolution
- [ ] Chart of accounts imported
- [ ] Tax rates imported
- [ ] Contacts imported with entity auto-mapping
- [ ] Delta sync runs every 15 min
- [ ] Archive detection flags options that became archived in Xero
- [ ] New project in platform creates matching tracking option in Xero
- [ ] Option creation is idempotent (doesn't duplicate)
- [ ] 100-option limit reached → blocking error with clear guidance

### Out of scope

- Custom field mapping (Future Tasks)
- Bulk contact reconciliation UI (basic only in Phase 1)
- Historical Xero backfill for setup of long-running entities (manual admin task)

---

## Prompt 5.3 — Financial Mirrors: Bills, Invoices, Payments, Credit Notes

**Dependencies:** Prompts 1.1–1.7, 2.4, 2.5, 5.1, 5.2  
**Tables in this prompt:** `xero_bills`, `xero_invoices`, `xero_payments`, `xero_credit_notes`  
**Estimated build time:** 5-7 days

### Build `xero_bills`

```
xero_bills
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_invoice_id                 varchar(100) NOT NULL
invoice_number                  varchar(100)
reference                       varchar(255)
contact_id                      varchar(100)
contact_name                    varchar(255) NOT NULL
invoice_type                    enum NOT NULL  ('ACCPAY','ACCPAYCREDIT')
invoice_date                    date NOT NULL
due_date                        date
status                          enum NOT NULL
                                  ('DRAFT','SUBMITTED','AUTHORISED','PAID','VOIDED','DELETED')
currency_code                   varchar(3) NOT NULL DEFAULT 'GBP'
sub_total                       decimal(14,2) NOT NULL
total_tax                       decimal(14,2) NOT NULL
total                           decimal(14,2) NOT NULL
amount_due                      decimal(14,2) NOT NULL
amount_paid                     decimal(14,2) NOT NULL DEFAULT 0
line_items                      jsonb NOT NULL DEFAULT '[]'
                                  -- [{lineItemId, description, quantity, unitAmount,
                                  --   accountCode, taxType, tracking: [{categoryName, optionName}]}]
sync_hash                       varchar(64)            -- SHA-256 of normalized content
is_fully_tagged                 boolean NOT NULL DEFAULT false
sync_error_type                 enum
                                  ('Missing_Project_Tag','Missing_Cost_Code','Invalid_Cost_Code',
                                   'Ambiguous_Tag','VAT_Mismatch','Other')
sync_error_details              text
xero_updated_date_utc           timestamp
first_synced_at                 timestamp NOT NULL DEFAULT now()
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_invoice_id)
- INDEX (xero_connection_id, status)
- INDEX (is_fully_tagged)
- INDEX (invoice_date DESC)
```

### Build `xero_invoices`

Same structure as xero_bills but for ACCREC / ACCRECCREDIT (sales invoices). Additional field:

```
xero_invoices
─────────────────────────────────────────────
(all fields from xero_bills, but invoice_type enum changes to):
invoice_type                    enum NOT NULL  ('ACCREC','ACCRECCREDIT')

source_type                     enum NOT NULL DEFAULT 'Pure_Xero_Origin'
                                  ('Plot_Sale','Intercompany_Valuation','Intercompany_Recharge',
                                   'Other_Platform_Generated','Pure_Xero_Origin')
related_plot_id                 uuid     -- Phase 5
related_valuation_id            uuid     -- Phase 4
generated_by_platform           boolean NOT NULL DEFAULT false

Indexes:
- UNIQUE (xero_invoice_id)
- INDEX (xero_connection_id, status)
- INDEX (invoice_date DESC)
```

### Build `xero_payments`

```
xero_payments
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_payment_id                 varchar(100) NOT NULL
xero_invoice_id                 varchar(100)
xero_credit_note_id             varchar(100)
xero_bank_account_id            varchar(100) NOT NULL
payment_date                    date NOT NULL
payment_type                    varchar(50)   -- ACCPAYPAYMENT, ACCRECPAYMENT, etc.
amount                          decimal(14,2) NOT NULL
reference                       varchar(255)
currency_rate                   decimal(10,6)
status                          varchar(20) NOT NULL   -- AUTHORISED, DELETED
linked_actual_id                uuid FK→actuals.id
first_synced_at                 timestamp NOT NULL DEFAULT now()
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_payment_id)
- INDEX (xero_invoice_id) WHERE xero_invoice_id IS NOT NULL
- INDEX (payment_date DESC)
```

### Build `xero_credit_notes`

```
xero_credit_notes
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_credit_note_id             varchar(100) NOT NULL
credit_note_number              varchar(100)
contact_id                      varchar(100)
contact_name                    varchar(255)
credit_note_type                enum NOT NULL  ('ACCPAYCREDIT','ACCRECCREDIT')
date                            date NOT NULL
status                          varchar(30) NOT NULL
currency_code                   varchar(3) NOT NULL DEFAULT 'GBP'
sub_total                       decimal(14,2) NOT NULL
total_tax                       decimal(14,2) NOT NULL
total                           decimal(14,2) NOT NULL
remaining_credit                decimal(14,2) NOT NULL
line_items                      jsonb NOT NULL DEFAULT '[]'
reference                       varchar(255)
allocations                     jsonb DEFAULT '[]'  -- [{invoice_id, amount, date}]
linked_reversing_actual_id      uuid FK→actuals.id
first_synced_at                 timestamp NOT NULL DEFAULT now()
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_credit_note_id)
- INDEX (xero_connection_id)
- INDEX (date DESC)
```

### UI

**`/xero/bills`** (finance view):
- Paginated list with filters: entity, date range, status, is_fully_tagged, sync_error_type.
- Columns: Invoice #, Contact, Date, Due, Status, Total, Tagged flag, Sync error.
- Filter "Untagged bills" shows bills needing attention.

**Bill detail:**
- Header: invoice_number, contact, dates, status, totals.
- Line items table: description, qty, unit amount, account, tax, tracking (project + cost code).
- Tagging assistance: for untagged lines, show dropdown of projects + cost codes.
- "Tag in Xero" action: push updated line to Xero; on success, sync refreshes bill and actuals created.
- "Open in Xero" link.

**`/xero/invoices`** (sales — finance view):
- Similar structure for ACCREC invoices.

**`/xero/reconciliation`** dashboard (per entity):
- Health indicator: % of bills tagged this month.
- Chart: trend over last 6 months.
- Top untagged suppliers (training opportunity).
- Count by sync_error_type.

### Business logic

**Initial backfill on connection:**

After reference sync (Prompt 5.2) completes:
```
1. Fetch bills for last 12 months (configurable):
   GET /api.xro/2.0/Invoices
     ?where=Type="ACCPAY" AND Date >= {12 months ago}
     &order=UpdatedDateUTC DESC
     &page=1,2,...
2. Process each (see below).
3. Same for invoices (ACCREC).
4. Fetch payments.
5. Fetch credit notes.
```

**Bill processing (core mapping logic):**

```
For each Xero bill:
  1. Compute sync_hash = SHA-256(normalized JSON of key fields).
  2. Upsert into xero_bills by xero_invoice_id.
  3. If status = VOIDED or DELETED:
     Void any linked actuals via source_type=Xero_Bill, external_id=xero_invoice_id+line_id.
     Skip further processing.
  4. If status = DRAFT:
     Store but don't create actuals (not yet committed).
     Skip further processing.
  5. For each line item:
     a. Extract tracking tags:
        project_tracking = line.tracking where categoryName matches 
                           xero_tracking_categories.category_role = Project
        costcode_tracking = similar for Cost_Code role
     b. Resolve project:
        xero_tracking_options where option_name = project_tracking.option_name
        → mapped_project_id
        If not found: mark line untagged (error type = Missing_Project_Tag).
     c. Resolve cost code: similar.
     d. If both resolved:
        Find budget_line in project.current_budget where cost_code_id matches.
        If not found: create "unbudgeted" budget_line with original=0 (flagged for PM review).
        Create or update actuals row:
          external_id = xero_invoice_id + "_" + line.line_item_id
          source_type = Xero_Bill
          source_reference = invoice_number
          transaction_date = invoice_date
          posting_date = min(invoice_date, today)
          net_amount = line.line_amount (ex tax)
          vat_amount = line.tax_amount
          gross_amount = line.line_amount + line.tax_amount
          vat_rate_pct = derive from tax_type
          is_vat_recoverable = tax_type IN (INPUT, INPUT2, DRCHARGE20 with input reclaim)
          supplier_name_snapshot = contact_name
          supplier_invoice_ref = invoice_number
          description = line.description
          project_id = resolved project
          budget_line_id = resolved budget line
          entity_id = connection.entity_id
          is_cis_applicable = cost_code.is_cis_applicable AND supplier is CIS
          status = 
            if bill.status = AUTHORISED: Posted
            if bill.status = PAID: Paid
     e. Apply CIS if applicable (Prompt 2.5 logic).
     f. Apply retention if applicable.
     g. Mark line is_fully_tagged on xero_bills if all lines tagged.
  6. Set is_fully_tagged = true only if ALL lines tagged.
  7. Set sync_error_type if any lines have issues.
```

**VAT treatment derivation:**
```
From Xero tax_type → platform treatment:
  NONE → no VAT
  OUTPUT, OUTPUT2 → 20% output VAT (sales)
  INPUT, INPUT2 → 20% input VAT recoverable (purchases)
  ZERORATED → 0% (new-build sales, exports)
  EXEMPTOUTPUT, EXEMPTINPUT → exempt
  DRCHARGE20 → domestic reverse charge 20%
  RRINPUT, RROUTPUT → reduced rate (5% — EWIT for some conversions)
  
VAT check: if platform-expected treatment != Xero treatment:
  Flag sync_error_type = VAT_Mismatch.
```

**CIS handling via Xero:**
- Xero's CIS module marks bills with CIS deductions.
- Platform reads CIS deduction amount from bill's line_amount / tax breakdown.
- Stores in actuals.cis_deduction_amount for reporting.

**Payment processing:**
```
For each xero_payment:
  If xero_invoice_id set:
    Find xero_bills or xero_invoices by xero_invoice_id.
    Update amount_paid / amount_due on xero_bills/invoices.
    If bill.amount_due == 0: change to PAID (if AUTHORISED).
    Link to matching actuals:
      If bill → actuals: mark actuals.status = Paid, paid_date, payment_reference.
```

**Credit note processing:**
```
For each xero_credit_note:
  Upsert xero_credit_notes.
  For each line (same mapping as bills):
    Create actuals row with source_type = Xero_Credit_Note, NEGATIVE amounts.
    linked_reversing_actual_id set if matched to original bill's actual.
```

**Edit detection via sync_hash:**
```
On re-sync, compare stored sync_hash vs new hash.
If different: bill edited in Xero.
  Process changes:
    Find actuals created from this bill.
    Update amounts, descriptions, tagging.
    Log in audit_log with reason "Xero bill edited".
```

**Xero push (platform → Xero):**

For sales invoices generated by platform (Phase 4 valuations, Phase 5 plot sales):
```
POST /api.xro/2.0/Invoices
  Body: {
    Type: "ACCREC",
    Contact: { ContactID: resolved from xero_contacts },
    Date: invoice_date,
    LineItems: [{
      Description: line_description,
      Quantity: 1,
      UnitAmount: net_amount,
      AccountCode: resolved_xero_nominal,
      TaxType: resolved_tax_type,
      Tracking: [
        { Name: "Project", Option: project_option_name },
        { Name: "Cost Code", Option: cost_code_option_name }
      ]
    }],
    Reference: platform_reference
  }

On success: update xero_invoices with returned xero_invoice_id.
```

### Permissions

- `xero_bills.view` — finance, PM (scoped by entity)
- `xero_invoices.view` — finance, PM (scoped by entity)
- `xero_bills.edit` — finance (to tag untagged bills)
- `xero_sync.admin` — director, finance (force sync, backfill)

### Acceptance criteria

- [ ] Initial backfill imports last 12 months of bills
- [ ] Fully-tagged bill creates actuals correctly
- [ ] Untagged bill stored but NO actuals created
- [ ] Re-sync of fully-tagged bill (previously untagged) creates actuals
- [ ] VAT treatment correctly applied
- [ ] Reverse charge (DRCHARGE20) treated correctly
- [ ] CIS deductions captured from Xero
- [ ] Credit note creates reversing actual
- [ ] Payment status updates bill + actuals
- [ ] Editing a bill in Xero (changing amount) updates actuals via sync_hash diff
- [ ] Voiding bill in Xero voids platform actuals
- [ ] Platform-generated sales invoice pushes to Xero successfully with tracking

### Out of scope

- Expense claims (Phase 4)
- Manual journals (Prompt 5.4)
- Bank transactions (Prompt 5.4)
- Formal subcontractor CIS verification (Phase 4)

---

## Prompt 5.4 — Sync Queue, Webhooks, Bank Transactions, Manual Journals

**Dependencies:** Prompts 1.1–1.7, 5.1, 5.2, 5.3  
**Tables in this prompt:** `xero_sync_queue`, `xero_webhooks`, `xero_bank_transactions`, `xero_manual_journals`  
**Estimated build time:** 5-7 days

### Build `xero_sync_queue`

```
xero_sync_queue
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
operation_type                  enum NOT NULL
                                  ('Fetch_Bill','Fetch_Invoice','Fetch_Payment','Fetch_Contact',
                                   'Fetch_Tracking_Categories','Fetch_Tracking_Options',
                                   'Fetch_COA','Fetch_Tax_Rates','Fetch_Bills_Delta',
                                   'Fetch_Invoices_Delta','Push_Invoice','Push_Bill',
                                   'Push_Credit_Note','Push_Tracking_Option','Push_Contact',
                                   'Reconcile_Sync','Webhook_Received')
payload                         jsonb NOT NULL DEFAULT '{}'
priority                        enum NOT NULL DEFAULT 'Normal'  ('Critical','High','Normal','Low')
status                          enum NOT NULL DEFAULT 'Queued'
                                  ('Queued','Running','Complete','Failed','Dead_Letter','Cancelled')
attempts                        int NOT NULL DEFAULT 0
max_attempts                    int NOT NULL DEFAULT 5
next_attempt_at                 timestamp
last_error                      text
last_attempted_at               timestamp
started_at                      timestamp
completed_at                    timestamp
triggered_by                    enum NOT NULL DEFAULT 'Polling'
                                  ('Webhook','Polling','Manual','Scheduled','Cascade')
triggered_by_user_id            uuid FK→users.id
correlation_id                  uuid
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (status, priority, next_attempt_at) WHERE status IN ('Queued','Failed')
- INDEX (xero_connection_id, status)
- INDEX (correlation_id) WHERE correlation_id IS NOT NULL
- INDEX (operation_type, status)
```

### Build `xero_webhooks`

```
xero_webhooks
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid FK→xero_connections.id ON DELETE CASCADE
xero_tenant_id                  varchar(100) NOT NULL
event_category                  enum NOT NULL  ('INVOICE','CONTACT')
event_type                      enum NOT NULL  ('CREATE','UPDATE')
resource_id                     varchar(100) NOT NULL     -- Xero invoice/contact ID
event_date_utc                  timestamp NOT NULL
webhook_payload                 jsonb NOT NULL
signature                       varchar(255) NOT NULL    -- HMAC-SHA256
signature_verified              boolean NOT NULL DEFAULT false
status                          enum NOT NULL DEFAULT 'Received'
                                  ('Received','Validated','Enqueued','Processed','Rejected','Duplicate')
related_sync_queue_id           uuid FK→xero_sync_queue.id
received_at                     timestamp NOT NULL DEFAULT now()
processed_at                    timestamp
processing_error                text
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (xero_tenant_id, received_at DESC)
- INDEX (status)
- UNIQUE (xero_tenant_id, event_category, resource_id, event_date_utc)  -- dedup
```

### Build `xero_bank_transactions`

```
xero_bank_transactions
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_transaction_id             varchar(100) NOT NULL
xero_bank_account_id            varchar(100) NOT NULL
bank_account_name               varchar(255)
transaction_type                varchar(20)   -- SPEND, RECEIVE, SPEND_OVERPAYMENT, etc.
transaction_date                date NOT NULL
contact_id                      varchar(100)
contact_name                    varchar(255)
reference                       varchar(255)
sub_total                       decimal(14,2) NOT NULL
total_tax                       decimal(14,2) NOT NULL
total                           decimal(14,2) NOT NULL
status                          varchar(20)   -- AUTHORISED, DELETED
line_items                      jsonb NOT NULL DEFAULT '[]'
is_reconciled                   boolean NOT NULL DEFAULT false
bank_transaction_category       varchar(50)
xero_updated_date_utc           timestamp
first_synced_at                 timestamp NOT NULL DEFAULT now()
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_transaction_id)
- INDEX (xero_connection_id, transaction_date DESC)
```

### Build `xero_manual_journals`

```
xero_manual_journals
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
xero_manual_journal_id          varchar(100) NOT NULL
date                            date NOT NULL
narration                       text
status                          varchar(20)   -- DRAFT, POSTED, DELETED, VOIDED
journal_lines                   jsonb NOT NULL DEFAULT '[]'
                                  -- [{account_code, description, tax_type, tax_amount,
                                  --   net_amount, tracking: [...]}]
url                             text
show_on_cash_basis_reports      boolean DEFAULT true
xero_updated_date_utc           timestamp
first_synced_at                 timestamp NOT NULL DEFAULT now()
last_synced_at                  timestamp NOT NULL DEFAULT now()
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (xero_manual_journal_id)
- INDEX (xero_connection_id, date DESC)
```

### Webhook endpoint

**`POST /xero/webhook`** (public, rate-limited):

```
1. Read request body as raw bytes.
2. Read x-xero-signature header.
3. Compute expected signature:
   HMAC-SHA256(body, webhook_key).base64()
4. Constant-time compare signatures.
5. If mismatch: return 401, log event.
6. Parse body JSON:
   { events: [ { resourceUrl, resourceId, eventDateUtc, eventType, eventCategory, tenantId, tenantType }, ... ] }
7. For each event:
   a. Lookup xero_connection by tenantId.
   b. Insert xero_webhooks row (status=Received; signature verified).
   c. Dedup check via (tenant_id, category, resource_id, event_date_utc) UNIQUE.
      If duplicate: status=Duplicate.
   d. Create xero_sync_queue row:
      operation_type = based on category (Fetch_Invoice / Fetch_Contact)
      priority = High
      triggered_by = Webhook
      correlation_id = webhook row UUID
      status = Queued
   e. Update webhook status=Enqueued.
8. Return 200 OK within 5 seconds (Xero webhook timeout).
9. Async worker picks up queue items and fetches full data.
```

### Sync queue worker

```
Background worker processes xero_sync_queue:
  Every 5 seconds:
    Dequeue jobs where:
      status = Queued
      priority DESC, next_attempt_at <= now()
      LIMIT N (per-connection concurrency limit, default 3)
    
    For each job:
      Mark status=Running, started_at=now().
      Call appropriate handler based on operation_type.
      
      On success:
        status=Complete, completed_at=now()
        Create xero_sync_events row (Prompt 5.5).
      
      On failure:
        attempts += 1
        last_error = error message
        
        If attempts >= max_attempts:
          status=Dead_Letter
          Notify: finance team (notification type = Xero_Sync_Error).
        Else:
          status=Failed
          next_attempt_at = now() + exponential_backoff(attempts)
            (2^attempts × 30 seconds, cap at 1 hour)
```

### UI

**`/xero/sync-queue`** (finance):
- List jobs with filter by status, operation_type, connection.
- Columns: created, operation, status, attempts, last error, next attempt.
- Actions: Retry (reset status to Queued, clear error), Cancel.
- Auto-refresh every 10s when Running jobs exist.

**`/xero/webhooks`** (admin):
- Recent webhooks received.
- Signature verification status indicator.
- Duplicate detection log.

**`/xero/bank-transactions`** (finance, per entity):
- List of bank transactions from Xero.
- Can link to actuals (for cost reconciliation) or cash_flow_entries.

**`/xero/journals`** (finance):
- List of manual journals from Xero.
- Read-only (don't push journals from platform).

### Business logic

**Queue job handlers:**

Operation types and their handlers:
```
Fetch_Bill:
  Call GET /api.xro/2.0/Invoices/{invoice_id}
  Process into xero_bills + actuals (Prompt 5.3 logic).

Fetch_Invoice: same for ACCREC.

Fetch_Payment:
  GET /api.xro/2.0/Payments/{payment_id}
  Process into xero_payments.

Fetch_Contact:
  GET /api.xro/2.0/Contacts/{contact_id}
  Upsert into xero_contacts.

Fetch_Bills_Delta:
  GET /api.xro/2.0/Invoices?where=Type="ACCPAY"&page=N
  Include ModifiedAfter header = last successful delta sync timestamp.
  Process all returned.

Push_Invoice:
  POST /api.xro/2.0/Invoices with payload.
  Update platform record with returned xero_invoice_id.

Reconcile_Sync:
  Full reconciliation pass (Prompt 5.5).

Webhook_Received:
  Wrapper that extracts resource from webhook payload and enqueues Fetch_*.
```

**Cascade logic:**
- When certain syncs complete, others are enqueued automatically:
  - Initial OAuth → enqueue Fetch_Tracking_Categories, Fetch_COA, Fetch_Tax_Rates, Fetch_Contacts (parallel).
  - All reference fetches complete → enqueue Fetch_Bills_Delta and Fetch_Invoices_Delta (for 12-month backfill).
  - Bill fetched with referenced contact missing → enqueue Fetch_Contact.
  - Credit note fetched → ensure related invoice fetched.

**Manual journal processing:**
- Journals are typically accountant adjustments.
- Not auto-converted to actuals (too variable).
- Stored for reference and audit visibility.
- Optional future extension: detect journals tagged with project+cost code and create actuals with source_type=Journal.

**Bank transaction processing:**
- Xero bank feeds produce these.
- Not auto-converted to actuals by default (usually correspond to payments of bills already synced).
- UI allows manual linking to actuals or cash_flow_entries.

### Permissions

- `xero_sync.view` — finance
- `xero_sync.admin` — director, finance (manual retries, cancel)

### Acceptance criteria

- [ ] Webhook endpoint validates HMAC signature correctly
- [ ] Invalid signature returns 401
- [ ] Duplicate webhooks detected and flagged
- [ ] Valid webhook creates xero_sync_queue row within 5 seconds
- [ ] Webhook returns 200 within 5-second Xero timeout
- [ ] Worker processes Queued jobs
- [ ] Failed job retries with exponential backoff
- [ ] Job reaching max_attempts goes to Dead_Letter + notification sent
- [ ] Cascade logic: bill sync triggers contact fetch when missing
- [ ] Bank transactions imported read-only
- [ ] Manual journals imported read-only
- [ ] Manual retry action works
- [ ] Cancel action works on Queued jobs
- [ ] Queue depth visible on dashboard

### Out of scope

- Journals → actuals auto-creation (Future Tasks)
- Bank reconciliation UI (basic view only in Phase 1)
- Multi-tenant webhook routing for Practice connections

---

## Prompt 5.5 — Reconciler, Sync Events, Delta Sync

**Dependencies:** Prompts 1.1–1.7, 5.1, 5.2, 5.3, 5.4  
**Tables in this prompt:** `xero_sync_events`  
**Estimated build time:** 3-4 days

Caps off Track 5 by adding the audit trail and reconciliation passes.

### Build `xero_sync_events`

```
xero_sync_events
─────────────────────────────────────────────
id                              uuid PK
xero_connection_id              uuid NOT NULL FK→xero_connections.id ON DELETE CASCADE
sync_queue_id                   uuid FK→xero_sync_queue.id
event_type                      enum NOT NULL  ('Fetch','Push','Create','Update','Delete','Reconcile','Error','Warning')
resource_type                   varchar(50) NOT NULL     -- "Bill","Invoice","Contact", etc.
resource_id                     varchar(100)
operation                       varchar(100) NOT NULL
outcome                         enum NOT NULL
                                  ('Success','Partial_Success','Failure','Skipped','Deduplicated')
record_count                    int DEFAULT 0
error_code                      varchar(50)
error_message                   text
request_duration_ms             int
request_url                     text
response_status                 int
details                         jsonb DEFAULT '{}'
triggered_by_user_id            uuid FK→users.id
correlation_id                  uuid
created_at                      timestamp NOT NULL DEFAULT now()  -- immutable

Indexes:
- INDEX (xero_connection_id, created_at DESC)
- INDEX (outcome) WHERE outcome IN ('Failure','Partial_Success')
- INDEX (resource_type, resource_id)
- INDEX (correlation_id) WHERE correlation_id IS NOT NULL
```

### UI

**`/xero/sync-events`** (finance + admin):
- Paginated list, filters: outcome, event_type, resource_type, date range, connection.
- Columns: time, operation, resource, outcome badge, duration, error (if any).
- Click event → detail modal with full request/response metadata.
- Export CSV for deep analysis.

**`/xero/dashboard`** per entity:
- KPI tiles:
  - Last successful sync: X minutes ago.
  - Bills tagged this month: X / Y (%).
  - Active sync queue depth.
  - Failed operations (24h): count.
  - Webhook events received (24h): count.
- Trend charts:
  - Daily operation count split by outcome.
  - Bill tag rate over time.
- Error breakdown by sync_error_type.

### Business logic

**Event logging (built into every sync operation):**

Every API call produces a xero_sync_events row:
```
Before call:
  start_time = now()

Try API call.

After call (success or failure):
  Create xero_sync_events:
    event_type = Fetch / Push / Create / Update / Delete
    resource_type = extracted from endpoint
    resource_id = extracted from response
    operation = endpoint path
    outcome = Success / Failure / Skipped / Deduplicated
    record_count = number of records returned or updated
    error_code = on failure
    error_message = on failure
    request_duration_ms = now() - start_time (ms)
    request_url = redacted (no sensitive query params)
    response_status = HTTP status
    details = structured extra info (e.g. rate_limit_remaining)
    correlation_id = from the originating sync_queue job
```

**Full delta reconciliation (nightly):**

Scheduled nightly per connection (configurable time, default 02:00 UTC):
```
correlation_id = new UUID for this reconciliation run.

1. Fetch all modified entities since last_successful_sync_at:
   - Bills: GET /Invoices?where=Type="ACCPAY"&ModifiedAfter={timestamp}
   - Invoices: GET /Invoices?where=Type="ACCREC"&ModifiedAfter={timestamp}
   - Payments: GET /Payments?ModifiedAfter={timestamp}
   - Credit notes: GET /CreditNotes?ModifiedAfter={timestamp}
   - Contacts: GET /Contacts?ModifiedAfter={timestamp}
   - Bank transactions: GET /BankTransactions?ModifiedAfter={timestamp}
   - Manual journals: GET /ManualJournals?ModifiedAfter={timestamp}
   
2. For each returned item:
   Compare sync_hash with stored value.
   If different: reprocess.
   If new: process fresh.
   Log event.

3. Orphan detection:
   a. Find actuals where source_type=Xero_Bill AND voided_at IS NULL 
      AND external_id not matching any current xero_bills OR 
      matching xero_bills.status IN ('VOIDED','DELETED').
      
      For each: void the actual with void_reason = "Xero bill voided/deleted via reconciliation".
      Log as xero_sync_events event_type=Delete, outcome=Success.
   
   b. Find xero_bills.amount_paid mismatch with sum of payments referencing it.
      Log Warning if mismatch > £0.01.

4. Amount reconciliation:
   Sum of xero_bills.total (AUTHORISED / PAID) per connection per quarter.
   Sum of corresponding platform actuals.
   Compare. Log Warning if mismatch > £1.
   
5. VAT reconciliation:
   Platform's computed VAT per quarter vs Xero's VAT Return totals.
   GET /Reports/TaxReturns for each quarter end.
   Compare. Log Warning if mismatch.

6. Mapping health:
   % of bills fully tagged in last 30 days.
   Number of Unmapped tracking options.
   List of suppliers with >3 untagged bills in 30 days.
   Summarise to dashboard metrics.

7. Update xero_connections.last_successful_sync_at = now() on completion.

8. Send summary notification to finance:
   "Nightly reconciliation complete. 42 bills updated, 1 warning (VAT mismatch Q1 2026 £2.13)."
```

**Manual reconciliation trigger:**
- Admin action: "Run reconciliation now" on /xero/dashboard.
- Same logic as nightly.
- Useful after fixing mapping issues.

### Permissions

- `xero_sync.view` — finance
- `xero_sync.admin` — director, finance (trigger reconciliation)

### Acceptance criteria

- [ ] Every Xero API call creates a xero_sync_events row
- [ ] Failed calls log error_code and error_message
- [ ] Request duration tracked
- [ ] Sync events dashboard shows recent activity
- [ ] Nightly reconciliation job runs
- [ ] Reconciliation detects voided-in-Xero bills and voids platform actuals
- [ ] Amount reconciliation detects mismatches above £1 threshold
- [ ] Dashboard KPIs render correctly
- [ ] Manual reconciliation trigger works
- [ ] Summary notification sent to finance after reconciliation
- [ ] correlation_id links sync_queue jobs to events

### Out of scope

- Real-time anomaly detection on sync patterns — Future Tasks
- External audit log export (to SIEM) — Future Tasks
- Cross-entity intercompany reconciliation — Future Tasks (monthly workflow Phase 2)

---

# End of Phase 1 Emergent Brief

## Summary of deliverable

This brief contains 25 prompts across 5 tracks, specifying the Phase 1 platform build:

**Track 1 — Foundation (7 prompts, 23 tables):**
- 1.1 Entities
- 1.2 Users, Roles, Permissions
- 1.3 Sessions, Login History, Invitations, SSO, API Keys
- 1.4 Audit Log
- 1.5 Projects, Project Team Members
- 1.6 Cost Codes
- 1.7 System Config, Notifications

**Track 2 — Commercial Engine (7 prompts, 22 tables):**
- 2.1 SDLT Rates, Appraisal Defaults
- 2.2 Appraisals Core (with SDLT/RLV/finance engines)
- 2.3 Appraisal Governance
- 2.4 Budgets Core
- 2.5 Actuals and Commitments
- 2.6 Budget Change Control, Forecasts
- 2.7 Cash Flow

**Track 3 — Programme (3 prompts, 10 tables):**
- 3.1 Templates, Calendars
- 3.2 Programmes, Tasks, CPM Engine
- 3.3 Task Updates, Baselines, Alerts, Weekly Reports

**Track 4 — QA & Documents (3 prompts, 7 tables):**
- 4.1 Document Types, Templates
- 4.2 Documents, Approvals, Access Log
- 4.3 Compliance Registers, Certificates & Permits

**Track 5 — Xero Integration (5 prompts, 15 tables):**
- 5.1 Connections (OAuth)
- 5.2 Reference Sync
- 5.3 Financial Mirrors
- 5.4 Sync Queue, Webhooks, Bank Txn, Journals
- 5.5 Reconciler, Sync Events

**Total:** 77 tables, ~1,288 fields.

**Build duration estimate:** 4-6 months with sequential builds; 3-4 months with parallel teams on Tracks 3 and 4.

**Next steps:**
1. Review this brief against Rhys's priorities.
2. Start Prompt 1.1 in Emergent.
3. Test each prompt's acceptance criteria before moving on.
4. Log deviations and refinements in a running change log.
5. Update this brief when prompts require clarification after real-world building.

This is a living document — refine as building proceeds.

---

_End of SY_Homes_Emergent_Brief_Phase1.md — version 1.0 — April 2026_
