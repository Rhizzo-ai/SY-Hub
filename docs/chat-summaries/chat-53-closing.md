# Chat 53 — Closing summary

**Build Pack:** B88 Pack 3 — Packages (the tendering spine).
**Branch:** `main`.
**Gate 1 (backend) — CLEARED:** operator verified file-by-file on
`origin/main`.
**Gate 2 (frontend + docs) — PROPOSED FOR EYEBALL.**

## What shipped

### Gate 1 — Backend (migration head `0047_packages`)

Six tables, four PG enums, two enum extensions (`permission_action.'award'`,
`permission_resource.'packages'`), six new permissions (`packages.view`,
`view_sensitive`, `create`, `edit`, `award`, `delete`), per-role grants
matching the operator-confirmed distribution, an award engine that holds
the package row `FOR UPDATE` across one DB transaction and enforces:

1. **Header Σ-guard** (LD-P3) — Σ(active awards' awarded_net) ≤
   `package.total_net` + £0.01 tolerance.
2. **Per-line quantity guard** — Σ(award_line.quantity) for each
   package_line, across active awards, ≤ `package_line.quantity`.

Server computes every `net = round(qty × rate, 2)`. Client nets are
rejected by schema. Downstream creates flow through the existing
`create_po` (materials) / `create_subcontract` (labour) services on the
same session; an exception anywhere rolls the whole call back (no
orphan PO, no orphan award row — T-AW-9 + T-AW-10).

**D4 — structural detail worth remembering.** Postgres does not allow
`DEFERRABLE` on `CHECK` constraints, so `ck_package_awards_one_downstream`
is non-deferrable. The award engine was therefore restructured to create
the downstream PO/SC FIRST, then INSERT the `package_awards` row with
the downstream id already populated. CK satisfied at row-insert time;
atomicity preserved.

**Tests.** 57 (21 service + 36 API). Both cold + warm green. Five live
HTTP proofs against the running pod (create / send-to-tender + 2 bids /
split award / over-total 422 with zero new POs / drive PO to `issued`
and watch the budget line's `committed_value` go to £95k).

### Gate 2 — Frontend (`/admin/packages`)

- `lib/api/packages.js` — 18 axios wrappers, one per endpoint.
- `pages/admin/PackagesList.jsx` — list + filters + "New package".
- `pages/admin/PackageDetail.jsx` — three tabs:
  - **Lines** (editable in draft only; budget-line picker pulls the
    package's budget grid).
  - **Bids** (visible from `out_to_tender`+; invite supplier picker
    filters by `kind/supplier_type` per LD-P6; "Enter bid" shows the
    live client-side `net = qty × rate` preview while the server stays
    authoritative).
  - **Award** (per-spec form supporting split awards across suppliers;
    Σ summary panel re-computes on every keystroke; **red inline
    alert + greyed-out submit** appears the instant
    `Total after > total_net + £0.01`).
- Every mutation handler surfaces the server `detail` via
  `sonner.toast` + inline. No silent `onError` anywhere.
- "Packages" nav entry beside "Cost Codes" (gated on `packages.view`).

## Locked operator decisions

| # | Decision | Where enforced |
|---|---|---|
| LD-P1 | Labour → Subcontract, Materials → PO | service award engine |
| LD-P2 | Status machine `draft → out_to_tender → partially_awarded → awarded`; cancelled from any non-terminal | `services.packages._recompute_award_totals` + transition guards |
| LD-P3 | Header Σ-guard with £0.01 tolerance | `award_package` line 360-ish |
| LD-P4 | Bidders compete on rate; client nets never trusted | schema rejects `net_amount`; service derives it |
| LD-P5 | Fast-track awards allowed (no source bid) | `award_package` accepts `source_bid_id=null` if package is draft AND every spec is fast-track |
| LD-P6 | Bidder type coherence (labour → Contractor; materials → Supplier OR Contractor) | `_supplier_kind_guard` |

## Files committed (this gate)

### Backend (Gate 1 — already on `origin/main`)
- `backend/alembic/versions/0047_packages.py`
- `backend/app/models/packages.py`
- `backend/app/models/__init__.py` (exports)
- `backend/app/models/rbac.py` (`RESOURCES += packages`, `ACTIONS += award`)
- `backend/app/schemas/packages.py`
- `backend/app/services/packages.py`
- `backend/app/routers/packages.py`
- `backend/app/seed_rbac.py` (perm block + director exclusion + role grants)
- `backend/server.py` (mount on `v1_router`)
- `backend/tests/_packages_common.py`
- `backend/tests/test_packages_service.py` (21 tests)
- `backend/tests/test_packages.py` (36 tests)
- `backend/scripts/b88_pack3_gate1_proofs.py` (live HTTP transcript)
- `memory/PRD.md` (Pack 3 section)

### Frontend (Gate 2 — added here)
- `frontend/src/lib/api/packages.js`
- `frontend/src/pages/admin/PackagesList.jsx`
- `frontend/src/pages/admin/PackageDetail.jsx`
- `frontend/src/components/packages/NewPackageDialog.jsx`
- `frontend/src/components/packages/packagesHelpers.js`
- `frontend/src/App.js` (routes)
- `frontend/src/components/AppShell.jsx` (nav entry)

### Docs (Gate 2 — added here; `SY_Hub_Phase2_Backlog.md` deliberately
untouched per operator rule)
- `CHANGELOG.md` (Chat 53 entry)
- `docs/chat-summaries/chat-53-closing.md` (this file)

## Live-eyeball script

1. Sign in as **test-pm** → `/admin/packages` → "New package" → pick
   project + budget + kind=materials → create.
2. Open the package → Lines tab → add 1–2 lines from the budget grid →
   "Send to tender". Status pill flips from `Draft` → `Out to tender`.
3. Bids tab → "Invite bidder" → select a `Supplier`-type bidder →
   invite. Row appears with `Invited` pill.
4. "Enter bid" → set rates per line → submit. Bid pill flips to
   `Received` and shows `total_net`.
5. Sign out, sign in as **test-finance** (MFA enrolled) → Award tab →
   "Award winner(s)" → pick supplier from the received-bids dropdown
   → "Source bid" → rates auto-populate from the bid → set qty per
   line → "Confirm award". On success: status flips to `Partially
   awarded` / `Awarded`, awards row shows the PO/SC link.
6. Re-open Award form → bump rate to absurd → red banner appears + 
   submit greys out instantly. Force-submit via DOM (the eyeball) is
   server-rejected with 422.

## Backlog touched by this pack — NONE

`docs/SY_Hub_Phase2_Backlog.md` was NOT modified per the operator rule.
The Pack 3 spine intentionally does NOT yet wire chat / notifications
/ exports / multi-version packages / template duplication — those are
left for future packs.

## Demo seed — operator-invoked only

`backend/scripts/seed_b88_pack3_packages_demo.py` builds three demo
packages (1 materials split award, 1 labour single award, 1 draft)
via the real service layer. HARD safety guard refuses to run unless
`SYHUB_ALLOW_DEMO_SEED=1` AND `--force`. Idempotent. NOT wired into
bootstrap.py / on-restart.sh.

```sh
# seed
cd /app/backend
SYHUB_ALLOW_DEMO_SEED=1 /root/.venv/bin/python \
    scripts/seed_b88_pack3_packages_demo.py --force

# clean (removes ONLY the demo rows it created)
SYHUB_ALLOW_DEMO_SEED=1 /root/.venv/bin/python \
    scripts/seed_b88_pack3_packages_demo.py --force --clean
```

---

End of Chat 53 closing.
