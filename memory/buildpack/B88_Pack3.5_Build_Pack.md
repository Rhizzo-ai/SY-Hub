# B88 — Commercial Spine — Pack 3.5 Build Pack

**Package types + cost-code subgrouping + package↔PO/subcontract link**

Author: Claude (Chat 55). Design LOCKED in Chat 54 (backlog block
"### Chat 54 — B88 Pack 3.5 design"). This Build Pack is fully
code-grounded against `origin/main` at alembic head `0047_packages`
(tarball-verified, Chat 55 open). **Do not re-litigate the locked design.**

Target migration: `0048_package_kind_3value_and_links`
(down-revision `0047_packages`).

---

## 0. Context & invariants (read before touching anything)

### 0.1 What this pack does, in one paragraph
Today a `package.kind` is one of two values — `labour` or `materials` —
and on award the service routes `materials → purchase_order` and
`labour → subcontract`. Pack 3.5 makes `kind` a **three-value** vocabulary:
`materials` (→ PO, unchanged), `subcontract` (→ subcontract; this is the
renamed-and-broadened successor to `labour`, covering both labour-only and
supply-&-fit), and `consultant` (→ PO, CIS-clean professional fees). Existing
`labour` rows migrate to `subcontract`. It adds a stored, bidirectional
`package_id` link on both `purchase_orders` and `subcontracts` so an order
created from a package knows its origin and vice-versa. It groups package
lines under their cost code with display-only per-cost-code subtotals, and
shows the cost-code **title** alongside the number ("4.02 — Groundworks") on
the packages screen.

### 0.2 Hard invariants — NEVER violate
- **Money traceability is sacred.** Every awarded line must still resolve
  estimate → package line → award line → downstream order line. No regression
  to the existing award-routing maths. `awarded_net` totals must reconcile
  exactly as they do today (Decimal, 2dp, `_q2`).
- **`materials` routing is unchanged.** Same `create_po` payload, same
  result. Pack 3.5 must not alter a single field in the materials → PO path.
- **The PG enum is additive-only.** Postgres cannot remove an enum value
  inside a transaction and we do not attempt to. `labour` stays as an
  orphaned enum member after migration (precedent: 0020, 0047 leave orphans).
  The CHECK constraint is what enforces the *live* allowed set.
- **Permission count stays at 142.** Pack 3.5 adds **no** new permission. It
  reuses the existing `packages.*` set (`view, view_sensitive, create, edit,
  award, delete`). `test_packages_service.py::...count == 142` must still pass
  unchanged. If you find yourself adding a permission, STOP — the design does
  not call for one.
- **Cost-code count stays at 133, role count stays at 10.** Untouched.
- **`package_id` is nullable on both downstream tables.** Standalone orders
  (the "Simple order" front door, and every PO/subcontract created before
  this pack) carry `package_id = NULL`. The column is a non-breaking add.
- **Demo-data-only migration.** On live, the only `labour` packages are demo
  data. The data migration (`labour → subcontract`) is a **light** gate — no
  production-backup ceremony. It must still be correct and reversible in the
  downgrade path for non-live environments.

### 0.3 Path truth (confirmed Chat 54/55)
- Routers carry **no internal prefix**; they mount on `v1_router` (`/v1`) →
  `api_router` (`/api`). All commercial surfaces live under `/api/v1`.
  **EXCEPTION:** the cost-codes router is mounted directly under `/api`
  (NOT `/api/v1`) — see `frontend/src/hooks/costCodes.js` comment. Treat the
  **live OpenAPI** as authoritative; verify every path against it at the
  relevant gate.
- Brand: teal `#0F6A7A`, orange `#FC7827`, grey `#CECECE`.

### 0.4 Files this pack touches (grounded — line numbers as of HEAD, re-confirm)
Backend:
- `backend/app/models/packages.py` — `PACKAGE_KINDS` (line 30, currently
  `("labour","materials")`); the `_package_kind_enum` PGEnum binding (38).
- `backend/alembic/versions/0048_*.py` — NEW migration.
- `backend/app/services/packages.py`:
  - `PACKAGE_KINDS` import (43) + `create_package` validation (327).
  - `_supplier_kind_guard` (731) — rewrite for 3 kinds; **flip the
    Consultant rejection**.
  - award routing (1174 `if p.kind == "materials"` / 1206 `elif p.kind ==
    "labour"`) — rename `labour`→`subcontract`, add `consultant`→PO branch,
    and thread `package_id` into both downstream create calls.
  - `_ser_package_line` (1384) — add `cost_code_name` enrichment.
  - `serialise_package` (1495) — pass the cost-code name map through.
