# Chat 55 — B88 Pack 3.5 Closing Document

**Pack name:** B88 Pack 3.5 — Packages → 3-value kind vocabulary  
**Migration head:** `0048_package_kind_3value_links`  
**Closed:** 2026-06-14  
**Suite count (2nd-run WARM-DB authoritative):** 1591 collected · 1569 passed · 19 failed (identical to baseline) · 2 xfailed · 1 xpassed.

## What landed

### Backend
1. **Migration `0048`** — additive enum extension (`subcontract`, `consultant`); data-migrate `labour → subcontract`; CHECK swap to the 3-value live set; nullable `package_id` UUID FK (`ON DELETE SET NULL`) + index on `purchase_orders` and `subcontracts`. `labour` left as orphaned enum member (precedent 0020 / 0047). Down/up round-trip clean.
2. **Kind vocabulary** — `PACKAGE_KINDS = ("materials", "subcontract", "consultant")`. `_supplier_kind_guard` rewritten with the consultant flip (consultant packages now REQUIRE `Consultant`; subcontract narrowed to `Contractor` only).
3. **Award routing** — three branches in `services/packages.py::award_package`:
   - `materials → po_svc.create_po` (unchanged maths)
   - `subcontract → sc_svc.create_subcontract` (CIS counterparty)
   - **NEW** `consultant → po_svc.create_po` (CIS-clean — the PO path applies no CIS by construction)
   All three pass `package_id=p.id` so the downstream object back-links to its origin.
4. **Standalone path** — `POCreate.package_id` and `SubcontractCreateBody.package_id` added; service validators UUID-coerce + exists + same-tenant + same-project before any write (422 on any mismatch).
5. **Serialiser enrichment** —
   - `_ser_package_line` adds `cost_code_name` via a single batched cost-code lookup in `serialise_package(db=...)`.
   - `serialise(po, ...)` and `serialise(sc, ...)` add `package_id` + `package_reference` (lazy `package` relationship on each ORM model).

### Frontend
1. **`packageLineGroup.js`** (new) — `groupPackageLinesByCostCode`, `dottedCodeKey`, `compareDottedCodes` (`4.02 < 4.05 < 4.10 < 4.20`), BigInt-pennies subtotal sum.
2. **`PackageDetail` LinesTab** — rewritten to render group header + lines + subtotal rows per cost code; `data-testid="package-line-group-header-{code}"` / `package-line-group-subtotal-{code}`.
3. **`NewPackageDialog`** — 3-radio set (Materials (PO) / Subcontract / Consultant (PO)).
4. **`PackagesList`** — kind filter updated to the 3-value vocab.
5. **`InviteBidderDialog`** — three-branch supplier filter (materials → Supplier/Contractor; subcontract → Contractor; consultant → Consultant). Header copy updated.
6. **`PurchaseOrderForm`** — "How are you creating this PO?" chooser fieldset; `Simple order` vs `From a Package`; `package_id` field threaded into the create payload only when the package path is chosen.
7. **`PurchaseOrderDetail`** — teal back-link callout `FROM PACKAGE <package_reference>` when `po.package_id` is set; nothing rendered for standalone POs.

## Build-Pack corrections (documented in CHANGELOG D-table)

| Code | What | Why |
|------|------|-----|
| D1 | Revision id shortened (`_and_` dropped) | `varchar(32)` constraint |
| D2 | Up/down step ordering fixed (CHECK straddles UPDATE) | Original ordering would 23514-violate `ck_packages_kind_values` |
| D3 | Existing `TTN_6/7/8` shifted to `9/10/11` | Build Pack §2.4 slot collision |
| D4 | `TM_2` package_kind asserted against CHECK, not pg_enum | Pack 3.5 leaves `labour` orphaned (§0.4) |
| D5 | 4 demo cost codes `4.02/05/10/20` inserted then removed | Live seed uses `XXX-NN`; needed dotted codes for visual sort proof |

## Live-API proofs captured

