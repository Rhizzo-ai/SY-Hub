/**
 * BillsPlaceholder — R6.
 *
 * Static, fetch-free placeholder. Bills belong to a later track
 * (Documents & Compliance) and are intentionally NOT wired in R6 —
 * the per-line expandable row owns POs + Receipts now; Bills surface
 * lands when the supplier-invoice domain ships.
 */
export function BillsPlaceholder() {
  return (
    <div
      className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500"
      data-testid="bg2-bills-placeholder"
    >
      Bills land in a later track (Documents &amp; Compliance).
    </div>
  );
}

export default BillsPlaceholder;
