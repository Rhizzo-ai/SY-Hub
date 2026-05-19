/**
 * MobileLineDetailDrawer — Chat 23 §R8.2.
 *
 * Tapping a card row in BudgetGridMobileReadOnly opens this drawer.
 * Renders the full line as a stacked read-only detail sheet with ONE
 * editable field: Notes (via the existing `NotesCell` component reused
 * verbatim — locked decision per §R8 operator follow-up).
 *
 * Bottom-anchored Sheet on mobile, full viewport width. The transaction
 * sub-sections (POs stub, Variations stub, Bills LIVE) are rendered via
 * the existing `BudgetGridDrilldown` so a Site Manager can check what's
 * been billed without leaving mobile.
 *
 * Constraints (Build Pack A locked decisions):
 *   - All line fields except Notes are READ-ONLY (no Description edit,
 *     no Original/Current budget edit, no Forecast edit, no FTC method
 *     pick — those routes belong to LineDrawer on desktop only).
 *   - NO bulk actions in this drawer.
 *   - Notes is editable: `canEdit = budgets.edit perm` (no isDesktop
 *     gate). NotesCell already debounces + optimistic-updates; mobile
 *     reuses that contract.
 */
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet';
import { formatMoney, formatPercent } from '@/lib/format';
import { useAuth } from '@/context/AuthContext';
import { useCostCodes, buildCostCodeMap } from '@/hooks/costCodes';
import { useMemo } from 'react';
import { VarianceBadge } from '../VarianceBadge';
import { NotesCell } from './NotesCell';
import { BudgetGridDrilldown } from './BudgetGridDrilldown';

function Row({ label, value, testid, mono = true }) {
  return (
    <div className="flex justify-between border-b border-slate-100 py-2 text-sm">
      <span className="text-slate-500">{label}</span>
      <span
        className={mono ? 'font-mono tabular-nums text-slate-900' : 'text-slate-900'}
        data-testid={testid}
      >
        {value}
      </span>
    </div>
  );
}

export function MobileLineDetailDrawer({
  lineId, budget, projectId, onClose,
}) {
  const { me } = useAuth();
  // Mobile Notes are editable per the §R8.2 operator follow-up:
  // do NOT apply the desktop-only gate. The permission check still
  // applies (read-only users can't edit on either platform).
  const canEditNotes = !!me?.permissions?.includes('budgets.edit');
  const canViewSensitive = !!me?.permissions?.includes('budgets.view_sensitive');

  const { data: costCodes = [] } = useCostCodes(projectId);
  const costCodeMap = useMemo(() => buildCostCodeMap(costCodes), [costCodes]);

  const line = useMemo(
    () => (budget?.lines ?? []).find((l) => l.id === lineId),
    [budget, lineId],
  );

  const open = !!lineId;
  const code = line ? costCodeMap.get(line.cost_code_id)?.code ?? '—' : '';
  const codeName = line ? costCodeMap.get(line.cost_code_id)?.name : null;

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose?.(); }}>
      <SheetContent
        side="bottom"
        // Full-viewport on mobile so it doesn't feel like a popover.
        className="h-[92vh] w-full max-w-full overflow-y-auto rounded-t-lg p-0"
        data-testid="bg2-mobile-drawer"
      >
        <SheetHeader className="border-b border-slate-200 bg-slate-50 px-4 py-3 text-left">
          <SheetTitle className="font-mono text-base" data-testid="bg2-mobile-drawer-code">
            {code}
          </SheetTitle>
          {codeName && (
            <SheetDescription className="text-xs text-slate-600">
              {codeName}
            </SheetDescription>
          )}
        </SheetHeader>

        {line ? (
          <div className="space-y-4 px-4 py-3">
            <section data-testid="bg2-mobile-drawer-fields">
              <div className="text-sm font-medium text-slate-900">
                {line.line_description ?? '—'}
              </div>
              <div className="mt-3">
                <Row
                  label="Original budget"
                  value={formatMoney(line.original_budget)}
                  testid="bg2-mobile-field-original"
                />
                <Row
                  label="Current budget"
                  value={formatMoney(line.current_budget)}
                  testid="bg2-mobile-field-current"
                />
                <Row
                  label="Approved changes"
                  value={formatMoney(line.approved_changes ?? 0)}
                  testid="bg2-mobile-field-approved"
                />
                {canViewSensitive && (
                  <>
                    <Row
                      label="Actual spent"
                      value={formatMoney(line.actuals_to_date)}
                      testid="bg2-mobile-field-actuals"
                    />
                    <Row
                      label="Committed"
                      value={formatMoney(line.committed_value ?? line.committed_not_invoiced ?? 0)}
                      testid="bg2-mobile-field-committed"
                    />
                    <Row
                      label="Forecast cost (FFC)"
                      value={formatMoney(line.forecast_final_cost)}
                      testid="bg2-mobile-field-ffc"
                    />
                    <Row
                      label="Cost to complete"
                      value={formatMoney(line.forecast_to_complete)}
                      testid="bg2-mobile-field-ftc"
                    />
                  </>
                )}
                <div className="flex items-center justify-between border-b border-slate-100 py-2 text-sm">
                  <span className="text-slate-500">Variance</span>
                  <span data-testid="bg2-mobile-field-variance">
                    <VarianceBadge
                      status={line.variance_status}
                      value={line.variance_value}
                      pct={line.variance_pct}
                    />
                  </span>
                </div>
                {line.variance_pct != null && (
                  <Row
                    label="Variance %"
                    value={formatPercent(line.variance_pct)}
                    testid="bg2-mobile-field-variance-pct"
                  />
                )}
              </div>
            </section>

            <section data-testid="bg2-mobile-drawer-notes">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Notes
              </h4>
              <NotesCell
                value={line.notes}
                lineId={line.id}
                budgetId={budget.id}
                canEdit={canEditNotes}
              />
            </section>

            <section data-testid="bg2-mobile-drawer-drilldown">
              <BudgetGridDrilldown
                line={line}
                budget={budget}
                projectId={projectId}
                canEdit={false}
                /* canEdit=false: line-item edits go through the desktop
                 * LineItemsBreakdown's edit form. Mobile users can still
                 * SEE breakdown rows + live Bills, just not mutate the
                 * 4-type breakdown. */
              />
            </section>
          </div>
        ) : (
          <div className="px-4 py-6 text-sm text-slate-500">
            Line not found.
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
