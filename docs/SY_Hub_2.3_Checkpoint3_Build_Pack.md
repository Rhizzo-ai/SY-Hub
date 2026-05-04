# SY Homes Hub — Prompt 2.3 Checkpoint 3 Build Pack

> **Status:** PRIMARY SPEC for Checkpoint 3. Supersedes §1 (Phase E) of `SY_Hub_2.3_Checkpoint3_Handoff.md`.
> **Inherits from handoff:** §0 (backend state), §3 (gotchas), §R0 (bootstrap recovery) — authoritative reference.
> **Written:** Chat 13, ahead of C3 Emergent fork. Same pattern as the C2 Build Pack.

---

## §0 — What this Build Pack supersedes and inherits

Two upstream documents, neither sufficient on its own for C3:

- **v6 prompt Phase E** (lines 711–801 of `SY_Hub_2_3_Prompt_v6.md`): originating UX spec, written before backend was built.
- **C3 Handoff §1 (Phase E)**: re-described by the C2 Emergent agent in handoff doc; diverges from v6 on five points and invents details on three more.

This Build Pack:
- **Locks five decisions (A–E)** where v6 and handoff disagreed (chat 13 review).
- **Adds ten SOTA enhancements (S1–S10)** not present in either doc.
- **Carries six sub-decisions (F1–F5, G1–G6)** verbatim from whichever doc was correct.
- **Corrects three factual errors in the fork summary** (NudgeBanner mount path, `api.js` path, missing `test-readonly` account).
- **Otherwise inherits handoff §0/§3/§R0 verbatim.**

The handoff doc itself stays in `/app/docs/`. Future readers should read this Build Pack first; consult handoff only for backend state, gotchas, and recovery.

---

## §1 — Locked decisions (architecture)

### Decision A — Component placement → **Handoff IA**

`ScenariosPanel` and `DecisionsTab` are top-level tabs on `AppraisalPage.jsx`. `RevisionTimeline` lives in the SummaryTab right column below the RLV panel, vertical orientation.

Tab order:
```
Header → Units → Costs → Finance → Scenarios (conditional) → Summary → Decisions
```

Scenarios tab renders only when `appraisal.scenario === 'Base'` AND user holds `appraisals.view`.

**Why this beats v6's "all on SummaryTab"**: cramming RevisionTimeline + ScenariosPanel + ScenarioComparator + RLV + KPIs onto SummaryTab produces a 1500+px scroll with five concerns competing for attention. SOTA IA (Linear, Vercel, GitHub) scopes by concern: one tab, one job.

### Decision B — Reopen vs New-version CTAs → **Handoff (two sibling buttons)**

Two buttons in the AppraisalPage header action row:

- **Reopen** (secondary style, left). Visible when `status ∈ {Approved, Rejected}` AND `is_current=true` AND user holds `appraisals.edit`. Onclick: POST `/reopen`. Label: **"Reopen for editing"** (per v6 E.1 wording).
- **New version** (primary style, right). Visible when `status === 'Approved'` AND `is_current=true` AND user holds `appraisals.edit`. Onclick: opens `NewVersionModal`.

`NewVersionModal`:
- `revision_reason` select (8 enum values).
- `summary_of_changes` textarea (min 10 chars after trim, counter visible from 0).
- Cancel + Submit. Submit POST `/new-version` → on 201 navigate to `/appraisals/{new.id}` (per F5).

**Implication for §3.1 RevisionTimeline:** the in-timeline "+ Create new version" CTA from v6 is **dropped** — header button is the sole entry point. CHANGELOG-flag.

### Decision C — Log Decision form pattern → **Handoff (inline split)**

DecisionsTab uses a 2/3 + 1/3 inline split:
- **Left (2/3):** chronological list, newest first.
- **Right (1/3):** "Log decision" form.

Form visibility gate matches server enforcement exactly:
- user holds `appraisals.approve`, AND
- `appraisal.is_current === true`, AND
- `appraisal.status === 'Approved'` *(R0 task: read `app/services/appraisal_decisions.py log_decision()` to confirm; if server enforces only `is_current`, drop the status gate from UI)*.

When the form is hidden, the right column collapses; list expands to full width.

### Decision D — `supporting_documents` field → **Omit (defer to Track 7)**

OMITTED from C3 form. Server schema accepts an empty array. Defer textarea/UUID picker to Track 7 (document pack). CHANGELOG-flag.

### Decision E — Decision-date picker timezone → **`date-fns-tz` Europe/London**

Use `date-fns-tz` for the decision-date picker default and max:
```js
import { formatInTimeZone } from 'date-fns-tz';
const today = formatInTimeZone(new Date(), 'Europe/London', 'yyyy-MM-dd');
```
Default value = today. Max value = today. This eliminates the `FUTURE_DATED_DECISION` 400 round-trip for users in non-UK timezones. Project already depends on `date-fns-tz` (Foundation track).

---

### Sub-decisions inherited from handoff (no flip)

- **F1** *(handoff §3.5)*: Scenario create only enabled on **Base v1 anchor**. Detect via `scenario_appraisal_id` comparison against current appraisal id (returned in `/scenarios` payload). On non-anchor Base (v2+): hide create CTAs, show explanatory banner with link to v1.
- **F2** *(handoff §3.4)*: Trim-before-length-check on `scenario_description` (mirrors server `ck_appraisal_scenarios_description_min_length`).
- **F3** *(handoff §3.6)*: Nudge re-fetch via `window.dispatchEvent(new CustomEvent('nudge-refresh', {detail: {projectId}}))`. Avoid full reloads.
- **F4** *(handoff §3.2)*: `decimal.js` for ALL comparator arithmetic and revision-delta arithmetic. Float is forbidden in 2.3 frontend per project policy. Eyeball every line.
- **F5** *(handoff §3.7)*: `/new-version` response → navigate to new appraisal id, NOT stay on now-Superseded source.

