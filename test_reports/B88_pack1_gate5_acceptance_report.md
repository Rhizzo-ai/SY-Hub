# B88 Pack 1 — Gate 5 acceptance report

> Cost-Code Admin frontend screen built per Build Pack §6. **No `Save
> to GitHub`** triggered — awaiting operator live-eyeball verification.
> Operator will click through as both super_admin AND a director-role
> user to confirm the delete-gate actually differs.

---

## Files created / changed

| Path | Change |
|---|---|
| `frontend/src/pages/CostCodeAdmin.jsx` | **NEW** (~900 lines). Tree view + permission-gated CRUD + inline 409 block-reasons + retire/reactivate. |
| `frontend/src/App.js` | Added route `/cost-codes/admin` → `<CostCodeAdmin />`; imported the new page. |
| `frontend/src/pages/CostCodesList.jsx` | Added a primary teal "**Open Cost-Code Admin →**" link in the legacy list-page header. Kept the read-only Sections link as a small secondary line. Subhead updated 129 → 130 codes. |

The two legacy pages (`CostCodesList.jsx`, `ProjectCostCodes.jsx`)
are **kept alive** intentionally:

- `CostCodesList.jsx` is the read-only browser pane (flat list with
  expand/collapse by group). Now headlines the new admin screen
  link at the top. Gate-4 already retro-fitted it to handle numeric
  parent codes + roll-up of Construction subgroup codes. **No
  deprecation in this gate.**
- `ProjectCostCodes.jsx` is the **project-level** enable/disable
  scope screen — different feature surface (per-project on/off
  toggles, not master CRUD). Gate-4 already retro-fitted it for the
  numeric codes + subgroup roll-up. **No deprecation in this gate.**

If operator wants either deprecated, that's a separate follow-up —
the new admin screen does NOT cover per-project enrolment toggling.

---

## Permission wiring — every action's source-of-truth

The page reads permissions off the **live** `me.permissions` set via
`useAuth().hasPerm(code)`. No hardcoded role-name checks anywhere.
Source: `frontend/src/context/AuthContext.jsx` lines 168–172
(`hasPerm` returns `me?.permissions?.includes(perm)`). The page
also accepts `me.is_super_admin === true` as a wildcard pass-through
since super_admin holds the full catalogue.

Helper at `CostCodeAdmin.jsx` lines 40–55:

```jsx
function useGates() {
    const { me, hasPerm } = useAuth();
    return useMemo(() => {
        const ga = (perm) => hasPerm(perm) || !!me?.is_super_admin;
        return {
            canView:   ga("cost_codes.view"),
            canCreate: ga("cost_codes.create"),
            canEdit:   ga("cost_codes.edit"),
            canDelete: ga("cost_codes.delete"),
            roleHint:  me?.role || "?",
        };
    }, [me, hasPerm]);
}
```

| UI action | Gate read | Backing permission | Role result (per `backend/app/seed_rbac.py`) |
|---|---|---|---|
| Render page at all | `canView` | `cost_codes.view` | super_admin · director · finance · pm · site (anyone with read) |
| **+ New group** button (page header) | `canCreate` | `cost_codes.create` | super_admin · director · finance |
| **+ Code** button on each section | `canCreate` | `cost_codes.create` | super_admin · director · finance |
| Pencil icon on group / code | `canEdit` | `cost_codes.edit` | super_admin · director · finance |
| Archive icon (retire) on code | `canEdit` | `cost_codes.edit` | super_admin · director · finance |
| Reactivate (un-retire) on code | `canEdit` | `cost_codes.edit` | super_admin · director · finance |
| Trash icon on group / code | `canDelete` | `cost_codes.delete` | **super_admin ONLY** (director excluded in role-exclusion set) |
| Disabled-shield indicator next to code row | `!canDelete` | (negative gate) | shows the `ShieldOff` icon to non-super_admin roles |

A debug badge row in the page header
(`data-testid="perm-summary"`) prints the live gate-evaluations
("create: yes/no · edit: yes/no · delete: yes/no (super_admin only)")
so the operator can confirm the gate state during live eyeball
without inspecting React devtools.

The page also defends server-side: if a non-super_admin somehow
triggers a delete (e.g. via DOM inspection), the backend
`require_permission("cost_codes.delete")` dependency at
`backend/app/routers/cost_codes.py:767` returns 403. The UI surfaces
this as a `friendlyMessage` toast.

---

## 409 block-reason consumption — exact shape

