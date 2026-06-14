# B88 Pack 3.5 Build Pack — Internal Audit (3 passes)

Reviewer: Claude, reading the Build Pack end-to-end as a fresh reviewer and
cross-checking every claim against `origin/main` code at head `0047_packages`
(tarball, Chat 55). Defects fixed in-place in the Build Pack; this file records
what was found and the disposition.

Severity: **Critical** (would break money/data/schema or block the build) /
**High** (would cause a gate to fail or a rework loop) / **Medium** (clarity,
robustness, test completeness).

---

## PASS 1 — correctness against live code

**C1 — `ALTER TYPE ADD VALUE` + same-transaction `UPDATE` ordering.**
Postgres will not let you use a newly-added enum value in the *same*
transaction that added it. The original draft risked implying the `UPDATE
... SET kind='subcontract'` could sit adjacent to the `ALTER TYPE` in the
autocommit block. Verified against 0047's pattern (the enum add is isolated in
`autocommit_block()`, everything else follows in the migration's own
transaction). **Fixed:** Gate 1.1 now states explicitly that the UPDATE runs
in the normal migration transaction *after* the autocommit block closes, so
the value is committed and usable. Critical because getting this wrong throws
`unsafe use of new value "subcontract"` at migration time.

**C2 — consultant must route to PO, never subcontract — LD2 hard-reject.**
Confirmed `create_subcontract` at `subcontracts.py:289` raises on any
`supplier_type != "Contractor"`. A consultant→subcontract route is impossible
by construction. The Build Pack routes consultant→PO and states the LD2 reason
inline. Verified PO model has **no** CIS field at all (grep returned nothing),
so a consultant PO is inherently CIS-clean — no flag needed. **Fixed/confirmed:**
Gate 3.4's `test_award_consultant_po_is_cis_clean` correctly asserts against
`created_subcontract_id IS NULL` rather than a non-existent PO CIS field.

**C3 — permission count must NOT change.** `test_packages_service.py:538`
hard-asserts `== 142`. The design adds no permission (kind change reuses
`packages.*`). Original draft was silent on this; a careless build might add a
`packages.consultant_*` perm and break the assertion. **Fixed:** §0.2 and the
Final Gate now state 142-unchanged as an invariant and explicitly forbid
adding a permission.

**H1 — the two backend tests that assert the 2-value world.** `:114`
(`package_kind == {"labour","materials"}`) and `:429`
(`test_TTN_4_labour_rejects_non_contractor`) will fail the instant the enum/
guard change. Original draft mentioned them in §0.4 but didn't make updating
them a gated requirement. **Fixed:** Gate 2.4 makes the rename/retarget of
both an explicit, named deliverable, plus the `_packages_common.py` fixture
sweep.

