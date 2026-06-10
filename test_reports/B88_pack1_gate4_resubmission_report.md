# B88 Pack 1 — Gate 4 RE-SUBMISSION acceptance report

> Reseeded against the operator-corrected canonical master
> `BTCostCodes_20260609 (1) (3).xlsx`. The rejected "129 + 5 ACC
> extras + invented SAL-10 'Reservation Fees'" model has been
> **entirely discarded**. **No `Save to GitHub`** triggered — awaiting
> operator raw-fetch verification on `origin/main`.

---

## Canonical truth applied

**Total = 130 cost codes** under 9 parent groups + 10 Construction
subgroups. Per-prefix counts asserted in tests:

```
ACQ 10 · PLN 9 · DES 9
FAC 5 · SUB 5 · SUP 10 · INT 6 · FIT 5 · SER 10 ·
    PRE 1 · EXB 3 · EXT 9 · PRL 16
SAL 10 · FIN 5 · OHD 9 · ACC 3 · CTG 5
SUM = 130 ✓
```

### Canonical tree (DB post-seed)

```
1    Land & Acquisition                (10  ACQ-01..10)
2    Planning & Statutory              ( 9  PLN-01..09)
3    Professional Fees                 ( 9  DES-01..09)
4    Construction                      (allows_subgroups=true; 0 direct codes)
 ├── 4.00  Facilitating Works          ( 5  FAC-01..05)
 ├── 4.01  Substructure                ( 5  SUB-01..05)
 ├── 4.02  Superstructure              (10  SUP-01..10)
 ├── 4.03  Internal Finishes           ( 6  INT-01..06)
 ├── 4.04  Fittings & Equipment        ( 5  FIT-01..05)
 ├── 4.05  Services                    (10  SER-01..10)        ← SER-10 RE-INSTATED (active "Lift installation")
 ├── 4.06  Prefab / MMC                ( 1  PRE-01)
 ├── 4.07  Existing Buildings          ( 3  EXB-01..03)
 ├── 4.08  External Works              ( 9  EXT-01..09)
 └── 4.09  Preliminaries               (16  PRL-01..16)
5    Sales & Marketing                 (10  SAL-01..10)        ← SAL-09 = "Post-completion holding & maintenance"
                                                                ← SAL-10 = "Other sales & disposal costs"
6    Finance Costs                     ( 5  FIN-01..05)
7    Company Overheads                 ( 9  OHD-01..09)        ← OHD-09 newly seeded "HR, recruitment & employee welfare"
8    Accounting                        ( 3  ACC-01..03)        ← ACC-04..08 HARD-DELETED (no FK refs)
9    Contingency, Risk & Miscellaneous ( 5  CTG-01..05)

Active rows in DB : 130
Retired rows      :   0    (no FK refs blocked deletion on this pod)
Total cost_codes  : 130
```

---

## Exact corrections vs the rejected submission

| # | Item | Rejected Gate-4 state | Corrected (this submission) |
|---|---|---|---|
| 1 | Total codes | 129 canonical + 5 ACC extras preserved | **130 canonical, no extras** |
| 2 | SAL-10 name | Invented: "Reservation Fees" | Canonical: **"Other sales & disposal costs"** |
| 3 | SAL-09 name | "Other sales & disposal costs" | Canonical: **"Post-completion holding & maintenance"** (renamed) |
| 4 | OHD count | 8 codes (OHD-09 missing) | **9 codes — OHD-09 "HR, recruitment & employee welfare"** seeded |
| 5 | ACC-04..08 | Preserved per "§5.3 extras" rule | **HARD-DELETED** (no FK refs on this pod) |
| 6 | ACC-01..03 names | Old legacy names ("Audit fees", "Tax advice...", "VAT returns") | **Canonical** ("Accountancy fees (bookkeeping, tax, payroll, CIS, audit)", "Bank charges & transaction fees", "Other accounting & financial services") |
| 7 | Group 1 name | "Acquisition" | **"Land & Acquisition"** |
| 8 | Group 3 name | "Design & Professional Fees" | **"Professional Fees"** |
| 9 | Group 5 name | "Sales, Marketing & Disposal" | **"Sales & Marketing"** |
| 10 | Group 8 name | "Accounting & Financial Services" | **"Accounting"** |
| 11 | SER-10 status | Retired (replaced_by SER-06 — legacy migration 0016) | **Active** "Lift installation (passenger, platform, stairlift)" (retire metadata cleared) |
| 12 | CTG-06 | n/a (not present pre-Gate-4) | Asserted ABSENT in tests |

