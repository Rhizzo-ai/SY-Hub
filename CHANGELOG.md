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

### 2026-05-02 — Prompt 1.2 Users
- Added preferred_name field to users table not specified in brief.
  Rationale: Several team members use different daily name vs legal name.
- Changed mfa_method default from TOTP to Email for easier initial onboarding.
  Spec says TOTP should be preferred; will revert after onboarding complete.

-->
