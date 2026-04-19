# Change Log — SY Homes Platform Build

Running log of deviations, refinements, and corrections made during the build
of Phase 1. Update this any time something built differs from what the
specification says, or when a specification error is found and corrected.

## Format

Each entry: date, prompt reference (if applicable), change, rationale.

## Entries

### 2026-04-19 — Initial Specification

- Phase 1 specification pack v1.0 committed.
- `programme_calendars` schema updated from XLSX (7 per-weekday booleans) to
  JSONB-based design to match Emergent brief. Field count 1,293 → 1,288.
- Platform Spec docx updated to reference 1,288 field count.

<!-- Add entries below as you build. Example format:

### 2026-04-19 — Prompt 1.1 Entities built

- Full vertical slice delivered: schema, migration, API, React UI, validation, seed data, scheduler.
- 8/8 acceptance criteria fully passing.
- Tenants table added (multi-tenant ready, single-tenant live); all other tables include tenant_id.
- Alembic migration 0001_initial_entities: tenants + entities + 5 enums + partial unique indexes + set_updated_at trigger + per-table triggers.
- APScheduler daily 06:00 UTC insurance expiry sweep; exact-day threshold logic (60/30/14/7/0) with expired daily-loop.
- 53 backend tests passing (31 API + 22 threshold sweep).
- Idempotent container bootstrap at /root/.emergent/on-restart.sh.

**Deviations:**
- Emergent initially deferred Alembic to create_all(), retrofitted before Prompt 1.2.
- Pattern set: Emergent to surface agreed-standard deviations upfront before deviating, not silently.

**Known items for future prompts:**
- Permission stubs in entities router to be wired in Prompt 1.2
- created_by_user_id on entities to be backfilled retroactively in Prompt 1.2
- Cosmetic React warning (`<span>` in `<option>`) to fix in Prompt 1.2
- Suggested 30-min polish when Prompt 1.7 lands: surface insurance urgency dot on Entities list once notifications table exists

### 2026-05-02 — Prompt 1.2 Users
- Added preferred_name field to users table not specified in brief.
  Rationale: Several team members use different daily name vs legal name.
- Changed mfa_method default from TOTP to Email for easier initial onboarding.
  Spec says TOTP should be preferred; will revert after onboarding complete.

-->
## Polish Pass TODOs (post-Phase 1)

UX refinements deferred until all 25 build prompts complete. Don't action
during build — log here, address in one focused polish pass.

### Entity UX
- Demote "Entities" from primary sidebar to Settings/Admin section.
  In daily operations SY Homes staff don't think of themselves as working
  for three separate companies; it's one team. Entity structure is plumbing,
  not foreground. Keep data model exactly as built (required for VAT, CT,
  lender reporting, ringfenced liability) — just tone down UI prominence.
- Auto-derive entity on cost postings from project (and linked ConstructionCo
  for construction costs). Don't require manual entity selection in common
  cases.
- Default dashboards to unified "Group" view; entity breakdown as optional
  filter, not default display.
- Keep entity exposure in finance/Xero flows (where Louise and the accountant
  genuinely care) and at project setup (set once, forgotten).

### Brand polish
- Apply SY Homes brand palette: orange #E85A1B (primary accent),
  navy #1F2D3D (primary dark).
- Select and apply production font stack.
- Unified component styling pass across all 10 modules.