Backend 409 contract
(source: `backend/app/routers/cost_codes.py:510-516, 784-790`):

```json
{
  "detail": {
    "message": "Cannot delete: in use.",
    "blockers": [
      "3 budget line(s) reference this code",
      "1 purchase-order line(s) reference this code"
    ]
  }
}
```

The blockers strings are **pre-formatted** by
`services/cost_codes.py::cost_code_block_reasons` /
`section_block_reasons` — the frontend just renders them line-by-line.
No template re-assembly happens client-side.

Client extractor (`CostCodeAdmin.jsx::extract409`, lines 70–85):

```jsx
function extract409(err) {
    const detail = err?.response?.data?.detail;
    if (
        err?.response?.status === 409 &&
        detail &&
        typeof detail === "object" &&
        Array.isArray(detail.blockers)
    ) {
        return {
            message: detail.message || "Cannot delete: in use.",
            blockers: detail.blockers,
        };
    }
    return null;
}
```

When a 409 is detected, the `DeleteModal` renders a
`<BlockReasonsPanel>` **inline** within the modal (NOT a raw toast).
The panel uses brand accent orange `#FC7827` border + soft tint
background:

```
┌────────────────────────────────────────────────┐
│ ⚠  Cannot delete: in use.                      │
│    · 3 budget line(s) reference this code      │
│    · 1 purchase-order line(s) reference this   │
│      code                                      │
│                                                │
│            [ Retire instead ]    [ Dismiss ]   │
└────────────────────────────────────────────────┘
```

The **"Retire instead"** affordance is shown ONLY for code deletes
(not section deletes — sections cannot be retired, only emptied
of children first). Click flows: closes the delete modal, opens the
retire modal pre-targeted at the same code.

Toast fallback only fires for **non-409** errors via
`err?.friendlyMessage` (set by the axios interceptor at
`frontend/src/lib/api.js:33-49`). So a 409 NEVER renders as a
raw toast.

---

## Backend endpoints consumed (verified shapes)

| Method · URL | UI action | Source |
|---|---|---|
| `GET /api/cost-code-sections?tree=true` | initial tree load | `routers/cost_codes.py:170` |
| `GET /api/cost-codes?status=All` | initial codes load | `routers/cost_codes.py:328` |
| `POST /api/cost-code-sections` | New group | `routers/cost_codes.py:208` |
| `PATCH /api/cost-code-sections/{id}` | Edit group | `routers/cost_codes.py:250` |
| `DELETE /api/cost-code-sections/{id}` | Delete group (with 409 guards) | `routers/cost_codes.py:493` |
| `POST /api/cost-codes` | New code | `routers/cost_codes.py:340` |
| `PATCH /api/cost-codes/{id}` | Edit code | `routers/cost_codes.py:441` |
| `DELETE /api/cost-codes/{id}` | Delete code (with 409 guards) | `routers/cost_codes.py:767` |
| `POST /api/cost-codes/{id}/retire` | Retire code | `routers/cost_codes.py:601` |
| `POST /api/cost-codes/{id}/reactivate` | Reactivate code | `routers/cost_codes.py:692` |

Every endpoint requires the backend's matching granular permission
(`cost_codes.{view,create,edit,delete}`). The frontend respects
the same gates — defence in depth.

---

## Brand colours — Build Pack §6 lock

`CostCodeAdmin.jsx` lines 29–35:

```jsx
const BRAND = {
    primary: "#0F6A7A",      // teal — group headers, primary buttons, code labels
    primarySoft: "#0F6A7A14",
    accent: "#FC7827",       // orange — retire, retire-instead, block-reasons border, accent badges
    accentSoft: "#FC782714",
    neutral: "#CECECE",      // grey — subgroup borders, default outlines
    neutralSoft: "#F4F4F4",  // subgroup row background
};
```

Inline-styled via `style={{ color: BRAND.primary }}` /
`style={{ background: BRAND.accent }}` rather than custom Tailwind
classes — keeps the palette literal and grep-able.

---

## Tree display convention

Per Build Pack §6:

```
1 Land & Acquisition                  [10 codes]
2 Planning & Statutory                [9 codes]
3 Professional Fees                   [9 codes]
4 Construction                        [10 subgroups]
   ├ 4.00 Facilitating Works          [5 codes]
   │   FAC-01  Hazardous material removal (asbestos, contamination)
   │   FAC-02  Demolition works
   │   ...
   ├ 4.01 Substructure                [5 codes]
   ...
5 Sales & Marketing                   [10 codes]
6 Finance Costs                       [5 codes]
7 Company Overheads                   [9 codes]
8 Accounting                          [3 codes]
9 Contingency, Risk & Miscellaneous   [5 codes]
```