### Sub-decisions inherited from v6 (no flip)

- **G1** *(v6 E.5)*: NudgeBanner is **NOT dismissible**. Handoff's sessionStorage dismiss flag is dropped — the entire point is gentle pressure on directors to log decisions.
- **G2** *(v6 E.5)*: NudgeBanner mounts on `ProjectDetail.jsx` **ONLY**. Handoff's "also AppraisalsList" mount is dropped — single canonical surface.
- **G3** *(v6 E.6)*: `data-testid` conventions per v6 — `revision-timeline-node-{n}`, `comparator-row-{metric}`, `comparator-cell-{metric}-{label}`, `create-scenario-button`, `log-decision-button`, `create-version-button`, `nudge-banner`, `scenario-card-{label}`, `decision-row-{id}`. Shorter, no `-btn` suffix noise.
- **G4** *(v6 E.3)*: Comparator empty-state copy: *"Create an Upside, Downside, or Sensitivity scenario to enable side-by-side comparison."*
- **G5** *(v6 E.3)*: Comparator first column is sticky.
- **G6** *(v6 E.3)*: Click any RevisionTimeline node to navigate to that appraisal (read-only when `is_current=false` OR status ∈ {Superseded, Withdrawn, Rejected}).

### Fork-summary errors corrected

- ❌ Fork summary said NudgeBanner lives on `AppraisalHeader.jsx`. ✅ Correct surface is `ProjectDetail.jsx` only (per G2).
- ❌ Fork summary said `/app/frontend/src/api/api.js`. ✅ Actual path is `/app/frontend/src/lib/api.js`.
- ❌ Fork summary listed 3 test accounts. ✅ Four accounts: `test-admin`, `test-director`, `test-pm`, `test-readonly` per `/app/memory/test_credentials.md`.

---

## §2 — SOTA scope additions (S1–S10)

These are NOT in v6 or the handoff. They lift this UI from "spec-compliant" to "best-in-class". **All in C3 scope, not optional.**

### S1 — Skeleton loaders
Every async fetch renders a skeleton placeholder matching the eventual layout shape during pending state. NEVER "Loading…" text. NEVER spinners.

Implementation: `tailwindcss-animate` is already installed; use `animate-pulse` on layout-matched divs. No new deps. Skeleton shapes mirror final card/table dimensions so there's no layout shift on data arrival.

### S2 — Optimistic UI on POST `/decisions`
On submit:
1. Append a pending decision card to the list with `aria-busy=true` and ~50% opacity.
2. Fire POST.
3. On 201: replace the pending card with the full server response.
4. On error: remove the pending card, surface error inline above the form (preserve form values for re-submit).

Cleaner than the current pattern of submit → wait → reload list. Same approach for any other write that hits the visible list (currently only decisions in C3).

### S3 — NudgeBanner avatar stack
Backend `/nudge` returns `distinct_decision_makers` (count). Augment client-side:
- Fetch `/api/v1/appraisals/{current_appraisal_id}/decisions`, filter to types ∈ {Go, No_Go, Defer}, dedupe by `decision_maker_user_id`.
- Render small (24px) circular avatars stacked left-to-right of who has decided.
- Render ghost avatar slots (dashed circle) for remaining slots up to `threshold`.
- Tooltip on populated avatars: name + decision type pill + relative date.

No backend change. Social-presence layer assembled client-side.

### S4 — ScenarioComparator interactivity bumps
Beyond v6 spec:
- **Hover-highlight**: hovering any cell highlights its row AND column intersect (subtle bg colour change).
- **Sortable columns**: click any metric header to sort scenarios by that metric (Base always pinned at column 0). Sort indicator (▲/▼) in header. Default sort: order returned by API.
- **Delta animation**: when a new scenario is created, animate the new column sliding in (`framer-motion` `<motion.td>` initial: `{x: 60, opacity: 0}`) and delta cells number-rolling from 0 to final value (`framer-motion` `useSpring`).
- **Sticky first column** (already in G5; reaffirmed).

S10 disables the scroll/animate variants for users with reduced motion preference.

### S5 — `Intl.NumberFormat` money rendering
Replace any `.toFixed(2)` + manual £ prefix throughout C3 with:
```js
const gbp0 = new Intl.NumberFormat('en-GB', {
  style: 'currency', currency: 'GBP', maximumFractionDigits: 0
});
const gbp2 = new Intl.NumberFormat('en-GB', {
  style: 'currency', currency: 'GBP', minimumFractionDigits: 2, maximumFractionDigits: 2
});
```
Locale-aware grouping, proper £ placement. Wrap as `formatMoney(value, {decimals=0})` helper in `appraisalMath.js` — accepts `Decimal` or number; whole pounds for tiles/headers; two decimals for line-item details only.

### S6 — Framer Motion micro-interactions
**New dependency**: `framer-motion` (was not in 2.2). Subtle, not showy:
- Tab switches: 120ms x-axis slide between tab contents.
- Modal open/close: 180ms fade + scale-from-0.96.
- NudgeBanner enter/exit: 200ms y-axis slide-down / slide-up.
- Decision card append (paired with S2): 240ms slide-in from top of list.
- Comparator new-column entrance + delta number rolls (paired with S4).