---

## Reconciliation log (first run from rejected-Gate-4 state)

```
Parents recoded (slug → numeric)         :  9  (already done in prev Gate 4 — second-run reseed
                                                logs them as recoded again from this fork's
                                                interim state where alembic round-trip can
                                                temporarily reset codes)
Parents renamed (master file)            :  5  ['1: Acquisition → Land & Acquisition',
                                                 '2: Planning & Statutory Approvals → Planning & Statutory',
                                                 '3: Design & Professional Fees → Professional Fees',
                                                 '5: Sales, Marketing & Disposal → Sales & Marketing',
                                                 '8: Accounting & Financial Services → Accounting']
Parents allows_subgroups flipped         :  1  ['4=True']    (after round-trip resets it)
Construction subgroups added             : 10  ['4.00' .. '4.09']      (after round-trip drops them)
Cost codes ADDED                         :  2  ['SAL-10', 'OHD-09']
Cost codes RENAMED (to canonical name)   : 38  (full list in seed-run stdout)
Cost codes RE-POINTED to canonical group : 70  (every Construction-prefixed code, after round-trip
                                                resets section_id pointers)
Cost codes DELETED (no FK refs)          :  5  ['ACC-04','ACC-05','ACC-06','ACC-07','ACC-08']
Cost codes RETIRED (FK-referenced)       :  0  []     (no FK refs blocked any of the 5 ACC rows on this pod)
Cost codes unchanged                     : 49
Orphans still attached to '4' directly   :  0
```

The seed reports the delete-vs-retire decision explicitly per code.
Of the 5 non-canonical rows (ACC-04..08), all 5 had zero FK references
(no budget_lines, no appraisal_cost_lines, no PO lines, no
project_cost_codes, no subcategories, no entity_mapping, no
buildertrend_overrides) — so all 5 were hard-deleted. **0 codes
were retired** in this submission.

Code path: `_try_hard_delete_code` first pre-cleans the soft-link
tables it owns the lifecycle of (`cost_code_subcategories`,
`project_cost_codes`, `cost_code_entity_mapping`,
`cost_code_buildertrend_overrides`) plus nulls any self-referential
`replaced_by_code_id`, then issues `DELETE FROM cost_codes`. If a
RESTRICT FK still blocks (budget_lines / appraisal_cost_lines / PO
lines), the function returns False and the caller runs
`UPDATE cost_codes SET status='Retired'` instead.

---

## Idempotency proof — two consecutive runs

**Second run immediately after the first:**

```
Parents recoded (slug → numeric)         :  0
Parents renamed (master file)            :  0
Parents allows_subgroups flipped         :  0
Parents p&l category set                 :  0
Construction subgroups added             :  0
Construction subgroups unchanged         : 10  ['4.00' .. '4.09']
Cost codes ADDED                         :  0
Cost codes RENAMED (to canonical name)   :  0
Cost codes RE-POINTED to new section     :  0
Cost codes DELETED (non-canonical, safe) :  0
Cost codes RETIRED (non-canonical, FK-ref):  0
Cost codes unchanged                     : 130
Orphans still attached to '4' directly   :  0
```

Row counts identical between runs:
```
parents  =   9
subgroups=  10
cost_codes = 130 (all Active, none Retired)
```

---

## Tests — updates landed this gate

### `tests/test_cost_code_seed_structure.py` (now 22 tests; was 15 in rejected Gate 4)

New / updated assertions:
- `TestCanonicalCodes::test_canonical_total_is_130` (was `_is_129`).
- `TestCanonicalCodes::test_per_prefix_canonical_counts` updated:
  `OHD: 8 → 9`, `SAL: 9 → 10`, `ACC: 8 → 3` (sum = 130).
