# C3 — Closing Summary

**Build Pack:** C3 — Corporate SDLT flat-rate undercharge fix (`C3-build-pack-v1.md`)
**Audit reference:** Full-platform audit **2026-06-19, finding C3 (CONFIRMED, Critical)**
**Type:** Backend bugfix only — money fix (money-gate proof required).
**Scope:** SDLT calculation only. No migration, no seed change, no `classify()`
change, no change to the progressive loop for any other category, no frontend,
no permission, no API-shape change.
**Backlog:** `docs/SY_Hub_Phase2_Backlog.md` left untouched (operator-only).

---

## 1. The bug

`backend/app/services/sdlt.py::calculate()` routed `Corporate_Flat_Rate`
through the generic **progressive** band loop. But Corporate_Flat_Rate is a
single-band **FLAT** charge: above the £500k threshold the 17% rate applies to
the **entire** consideration, not just the slice above £500k. The progressive
loop charged 17% only on the slice — a material undercharge.

**Blast radius:** `appraisal_classification.classify()` auto-routes
`Residential_Surcharge` + no developer relief + price > £500k →
`Corporate_Flat_Rate`. So every company dwelling purchase above £500k was
undercharged.

| Purchase price | Computed (buggy) | Correct (flat 17%) | Undercharge |
|---------------:|-----------------:|-------------------:|------------:|
| £600,000       | £17,000          | £102,000           | £85,000     |
| £500,001       | £0.17 (slice)    | £85,000.17         | ~£85,000    |
| £500,000       | £0               | £0                 | —           |
| £400,000       | £0               | £0                 | —           |

## 2. The fix

`backend/app/services/sdlt.py` — a dedicated branch intercepts
`Corporate_Flat_Rate` **before** the progressive loop, immediately after
`amount = Decimal(consideration)`:

```python
if category == "Corporate_Flat_Rate":
    band = bands[0]
    threshold = Decimal(band.band_lower)
    if amount <= threshold:
        return Decimal("0.00")
    return _round_penny(amount * (Decimal(band.rate_pct) / Decimal("100")))
```

- Reuses the existing `_round_penny` (ROUND_HALF_UP).
- Reads `band.band_lower` (£500,000) and `band.rate_pct` (17.000) from the live
  seed — single-band assumption is safe (seed defines exactly one
  Corporate_Flat_Rate band).
- Intercepts **only** Corporate_Flat_Rate; every other category falls through to
  the unchanged progressive loop.
- The misleading docstring (which wrongly claimed the progressive loop produces
  the same answer as a flat application) was corrected to describe the flat
  branch accurately.

Confirmed `classify()` already gates auto-selection on `price > £500k`
(`CORPORATE_FLAT_THRESHOLD`); no change needed there.

## 3. What was NOT touched (scope discipline)

- No seed change, no migration.
- No change to `classify()`.
- No change to the progressive loop for any other category.
- No frontend, no permission, no API-shape change.
- `docs/SY_Hub_Phase2_Backlog.md` untouched.

## 4. Tests

New `backend/tests/test_sdlt_corporate.py` — 16 tests, all against the **live
seeded Postgres** via `app.db.SessionLocal`:

- **Flat cases:** £600k→£102,000.00, £500k→£0.00, £500,001→£85,000.17,
  £400k→£0.00; negative consideration raises `ValueError`.
- **Flat ≠ slice regression:** asserts £600k = £102,000 and explicitly `!=`
  £17,000 (the buggy slice figure).
- **Other categories unchanged:** Residential_Standard (£500k→£15,000;
  £600k→£20,000 still progressive), Residential_Surcharge (£500k→£40,000),
  Non_Residential (£250k→£2,000; £600k→£19,500 still progressive).
- **Classification routing:** company dwelling > £500k → Corporate_Flat_Rate;
  exactly £500k stays Surcharge; developer relief downgrades to Standard;
  explicit Non_Residential passthrough; full end-to-end classify→calculate.

**Pre-existing tests:** none asserted the buggy £17,000 figure, so **no existing
test required updating.** `test_reference_data.py` SDLT calc + seed suites remain
green.

## 5. Money-gate proof (live, operator-cleared)

Captured against live Postgres (postmaster start `2026-06-19 21:25:09Z`, single
PID, no recycle during capture; re-verified stable at 21:30Z).

**Live echo:**
```
Corporate_Flat_Rate live seed: band_lower=500000.00, band_upper=None, rate_pct=17.000, effective_from=2025-04-01
calculate(600000, "Corporate_Flat_Rate") = 102000.00
calculate(500000, "Corporate_Flat_Rate") = 0.00
calculate(500001, "Corporate_Flat_Rate") = 85000.17
calculate(400000, "Corporate_Flat_Rate") = 0.00
```

**Raw pytest:**
```
tests/test_sdlt_corporate.py ................                            [100%]
16 passed in 0.41s

tests/test_reference_data.py (TestSdltCalculator + TestSeed) .........   [100%]
9 passed in 0.42s
```

Operator cleared the money-gate proof on 2026-06-19.

## 6. Files changed

- `backend/app/services/sdlt.py` — flat-rate branch + docstring correction.
- `backend/tests/test_sdlt_corporate.py` — new, 16 tests.
- `CHANGELOG.md` — C3 entry.
- `docs/chat-summaries/C3-closing.md` — this doc.

## 7. Guardrails honoured

- Backend bugfix only; intercepts ONLY Corporate_Flat_Rate.
- No backlog edit (`docs/SY_Hub_Phase2_Backlog.md` operator-only).
- No scope expansion — no smarter-approach deviation taken; nothing to flag.
- No git push by the agent — push via "Save to GitHub".