- `backend/app/services/purchase_orders.py` — `create_po` (200): accept
  optional `package_id` in payload, set it on the `PurchaseOrder(...)`
  constructor (line ~310).
- `backend/app/services/subcontracts.py` — `create_subcontract` (252): accept
  optional `package_id` kwarg, set on the `Subcontract(...)` constructor
  (~344).
- `backend/app/models/purchase_orders.py` — add `package_id` column +
  relationship.
- `backend/app/models/subcontracts.py` — add `package_id` column +
  relationship.
- `backend/app/schemas/packages.py` — `PackageCreateBody.kind` comment (22).
- `backend/app/routers/purchase_orders.py` — `POCreate` body (62): add
  optional `package_id`.
- `backend/app/routers/subcontracts.py` — `SubcontractCreateBody` (46): add
  optional `package_id`.
- `backend/app/seed_rbac.py` — **no change** (no new perm). Listed only to
  assert it is NOT touched.

Frontend:
- `frontend/src/components/packages/NewPackageDialog.jsx` — kind radio set
  (currently materials/labour) → three choices; labels updated.
- `frontend/src/pages/admin/PackagesList.jsx` — kind filter options (146-147)
  + kind display (228).
- `frontend/src/pages/admin/PackageDetail.jsx` — kind display (163), the
  supplier-picker kind filter (792-803), the "Contractor only" hint (847),
  and the line-render sections (506, 988, 1520) to group + subtotal + show
  cost-code title.
- `frontend/src/lib/packageLineGroup.js` — **NEW** string-keyed grouping
  helper (do NOT reuse `budgetCategoryGroup.js` verbatim — see §0.5).
- `frontend/src/pages/projects/PurchaseOrderForm.jsx` — the "one front door"
  choice (Simple order vs Package) — see §6.
- API layer: `frontend/src/lib/api/packages.js`, `.../purchaseOrders.js`,
  `.../subcontracts.js` — pass `package_id` where relevant.

Tests that ASSERT the 2-value world and MUST be updated (not deleted):
- `backend/tests/test_packages_service.py:114` — asserts
  `package_kind == {"labour","materials"}`. Update to the new live set
  `{"materials","subcontract","consultant"}` (the orphaned `labour` enum
  member is not asserted against; assert against the CHECK-allowed set or the
  `PACKAGE_KINDS` tuple).
- `backend/tests/test_packages_service.py:429`
  `test_TTN_4_labour_rejects_non_contractor` — rename/retarget to
  `subcontract` kind.
- `backend/tests/test_packages_service.py:442`
  `test_TTN_5_materials_accepts_supplier` — unaffected, but re-verify.
- Any fixture in `_packages_common.py` that creates `kind="labour"` packages.

### 0.5 The string-vs-id grouping catch (locked design, do not get this wrong)
`budgetCategoryGroup.js::groupLinesByCategory(lines, costCodeMap)` keys each
line by `line.cost_code_id` and resolves the label via a `Map<cost_code_id,
row>`. **Package lines do NOT carry `cost_code_id`** — `_ser_package_line`
returns `cost_code` as a **string** (e.g. `"4.02"`). Therefore:
- Build a **new** helper `frontend/src/lib/packageLineGroup.js` that groups by
  the `cost_code` string directly.
- Subtotals are display-only — sum `budgeted_net_amount` per cost-code group.
  **No stored group reference** anywhere (backend stores nothing new for
  grouping; it is purely a render concern).
- The cost-code **title** for the group header comes from the new
  `cost_code_name` field added to the serialised line (§Gate 5), so the
  screen needs **no** second fetch keyed by string.

---

## GATE STRUCTURE

Hard STOPs (no batching — money / data / permission / schema risk):
- **Gate 1** — enum + data migration (`0048`).
- **Gate 2** — model + service kind vocabulary + `_supplier_kind_guard` flip.
- **Gate 3** — award money-routing (consultant→PO, labour→subcontract rename)
  + `package_id` threading.
- **Gate 4** — `package_id` columns live on `purchase_orders` +
  `subcontracts`, set end-to-end on award.

Batchable (UI / grouping / titles — no money/permission/data risk):
- **Gate 5** — backend line serialiser `cost_code_name` enrichment + string
  grouping helper + packages-screen grouping/subtotals/titles.
- **Gate 6** — create dialog 3-kind radios + list/detail kind display +
  supplier-picker filters.
- **Gate 7** — "one front door" (Simple order vs Package) + bidirectional
  link display.