All gated on `useReducedMotion()` (S10) → set transition duration to 0.

### S7 — Empty states with iconography
Every empty state gets:
- Lucide icon (size=48, muted colour `text-muted-foreground`).
- Concise heading (`text-lg font-medium`).
- Concise body (≤2 lines, `text-sm text-muted-foreground`).
- Clear CTA where appropriate.

Component-specific examples:
- **RevisionTimeline (v1 only)**: icon=`Clock`, heading="No revisions yet", body="This is the initial draft. New versions appear here when created."
- **ScenariosPanel (Base only, no others)**: icon=`GitBranch`, heading="No alternative scenarios", body="Compare upside, downside, and sensitivity cases against your base."
- **ScenarioComparator (Base only)**: per G4 copy.
- **DecisionsTab (no decisions logged)**: icon=`Gavel`, heading="No decisions logged", body varies by state — "Approve the appraisal first, then log Go/No-Go." when status !== Approved; "Log the first Go/No-Go to start tracking sentiment." when Approved.

### S8 — RevisionTimeline diff hover
Hover any non-v1 node → tooltip card pops out (200ms fade-in) showing:
- Δ GDV £±N (decimal.js, formatMoney).
- Δ Cost £±N.
- Δ Profit £±N.
- `revision_reason` badge.
- `summary_of_changes` (full text, `line-clamp-3`).

Cheap to render — data already in the `/revisions` response. Tooltip uses Shadcn `HoverCard` primitive.

### S9 — Keyboard navigation
Standard set:
- `j` / `k`: walk versions in RevisionTimeline (next/prev node, focuses + scrolls into view).
- `Esc`: close any open modal.
- `Cmd+Enter` / `Ctrl+Enter`: submit any open form (if valid; otherwise focus first invalid field).
- Tab order respects visual order in all components.

Implementation: native `keydown` event listeners on the components themselves, scoped to focused state. No `react-hotkeys-hook` or similar — keep deps lean.

### S10 — Reduced-motion respect
All animations gated on `prefers-reduced-motion: reduce`:
- `useReducedMotion()` from framer-motion → transition duration = 0.
- S4 column-slide-in and number-rolling: replace with instant render.
- S8 hover-card: instant show/hide instead of fade.

Tested via DevTools rendering panel: "Emulate CSS media feature prefers-reduced-motion: reduce".

---

## §3 — Component canonical specs

### §3.1 — RevisionTimeline (NEW)

**File**: `/app/frontend/src/components/appraisal/RevisionTimeline.jsx`
**Mount**: SummaryTab right column, below the RLV panel. Vertical orientation.
**Data**: `GET /api/v1/appraisals/{id}/revisions` → `{appraisals: [...], revisions: [...]}`.

**Render**:
- Skeleton on pending (S1).
- Empty state when `appraisals.length === 1` and `revisions.length === 0`: S7 empty state.
- Non-empty: vertical line with one node per appraisal in lineage (oldest top → newest bottom).

Each node:
- Status badge from `atoms.STATE_BADGE`.
- `v{version_number}` label.
- Relative timestamp (e.g. "3 days ago") via `date-fns formatDistanceToNow`.
- Active-version highlight: bolder ring + "Current" pill if `is_current=true`.
- **Hover (S8)**: HoverCard with Δ chips + revision_reason + summary_of_changes.
- **Click (G6)**: navigate to `/appraisals/{id}` (read-only mode if status ∈ {Superseded, Withdrawn, Rejected}).

**No in-timeline "+ Create new version" CTA** — header button is sole entry point per Decision B.

**`data-testid`s**: `revision-timeline`, `revision-timeline-node-{version_number}`, `revision-timeline-node-{n}-current` (active node).

### §3.2 — ScenariosPanel (NEW)

**File**: `/app/frontend/src/components/appraisal/ScenariosPanel.jsx`
**Mount**: AppraisalPage as top-level tab labelled "Scenarios", between Finance and Summary tabs.
**Conditional render**: `appraisal.scenario === 'Base'` AND user holds `appraisals.view`.
**Data**: `GET /api/v1/appraisal-groups/{group_id}/scenarios`.

**Render**:
- Skeleton on pending.
- 2×2 grid of slots: Base (top-left), Upside (top-right), Downside (bottom-left), Sensitivity (bottom-right).

**Populated slot card**:
- `scenario_label` badge.
- `scenario_description` (line-clamp-2; full text in HoverCard).
- "Open v{version_number}" link → `/appraisals/{current_appraisal_id}`.
- Status badge.
- Last-modified relative timestamp.
- KPI mini-row: GDV / Profit / Margin % via `formatMoney` (S5).

**Empty slot card** (only on non-Base slots):
- Muted dashed border.
- "+ Create {label} scenario" button.
- Visible only when user holds `appraisals.edit` AND current appraisal IS the Base v1 anchor (per F1).
- On non-anchor Base (v2+): hide create CTAs, show banner *"Scenarios can only be created from the Base v1 appraisal"* with link to v1.
- Empty state styling per S7 when ALL three non-Base slots are empty.

**CreateScenarioModal**:
- `scenario_label` pre-filled and disabled (slot determines label).
- `scenario_description` textarea (min 10 chars after trim — F2; counter; Save disabled until valid).
- Cancel + Save. Save POST `/api/v1/appraisals/{base_id}/scenarios` → on 201: refresh `/scenarios`, refresh `/comparator`, close modal.
- Modal animation: S6 fade + scale.