**H2 — `extra="forbid"` on `POCreate`.** Verified `POCreate` has
`model_config = ConfigDict(extra="forbid")`. That means the award path
threading `package_id` into the PO payload would 422 *unless* `package_id` is
declared on the schema. Original draft added it in Gate 4 but the award path
(Gate 3) sends it first — ordering hazard. **Fixed:** Gate 3.3 notes the
service reads `payload.get("package_id")` (service-level, not schema-gated, so
the internal award call is safe because it goes through `create_po` directly
with a dict), and Gate 4.2 adds the schema field for the *external* standalone
caller. Clarified that the award path constructs the payload dict in-service
and does not pass through `POCreate` validation, so Gate 3 is not blocked on
Gate 4's schema edit. Confirmed: award routing calls `po_svc.create_po(db,
..., payload=po_payload)` directly — no Pydantic body in that path.

---

## PASS 2 — completeness, sequencing, test coverage

**H3 — cost-code title source needed proof.** The Build Pack claims
"4.02 — Groundworks" = `code` + `name`. Verified `CostCode.name`
(`models/cost_codes.py:70`, String(255)) is the title; the project cost-codes
endpoint returns `{id, code, label/name}`. But package lines store the
`cost_code` **string**, and the serialiser path is pure (no DB). Original draft
hand-waved how the name reaches the line. **Fixed:** Gate 5.1 now specifies a
single `SELECT code, name WHERE code = ANY(:codes)` built once per package in
`serialise_package`, passed into `_ser_package_line` as a map — no per-line
query, no frontend string-keyed fetch.

**H4 — string-vs-id grouping must not reuse the grid helper.** Verified
`budgetCategoryGroup.js` keys on `cost_code_id` via a `Map` and would route
every package line to "Uncategorised" (because package lines have no
`cost_code_id`). **Confirmed/fixed:** Gate 5.2 mandates a NEW
`packageLineGroup.js` keyed on the `cost_code` string, with its own unit test,
and explicitly forbids importing the grid helper. This is the single most
likely silent bug in the pack and is now fenced.

**H5 — natural sort of dotted codes.** "4.10" must sort after "4.02", not
before (lexicographic would misorder). **Fixed:** Gate 5.2 calls for a
numeric-aware sort on the dotted code and the helper's unit test must cover
"4.02 < 4.10".

**M1 — `serialise` field-add location pinned.** Verified the PO `serialise`
dict (purchase_orders.py) and the subcontract `serialise` (subcontracts.py:164)
— both are explicit dict literals. Gate 4.3 + 7.2 now name them so Emergent
adds `package_id` (+ `package_reference`) in the right place rather than
guessing. **Fixed.**

**M2 — bidirectional link: extra round-trip vs serialiser field.** Original
draft left "fetch the package reference" vague. **Fixed:** Gate 7.2 prefers
including `package_reference` server-side in the PO/subcontract read
serialiser (one query at serialise time) over a frontend N+1. Cleaner and
faster, fits the <2s budget constraint.

**M3 — downgrade correctness for genuine `consultant` rows.** A forward
migration creating real `consultant` packages then a downgrade would leave
rows violating the restored 2-value CHECK. **Fixed:** Gate 1 downgrade now
documents this explicitly as best-effort (demo-data-only forward migration),
guards with a comment, and notes the operator must clear `consultant` rows
before downgrading in a non-live env. Acceptable given the locked
"demo-data-only on live" decision.

**M4 — award sub-tables (988, 1520) grouping scope.** Verified there are three
line-render sites in PackageDetail. Original draft risked implying all three
must be regrouped, which could disturb award-table maths. **Fixed:** Gate 5.3
scopes the grouping to the primary package-lines table; bid/award tables are
left unless trivially safe, with a flag-in-report instruction. Protects the
money tables from cosmetic churn.

---

## PASS 3 — robustness, ambiguity, gate discipline

**H6 — live-API proof, not just suite counts.** The opener demands LIVE-API
verification of new endpoints/flows. Original Gate 3 leaned on unit tests.
**Fixed:** Gate 3 STOP now requires an authenticated end-to-end award of all
three kinds against the running pod with pasted JSON (PO `package_id`
populated, `created_subcontract_id` null for consultant; subcontract
`package_id` populated for subcontract). Gates 4/5/6/7 each carry a live
eyeball/curl requirement.

**M5 — "one front door" placement ambiguity.** The two CTAs (New PO vs New
package) may live on different screens today. A rigid instruction could send
Emergent rebuilding navigation. **Fixed:** Gate 7.1 makes the chooser a
routing shim only, explicitly forbids rebuilding either underlying flow,
preserves existing deep-links/testids, and asks Emergent to confirm the exact
placement in the gate report rather than guess-and-build. Reduces rework risk
on a low-value-but-visible surface.

**M6 — `_package_kind_enum` binding vs physical DB enum.** Clarified in Gate
2.1 that `create_type=False` means SQLAlchemy never reconciles enum members,
so binding the 3 live values while the DB physically retains `labour` is
correct and safe. Pre-empts a "should I recreate the type?" detour (which would
be destructive and is explicitly not wanted).

**M7 — index + FK names spelled out.** Gate 1.1 gives exact constraint/index
names (`fk_purchase_orders_package_id`, `ix_purchase_orders_package_id`, and
subcontract equivalents) so downgrade can drop them by name and so they match
repo naming convention. Prevents anonymous-constraint downgrade failures.

**M8 — count baseline discipline.** Every gate that runs the suite must state
the **pre-pack baseline** and the new count, with deltas accounted for as
named added tests. **Fixed:** Gates 2/3/4/5 and the Final Gate all require
baseline→final reconciliation, matching the "no silent losses" rule.

**M9 — verification mirror.** Given raw.githubusercontent was stale all of
Chat 54, the Final Gate mandates per-file verification against the **codeload
tarball**, not raw. **Confirmed present.**

---

## Disposition summary
- Critical: 3 found, 3 fixed (C1 migration ordering, C2 consultant routing /
  CIS-clean assertion, C3 permission-count invariant).
- High: 6 found, 6 fixed (H1 stale tests gated, H2 schema/award ordering,
  H3 title source, H4 string grouping fenced, H5 dotted sort, H6 live-API
  proof).
- Medium: 9 found, 9 fixed.

No open defects. The Build Pack is internally consistent, every code anchor is
verified against HEAD, and the gate sequence protects money/data/schema before
any cosmetic work. Ready to issue to Emergent.

### Residual risks to watch during build (not defects — operational)
1. Mirror lag on verification — use the tarball, wait a full 60s.
2. The cost-code-name `SELECT ... = ANY(:codes)` must use the same `code`
   string form the package lines store (e.g. "4.02"); if any legacy line holds
   a non-canonical code, `cost_code_name` returns null and the UI falls back to
   the bare code — acceptable, but watch the eyeball at Gate 5.
3. If `PackageDetail.test.jsx` asserts flat (ungrouped) rows in the DOM, it
   will need fixture/DOM updates at Gate 5 — expected, not a regression.
