# B88 Pack 1 — Gate 4 acceptance report

> Canonical cost-code structure reseeded. Two warm-DB full-suite runs
> green. **STOPPED at Gate 4 as instructed** — no `Save to GitHub`
> triggered, awaiting operator raw-fetch verification on
> `origin/main`. Gate 5 (frontend eyeball) remains untouched.

---

## Deliverables

| Item | Path |
|---|---|
| Canonical seed script | `backend/scripts/seed_cost_code_structure.py` |
| Structure test file (15 tests) | `backend/tests/test_cost_code_seed_structure.py` |
| Gate-3 follow-up: cosmetic rename | `backend/tests/test_permissions_2_8b.py::test_total_permissions_in_db` (was `_is_129`) |
| Round-trip teardown reseed | `backend/tests/test_migration_0025_actuals.py::test_downgrade_upgrade_round_trip_preserves_schema` |
| Updated legacy tests | `backend/tests/test_cost_codes.py` (TestSeed, TestCRUD, bulk-toggle, audit) |
| Updated legacy frontend pages | `frontend/src/pages/CostCodesList.jsx`, `frontend/src/pages/ProjectCostCodes.jsx` |

---

## Canonical structure (printed tree, post-seed)

```
1    Acquisition                        (10 codes: ACQ-01..10)
2    Planning & Statutory               (9  codes: PLN-01..09)
3    Design & Professional Fees         (9  codes: DES-01..09)
4    Construction                       (allows_subgroups=true; codes hang off subgroups)
 ├── 4.00  Facilitating Works           (5  codes: FAC-01..05)
 ├── 4.01  Substructure                 (5  codes: SUB-01..05)
 ├── 4.02  Superstructure               (10 codes: SUP-01..10)
 ├── 4.03  Internal Finishes            (6  codes: INT-01..06)
 ├── 4.04  Fittings & Equipment         (5  codes: FIT-01..05)
 ├── 4.05  Services                     (10 codes: SER-01..10)
 ├── 4.06  Prefab / MMC                 (1  code:  PRE-01)              ← operator-resolved renumbering
 ├── 4.07  Existing Buildings           (3  codes: EXB-01..03)          ← operator-resolved renumbering
 ├── 4.08  External Works               (9  codes: EXT-01..09)          ← operator-resolved renumbering (no collision)
 └── 4.09  Preliminaries                (16 codes: PRL-01..16)
5    Sales, Marketing & Disposal        (10 codes: SAL-01..10)          ← SAL-10 newly seeded ("Reservation Fees")
6    Finance Costs                      (5  codes: FIN-01..05)
7    Company Overheads                  (8  codes: OHD-01..08)
8    Accounting & Financial Services    (3  codes: ACC-01..03)          ← canonical; ACC-04..08 retained as extras
9    Contingency, Risk & Miscellaneous  (5  codes: CTG-01..05)

Totals: 9 parent groups · 10 Construction subgroups · 129 canonical codes
        + 5 extras (ACC-04..08) retained per Build Pack §5.3
        = 134 cost code rows total in DB
```

Parent codes are the canonical **numeric** values `"1".."9"` per Build
Pack §5.1; subgroup codes are `"4.00".."4.09"` per §5.2; the
spreadsheet's duplicate-4.08 collision is resolved exactly as
operator-locked: 4.06 = Prefab/MMC, 4.07 = Existing Buildings,
4.08 = External Works.

---

## Idempotency proof — two seed runs back-to-back

### First run (raw — pre-seed slug-coded state, no subgroups)

```
Parents recoded (slug → numeric)        :    9  ['acquisition→1', 'planning→2', 'design→3',
                                                  'construction→4', 'sales_marketing→5',
                                                  'finance→6', 'company_overheads→7',
                                                  'accounting→8', 'contingency→9']
Parents renamed (name canonicalised)    :    1  ["planning: 'Planning & Statutory Approvals' →
                                                  'Planning & Statutory'"]
Parents w/ allows_subgroups flipped     :    1  ['4=True']
Construction subgroups added            :   10  ['4.00', '4.01', ..., '4.09']
Construction subgroups unchanged        :    0  []
Cost codes re-pointed to new section_id :   70
Cost codes already on correct section   :   58
Cost codes added (new canonical rows)   :    1  ['SAL-10']
EXTRA live codes (NOT deleted)          :    5  ['ACC-04', 'ACC-05', 'ACC-06', 'ACC-07', 'ACC-08']
Orphans still attached to '4' directly  :    0  []
```