**`data-testid`s**: `scenarios-panel`, `scenario-card-{Base|Upside|Downside|Sensitivity}`, `create-scenario-button-{label}`, `create-scenario-modal`, `scenario-description-input`, `create-scenario-submit`.

### §3.3 — ScenarioComparator (NEW)

**File**: `/app/frontend/src/components/appraisal/ScenarioComparator.jsx`
**Mount**: inside ScenariosPanel, full-width below the 2×2 grid.
**Conditional render**: ≥2 scenarios in the group; otherwise show G4 empty-state copy (S7 styling).
**Data**: `GET /api/v1/appraisal-groups/{group_id}/comparator`.

**Render**:
- Skeleton on pending.
- HTML table: rows = metrics, columns = scenarios in returned order (Base → Upside → Downside → Sensitivity).
- Sticky first column (G5).
- Base column: absolute values via `formatMoney` (S5).
- Non-Base columns: absolute + delta vs Base (smaller text below the absolute).

**Metric rows**:
- GDV
- Total Cost
- Profit
- Profit-on-Cost %
- Profit-on-GDV %
- Residual Land Value
- Total Units
- Passes Hurdle (boolean: ✓/✗ icon, no delta cell)

**Delta computation** (F4 — decimal.js):
```js
const delta = new Decimal(scenario.value).minus(new Decimal(base.value));
```

**Favourable direction** (colour mapping):
- GDV, Profit, Profit-on-Cost %, Profit-on-GDV %, RLV, Total Units → positive favourable (green for +Δ).
- Total Cost → negative favourable (green for −Δ).
- Passes Hurdle → boolean, no delta.
- Zero delta → muted.

**Interactivity (S4)**:
- Hover-highlight row + column intersect.
- Sortable columns by metric (Base pinned at column 0).
- New-scenario column slide-in animation (S6 + framer-motion + S10 reduced-motion gate).

**`data-testid`s**: `scenario-comparator-table`, `comparator-row-{metric_key}` (e.g. `comparator-row-gdv`), `comparator-cell-{metric_key}-{scenario_label}`, `comparator-delta-{metric_key}-{scenario_label}`.

### §3.4 — DecisionsTab (NEW or replace placeholder)

**File**: `/app/frontend/src/components/appraisal/DecisionsTab.jsx`
**Mount**: AppraisalPage as top-level tab labelled "Decisions", final tab after Summary.

**R0 task**: confirm whether `DecisionsTab.jsx` already exists as a placeholder. If yes, replace contents wholesale. If no, create new.

**Data**:
- Primary: `GET /api/v1/appraisals/{id}/decisions` → `{items: [...]}`.
- Secondary (per-decision): `GET /api/users/{decision_maker_user_id}` for name resolution. Cache results in component-local `Map`. On 4xx fall back to truncated UUID (8 chars) + clipboard-copy button.

**Layout (Decision C)**: 2/3 + 1/3 inline split.

**Left column (2/3)**: chronological decision list (newest first).

Each card:
- `decision_type` pill colour-coded (G3): Go=green, No_Go=red, Defer=amber, Conditional_Go=blue, Request_Revision=purple, Correction=gray.
- `decision_date` formatted `dd MMM yyyy`.
- `decision_maker_name` + relative timestamp.
- `decision_rationale` (line-clamp-3, "Read more" expander).
- Conditions block (only when type=Conditional_Go) — collapsed by default.
- `key_assumptions_challenged` block (when non-empty) — collapsed by default.
- `supporting_documents` NOT rendered (D — deferred to Track 7).
- Correction-of chip (when type=Correction) → click scrolls to / pulses the corrected decision card.
- Optimistic-UI pending state (S2): `aria-busy=true` + 50% opacity until 201 reconciles. Card append animation (S6).

Empty state: S7 — icon=Gavel.

**Right column (1/3)**: "Log decision" form.

Visibility gate (Decision C): user holds `appraisals.approve` AND `appraisal.is_current=true` AND `appraisal.status === 'Approved'` *(R0-confirm against server)*.

When hidden, right column collapses; list expands to full width.

Form fields (React Hook Form + Zod):
- `decision_type` select (6 enum values).
- `decision_date` picker — `date-fns-tz` Europe/London (E). Default today, max today.
- `decision_rationale` textarea (min 10 trim-checked, counter, Save disabled until valid).
- `conditions` textarea (visible+required only when `decision_type === 'Conditional_Go'`).
- `key_assumptions_challenged` textarea (optional).
- `correction_of_decision_id` select (visible+required only when `decision_type === 'Correction'`; populated from existing decisions on this appraisal).
- `supporting_documents` OMITTED (D).
- Submit + Reset buttons.

**Submit**:
- POST `/api/v1/appraisals/{id}/decisions` with `appraisal_version = appraisal.version_number`.
- On 201: optimistic card reconciles, form resets, fire `nudge-refresh` event (F3).
- On 400: surface error code's message inline above form, preserve values.

**`data-testid`s**: `decisions-tab`, `decision-list`, `decision-row-{decision_id}`, `decision-row-pending` (S2), `log-decision-form`, `decision-type-select`, `decision-date-input`, `decision-rationale-textarea`, `decision-conditions-textarea`, `decision-correction-of-select`, `log-decision-button` (form submit).

