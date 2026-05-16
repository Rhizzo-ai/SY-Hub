/**
 * ActualsList page (Chat 19B §R2.3).
 *
 * Per-project list of actuals. TanStack Table; status / source / search
 * filters; create button (Sheet on desktop, route on mobile); mobile
 * read-only banner (Q2); sensitive-field banner (D26).
 */
import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { useProjectActuals } from '@/hooks/actuals';
import { useProjectBudgets, useBudget } from '@/hooks/budgets';
import {
  canViewActuals, canCreateActual, canViewSensitive,
} from '@/lib/actualCapability';
import { ActualsTable } from '@/components/actuals/ActualsTable';
import { ActualsFilters } from '@/components/actuals/ActualsFilters';
import { CreateActualSheet } from '@/components/actuals/CreateActualSheet';
import { ActualsSensitiveBanner } from '@/components/actuals/ActualsSensitiveBanner';
import { Button } from '@/components/ui/button';

export default function ActualsList() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const isDesktop = useIsDesktop();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [filters, setFilters] = useState({
    status: undefined,
    source_type: undefined,
    search: '',
  });

  const canView = canViewActuals(me);
  const canCreate = canCreateActual(me, isDesktop);
  const showSensitiveBanner = canView && !canViewSensitive(me);

  // Server-side filtering for status + source_type. Search is client-side
  // (debounced) — backend has no full-text search endpoint yet, B31 territory.
  const apiParams = useMemo(() => {
    const p = { limit: 200, offset: 0 };
    if (filters.status && filters.status !== 'All') p.status = filters.status;
    if (filters.source_type) p.source_type = filters.source_type;
    return p;
  }, [filters.status, filters.source_type]);

  const { data, isLoading, isError, error } = useProjectActuals(
    projectId,
    { params: apiParams, enabled: canView },
  );

  // Best-effort enrichment: resolve budget_line_id → line_description.
  // The list endpoint returns SUMMARY objects with no `lines` field; we
  // additionally fetch the detail of the project's current (Active/Locked)
  // budget to populate the lookup. If no current budget exists, the column
  // falls back to truncated-UUID display.
  const { data: budgetsListData } = useProjectBudgets(projectId, {
    enabled: canView,
  });
  const currentBudgetId = useMemo(() => {
    const items = budgetsListData?.items ?? [];
    const found =
      items.find(
        (b) => b.is_current && (b.status === 'Active' || b.status === 'Locked'),
      ) ||
      items.find((b) => b.status === 'Active') ||
      items.find((b) => b.status === 'Locked');
    return found?.id;
  }, [budgetsListData]);
  const { data: currentBudgetDetail } = useBudget(currentBudgetId, {
    enabled: canView && !!currentBudgetId,
  });
  const lineLookup = useMemo(() => {
    const map = new Map();
    for (const line of currentBudgetDetail?.lines ?? []) {
      map.set(line.id, line.line_description ?? '(unnamed line)');
    }
    return map;
  }, [currentBudgetDetail]);

  // Client-side search filter — applied AFTER server returns
  const filteredItems = useMemo(() => {
    const items = data?.items ?? [];
    const q = filters.search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (a) =>
        (a.description || '').toLowerCase().includes(q) ||
        (a.supplier_name_snapshot || '').toLowerCase().includes(q),
    );
  }, [data, filters.search]);

  if (!canView) {
    return (
      <div
        data-testid="actuals-list-no-perm"
        className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600"
      >
        You don't have access to actuals. Contact a director if you need this.
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 md:p-6" data-testid="actuals-list-page">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-heading text-2xl text-slate-900">Actuals</h1>
        {canCreate && (
          <Button
            data-testid="actuals-create-button"
            onClick={() => {
              if (isDesktop) setSheetOpen(true);
              else navigate(`/projects/${projectId}/actuals/new`);
            }}
            className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
          >
            + Create actual
          </Button>
        )}
      </div>

      {showSensitiveBanner && <ActualsSensitiveBanner />}

      {!isDesktop && (
        <div
          data-testid="actuals-list-mobile-banner"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          Actions like Post, Mark Paid, Void are desktop-only. Tap an actual to view detail.
        </div>
      )}

      <ActualsFilters value={filters} onChange={setFilters} />

      {isLoading ? (
        <div
          data-testid="actuals-list-loading"
          className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
        >
          Loading actuals…
        </div>
      ) : isError ? (
        <div
          data-testid="actuals-list-error"
          className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
        >
          Failed to load actuals: {error?.message ?? 'unknown error'}
        </div>
      ) : filteredItems.length === 0 ? (
        <EmptyState
          onClear={() =>
            setFilters({
              status: undefined,
              source_type: undefined,
              search: '',
            })
          }
        />
      ) : (
        <ActualsTable
          actuals={filteredItems}
          projectId={projectId}
          lineLookup={lineLookup}
        />
      )}

      <CreateActualSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        projectId={projectId}
      />
    </div>
  );
}

function EmptyState({ onClear }) {
  return (
    <div
      data-testid="actuals-empty-state"
      className="rounded-lg border border-dashed border-slate-300 p-12 text-center"
    >
      <p className="text-slate-600">No actuals match your filters.</p>
      <button
        onClick={onClear}
        className="mt-3 text-sm font-medium text-sy-teal hover:brightness-110"
      >
        Clear filters
      </button>
    </div>
  );
}
