/**
 * BudgetGridMobileReadOnly — Chat 23 §R8.1.
 *
 * Mobile-only budget surface. Replaces the R3 stub. Treatment per
 * Build Pack A locked decisions:
 *
 *   1. Header tiles (vertically stacked, full width each) — reuses
 *      `BudgetGridHeaderTiles` with `stacked` prop so the sensitive
 *      gating contract stays in one place.
 *   2. Search input — the ONLY filter on mobile (no chips, no
 *      "actuals/variance" toggles, no presets dropdown).
 *   3. Stripped-down list — each line renders as a card: cost code
 *      label + description (truncated) + current budget + variance
 *      badge. Tapping the card opens `MobileLineDetailDrawer` which
 *      surfaces the full read-only line + editable Notes.
 *
 * Explicit NON-features (caught by the test suite):
 *   - NO bulk actions bar (no checkboxes, no Export/Delete/Clear).
 *   - NO BudgetGridToolbar (no column visibility menu, no presets
 *     dropdown, no "Manage views" / "Save view" affordance).
 *   - NO drilldown row-expand (transactions surface in the drawer
 *     only).
 *
 * Sensitive-field gating: the card shows `current_budget` only (always
 * returned by the API). Sensitive figures (actuals, FFC, FTC, variance)
 * are shown in the drawer, gated there per the same rules.
 */
import { useMemo, useState } from 'react';
import { useCostCodes, buildCostCodeMap } from '@/hooks/costCodes';
import { useAuth } from '@/context/AuthContext';
import { formatMoney } from '@/lib/format';
import { VarianceBadge } from '../VarianceBadge';
import { BudgetGridHeaderTiles } from './BudgetGridHeaderTiles';
import { MobileLineDetailDrawer } from './MobileLineDetailDrawer';

export function BudgetGridMobileReadOnly({ budget, projectId }) {
  const { me } = useAuth();
  const canViewSensitive = !!me?.permissions?.includes('budgets.view_sensitive');

  const { data: costCodes = [] } = useCostCodes(projectId);
  const costCodeMap = useMemo(() => buildCostCodeMap(costCodes), [costCodes]);

  const [search, setSearch] = useState('');
  const [openLineId, setOpenLineId] = useState(null);

  const filtered = useMemo(() => {
    const lines = budget?.lines ?? [];
    if (!search.trim()) return lines;
    const q = search.trim().toLowerCase();
    return lines.filter((l) => {
      const code = (costCodeMap.get(l.cost_code_id)?.code ?? '').toLowerCase();
      const desc = (l.line_description ?? '').toLowerCase();
      return code.includes(q) || desc.includes(q);
    });
  }, [budget?.lines, search, costCodeMap]);

  return (
    <div className="space-y-3" data-testid="bg2-mobile">
      <BudgetGridHeaderTiles
        budget={budget}
        canViewSensitive={canViewSensitive}
        stacked
      />

      <input
        type="search"
        placeholder="Search cost code or description…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
        data-testid="bg2-mobile-search"
      />

      <ul
        className="divide-y divide-slate-200 rounded border border-slate-200 bg-white"
        data-testid="bg2-mobile-list"
      >
        {filtered.length === 0 ? (
          <li
            className="px-3 py-6 text-center text-xs text-slate-500"
            data-testid="bg2-mobile-empty"
          >
            {search.trim()
              ? 'No matches — try a different search term.'
              : 'This budget has no lines yet.'}
          </li>
        ) : (
          filtered.map((line) => {
            const code = costCodeMap.get(line.cost_code_id)?.code ?? '—';
            return (
              <li key={line.id}>
                <button
                  type="button"
                  onClick={() => setOpenLineId(line.id)}
                  className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left hover:bg-slate-50 active:bg-slate-100"
                  data-testid={`bg2-mobile-line-${line.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div
                      className="font-mono text-sm font-medium text-slate-900"
                      data-testid={`bg2-mobile-line-${line.id}-code`}
                    >
                      {code}
                    </div>
                    <div className="truncate text-xs text-slate-500">
                      {line.line_description ?? '—'}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <div
                      className="font-mono text-sm tabular-nums text-slate-900"
                      data-testid={`bg2-mobile-line-${line.id}-budget`}
                    >
                      {formatMoney(line.current_budget)}
                    </div>
                    <VarianceBadge
                      status={line.variance_status}
                      value={line.variance_value}
                      pct={line.variance_pct}
                    />
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>

      <MobileLineDetailDrawer
        lineId={openLineId}
        budget={budget}
        projectId={projectId}
        onClose={() => setOpenLineId(null)}
      />
    </div>
  );
}
