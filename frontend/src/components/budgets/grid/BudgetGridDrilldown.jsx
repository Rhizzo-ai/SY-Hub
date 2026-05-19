/**
 * BudgetGridDrilldown — Chat 23 R4.5.
 *
 * Rendered by TanStack Table's expanded-row sub-component slot. Mounts
 * the 4-item breakdown editor plus the 3 transaction sections (POs
 * stub, Variations stub, Bills LIVE).
 *
 * Receives `line` directly (not the TanStack row wrapper) so it can be
 * unit-tested without TanStack's row context.
 */
import { LineItemsBreakdown } from './PerLineTransactionDrilldown/LineItemsBreakdown';
import { POsSectionStub } from './PerLineTransactionDrilldown/POsSectionStub';
import { VariationsSectionStub } from './PerLineTransactionDrilldown/VariationsSectionStub';
import { BillsSection } from './PerLineTransactionDrilldown/BillsSection';

export function BudgetGridDrilldown({ line, budget, projectId, canEdit }) {
  return (
    <div
      className="space-y-4 bg-slate-50 px-6 py-4"
      data-testid={`bg2-drilldown-${line.id}`}
    >
      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Breakdown (4-type)
        </h4>
        <LineItemsBreakdown
          line={line}
          budget={budget}
          canEdit={canEdit}
        />
      </section>

      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Transactions
        </h4>
        <div className="grid gap-3">
          <div>
            <h5 className="mb-1 text-xs font-medium text-slate-600">Purchase Orders</h5>
            <POsSectionStub />
          </div>
          <div>
            <h5 className="mb-1 text-xs font-medium text-slate-600">Variations</h5>
            <VariationsSectionStub />
          </div>
          <div>
            <h5 className="mb-1 text-xs font-medium text-slate-600">Bills</h5>
            <BillsSection budgetLineId={line.id} projectId={projectId} />
          </div>
        </div>
      </section>
    </div>
  );
}