Each gate ends with a numbered STOP. Do not auto-advance. The 2nd-run
WARM-DB suite count is authoritative. Test files named EXACTLY as specified.

---

## GATE 1 — Enum extension + data migration (HARD STOP)

### 1.1 Migration file
Create `backend/alembic/versions/0048_package_kind_3value_and_links.py`,
`down_revision = "0047_packages"`.

**Upgrade, in this exact order:**

1. **Extend the PG enum** (additive, must be outside a transaction — copy the
   0047 pattern exactly):
   ```python
   with op.get_context().autocommit_block():
       op.execute(
           "ALTER TYPE package_kind ADD VALUE IF NOT EXISTS 'subcontract'"
       )
       op.execute(
           "ALTER TYPE package_kind ADD VALUE IF NOT EXISTS 'consultant'"
       )
   ```
   `labour` remains a member of the enum (orphaned after data migration —
   acceptable, matches 0020/0047 precedent). Do **not** attempt to drop it.

2. **Data-migrate existing rows** (demo data only on live):
   ```python
   op.execute("UPDATE packages SET kind = 'subcontract' WHERE kind = 'labour'")
   ```
   This must run **after** the enum value exists and in a **separate**
   statement from the autocommit block (the new enum value is only usable in a
   new transaction after `ALTER TYPE ... ADD VALUE` — do the UPDATE in the
   normal migration transaction that follows the autocommit block).

3. **Drop + recreate the named CHECK** to the new live value set:
   ```python
   op.drop_constraint("ck_packages_kind_values", "packages", type_="check")
   op.create_check_constraint(
       "ck_packages_kind_values",
       "packages",
       "kind IN ('materials','subcontract','consultant')",
   )
   ```
   Note `labour` is deliberately **absent** from the CHECK — no live row may
   carry it after step 2, and none may be created going forward.

4. **Add `package_id` columns** (see Gate 4 — done in this same migration so
   schema lands atomically; the column add is data-safe and nullable):
   ```python
   op.add_column("purchase_orders", sa.Column(
       "package_id", postgresql.UUID(as_uuid=True), nullable=True,
   ))
   op.create_foreign_key(
       "fk_purchase_orders_package_id", "purchase_orders", "packages",
       ["package_id"], ["id"], ondelete="SET NULL",
   )
   op.create_index(
       "ix_purchase_orders_package_id", "purchase_orders", ["package_id"],
   )
   op.add_column("subcontracts", sa.Column(
       "package_id", postgresql.UUID(as_uuid=True), nullable=True,
   ))
   op.create_foreign_key(
       "fk_subcontracts_package_id", "subcontracts", "packages",
       ["package_id"], ["id"], ondelete="SET NULL",
   )
   op.create_index(
       "ix_subcontracts_package_id", "subcontracts", ["package_id"],
   )
   ```
   `ondelete="SET NULL"`: deleting a package must not cascade-destroy a real
   financial order. The link nulls; the order survives.

**Downgrade, in reverse:**
- Drop the two FKs, indexes, and columns.
- Drop + recreate `ck_packages_kind_values` back to
  `kind IN ('labour','materials')`.
- Reverse the data migration: `UPDATE packages SET kind = 'labour' WHERE
  kind = 'subcontract'`. (Accept that genuine `consultant` rows have no
  pre-image — downgrade in a non-live env is best-effort; document that
  `consultant` rows will violate the restored CHECK and the operator must
  delete them first. Add a guard comment. This is acceptable for a
  demo-data-only forward migration.)