### §3.5 — NudgeBanner (NEW)

**File**: `/app/frontend/src/components/appraisal/NudgeBanner.jsx`
**Mount**: top of `ProjectDetail.jsx` (above existing tabs/content). NOT mounted on `AppraisalsList.jsx` (G2). NOT dismissible (G1).

**Data**:
- Primary: `GET /api/v1/projects/{project_id}/nudge` → `{should_show, threshold, distinct_decision_makers, current_appraisal_id, actor_has_decided, message}`.
- For S3 avatar stack: `GET /api/v1/appraisals/{current_appraisal_id}/decisions`, filter to types ∈ {Go, No_Go, Defer}, dedupe by `decision_maker_user_id`.

**Render**:
- Render only when `should_show === true`.
- Amber banner: lucide `AlertCircle` icon (28px) on left.
- Body text: pull from server `message` field directly. Format: *"{N} of {threshold} decision-makers have logged Go/No_Go/Defer on the current appraisal."*
- **S3 avatar stack** to right of body: 24px circular avatars of deciders + ghost slots (dashed circles) for remaining (total = threshold). Tooltip per avatar: name + decision type pill + relative date.
- CTA "Log your decision →" — deep link `/appraisals/{current_appraisal_id}?tab=decisions`.
  - Visible only when `actor_has_decided === false` AND user holds `appraisals.approve`.
  - User lacks `appraisals.approve`: omit CTA, show tooltip "Contact a director to log decisions."
- When `actor_has_decided === true`: replace CTA with confirmation copy — *"Thanks — your decision is recorded. Waiting on {threshold − distinct_decision_makers} more."*
- Listens for `window` event `nudge-refresh` and re-fetches both endpoints (F3).
- Framer Motion enter/exit: 200ms y-axis slide-down/up (S6 + S10).

**`data-testid`s**: `nudge-banner`, `nudge-cta-log-decision`, `nudge-avatar-{user_id}`, `nudge-avatar-empty-{n}`.

### §3.6 — AppraisalPage extensions

**File**: `/app/frontend/src/pages/AppraisalPage.jsx`

**Changes**:
- Add tab `Scenarios` between Finance and Summary, conditional render per §3.2.
- Add tab `Decisions` after Summary.
- Add header action row: `Reopen` + `New version` per Decision B.
- URL param handling: read `?tab=decisions` from `useSearchParams()` on mount; if present and Decisions tab is visible, select it. After mount, scroll log-form into view if user holds `appraisals.approve`. Clear param after handling.
- Existing Reopen CTA messaging update per v6 E.1: button label **"Reopen for editing"** (not just "Reopen").
- Tab switch animation (S6).

### §3.7 — ProjectDetail.jsx + AppraisalsList.jsx

- **ProjectDetail.jsx**: mount `<NudgeBanner projectId={id} />` at top.
- **AppraisalsList.jsx**: NO MOUNT (per G2). Existing list view unchanged in C3.

### §3.8 — Library extensions

**`/app/frontend/src/lib/api.js`** *(corrected path — fork summary said `src/api/api.js`)*:
- `fetchRevisions(appraisalId)` → `GET /api/v1/appraisals/{id}/revisions`
- `createNewVersion(appraisalId, body)` → `POST /api/v1/appraisals/{id}/new-version`
- `fetchProjectRevisions(projectId)` → `GET /api/v1/projects/{id}/revisions`
- `fetchGroupScenarios(groupId)` → `GET /api/v1/appraisal-groups/{id}/scenarios`
- `fetchComparator(groupId)` → `GET /api/v1/appraisal-groups/{id}/comparator`
- `createScenario(baseId, body)` → `POST /api/v1/appraisals/{base_id}/scenarios`
- `fetchDecisions(appraisalId)` → `GET /api/v1/appraisals/{id}/decisions`
- `logDecision(appraisalId, body)` → `POST /api/v1/appraisals/{id}/decisions`
- `fetchNudge(projectId)` → `GET /api/v1/projects/{id}/nudge`

**`/app/frontend/src/lib/appraisalMath.js`**:
- `computeScenarioDelta(base, compare, field)` → `Decimal`
- `formatDelta(d, {sign='auto', currency=true})` → `{text, className}`
- `formatMoney(value, {decimals=0})` → `string` (S5; accepts `Decimal` or number)

**`/app/frontend/src/components/appraisal/atoms.jsx`**:
- Adopt `formatMoney` from `appraisalMath.js` for any KPI tile rendering. Replace any in-place `.toFixed(2)` + manual £.
- **Single source of truth**: if atoms.jsx already exports its own money formatter, REPLACE it with a re-export of `formatMoney` from appraisalMath.js. Do NOT leave two formatters in the codebase.

---

## §4 — Restart plan (R0–R10)

### R0 — Recover DB if bootstrap wiped
Inherit handoff §R0 verbatim. Expected post-recovery: alembic head `0022_appraisal_governance`, 581/581 backend tests.

