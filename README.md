# SY Hub — Custom Platform

Phase 1 specification and build artefacts for the SY Homes custom property
development platform.

## What's in this repo

| File | Purpose |
|------|---------|
| `SY_Homes_Data_Model.xlsx` | Complete data model — 77 tables, 1,288 fields, relationships, seed data |
| `SY_Homes_Platform_Spec_v2.docx` | Narrative specification — design principles, module explanations, calculations |
| `SY_Homes_Emergent_Brief_Phase1.md` | Build brief — 25 prompts across 5 tracks for feeding into Emergent AI |
| `SY_Homes_Future_Tasks.md` | Phase 2+ deferred items — running list of things out of scope for Phase 1 |
| `SY_Homes_Audit_Report.md` | Formal audit of the Phase 1 specification pack |

## How to use

Start with `SY_Homes_Emergent_Brief_Phase1.md`. Read the "How to use this brief"
section at the top. Work through the 25 prompts sequentially starting with
Prompt 1.1 Entities. Use the other documents as reference.

## Build approach

Each prompt is pasted into Emergent, which generates the corresponding tables,
UI, and business logic. After each prompt, verify against the acceptance
criteria before moving on. Commit to this repo after each completed prompt.

Target Phase 1 build time: 4-6 months with consistent 15-20 hours/week.

## Versioning

Specification version 1.0, dated April 2026. Changes during build will be
logged in `CHANGELOG.md` so the spec can be kept broadly in sync with what's
actually built.