### Second run (immediately after the first)

```
Parents recoded (slug → numeric)        :    0  []
Parents renamed (name canonicalised)    :    0  []
Parents w/ allows_subgroups flipped     :    0  []
Construction subgroups added            :    0  []
Construction subgroups unchanged        :   10  ['4.00', '4.01', ..., '4.09']
Cost codes re-pointed to new section_id :    0
Cost codes already on correct section   :  129
Cost codes added (new canonical rows)   :    0  []
EXTRA live codes (NOT deleted)          :    5  ['ACC-04', 'ACC-05', 'ACC-06', 'ACC-07', 'ACC-08']
Orphans still attached to '4' directly  :    0  []
```

Row counts identical between runs:
```
parents:    9    subgroups:   10    cost_codes:  134
```

The seed is **also resilient to alembic round-trip damage** — when
`test_migration_0025_actuals.py` walks the head back past
`0044_cost_code_groups` and then re-upgrades, the `parent_section_id`
and `allows_subgroups` columns are dropped + re-created empty. The
seed's matching strategy (`by_code → by_legacy_slug → by_display_order`)
recovers correctly: subgroup rows still exist (their PK survives),
just with parent_section_id=NULL, and the seed re-parents them. A
finalising `_reseed()` call now lives at the end of the round-trip
test so downstream test modules see a healed canonical structure.

---

## Test file `tests/test_cost_code_seed_structure.py` — 15/15 green

```
tests/test_cost_code_seed_structure.py::TestParentGroups::test_exactly_nine_parent_groups                              PASSED
tests/test_cost_code_seed_structure.py::TestParentGroups::test_only_construction_allows_subgroups                      PASSED
tests/test_cost_code_seed_structure.py::TestConstructionSubgroups::test_exactly_ten_subgroups                          PASSED
tests/test_cost_code_seed_structure.py::TestConstructionSubgroups::test_subgroup_names_canonical                       PASSED
tests/test_cost_code_seed_structure.py::TestConstructionSubgroups::test_operator_resolved_renumbering                  PASSED
tests/test_cost_code_seed_structure.py::TestConstructionSubgroups::test_only_construction_has_subgroups                PASSED
tests/test_cost_code_seed_structure.py::TestConstructionSubgroups::test_subgroups_all_have_allows_subgroups_false      PASSED
tests/test_cost_code_seed_structure.py::TestCanonicalCodes::test_canonical_total_is_129                                PASSED
tests/test_cost_code_seed_structure.py::TestCanonicalCodes::test_per_prefix_canonical_counts                           PASSED
tests/test_cost_code_seed_structure.py::TestCanonicalCodes::test_every_code_points_at_canonical_section                PASSED
tests/test_cost_code_seed_structure.py::TestCanonicalCodes::test_no_construction_code_attached_directly_to_parent      PASSED
tests/test_cost_code_seed_structure.py::TestSAL10Added::test_sal_10_exists                                             PASSED
tests/test_cost_code_seed_structure.py::TestExtras::test_extras_still_present_not_deleted                              PASSED
tests/test_cost_code_seed_structure.py::TestIdempotency::test_seed_is_idempotent                                       PASSED
tests/test_cost_code_seed_structure.py::TestIdempotency::test_reconciliation_repoints_a_misplaced_code                 PASSED
```

The module also covers (per Build Pack §7.4):
- 9 parent groups; only Construction has `allows_subgroups=true`.
- 10 Construction subgroups with correct names + display order; no
  subgroup is itself allowed to host subgroups; no non-Construction
  parent has subgroups.
- 129 canonical (prefix, sequence) pairs all present; per-prefix
  count matches Build Pack §5.3; every code points at the right
  (sub)group; no Construction-prefixed code is attached directly
  to "4".
- Run-twice idempotency proof (run 2 yields zero changes, counts
  identical).
- Reconciliation proof (move FAC-01 off 4.00, re-run seed → seed
  moves it back).
- ACC-04..08 extras remain (not deleted) per §5.3.

---

## Gate-4 carry-over from Gate 3 (un-xfailed + updated)

### Carry-over 1: `TestSeed::test_nine_sections` un-xfailed and recoded

The xfail marker pointing at "Gate 4 reseed" is removed. The test
now asserts the canonical parent-group code list and explicitly
filters subgroups out via `parent_section_id IS NULL`. Now passes.