**Additional R0 pre-flight for C3**:
```bash
# Frontend baseline
cd /app/frontend && yarn install --frozen-lockfile 2>&1 | tail -3
sudo supervisorctl status frontend

# Confirm existing deps
grep '"decimal.js"' package.json    # expect ^10.6.0
grep '"date-fns-tz"' package.json   # expect present (Foundation track)

# Add new dep for SOTA scope
yarn add framer-motion
grep '"framer-motion"' package.json # confirm

# Confirm server gate on /decisions POST (Decision C R0 task)
grep -A 30 "def log_decision" /app/backend/app/services/appraisal_decisions.py
# Look for: status check (Approved required?), is_current check, version match.
# Lock UI form gate per findings.

# Confirm DecisionsTab.jsx placeholder existence (§3.4 R0 task)
ls /app/frontend/src/components/appraisal/DecisionsTab.jsx 2>&1
# If exists: replace contents. If not: create new file.

# Sanity-check C1 retrofit completeness (no stale field names)
grep -rn "appraisal\.version[^_]" /app/frontend/src/    # expect 0 hits
grep -rn "appraisal\.state[^a-z]" /app/frontend/src/   # expect 0 hits
grep -rn "appraisal\.total_gdv\|appraisal\.total_profit" /app/frontend/src/  # expect 0 hits
```

### R1 — Pin Build Pack as primary spec
This document at `/app/docs/SY_Hub_2.3_Checkpoint3_Build_Pack.md` is primary. Read in full. Handoff §1 (Phase E) is superseded — use handoff §0/§3/§R0 as supplementary reference only.

### R2 — Scaffold five new component files + library extensions
Create:
- `src/components/appraisal/RevisionTimeline.jsx`
- `src/components/appraisal/ScenariosPanel.jsx`
- `src/components/appraisal/ScenarioComparator.jsx`
- `src/components/appraisal/DecisionsTab.jsx` (or replace placeholder per §3.4 R0 finding)
- `src/components/appraisal/NudgeBanner.jsx`
- Extend `src/lib/api.js` and `src/lib/appraisalMath.js` per §3.8.
- Update `src/components/appraisal/atoms.jsx` to use `formatMoney`.

**Component guidelines**:
- Each component <250 lines; if larger, split into sub-components in the same dir.
- Shadcn UI primitives from `/app/frontend/src/components/ui/` (Card, Table, Dialog, HoverCard, Textarea, Select, Badge, Tooltip).
- React Hook Form + Zod for both `NewVersionModal` (per Decision B) and `DecisionLogForm` (per §3.4) — match existing auth-form patterns from 1.3.
- `decimal.js` for ALL arithmetic (F4).
- `framer-motion` + `useReducedMotion()` for animations (S6 + S10).
- `Intl.NumberFormat` for ALL money via `formatMoney` (S5).
- Lucide icons for all empty states (S7).

### R3 — Wire components into existing pages
Per §3.6 / §3.7. Tab order: Header → Units → Costs → Finance → Scenarios (conditional) → Summary → Decisions.

### R4 — `/reopen` vs `/new-version` CTA split
Per Decision B. `Reopen` secondary, `New version` primary, both in `AppraisalPage` header action row. Reopen relabelled "Reopen for editing".

### R5 — Decision form gate
Per Decision C — UI gate matches server enforcement exactly. R0 task confirms whether `status==='Approved'` is part of server enforcement.

### R6 — Nudge deep-link handler
Per §3.6 — `?tab=decisions` URL param handling on AppraisalPage mount.

### R7 — Playwright fixture refresh
`testing_agent_v3_fork` creates its own users + fresh fixtures. Tab set is now: Header, Units, Costs, Finance, **Scenarios (conditional)**, Summary, **Decisions**. 7 tabs on Base appraisals; 6 tabs on non-Base appraisals.

E2E scenarios per R9 payload include the SOTA flows (avatar stack render, optimistic UI, hover diff, etc.).

### R8 — Run full backend suite + frontend smoke
```bash
cd /app/backend && set -a && source .env && set +a
export REACT_APP_BACKEND_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d'=' -f2)
pytest --tb=no 2>&1 | grep -E "passed|failed"
# Expect: 581 passed
```

Then `screenshot_tool` against:
- `{REACT_APP_BACKEND_URL}/projects/{any_id}/appraisals/{any_id}` → confirm 7 tabs (or 6 if non-Base), RevisionTimeline mounted in SummaryTab right column.
- `{REACT_APP_BACKEND_URL}/projects/{any_id}` → confirm NudgeBanner mounts on ProjectDetail (top), with avatar stack.
- `{REACT_APP_BACKEND_URL}/projects/{any_id}/appraisals` → confirm NudgeBanner does NOT mount on AppraisalsList (G2).

### R9 — Call `testing_agent_v3_fork`

