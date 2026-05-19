/**
 * BudgetGridToolbar — Chat 23 R3.7.
 *
 * Five filter controls, left-to-right:
 *   1. Full-text search (debounced 200ms; filter applied directly via
 *      onFiltersChange — debounce handled inside this component so the
 *      parent useMemo doesn't re-run on every keystroke).
 *   2. Cost-code category multi-select.
 *   3. Variance band chips (All / Green / Amber / Red).
 *   4. "Only with actuals" chip.
 *   5. "Only with variance" chip.
 *
 * Rightmost: ViewPresetsDropdown + ColumnVisibilityMenu.
 */
import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { ViewPresetsDropdown } from './ViewPresetsDropdown';
import { ColumnVisibilityMenu } from './ColumnVisibilityMenu';
import { CATEGORY_BY_PREFIX } from '@/lib/budgetCategoryGroup';

const BANDS = ['All', 'Green', 'Amber', 'Red'];

const BAND_CLASS = {
  All:   'bg-slate-100 text-slate-700',
  Green: 'bg-emerald-50 text-emerald-800',
  Amber: 'bg-amber-50 text-amber-800',
  Red:   'bg-rose-50 text-rose-800',
};

export function BudgetGridToolbar({
  filters, onFiltersChange, table,
  canViewSensitive, onApplyPreset,
  savedViews, onApplyView, onOpenSaveView, onOpenManageViews,
}) {
  // Debounce only the search box (200ms). Other filters apply
  // immediately because they're click-driven, not type-driven.
  const [searchDraft, setSearchDraft] = useState(filters.search ?? '');
  const t = useRef(null);
  useEffect(() => {
    clearTimeout(t.current);
    t.current = setTimeout(() => {
      if (searchDraft !== (filters.search ?? '')) {
        onFiltersChange({ ...filters, search: searchDraft });
      }
    }, 200);
    return () => clearTimeout(t.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  function toggleCategory(prefix) {
    const next = new Set(filters.categories ?? []);
    if (next.has(prefix)) next.delete(prefix);
    else next.add(prefix);
    onFiltersChange({ ...filters, categories: Array.from(next) });
  }

  function selectBand(band) {
    onFiltersChange({
      ...filters,
      varianceBand: band === 'All' ? null : band,
    });
  }

  const currentBand = filters.varianceBand ?? 'All';

  return (
    <div
      className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
      data-testid="bg2-toolbar"
    >
      {/* Search */}
      <div className="relative">
        <Search
          size={14}
          className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
        />
        <Input
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          placeholder="Search cost code or description"
          className="h-8 w-64 pl-7 text-sm"
          data-testid="bg2-filter-search"
        />
      </div>

      {/* Categories */}
      <div className="flex flex-wrap items-center gap-1">
        {Object.entries(CATEGORY_BY_PREFIX).map(([prefix, { label }]) => {
          const active = (filters.categories ?? []).includes(prefix);
          return (
            <button
              key={prefix}
              type="button"
              onClick={() => toggleCategory(prefix)}
              className={`rounded-full px-2 py-0.5 text-xs font-medium transition-colors ${
                active
                  ? 'bg-sy-teal text-white'
                  : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100'
              }`}
              data-testid={`bg2-filter-cat-${prefix}`}
              title={label}
            >
              {prefix}
            </button>
          );
        })}
      </div>

      {/* Variance band chips */}
      <div className="flex items-center gap-1">
        {BANDS.map((band) => (
          <button
            key={band}
            type="button"
            onClick={() => selectBand(band)}
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              currentBand === band
                ? `${BAND_CLASS[band]} ring-2 ring-offset-1 ring-slate-300`
                : `${BAND_CLASS[band]} opacity-60 hover:opacity-100`
            }`}
            data-testid={`bg2-filter-band-${band.toLowerCase()}`}
          >
            {band}
          </button>
        ))}
      </div>

      {/* Boolean filters */}
      <label
        className="inline-flex items-center gap-1.5 text-xs text-slate-600"
        data-testid="bg2-filter-actuals"
      >
        <Checkbox
          checked={!!filters.onlyWithActuals}
          onCheckedChange={(v) =>
            onFiltersChange({ ...filters, onlyWithActuals: Boolean(v) })
          }
        />
        Only with actuals
      </label>
      <label
        className="inline-flex items-center gap-1.5 text-xs text-slate-600"
        data-testid="bg2-filter-variance"
      >
        <Checkbox
          checked={!!filters.onlyWithVariance}
          onCheckedChange={(v) =>
            onFiltersChange({ ...filters, onlyWithVariance: Boolean(v) })
          }
        />
        Only with variance
      </label>

      <div className="ml-auto flex items-center gap-2">
        <ViewPresetsDropdown
          canViewSensitive={canViewSensitive}
          onApplyPreset={onApplyPreset}
          savedViews={savedViews}
          onApplyView={onApplyView}
          onOpenSaveView={onOpenSaveView}
          onOpenManageViews={onOpenManageViews}
        />
        {table && <ColumnVisibilityMenu table={table} />}
      </div>
    </div>
  );
}