- **Gate 3** — three full award flows POSTed against `REACT_APP_BACKEND_URL` showing materials → PO £240, subcontract → SC `cis_applies: true`, consultant → PO `created_subcontract_id: null`. Pasted JSON in the Gate 3 STOP.
- **Gate 4** — standalone PO POSTs: (a) with `package_id` → 201 + `package_reference` enriched on read; (b) without → 201 + both null; (c) foreign-project `package_id` → 422 pre-write. Pasted JSON in the Gate 4 STOP.
- **Gates 5/6/7** — screenshots captured against the live preview:
  - `/tmp/g5_package_detail.png` — 4.02 < 4.05 < 4.10 < 4.20 group order with subtotals.
  - `/tmp/g6_list_filter.png` — All / Materials / Subcontract / Consultant.
  - `/tmp/g6_new_dialog.png` — 3 radios in the create dialog.
  - `/tmp/g6_invite_consultant.png` — out_to_tender consultant package; picker lists ONLY `(Consultant)` rows.
  - `/tmp/g6_invite_subcontract.png` — out_to_tender subcontract package; picker lists ONLY `(Contractor)` rows.
  - `/tmp/g7_po_chooser.png` — front-door chooser with package_id field revealed.
  - `/tmp/g7_po_link.png` — `FROM PACKAGE PKG-0001` callout on a PO that was created with `package_id`.
- **Gate 6 server rejection** — three wrong-type invites against the live API returned 422 with the exact guard messages:
  ```
  consultant_pkg + Contractor   → 422  consultant packages require a Consultant bidder; got supplier_type='Contractor'
  subcontract_pkg + Consultant  → 422  subcontract packages require a Contractor bidder (CIS counterparty); got supplier_type='Consultant'
  subcontract_pkg + Supplier    → 422  subcontract packages require a Contractor bidder (CIS counterparty); got supplier_type='Supplier'
  ```

## Invariants (final state)

| Counter           | Pre-Pack-3.5 | Post-Pack-3.5 |
|-------------------|---------------|----------------|
| `permissions`     | 142           | **142**        |
| `roles`           | 10            | **10**         |
| `cost_codes`      | 130 (canonical per Pack 1 G4 corrected master) | **130** |
| `alembic head`    | 0047_packages | **0048_package_kind_3value_links** |
| Suite passed (2nd-run WARM-DB) | 1557 | **1569** (+12 new Pack 3.5 tests) |
| Suite failed | 19 (legacy stale assertions) | **19 (IDENTICAL set)** |

## Tests added (named exactly as in Build Pack)

- `test_TTN_4_subcontract_rejects_non_contractor` (renamed from labour-rejects-non-contractor)
- `test_TTN_6_consultant_accepts_consultant`
- `test_TTN_7_consultant_rejects_non_consultant`
- `test_TTN_8_materials_rejects_consultant`
- `test_TM_1_alembic_head_is_0048` (renamed/updated from `_0047`)
- `test_award_consultant_routes_to_po`
- `test_award_subcontract_routes_to_subcontract`
- `test_award_materials_po_carries_package_id`
- `test_award_consultant_po_is_cis_clean`
- `test_consultant_award_reconciles_awarded_net`
- `test_standalone_po_create_with_package_id_links`
- `test_standalone_po_create_without_package_id_unlinked`
- `test_po_create_rejects_foreign_package_id`
- `test_subcontract_create_with_package_id_links`

Plus extensions to `TAW_1`, `TAW_2`, `TCX_3`, `TM_2` (assertions adapted to the 3-value vocab).

## Untouched

- `/app/docs/SY_Hub_Phase2_Backlog.md` — backlog file not touched per Build Pack §0.2.
- Materials → PO routing — identical to pre-3.5 (invariant respected).
- Permission table — no add/remove, count holds at 142.
- Decimal `_q2` money maths — untouched in any branch.

## Closing

Pack 3.5 ships clean: 2nd-run WARM-DB suite reconciles exactly to the baseline failure set, every money path proven end-to-end via live API and screenshot, no schema/data/perm regression.