```json
{
  "original_problem_statement_and_user_choices_inputs": "Prompt 2.3 v6 — Appraisal Governance Checkpoint 3 (Frontend + E2E). Backend at C2 baseline 581/581. Build Pack at /app/docs/SY_Hub_2.3_Checkpoint3_Build_Pack.md is primary spec — supersedes handoff §1. Five UI components: RevisionTimeline, ScenariosPanel, ScenarioComparator, DecisionsTab, NudgeBanner. SOTA scope per §2: skeleton loaders, optimistic UI, avatar stack, comparator interactivity, Intl.NumberFormat, framer-motion, icon empty states, hover diffs, keyboard nav, reduced-motion gating. Five locked decisions (A-E) + sub-decisions (F1-F5, G1-G6).",

  "features_or_bugs_to_test": [
    "POST /api/v1/appraisals/{id}/new-version via NewVersionModal (header New version button) creates new Draft + revision row; user redirects to new appraisal id",
    "Reopen button label is 'Reopen for editing' (not just 'Reopen'); /reopen toggles status=Reopened with no clone",
    "GET /api/v1/appraisals/{id}/revisions powers RevisionTimeline mounted on SummaryTab right column below RLV (vertical orientation)",
    "Hovering a non-v1 timeline node shows delta tooltip with reason + summary + Δ chips (S8)",
    "Click any timeline node navigates to that appraisal; read-only when status in {Superseded, Withdrawn, Rejected} (G6)",
    "POST /api/v1/appraisals/{base_id}/scenarios from ScenariosPanel modal creates Upside/Downside/Sensitivity from Base v1 only",
    "Non-Base-v1 anchor (e.g. Base v3): ScenariosPanel CTAs hidden, explanatory text shown with link to v1 (F1)",
    "GET /api/v1/appraisal-groups/{group_id}/comparator powers ScenarioComparator with sticky first column, hover-highlight, sortable headers (S4)",
    "Comparator deltas computed via decimal.js (no float drift on £10M+ values; F4)",
    "Comparator empty state when only Base scenario exists (G4 copy)",
    "POST /api/v1/appraisals/{id}/decisions via DecisionsTab inline form (right column 1/3 width)",
    "Optimistic UI: pending decision card appears immediately on submit, reconciles on 201, removes on 400 (S2)",
    "Decision form hidden when appraisal.is_current=false OR status != Approved per server enforcement",
    "Decision-date picker uses date-fns-tz Europe/London — no FUTURE_DATED_DECISION 400s for users in non-UK timezones (Decision E)",
    "supporting_documents field omitted from form (Decision D)",
    "GET /api/v1/projects/{id}/nudge powers NudgeBanner on ProjectDetail.jsx ONLY (NOT AppraisalsList per G2)",
    "NudgeBanner shows avatar stack of deciders + ghost slots for remaining (S3)",
    "NudgeBanner is NOT dismissible (G1)",
    "NudgeBanner CTA hidden when user lacks appraisals.approve (tooltip 'Contact a director to log decisions')",
    "NudgeBanner CTA copy swap when actor_has_decided=true",
    "Banner deep-link to /appraisals/{id}?tab=decisions selects Decisions tab and scrolls log-form into view",
    "Logging a decision fires nudge-refresh event; banner re-fetches and updates avatar stack (F3)",
    "Skeleton loaders render for all async fetches; no 'Loading…' text (S1)",
    "Empty states use Lucide icons + concise copy (S7)",
    "Money rendered via Intl.NumberFormat en-GB (£ prefix, comma grouping, no decimals on whole pounds) (S5)",
    "Framer Motion: tab switches, modal open/close, banner enter/exit, decision card append, comparator new column (S6)",
    "Keyboard nav: j/k walks revision timeline; Esc closes modals; Cmd+Enter submits forms (S9)",
    "Reduced-motion preference disables all framer-motion animations and number-rolling (S10)"
  ],

  "files_of_reference": [
    "Build Pack: /app/docs/SY_Hub_2.3_Checkpoint3_Build_Pack.md (PRIMARY SPEC)",
    "Handoff (supplementary): /app/docs/SY_Hub_2.3_Checkpoint3_Handoff.md (§0, §3, §R0 only)",
    "Frontend new: src/components/appraisal/{RevisionTimeline,ScenariosPanel,ScenarioComparator,DecisionsTab,NudgeBanner}.jsx",
    "Frontend extended: src/pages/{AppraisalPage,ProjectDetail}.jsx",
    "Frontend extended: src/lib/api.js (NOT src/api/api.js — fork summary error), src/lib/appraisalMath.js",
    "Frontend extended: src/components/appraisal/atoms.jsx (formatMoney adoption)",
    "Backend reference: app/routers/appraisal_governance.py, app/services/appraisal_decisions.py"
  ],

  "required_credentials": [
    "/app/memory/test_credentials.md — test-admin, test-director, test-pm, test-readonly (4 accounts; fork summary listed only 3)"
  ],

  "testing_type": "both",

  "agent_to_agent_context_note": "Backend is 581/581 green; C3 is frontend + E2E. NO backend changes expected. Build Pack §1 supersedes handoff §1 — five locked decisions (A-E) + ten SOTA enhancements (S1-S10). SOTA scope is in scope, not optional.",

  "prev_test_files_and_folder": "/app/test_reports/iteration_9.json (last C1-era pre-C2 frontend run; stale — pre-tab-additions and pre-SOTA)",

  "mocked_api": { "has_mocked_apis": false, "mocked_apis_list": [] },

  "other_misc_info": "decimal.js MUST be used for all arithmetic. Intl.NumberFormat MUST be used for all money rendering. framer-motion is a NEW dependency added in C3. NudgeBanner is NOT dismissible (G1) and mounts only on ProjectDetail.jsx (G2). Avatar stack data is assembled client-side from /decisions endpoint. Decision form gate must match server enforcement exactly — verified via /app/backend/app/services/appraisal_decisions.py read in R0."
}
```

### R10 — Self-report and STOP

