/**
 * BudgetLineExpandedRow — R6 (Buildertrend-style inline expandable row).
 *
 * Rendered directly under a line in the budget grid when that line's
 * id appears in the URL `?expanded=` list. Owns the per-line breakdown
 * editor (kept from R4.5) plus the three transaction sections:
 *
 *   • Purchase Orders  — LIVE, lazy-fetch via /budget-lines/{id}/purchase-orders
 *   • Receipts         — LIVE, nested under each issued PO (lazy)
 *   • Bills            — STATIC placeholder (later track)
 *
 * Mounting is gated by the parent grid: when the line collapses, the
 * whole component unmounts, all React-Query subscriptions detach, and
 * any in-flight requests abort via their AbortControllers.
 *
 * Accessibility:
 *   - The collapse/expand affordance lives on the row above (the grid
 *     manages `aria-expanded` + `aria-controls`); this panel ships its
 *     own `role="region"` + `aria-labelledby` for screen-readers.
 */
import { LineItemsBreakdown } from './LineItemsBreakdown';
import { POsSection } from './POsSection';
import { BillsPlaceholder } from './BillsPlaceholder';

export function BudgetLineExpandedRow({
  line, budget, projectId, canEdit,
}) {
  const labelId = `bg2-expanded-label-${line.id}`;
  return (
    <div
      role="region"
      aria-labelledby={labelId}
      className="space-y-4 bg-slate-50 px-4 py-4 md:px-6"
      data-testid={`bg2-expanded-${line.id}`}
    >
      <h3
        id={labelId}
        className="sr-only"
      >
        Line {line.line_description ?? line.id} — purchase orders, receipts, bills
      </h3>

      <section data-testid={`bg2-expanded-breakdown-${line.id}`}>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Breakdown (4-type)
        </h4>
        <LineItemsBreakdown
          line={line}
          budget={budget}
          canEdit={canEdit}
        />
      </section>

      <section data-testid={`bg2-expanded-pos-${line.id}`}>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Purchase Orders
        </h4>
        <POsSection lineId={line.id} projectId={projectId} />
      </section>

      <section data-testid={`bg2-expanded-bills-${line.id}`}>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Bills
        </h4>
        <BillsPlaceholder />
      </section>
    </div>
  );
}

export default BudgetLineExpandedRow;