- Do **not** attempt to remove enum values on downgrade (Postgres can't).

### 1.2 Migration hygiene
- `alembic heads` returns a single head `0048_*` after apply.
- `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade
  head` round-trips clean on a scratch DB with at least one `labour`-origin
  package seeded (prove the data migration both directions).

### ⛔ GATE 1 STOP — report:
1. `alembic upgrade head` output; confirm head is `0048_*`.
2. `SELECT DISTINCT kind FROM packages;` — no `labour` rows remain.
3. `\d+ packages` showing the recreated CHECK with the 3-value set.
4. `\d purchase_orders` and `\d subcontracts` showing `package_id` column +
   FK + index.
5. Down/up round-trip result.
**Do not proceed to Gate 2 until verified on the live pod DB.**

---

## GATE 2 — Kind vocabulary in model + service + supplier guard (HARD STOP)

### 2.1 `models/packages.py`
```python
PACKAGE_KINDS = ("materials", "subcontract", "consultant")
```
The `_package_kind_enum` PGEnum binding must list the **live** set used by the
ORM. Because `ALTER TYPE` already added the members, binding
`PGEnum(*PACKAGE_KINDS, name="package_kind", create_type=False)` is correct —
the ORM only needs to know the values it will read/write, and it will never
write `labour`. (The DB enum physically still contains `labour`; that is fine
— SQLAlchemy `create_type=False` does not reconcile members.)

### 2.2 `services/packages.py::create_package`
The validation `if kind not in PACKAGE_KINDS` (line 327) now naturally accepts
all three. No other change to `create_package`. Update the module docstring
(lines 19-20) routing comment to the 3-value reality.

### 2.3 `_supplier_kind_guard` rewrite (line 731) — THE FLIP
Replace the body. New rules (locked design §"_supplier_kind_guard rewrite"):
- `materials` → bidder must be `Supplier` OR `Contractor`.
- `subcontract` → bidder must be `Contractor` (CIS counterparty).
- `consultant` → bidder must be `Consultant`. **This is the flip** — today the
  guard rejects `Consultant` outright; now `consultant` packages *require* it.
- `Other` remains invalid for every kind.

```python
def _supplier_kind_guard(supplier: Supplier, kind: str) -> None:
    """Kind/supplier-type coherence (Pack 3.5 — 3-value vocabulary)."""
    st = supplier.supplier_type
    if kind == "materials":
        if st not in ("Supplier", "Contractor"):
            raise ValueError(
                f"materials packages require a Supplier or Contractor "
                f"bidder; got supplier_type={st!r}"
            )
    elif kind == "subcontract":
        if st != "Contractor":
            raise ValueError(
                f"subcontract packages require a Contractor bidder "
                f"(CIS counterparty); got supplier_type={st!r}"
            )
    elif kind == "consultant":
        if st != "Consultant":
            raise ValueError(
                f"consultant packages require a Consultant bidder; "
                f"got supplier_type={st!r}"
            )
    else:  # pragma: no cover — kind constrained by enum + CHECK
        raise ValueError(f"Unknown package kind {kind!r}")
```
Both call-sites (`invite_bidder` ~763, `enter_bid` ~990) call this unchanged.

### 2.4 Tests (HARD — name exactly)
Update `backend/tests/test_packages_service.py`:
- Line 114 assertion → live set `{"materials","subcontract","consultant"}`.
- `test_TTN_4_labour_rejects_non_contractor` → rename
  `test_TTN_4_subcontract_rejects_non_contractor`, `kind="subcontract"`.
- ADD `test_TTN_6_consultant_accepts_consultant` — consultant package, bidder
  `supplier_type="Consultant"` → invite succeeds.
- ADD `test_TTN_7_consultant_rejects_non_consultant` — consultant package,
  bidder `supplier_type="Contractor"` → ValueError.
- ADD `test_TTN_8_materials_rejects_consultant` — materials package, bidder
  `supplier_type="Consultant"` → ValueError (regression guard on the old
  reject path, now narrowed).
- Fix any `_packages_common.py` fixture creating `kind="labour"`.

### ⛔ GATE 2 STOP — report:
1. Full backend suite, **2nd-run WARM-DB count** (authoritative). State the
   pre-pack baseline and the new count; every delta must be an added test, no
   silent losses.
2. The four new/renamed TTN test names with pass status.
3. `python -c "from app.models.packages import PACKAGE_KINDS; print(PACKAGE_KINDS)"`
   → `('materials','subcontract','consultant')`.
**Do not proceed until the suite is green on 2nd run.**

---

## GATE 3 — Award money-routing: consultant→PO, labour→subcontract rename, package_id threading (HARD STOP)

This is the money gate. The award routing block is `services/packages.py`
~1174-1230. Rewrite the branch logic:

### 3.1 Routing
- `if p.kind == "materials"` → unchanged PO path, **plus** thread
  `package_id` (§3.2).
- `elif p.kind == "subcontract"` → the EXISTING `labour` branch, renamed.
  Same `create_subcontract` call, same `cis_applies` handling (default True
  for CIS subcontractors), **plus** thread `package_id`.
- `elif p.kind == "consultant"` → **NEW** branch. Routes to **PO**
  (`po_svc.create_po`), identical payload shape to the materials branch, with
  one critical difference: **consultant POs are CIS-clean**. The PO path does
  not apply CIS (CIS lives only on the subcontract/Contractor path), so a
  consultant→PO is automatically CIS-free — no flag needed at this layer.
  Set `downstream_kind = "purchase_order"`. Thread `package_id`.
- `else:` → keep the defensive `raise PackageStateError(f"Unknown package
  kind {p.kind!r}")`.

**Why consultant → PO and not subcontract:** `create_subcontract` hard-rejects
any supplier whose `supplier_type != "Contractor"` (LD2, line ~289). A
Consultant cannot be a subcontract counterparty by construction. Routing
consultant spend through the PO path is both correct (professional fees are
purchase orders, not CIS subcontracts) and the only path that doesn't trip
LD2. Verified against `subcontracts.py:289` at HEAD.

### 3.2 Thread `package_id` into both downstream creates
- Materials + consultant branches: add `"package_id": str(p.id)` to the
  `po_payload` dict.
- Subcontract branch: add `package_id=p.id` to the `sc_kwargs` passed to
  `create_subcontract`.
The downstream services must accept and persist it (Gate 4).

### 3.3 Service signature additions (this gate, consumed by Gate 4 schema)
- `purchase_orders.py::create_po` — read `payload.get("package_id")`, coerce
  to UUID if present, set on the `PurchaseOrder(...)` constructor as
  `package_id=...`. Validate (if present) that the package exists and belongs
  to the same tenant/project; on mismatch raise `ValueError` (→ 422). For the
  award path the package is guaranteed valid; for the standalone path
  (§6) it will normally be absent.
- `subcontracts.py::create_subcontract` — add `package_id: Optional[uuid.UUID]
  = None` kwarg; same validation; set on `Subcontract(...)`.

### 3.4 Tests (HARD — name exactly)
Add to `backend/tests/test_packages_service.py` (award-flow section):
- `test_award_consultant_routes_to_po` — create consultant package, line,
  tender, consultant bid, award → assert a PO is created
  (`created_purchase_order_id` set, `created_subcontract_id` NULL), and the
  PO carries `package_id == package.id`.
- `test_award_subcontract_routes_to_subcontract` — (renamed from any
  labour-routing test) → subcontract created, `package_id` set, `cis_applies`
  True.
- `test_award_materials_po_carries_package_id` — extend existing materials
  award test to assert `po.package_id == package.id`.
- `test_award_consultant_po_is_cis_clean` — assert the consultant-origin PO
  has no CIS treatment applied (assert at whatever field/þabsence the PO model
  exposes; if PO has no CIS field at all, assert the subcontract path was NOT
  taken — `created_subcontract_id IS NULL`).
- `test_consultant_award_reconciles_awarded_net` — awarded_net on the package
  equals the sum of awarded line nets, identical maths to materials.

### ⛔ GATE 3 STOP — report:
1. 2nd-run WARM-DB suite count + the five new/renamed award tests passing.
2. **LIVE-API proof** (not just unit tests): against the running pod, via
   authenticated curl against live OpenAPI paths —
   - create a `consultant` package + line, send to tender, invite a
     `Consultant` supplier, enter a bid, award it;
   - `GET` the resulting PO and show `package_id` populated and
     `created_subcontract_id` NULL on the award;
   - repeat the award flow for a `subcontract` package against a `Contractor`
     and show the subcontract carries `package_id`.
   Paste the actual JSON responses (redact nothing structural).
**Do not proceed until live-API award proof is shown for all three kinds.**

---

## GATE 4 — package_id columns live + set end-to-end (HARD STOP)

The migration (Gate 1) already added the columns. This gate proves the
**ORM + schema + end-to-end wiring**.

### 4.1 Models
- `models/purchase_orders.py` — add:
  ```python
  package_id = Column(
      UUID(as_uuid=True),
      ForeignKey("packages.id", ondelete="SET NULL"),
      nullable=True,
  )
  ```
  Add a relationship if the codebase convention uses them on this model
  (check existing pattern — only add if siblings do). Add `package_id` to the
  PO serialiser output (`_snap_po` / `serialise`).
- `models/subcontracts.py` — same column; add to that model's serialiser.

### 4.2 Schemas / router bodies
- `routers/purchase_orders.py::POCreate` — add `package_id: Optional[uuid.UUID]
  = None`. `model_config` is `extra="forbid"`, so the field MUST be declared
  or standalone callers passing it would 422.
- `routers/subcontracts.py::SubcontractCreateBody` — add `package_id:
  Optional[uuid.UUID] = None`, and thread it through the `create_subcontract`
  call in the endpoint (line ~111-124).
- PO create endpoint already does `body.model_dump(... exclude_unset=True)` →
  `package_id` flows into payload automatically once on the schema. Confirm.

### 4.3 Serialiser exposure
Both PO and subcontract read serialisers must return `package_id` (string or
null) so the frontend can render the "from package X" backlink (Gate 7).

### 4.4 Tests (HARD — name exactly)
- `backend/tests/test_purchase_orders.py::test_create_po_accepts_package_id`
  — standalone PO create with a valid `package_id` persists + serialises it.
- `..._service.py::test_create_po_rejects_foreign_package_id` — `package_id`
  for a package in another tenant/project → 422.
- `backend/tests/test_subcontracts.py::test_create_subcontract_accepts_package_id`.
- `...::test_create_subcontract_null_package_id_ok` — omitted `package_id`
  → standalone subcontract, NULL link (the common case).

### ⛔ GATE 4 STOP — report:
1. 2nd-run WARM-DB suite count + the four new tests passing.
2. `\d purchase_orders` / `\d subcontracts` already shown at Gate 1 — confirm
   ORM reflects them (`python -c "from app.models.purchase_orders import
   PurchaseOrder; print('package_id' in PurchaseOrder.__table__.c)"` → True;
   same for Subcontract).
3. LIVE-API: create a **standalone** PO via `POST
   /api/v1/projects/{id}/purchase-orders` with NO `package_id` → 201, link
   null; then one WITH a valid `package_id` → 201, link set. Paste responses.
**Do not proceed until verified.**

---

## GATE 5 — Line serialiser cost-code-name enrichment + grouping + subtotals + titles (BATCHABLE)

### 5.1 Backend: enrich the serialised package line with the cost-code title
`_ser_package_line` (line 1384) currently returns `cost_code` (string) only.
Add `cost_code_name`. The package service already has DB access in the
serialise path? — **No**, the serialisers are pure (take ORM objects). So:
- In `serialise_package` (1495), build a `Map<code_string, name>` once per
  package by querying `CostCode.code, CostCode.name` for the distinct
  `cost_code` strings on the package's lines (single `SELECT ... WHERE code =
  ANY(:codes)`), and pass the map into `_ser_package_line` so each line gets
  `cost_code_name`. If a code string has no match (legacy/freetext), return
  `cost_code_name = None` and the frontend falls back to showing the bare
  code.
- This keeps the frontend free of any string-keyed cost-code fetch.

Add `cost_code_name` to the serialised line in `_ser_package_line` (it is
**not** sensitive — title is not pricing — so it is always present regardless
of `include_sensitive`).

### 5.2 Frontend: new string-keyed grouping helper
Create `frontend/src/lib/packageLineGroup.js`:
- `groupPackageLinesByCostCode(lines)` → array of group objects:
  `{ costCode, costCodeName, lines, subtotalNet }` where `subtotalNet` =
  Σ `Number(line.budgeted_net_amount ?? 0)` over the group, and groups are
  ordered by `costCode` ascending (natural numeric-ish sort on the dotted
  code, e.g. "4.02" < "4.10").
- Lines with no `cost_code` fall into a trailing `"—"` / "Uncategorised"
  group.
- **Do not import `budgetCategoryGroup.js`** — different key space.
- Unit-test it: `frontend/src/lib/__tests__/packageLineGroup.test.js` with
  fixtures covering multi-code grouping, subtotal maths, sort order, and the
  uncategorised bucket.

### 5.3 Frontend: render grouping + subtotals + titles on PackageDetail
In `PackageDetail.jsx`, the line tables at ~506, ~988, ~1520 currently render
a flat list showing `ln.cost_code`. Update the primary package-lines table to:
- Group via `groupPackageLinesByCostCode`.
- Render a group header row per cost code showing **"{code} — {name}"**
  (e.g. "4.02 — Groundworks"), using `cost_code_name` from the serialised line
  (fall back to bare code if null).
- Render a per-group subtotal row (net) — display-only, clearly a subtotal.
- Keep individual line rows indented under their group header.
- The bid/award sub-tables (988, 1520) may stay as-is for this gate unless the
  grouping reads naturally there too — operator-facing priority is the package
  lines table. (If trivial, apply the same grouping; if it risks the
  award-table maths, leave it — flag in the gate report.)

### ⛔ GATE 5 STOP — report:
1. 2nd-run WARM-DB backend count (new serialiser test:
   `test_ser_package_line_includes_cost_code_name`).
2. Frontend test run: `packageLineGroup.test.js` green + existing
   `PackageDetail.test.jsx` still green (update its fixtures for the new
   grouped DOM if it asserts flat rows).
3. **LIVE eyeball**: screenshot/describe the package detail showing grouped
   lines under "4.xx — Title" headers with per-group subtotals. Confirm the
   dev-server route renders (not just the test).
This is a UI gate — may batch with Gate 6 if you reach it cleanly.

---

## GATE 6 — Create dialog 3 kinds + list/detail kind display + supplier-picker filters (BATCHABLE)

### 6.1 `NewPackageDialog.jsx`
Replace the two-radio `fieldset` (materials/labour) with three radios:
- `materials` — label **"Materials (Purchase Order)"**, testid
  `new-package-kind-materials`.
- `subcontract` — label **"Subcontract — labour or supply & fit
  (Subcontract)"**, testid `new-package-kind-subcontract`.
- `consultant` — label **"Consultant — professional fees (Purchase Order)"**,
  testid `new-package-kind-consultant`.
Default stays `materials`. The `kind` state + the `createPackage` body need no
other change (the API already passes `kind` through).

### 6.2 `PackagesList.jsx`
- Filter `<select>` (146-147): replace the two options with three —
  `materials` / `subcontract` / `consultant`, human labels "Materials",
  "Subcontract", "Consultant".
- Kind display cell (228): show a humanised label. Add a tiny map
  `{materials:'Materials', subcontract:'Subcontract', consultant:'Consultant'}`
  rather than raw enum text; keep the existing styling.

### 6.3 `PackageDetail.jsx` supplier-picker filter (792-803) + hint (847)
Rewrite the supplier filter to mirror the backend guard exactly:
```js
const items = (data?.items || data || []).filter((s) => {
  if (pkg.kind === 'subcontract') return s.supplier_type === 'Contractor';
  if (pkg.kind === 'materials')
    return ['Supplier', 'Contractor'].includes(s.supplier_type);
  if (pkg.kind === 'consultant') return s.supplier_type === 'Consultant';
  return false;
});
```
Hint text (847): 
- `subcontract` → "(Contractor only — CIS counterparty)";
- `materials` → "(Supplier / Contractor)";
- `consultant` → "(Consultant only)".
Kind display (163) → humanised label as in 6.2.

### ⛔ GATE 6 STOP — report:
1. Frontend tests green (update `PackagesList.test.jsx`,
   `PackageDetail.test.jsx`, `NewPackageDialog` tests for the new testids /
   options).
2. **LIVE eyeball**: create one package of each kind via the dialog; show the
   list filter working for all three; on a consultant package, show the
   invite-bidder picker lists only Consultants; on a subcontract package, only
   Contractors. Confirm a wrong-type invite is rejected by the server with a
   visible error (mutation handler surfaces it).

---

## GATE 7 — One front door (Simple order vs Package) + bidirectional link display (BATCHABLE)

### 7.1 The front door
Today the standalone PO entry point is `+ New PO` →
`/projects/:id/purchase-orders/new` (`PurchaseOrderForm.jsx`). The package
flow is separate (NewPackageDialog). Locked design: **one "New order" front
door** that asks the user to choose:
- **Simple order** → today's PO form, entirely unchanged underneath.
- **Package** → today's package flow (NewPackageDialog), unchanged underneath.

Implement as a lightweight chooser (modal or two-button intercept) at the
"New order" CTA. **Do not rebuild either underlying flow** — this is a routing
shim only. Both paths must remain reachable and behave exactly as they do
today. Keep existing deep-links/testids working (don't break automation that
hits the PO form route directly).

Confirm the exact CTA location during build (read `PurchaseOrderList.jsx` and
wherever the package "New package" CTA lives) and place the chooser at the
natural single entry point. If the two CTAs live on different screens today,
the minimal correct move is: add the chooser at the PO list "New" CTA and have
the "Package" choice deep-link into the existing package create. Flag the
exact placement decision in the gate report for confirmation.

### 7.2 Bidirectional link display
- **On a PO / subcontract that has `package_id`**: show a "From package
  {reference}" link back to the package detail. Source: the new `package_id`
  on the read serialiser (Gate 4.3) — resolve the reference via a small fetch
  or include `package_reference` in the serialiser (prefer including
  `package_reference` server-side to avoid an extra round-trip; add it
  alongside `package_id` in the PO/subcontract read serialiser).
- **On the package award tab**: already half-there via
  `package_awards.created_purchase_order_id` / `created_subcontract_id`. Show
  the created order's number/reference as a link to the PO/subcontract detail.
  Verify this renders for all three kinds.

### ⛔ GATE 7 STOP — report:
1. Frontend tests green (chooser component test; link-render tests).
2. **LIVE eyeball**: from a "New order" CTA, show the chooser; pick Simple
   order → lands on the unchanged PO form; pick Package → lands on package
   create. Then: open a package-origin PO and show the "From package X"
   backlink; open the originating package and show the created-order link on
   the award tab. Do this for a consultant-origin PO and a subcontract.

---

## FINAL GATE — full-suite, count reconciliation, docs

### F.1 Counts
- Permissions **142** (unchanged — assert `test_packages_service` count test
  passes untouched).
- Cost codes **133**, roles **10** (untouched).
- Alembic head **`0048_package_kind_3value_and_links`**.
- 2nd-run WARM-DB backend suite: state baseline → final; the only deltas are
  the added tests enumerated in Gates 2/3/4/5.

### F.2 Live health
`/api/health` 200; `SELECT DISTINCT kind FROM packages` shows only the live
3-value set; a smoke award of each kind succeeded (from Gate 3/6 evidence).

### F.3 Docs (Emergent writes CHANGELOG + chat summary — NOT the backlog)
- CHANGELOG entry under a Pack 3.5 heading: enum change, data migration,
  `_supplier_kind_guard` flip, consultant→PO routing, `package_id` links,
  grouping/titles UI, one-front-door shim. List every deviation.
- `docs/chat-summaries/chat-55-closing.md`.
- **Do NOT touch `docs/SY_Hub_Phase2_Backlog.md`** — operator-hand-edited only.

### F.4 Push discipline
Two commits (code+tests, then docs), both pushed via Save-to-GitHub. On
conflict: Branch & Push → PR → merge → wait 60s → verify per-file against the
**codeload tarball** (raw mirror was stale all of Chat 54 — do not trust raw
for verification). Confirm the migration file, both model edits, the service
routing block, and the new frontend helper all landed on `main`.

---

## Appendix A — exact existing-code anchors (re-confirm at HEAD before editing)

| What | File | Anchor (HEAD) |
|---|---|---|
| `PACKAGE_KINDS` tuple | `models/packages.py` | line 30 |
| kind PGEnum binding | `models/packages.py` | line 38 |
| named CHECK `ck_packages_kind_values` | migration 0047 | line 157 |
| enum-add autocommit pattern | migration 0047 | lines 50-57 |
| `create_package` kind validation | `services/packages.py` | line 327 |
| `_supplier_kind_guard` | `services/packages.py` | line 731 |
| guard caller (invite) | `services/packages.py` | line 763 |
| guard caller (enter_bid) | `services/packages.py` | line 990 |
| award routing branch | `services/packages.py` | lines 1174 / 1206 / 1228 |
| `_ser_package_line` | `services/packages.py` | line 1384 |
| `serialise_package` | `services/packages.py` | line 1495 |
| `create_po` constructor | `services/purchase_orders.py` | line ~310 |
| `create_subcontract` constructor | `services/subcontracts.py` | line ~344 |
| `cis_applies` default True | `services/subcontracts.py` | line 264 |
| LD2 Contractor hard-reject | `services/subcontracts.py` | line ~289 |
| `POCreate` body | `routers/purchase_orders.py` | line 62 |
| PO create endpoint | `routers/purchase_orders.py` | line 331 |
| `SubcontractCreateBody` | `routers/subcontracts.py` | line 46 |
| SC create endpoint | `routers/subcontracts.py` | line 100 |
| packages perm seed (no change) | `seed_rbac.py` | line 210 |
| count==142 assertion | `tests/test_packages_service.py` | line 538 |
| enum set assertion | `tests/test_packages_service.py` | line 114 |
| labour-rejects test | `tests/test_packages_service.py` | line 429 |
| grid grouping helper (do NOT reuse) | `lib/budgetCategoryGroup.js` | whole |
| cost-code hook | `hooks/costCodes.js` | whole |
| CostCode.name (title source) | `models/cost_codes.py` | line 70 |
| NewPackageDialog kind radios | `components/packages/NewPackageDialog.jsx` | ~205-240 |
| PackagesList kind filter/display | `pages/admin/PackagesList.jsx` | 146-147 / 228 |
| PackageDetail supplier filter | `pages/admin/PackageDetail.jsx` | 792-803 |
| PackageDetail kind hint | `pages/admin/PackageDetail.jsx` | 847 |

## Appendix B — sandbox recovery (if pod recycles mid-build)
```
bash /app/scripts/provision_postgres.sh
/root/.venv/bin/python -m app.bootstrap
```
Reseed; health = `/api/health` 200, 133 cost_codes, 142 permissions, alembic
head `0047` (→ `0048` after this pack's migration applies).