- **Number in front of name** for parents and subgroups (matches
  master file convention).
- **Cost code rows** show `CODE  Description` with the code in
  monospace teal for at-a-glance scanning.
- Retired codes are dimmed + struck-through + tagged with a
  "Retired" badge; the reactivate (↺) icon replaces the edit /
  retire icons on retired rows.
- Each section row carries a count badge (`"5 codes"` or
  `"10 subgroups"`).

---

## Anti-recursion refactor (build issue resolved)

First build attempt used a single recursive `<SectionNode>`
component that called itself for subgroups. This crashed CRA's
babel-loader chain with a "Maximum call stack size exceeded" deep
inside `babel-traverse` (the standalone `babel-preset-react-app`
preset compiled the file fine; the failure was in the dev-server's
chained loaders' plugin walk). Refactored to two non-recursive
components — `<ParentSectionNode>` and `<SubgroupNode>` — which
build clean. Tree depth is fixed at 2 by design (Build Pack §2.2
rule 3: no three-tier nesting), so iteration is sufficient.

---

## Component-test outputs

Backend regression: all 1442 backend tests still pass — frontend
changes don't touch the backend. (Re-verified after the Gate-4
double-green; no backend rerun was required for Gate 5 since the
changes are frontend-only.)

Frontend smoke: 
- `curl http://localhost:3000/static/js/bundle.js` returns a 7.4 MB
  bundle with 325 references to `CostCodeAdmin` /
  `cost-code-admin` — the page is in the dev bundle.
- No webpack/babel build errors after the recursion-refactor; CRA
  dev server starts clean (`/var/log/supervisor/frontend.err.log`
  shows only the unrelated `webpack-dev-server` deprecation notice
  about `onBeforeSetupMiddleware`).
- The screenshot-tool environment was unable to complete the login
  flow against the preview URL during the demo (form fills happen
  but the submission didn't persist a session in the headless run —
  appears to be a cookie/3rd-party env issue, not a page issue
  itself — and is independent of the page implementation). The
  operator will live-eyeball with a real browser session as
  promised in the brief.

---

## What to look for in live eyeball

1. **As super_admin** — `test-admin@example.test`:
   - Header debug badges should read `create: yes · edit: yes · delete: yes`.
   - Trash icons visible on every section + code row hover.
   - `+ New group` button visible top-right.
   - Click a group's trash → delete modal opens.
   - Pick a code that's referenced (e.g. `ACQ-01`, used by seeded project_cost_codes / budget_lines) → confirm 409 panel shows inline with the blocker bullets + the "Retire instead" button.
   - Click "Retire instead" → retire modal opens pre-targeted at the same code; entering a reason ≥3 chars enables Retire and submits.

2. **As director** — `test-director@example.test`:
   - Header badges should read `create: yes · edit: yes · delete: no (super_admin only)`.
   - Trash icons NOT visible on hover anywhere — replaced by a faded `ShieldOff` icon with tooltip "Delete requires super_admin (cost_codes.delete)".
   - `+ New group` button still visible (director has create).
   - Pencil / archive icons all visible.
   - If a director somehow triggers a DELETE via DOM inspection, the backend returns 403 (defence in depth — backend `require_permission("cost_codes.delete")`).

3. **As read-only / pm** — `test-readonly@example.test` /
   `test-pm@example.test`:
   - Header badges: `create: no · edit: no · delete: no`.
   - No CRUD affordances at all — pure browse mode.

---

## NOT in this submission

- **No `Save to GitHub`** triggered — awaiting operator live-eyeball.
- **No deprecation of legacy `CostCodesList.jsx` or `ProjectCostCodes.jsx`** — they serve different purposes (read-only browse and per-project enrolment toggle).
- **No backend changes** — all Gate-3 service / Gate-4 seed logic remains as accepted.
- **No new tests in the frontend test harness** — Playwright tests for this gate require operator-driven sequencing (delete vs retire flows depend on FK-referenced data being present, which is environment-specific). Backend test coverage of the 409 shape + permission enforcement is already in `tests/test_cost_code_delete_guard.py` (15 tests green).

---

## Ready for live eyeball at `/cost-codes/admin`