### Carry-over 2: `TestSeed::test_section_p_and_l_categories` updated

Old: keyed off `rows["finance"]`, `rows["company_overheads"]`, etc.
New: keyed off `rows["6"]`, `rows["7"]`, `rows["8"]`, `rows["5"]` —
canonical numeric parent codes. Subgroups filtered out.

### Carry-over 3: `TestSeed::test_133_total_cost_codes` → `test_canonical_total_is_129`

Renamed and updated to assert 129 in the canonical (prefix, sequence)
range. Build Pack §5.3 honoured: live extras (ACC-04..08) are NOT
counted in the canonical assertion but DO survive in the DB.

### Carry-over 4: `TestSeed::test_per_prefix_counts` updated

`SAL: 9 → 10`, `ACC: 8 → 3` to match the canonical counts.

### Carry-over 5: `TestCRUD::test_filter_by_section` rewritten

Old: queried codes where `section_id = '4'` (the Construction parent)
and asserted the set of Construction prefixes. After Gate 4 reseed
no Construction code hangs directly off `"4"` — they all live under
subgroups. The test now queries every Construction subgroup and
unions the resulting prefixes, asserting the canonical set
`{FAC, SUB, SUP, INT, FIT, SER, PRE, EXB, EXT, PRL}`.

### Carry-over 6: bulk-toggle + audit tests

`section_code="company_overheads"` → `"7"`,
`section_code="accounting"` → `"8"`,
`SELECT FROM cost_code_sections WHERE code='accounting'` → `code='8'` (8 occurrences),
`code='acquisition'` → `'1'` (3 occurrences),
`code='construction'` → `'4'` (1 occurrence).

### Carry-over 7 (cosmetic): renamed `test_total_permissions_is_129`

Renamed to `test_total_permissions_in_db` in
`tests/test_permissions_2_8b.py:30`. Assertion still says 136 —
just the function name no longer pins to the stale 129 integer.

---

## Frontend touched to keep legacy pages alive

The Build Pack §6 frontend deliverable is Gate 5 (NEW Cost-Code Admin
screen). Two legacy pages (`CostCodesList.jsx`,
`ProjectCostCodes.jsx`) hardcoded the slug parent codes
(`"acquisition"`, `"planning"`, ...) and would have broken once the
seed renamed parents to `"1".."9"`. Surgical updates:

- `SECTION_HEADER_ORDER` recoded to `["1".."9"]`.
- `showSubgroups` check: `sec.code === "construction"` → `sec.code === "4"`.
- `grouped` look-up now walks `parent_section_id` up to the tier-1
  parent so codes hanging off subgroups `4.00..4.09` roll up under
  `"4"` Construction for display. (Without this, Construction would
  render empty since every Construction code lives under a subgroup.)
- `ProjectCostCodes.jsx` got the same `grouped` rewrite.
- Subhead text updated: "9 sections · 18 prefixes · 133 codes" →
  "9 parent groups · 10 Construction subgroups · 18 prefixes · 129 codes".

Gate 5 will replace these screens with the proper Cost-Code Admin
screen per Build Pack §6; this is interim glue so the pages don't
404 between Gate 4 and Gate 5.

---

## Full pytest suite — two warm-DB runs

### Run 1
```
1437 passed, 3 xpassed, 2 warnings in 264.26s (0:04:24)
```

### Run 2
```
1437 passed, 3 xpassed, 2 warnings in 261.37s (0:04:21)
```

- **Failed: 0** both runs.
- Test count grew from 1421 → 1437: +15 from `test_cost_code_seed_structure.py`, +1 from un-xfailing `TestSeed::test_nine_sections`. Net delta = +16. (Note: `1437 - 1421 = 16`. The 3 previously-xfailed tests are now `xpassed`, not counted in the passed total, so the visible "passed" delta is +16.)
- The 2 warnings are unchanged pre-existing pydantic v1 + python_multipart notices, unrelated to B88.

---

## NOT in this submission

- **No `Save to GitHub`** triggered.
- **No frontend admin screen** (Gate 5 scope — separate gate).
- **No deletion of the ACC-04..08 extras** — Build Pack §5.3 explicitly
  forbids deleting non-canonical live codes; operator decides what to
  do with them in a separate decision.
- **No `docs/SY_Hub_Phase2_Backlog.md` edits** — operator-hand-edited only.

---

## Ready for operator raw-fetch verification on `origin/main`