```
## Checkpoint 3 self-report

**Components landed**
- RevisionTimeline.jsx (___ lines)
- ScenariosPanel.jsx (___ lines)
- ScenarioComparator.jsx (___ lines)
- DecisionsTab.jsx (___ lines; replaced placeholder / created new — circle one)
- NudgeBanner.jsx (___ lines)
- AppraisalPage.jsx extended: +2 tabs, +Reopen relabel, +New version primary button + modal, +URL param handler
- ProjectDetail.jsx: NudgeBanner mounted (NOT mounted on AppraisalsList per G2)
- src/lib/api.js: +9 endpoint wrappers
- src/lib/appraisalMath.js: +computeScenarioDelta, +formatDelta, +formatMoney
- atoms.jsx: formatMoney adopted

**SOTA delivered**:
- S1 skeleton loaders ✓ / ✗
- S2 optimistic UI on /decisions ✓ / ✗
- S3 NudgeBanner avatar stack ✓ / ✗
- S4 comparator interactivity (hover, sortable, animation) ✓ / ✗
- S5 Intl.NumberFormat money rendering ✓ / ✗
- S6 framer-motion micro-interactions ✓ / ✗
- S7 icon empty states ✓ / ✗
- S8 RevisionTimeline hover diff ✓ / ✗
- S9 keyboard nav (j/k, Esc, Cmd+Enter) ✓ / ✗
- S10 reduced-motion gating ✓ / ✗

**Backend tests**: 581 passed (unchanged from C2 baseline).

**Frontend tests** (testing_agent_v3_fork): ___ scenarios passed / ___ failed. Iteration: /app/test_reports/iteration_{N}.json.

**New deps**: framer-motion (added).

**Server-gate confirmation** (R0 finding): /decisions POST enforces is_current ___ + status ___ ___. UI form gate set to match.

**Issues encountered** (if any): ___

**Deviations from Build Pack** (if any): ___

**Ready for user acceptance review + merge of prompt-2-3-checkpoint-1 → main.**
```

---

## §5 — Gotchas (inherited from handoff §3)

Inherit handoff §3.1–§3.9 verbatim except:

- **§3.1 supersession**: Decision E now uses `date-fns-tz` Europe/London for the decision-date picker. The handoff's "don't bother with London-aware client-side" advice is dropped. One-line `formatInTimeZone` helper, no occasional 400 round-trips.
- **§3.5 reaffirmed**: F1 (Base v1 anchor only). Detection logic in §3.2.
- **§3.9 ongoing**: bootstrap chicken-and-egg — known recurrence count 4. Mark the moment if it fires in C3 for a 5th data point before deciding on the P0 fix approach.

---

## §6 — File paths quick-ref

| Concern | Path |
|---|---|
| Build Pack (this doc) | `/app/docs/SY_Hub_2.3_Checkpoint3_Build_Pack.md` |
| Handoff (supplementary — §0, §3, §R0 only) | `/app/docs/SY_Hub_2.3_Checkpoint3_Handoff.md` |
| C2 handoff (historical) | `/app/docs/SY_Hub_2.3_Checkpoint2_Handoff.md` |
| New components | `/app/frontend/src/components/appraisal/{RevisionTimeline,ScenariosPanel,ScenarioComparator,DecisionsTab,NudgeBanner}.jsx` |
| Extended pages | `/app/frontend/src/pages/{AppraisalPage,ProjectDetail}.jsx` |
| Library extensions | `/app/frontend/src/lib/{api,appraisalMath}.js` *(NOT `src/api/api.js` — fork summary error)* |
| Existing tab modules (style reference) | `/app/frontend/src/components/appraisal/{atoms,HeaderTab,UnitsTab,CostsTab,FinanceTab,SummaryTab}.jsx` |
| Backend governance router (read-only ref) | `/app/backend/app/routers/appraisal_governance.py` |
| Backend governance services (behavioural ref) | `/app/backend/app/services/{appraisal_revisions,appraisal_scenarios,appraisal_decisions}.py` |
| Test credentials (4 accounts, not 3) | `/app/memory/test_credentials.md` |
| CHANGELOG (append C3 entry) | `/app/CHANGELOG.md` |
| PRD (append C3 entry) | `/app/memory/PRD.md` |
| Test report archive | `/app/test_reports/iteration_{N}.json` (next N ≥ 10) |

---

## §7 — Out of scope (deferred)

- `supporting_documents` picker (Decision D — Track 7 document pack).
- Decision-document PDF auto-generation (Future_Tasks).
- E-signature integration (Future_Tasks).
- Decision proxy / log-on-behalf-of (spec forbids in 2.3).
- `/api/users/{id}` global caching layer beyond per-component Map (polish-pass).
- Comparator full-report `/projects/{id}/scenario-comparator` route (polish-pass).
- Long-TTL nudge dismissal (G1 — banner is NOT dismissible at all).
- IRR / ROCE on appraisals (Future_Tasks).
- Optimistic concurrency control on appraisal edits (Future_Tasks).
- Backend changes of any kind — C3 is pure frontend.

---

## §8 — Estimated context budget

180–240k tokens for C3 in fresh session. SOTA work adds ~30k vs handoff baseline.

Burn breakdown:
- Read Build Pack + handoff §0/§3/§R0: ~10k.
- Existing tab modules (atoms → SummaryTab) for style + testid conventions: ~15k.
- New deps install + framer-motion patterns review: ~5k.
- React Hook Form + Zod schemas (NewVersionModal + DecisionLogForm): ~7k.
- decimal.js + Intl.NumberFormat usage review: ~3k.
- testing_agent_v3_fork iteration cycle: ~25–40k (E2E commonly finds gating mismatches).
- CHANGELOG + PRD updates: ~3k.
- Bootstrap recovery padding: +5–10k.

**If 30k tokens remain mid-execution**: halt cleanly, prep R11 follow-up handoff. Better land clean than rush.

---

**End of Build Pack.** The next agent: read this in full before writing any code. The v6 Phase E and the C3 handoff §1 are superseded — they are reference only.