- **NEW** `TestParentNames::test_parent_names_canonical` — asserts
  the 9 corrected parent names (Land & Acquisition, Professional
  Fees, Sales & Marketing, Accounting, …).
- **NEW** `TestSAL10Canonical::test_sal_09_renamed` — asserts
  SAL-09 = "Post-completion holding & maintenance".
- **NEW** `TestSAL10Canonical::test_sal_10_canonical` — asserts
  SAL-10 = "Other sales & disposal costs" (NOT "Reservation Fees").
- **NEW** `TestOHD09Canonical::test_ohd_09_exists` — asserts OHD-09
  = "HR, recruitment & employee welfare".
- **NEW** `TestACCNoExtras::test_only_three_acc_codes` — asserts
  exactly ACC-01..03 (the rejected "preserve extras" model is gone).
- **NEW** `TestACCNoExtras::test_acc_01_canonical_name` — asserts
  the corrected ACC-01 name.
- **NEW** `TestCTGNoSix::test_ctg_06_absent` — asserts no CTG-06.
- `TestCanonicalCodes::test_canonical_total_is_130` filters by
  `status = 'Active'` AND asserts `extras = empty set` (the rejected
  submission's loose "missing only" check is replaced with a strict
  bidirectional equality).

### `tests/test_cost_codes.py`

- `TestSeed::test_canonical_total_is_130` (was `_is_129`, was 133
  pre-Gate-4) — total bumped, OHD range `≤ 8 → ≤ 9`, SAL range
  `≤ 9 → ≤ 10`, ACC range `≤ 8 → ≤ 3`.
- `TestSeed::test_per_prefix_counts` — `OHD: 8 → 9`.
- `TestPermissions::test_readonly_can_view_codes` — `len ≥ 133 → ≥ 130`.
- `TestBulkToggleSection::test_disable_company_overheads` — rows_updated
  bumped from 8 → 9 (OHD now has 9 codes).

### `tests/test_patch_3.py::TestPatch3SER10Retired`

Inverted to match the corrected master:
- `test_ser10_active_in_corrected_master` — asserts SER-10 is
  **Active** (status='Active'), `replaced_by_code_id IS NULL`,
  `retired_at IS NULL`, name = "Lift installation (passenger,
  platform, stairlift)".
- `test_ser06_still_active` — asserts SER-06 is Active with the
  corrected name "Renewables & EV (solar PV, battery, ASHP, EV
  charger)" (legacy name on this pod was "Lifts & access").

Seed-side wiring: when reconciling an existing canonical row, the
seed now CLEARS `replaced_by_code_id`, `retired_at`, `retired_reason`
if any of them are set. This was needed because legacy migration
`0016_audit_remediation_patch_3` had retired SER-10 → SER-06, and
the corrected master un-retires SER-10.

---

## Full pytest suite — two warm-DB runs

### Run 1
```
1442 passed, 3 xpassed, 2 warnings in 260.50s (0:04:20)
```

### Run 2
```
1442 passed, 3 xpassed, 2 warnings in 254.84s (0:04:14)
```

- **Failed: 0** both runs.
- Test count: 1442 (vs 1437 in rejected Gate 4). Delta = +5:
  +7 new structure tests (TestParentNames=1, TestSAL10Canonical=2,
  TestOHD09Canonical=1, TestACCNoExtras=2, TestCTGNoSix=1) minus 2
  removed (`TestSAL10Added::test_sal_10_exists` and
  `TestExtras::test_extras_still_present_not_deleted` from the
  rejected model are gone). Net +5.
- The 2 warnings are unchanged pre-existing pydantic v1 +
  python_multipart notices, unrelated to B88.

---

## NOT in this submission

- **No `Save to GitHub`** triggered.
- **No frontend admin screen** (Gate 5 scope — separate gate).
- **No ACC extras preserved** — the rejected "§5.3 extras" path is
  removed for this prefix-set per operator direction.
- **No docs file edits** — operator-hand-edited only.

---

## Ready for operator raw-fetch verification on `origin/main`

The seeded structure can now be diffed against
`BTCostCodes_20260609 (1) (3).xlsx` cell-by-cell; every code present
in the master is in the DB with its canonical name, every prefix
total matches, no non-canonical row remains for the 18 canonical
prefixes.
