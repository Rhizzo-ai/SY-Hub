# Chat 23 closing notes — scoped deviations from Build Pack v-final

Running log of intentional deviations from `docs/Chat_23_Build_Pack_v_final.md`
during execution. Each entry: scope, what changed, why, operator sign-off.

## R3.9b — provisional allocation source field
- **Build Pack wording:** allocation pulls from "sale_price / revenue".
- **As implemented:** allocation pulls from `appraisal.gdv_total` (the
  only column carrying aggregate development revenue; per-unit prices
  live on `appraisal_units.price_per_unit`).
- **Why:** there is no literal `sale_price` or `revenue` column on
  `appraisals`; `gdv_total` IS the aggregate the spec described.
- **Operator confirm:** R6 prompt — "gdv_total is the total expected
  sale value, you're correct."
- **Scope:** R3.9b only.

## R5.1 — NotesCell input type
- **Build Pack wording:** §R5.1 specifies `type="text"` for the inline
  Notes input.
- **As implemented:** `<Textarea>` (multi-line) with `Shift+Enter` for
  newline + `Enter` to commit. `maxLength=500` enforced.
- **Why:** Operator-approved deliberate improvement. Notes routinely
  span 2-4 lines on real budgets; a single-line `<input>` would force
  users to either dump everything as a run-on sentence or switch to
  the LineDrawer for any multi-line note, defeating the inline-edit
  intent.
- **Operator confirm:** R6 prompt — "deliberate improvement over Build
  Pack §R5.1 which specified type='text'. Log... as a scoped
  deviation, not a defect."
- **Scope:** R5 only. The R8 mobile-card-list NotesCell will reuse
  this same textarea-based component.

## R6 — autosave debounce
- **Build Pack wording:** §R6.2 specifies 500ms autosave debounce.
- **As implemented:** 500ms (matches Build Pack as-written).
- **Note for next agent:** R5 NotesCell already uses 600ms for its own
  PATCH. Different debounces are intentional — the 600ms on Notes
  matches the proven Notes-debounce pattern from earlier surfaces;
  the 500ms on autosaved column-layout state is fine to be snappier
  because nobody types into the autosaved payload.
