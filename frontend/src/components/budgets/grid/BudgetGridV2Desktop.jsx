/**
 * BudgetGridV2Desktop — Chat 23 R3.1/R3.5/R3.6/R3.7/R3.8.
 *
 * Top-level desktop renderer. Owns:
 *   - TanStack Table state (sorting, columnVisibility, columnOrder,
 *     expanded, rowSelection, filters)
 *   - The filter → group → sort pipeline (R3.7 → R3.5 → R3.8)
 *   - Header tiles (R3.10)
 *   - Drag-reorder for lines (carried over from v1 — only enabled when
 *     no sort is active)
 *   - LineDrawer mounting (kept from v1; actions menu still opens it)
 *
 * Mobile users get BudgetGridMobileReadOnly instead (R8).
 */
import { useMemo, useState, useEffect, useRef, useCallback, Fragment } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  flexRender, getCoreRowModel, getExpandedRowModel,
  getSortedRowModel, useReactTable,
} from '@tanstack/react-table';
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor,
  useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';

import { useAuth } from '@/context/AuthContext';
import {
  useReorderBudgetLines,
} from '@/hooks/budgets';
import { useCostCodes, buildCostCodeMap } from '@/hooks/costCodes';
import { isBudgetEditable, canEditLines } from '@/lib/budgetCapability';
import { buildReorderedIds } from '@/lib/buildReorderedIds';
import { groupLinesByCategory } from '@/lib/budgetCategoryGroup';

import { LineDrawer } from '../LineDrawer';
import { BudgetGridToolbar } from './BudgetGridToolbar';
import { BudgetGridHeaderTiles } from './BudgetGridHeaderTiles';
import { BudgetLineExpandedRow }
  from './PerLineTransactionDrilldown/BudgetLineExpandedRow';
import { BulkActionsBar } from './BulkActionsBar';
import { SaveViewDialog } from './SaveViewDialog';
import { ManageViewsDialog } from './ManageViewsDialog';
import {
  makeColumns, INITIAL_COLUMN_VISIBILITY,
} from './BudgetGridColumns';
import { SORT_KEY_MAP, computedLineValue } from './SORT_KEY_MAP';
import {
  useUserPreferences, useSetCurrentPreference,
} from '@/hooks/userPreferences';

const SURFACE_KEY = 'budgets.grid.v2';
const AUTOSAVE_DEBOUNCE_MS = 500;

function applyFilters(lines, filters, costCodeMap) {
  return lines.filter((line) => {
    if (filters.search) {
      const code = costCodeMap.get(line.cost_code_id)?.code ?? '';
      const haystack = `${code} ${line.line_description ?? ''}`.toLowerCase();
      if (!haystack.includes(filters.search.toLowerCase())) return false;
    }
    if (filters.categories?.length) {
      const code = costCodeMap.get(line.cost_code_id)?.code ?? '';
      const prefix = code.split('-')[0].toUpperCase();
      if (!filters.categories.includes(prefix)) return false;
    }
    if (filters.varianceBand && filters.varianceBand !== 'All') {
      if (line.variance_status !== filters.varianceBand) return false;
    }
    if (filters.onlyWithActuals
        && !(Number(line.actuals_to_date ?? 0) > 0)) return false;
    if (filters.onlyWithVariance
        && Number(line.variance_value ?? 0) === 0) return false;
    return true;
  });
}

function applySort(grouped, sorting) {
  if (!sorting.length) return grouped;
  const { id, desc } = sorting[0];
  if (process.env.NODE_ENV !== 'production' && !(id in SORT_KEY_MAP)) {
    // Catches: developer added a sortable column but forgot to add it
    // to SORT_KEY_MAP. Without this warn the sort silently no-ops.
    // eslint-disable-next-line no-console
    console.warn(
      `[BudgetGridV2] No SORT_KEY_MAP entry for column "${id}". `
      + `Sort will no-op. Add the column id to SORT_KEY_MAP.js.`,
    );
  }
  const backendKey = SORT_KEY_MAP[id];
  function lineValue(line) {
    const synthetic = computedLineValue(line, id);
    if (synthetic !== null) return synthetic;
    if (backendKey == null) return 0;
    return Number(line[backendKey] ?? 0);
  }
  const groupsSorted = backendKey == null
    ? [...grouped]
    : [...grouped].sort((a, b) => {
        const av = Number(a.totals?.[backendKey] ?? 0);
        const bv = Number(b.totals?.[backendKey] ?? 0);
        return desc ? bv - av : av - bv;
      });
  return groupsSorted.map((g) => ({
    ...g,
    subRows: [...g.subRows].sort((a, b) => {
      const av = lineValue(a);
      const bv = lineValue(b);
      return desc ? bv - av : av - bv;
    }),
  }));
}

function LineDragHandle({ lineId, disabled }) {
  // Line drag handle — uses the parent useSortable context wired in
  // the row body. When `disabled` we still render a placeholder so the
  // table column width stays consistent.
  const { attributes, listeners, setActivatorNodeRef } = useSortable({
    id: lineId, disabled,
  });
  if (disabled) {
    return <span className="inline-block w-4" aria-hidden="true" />;
  }
  return (
    <button
      ref={setActivatorNodeRef}
      type="button"
      {...attributes}
      {...listeners}
      aria-label={`Drag to reorder`}
      className="cursor-grab text-slate-400 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-teal rounded"
      data-testid={`bg2-line-drag-${lineId}`}
    >
      <GripVertical size={14} />
    </button>
  );
}

function SortableLineRowBody({ row, lineId, dragDisabled, children }) {
  const {
    setNodeRef, transform, transition, isDragging,
  } = useSortable({ id: lineId, disabled: dragDisabled });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <tr
      ref={setNodeRef}
      style={style}
      className="border-t border-slate-100 hover:bg-slate-50"
      data-testid={`bg2-row-line-${lineId}`}
    >
      {children}
    </tr>
  );
}

export function BudgetGridV2Desktop({ budget, projectId }) {
  const { me } = useAuth();
  const canEdit = canEditLines(me, budget.status);
  const canViewSensitive = !!me?.permissions?.includes('budgets.view_sensitive');
  const editable = isBudgetEditable(budget.status);

  const { data: costCodes = [] } = useCostCodes(projectId);
  const costCodeMap = useMemo(() => buildCostCodeMap(costCodes), [costCodes]);

  // ----- Drawer (R3.1 — kept from v1, NOT removed) -----
  const [openLineId, setOpenLineId] = useState(null);
  const [drawerFocus, setDrawerFocus] = useState(null);
  const openDrawer = (lineId, opts = {}) => {
    setOpenLineId(lineId);
    setDrawerFocus(opts.focus ?? null);
  };

  // ----- Mutations -----
  const reorderMut = useReorderBudgetLines(budget.id, projectId);
  // NotesCell owns the notes mutation itself (Chat 23 R5 — debounced
  // PATCH with optimistic update + error rollback live inside the
  // cell). The grid no longer wires onUpdateNotes.

  // ----- Filter state -----
  const [filters, setFilters] = useState({
    search: '', categories: [], varianceBand: null,
    onlyWithActuals: false, onlyWithVariance: false,
  });

  // ----- Table state -----
  const [sorting, setSorting] = useState([]);
  const [columnVisibility, setColumnVisibility] =
    useState(INITIAL_COLUMN_VISIBILITY);
  const [columnOrder, setColumnOrder] = useState([]);
  const [rowSelection, setRowSelection] = useState({});

  // ----- R6: user_preferences hydration + autosave ---------------------
  // Hydration policy: on first snapshot fetch, if `current.payload`
  // is non-empty, apply it (column visibility / order / sorting /
  // filters). Otherwise keep the Standard preset defaults.
  // Hydration runs ONCE per mount — a refetch must not clobber the
  // user's in-flight edits.
  const prefsQuery = useUserPreferences(SURFACE_KEY);
  const setCurrentMut = useSetCurrentPreference(SURFACE_KEY);
  const hydratedRef = useRef(false);
  const autosaveTimer = useRef(null);

  useEffect(() => {
    if (hydratedRef.current) return;
    if (prefsQuery.isLoading) return;
    hydratedRef.current = true;
    const payload = prefsQuery.data?.current;
    if (payload && typeof payload === 'object'
        && Object.keys(payload).length > 0) {
      if (payload.columnVisibility) {
        setColumnVisibility({
          ...INITIAL_COLUMN_VISIBILITY, ...payload.columnVisibility,
        });
      }
      if (Array.isArray(payload.columnOrder)) {
        setColumnOrder(payload.columnOrder);
      }
      if (Array.isArray(payload.sorting)) setSorting(payload.sorting);
      if (payload.filters) {
        setFilters((f) => ({ ...f, ...payload.filters }));
      }
    }
    // We deliberately depend on the loading flag so the effect re-runs
    // exactly once when the snapshot lands. After that hydratedRef
    // gates further runs.
  }, [prefsQuery.isLoading, prefsQuery.data]);

  // Autosave: any change to visibility / order / sorting / filters
  // schedules a debounced PUT. Rapid changes collapse to one call.
  useEffect(() => {
    if (!hydratedRef.current) return; // don't fire during initial hydration
    clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(() => {
      setCurrentMut.mutate({
        columnVisibility, columnOrder, sorting, filters,
      });
    }, AUTOSAVE_DEBOUNCE_MS);
    return () => clearTimeout(autosaveTimer.current);
    // setCurrentMut is stable across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columnVisibility, columnOrder, sorting, filters]);

  // ----- R6: saved-view dialogs ----------------------------------------
  const [saveOpen, setSaveOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const savedViews = prefsQuery.data?.views ?? [];

  function applySavedView(view) {
    const p = view.payload ?? {};
    setColumnVisibility(
      p.columnVisibility
        ? { ...INITIAL_COLUMN_VISIBILITY, ...p.columnVisibility }
        : INITIAL_COLUMN_VISIBILITY,
    );
    setColumnOrder(Array.isArray(p.columnOrder) ? p.columnOrder : []);
    setSorting(Array.isArray(p.sorting) ? p.sorting : []);
    setFilters({
      search: '', categories: [], varianceBand: null,
      onlyWithActuals: false, onlyWithVariance: false,
      ...(p.filters ?? {}),
    });
  }

  // ----- Pipeline: filter → group → sort -----
  const rawLines = budget.lines ?? [];
  const filteredLines = useMemo(
    () => applyFilters(rawLines, filters, costCodeMap),
    [rawLines, filters, costCodeMap],
  );
  const grouped = useMemo(
    () => groupLinesByCategory(filteredLines, costCodeMap),
    [filteredLines, costCodeMap],
  );
  const sortedGrouped = useMemo(
    () => applySort(grouped, sorting),
    [grouped, sorting],
  );

  // ----- R6: URL-backed expanded set (?expanded=lineId,lineId) ---------
  // Category-group rows still expand/collapse via local state — only
  // line-row expansion is URL-backed (deep-linkable, share-able).
  // We use `router.replace` so toggling rows doesn't pollute history.
  const [searchParams, setSearchParams] = useSearchParams();
  const expandedLineSet = useMemo(() => {
    const raw = searchParams.get('expanded') ?? '';
    const ids = raw.split(',').map((s) => s.trim()).filter(Boolean);
    return new Set(ids);
  }, [searchParams]);

  const toggleExpandedLine = useCallback((lineId) => {
    setSearchParams((prev) => {
      // `prev` is a URLSearchParams; clone so we don't mutate React's
      // current state object.
      const next = new URLSearchParams(prev);
      const current = (next.get('expanded') ?? '')
        .split(',').map((s) => s.trim()).filter(Boolean);
      const idx = current.indexOf(lineId);
      if (idx === -1) current.push(lineId);
      else current.splice(idx, 1);
      if (current.length === 0) next.delete('expanded');
      else next.set('expanded', current.join(','));
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  // ----- Default expansion (R3.6): TanStack `expanded` for category-group
  // rows; line expansion is URL-backed via `expandedLineSet` below.
  // (Initial state keys here are intentionally the bare groupKey, NOT
  // the row id — TanStack expects the row id (`g:<groupKey>`) for hits,
  // so groups start collapsed and the user toggles them open. This
  // matches Chat 23 R3.6 behavior + the BudgetGridV2-CostCodeRender
  // test pins.)
  const [expandedGroups, setExpandedGroups] = useState(() =>
    Object.fromEntries(grouped.map((g) => [g.groupKey, true])),
  );

  // ----- Columns -----
  const columns = useMemo(
    () => makeColumns({
      costCodeMap, canEdit, canViewSensitive,
      budgetId: budget.id,
      onOpenDrawer: openDrawer,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [costCodeMap, canEdit, canViewSensitive, budget.id],
  );

  // ----- TanStack Table instance -----
  const table = useReactTable({
    data: sortedGrouped,
    columns,
    state: {
      sorting, columnVisibility, columnOrder, expanded: expandedGroups, rowSelection,
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: setColumnOrder,
    onExpandedChange: setExpandedGroups,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getSubRows: (row) => row.subRows,
    // Only group rows expand via TanStack; line rows expand via the URL
    // (`?expanded=lineId,...`) and bypass TanStack's expanded state.
    getRowCanExpand: (row) => row.original.isGroup,
    getRowId: (row, index, parent) => {
      // Group rows use groupKey; line + item rows use their UUID id.
      if (row.isGroup) return `g:${row.groupKey}`;
      return `${parent ? parent.id + ':' : ''}${row.id}`;
    },
    enableRowSelection: (row) => !row.original.isGroup && !row.original.isItem,
    manualSorting: true,    // R3.8 — sort is applied client-side in
                            // applySort() above; TanStack just tracks
                            // the sorting state for header click cycle.
    enableExpanding: true,
  });

  // ----- Drag-reorder for LINES (carry-over from v1) -----
  // Per Build Pack R3.1/R3.8 — disabled when a sort is active.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const dragDisabled =
    sorting.length > 0 || !editable || !canEdit || reorderMut.isPending;
  const lineIdsForDnd = useMemo(
    () => filteredLines.map((l) => l.id),
    [filteredLines],
  );
  function handleDragEnd(event) {
    const orderedIds = buildReorderedIds(filteredLines, event);
    if (orderedIds) reorderMut.mutate(orderedIds);
  }

  return (
    <div className="space-y-4" data-testid="bg2-root">
      <BudgetGridHeaderTiles
        budget={budget}
        canViewSensitive={canViewSensitive}
      />

      {Object.keys(rowSelection).length > 0 && (
        <BulkActionsBar
          selectedLines={(() => {
            // Map TanStack selection state back to the underlying line
            // objects. Row IDs are constructed by getRowId as
            // `g:<groupKey>:<lineId>` for line rows; we filter the
            // selected ids to those that match a real line in `rawLines`.
            const selectedIds = new Set(
              Object.keys(rowSelection).map((rid) => rid.split(':').pop()),
            );
            return rawLines.filter((l) => selectedIds.has(l.id));
          })()}
          table={table}
          budget={budget}
          costCodeMap={costCodeMap}
          canEdit={canEdit}
          editable={editable}
          onClear={() => setRowSelection({})}
        />
      )}

      <BudgetGridToolbar
        filters={filters}
        onFiltersChange={setFilters}
        table={table}
        canViewSensitive={canViewSensitive}
        onApplyPreset={(_name, preset) => {
          setColumnVisibility({ ...INITIAL_COLUMN_VISIBILITY, ...preset.visibility });
          setColumnOrder(preset.columnOrder ?? []);
          setSorting(preset.sorting ?? []);
          setFilters({
            search: '', categories: [], varianceBand: null,
            onlyWithActuals: false, onlyWithVariance: false,
            ...(preset.filters ?? {}),
          });
        }}
        savedViews={savedViews}
        onApplyView={applySavedView}
        onOpenSaveView={() => setSaveOpen(true)}
        onOpenManageViews={() => setManageOpen(true)}
      />

      {reorderMut.isError && (
        <div
          className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
          data-testid="bg2-reorder-error"
        >
          Reorder failed — order restored. {reorderMut.error?.message}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-sm" data-testid="bg2-table">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                <th className="w-8" aria-hidden="true" />
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    scope="col"
                    className={`px-3 py-2 text-left ${
                      h.column.getCanSort() ? 'cursor-pointer select-none' : ''
                    }`}
                    style={{ minWidth: h.column.columnDef.size }}
                    onClick={h.column.getToggleSortingHandler()}
                    data-testid={`bg2-header-${h.id}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {h.column.getIsSorted() === 'asc' && <span>▲</span>}
                      {h.column.getIsSorted() === 'desc' && <span>▼</span>}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>

          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={lineIdsForDnd}
              strategy={verticalListSortingStrategy}
            >
              <tbody>
                {table.getRowModel().rows.map((row) => {
                  const orig = row.original;
                  // Group row
                  if (orig.isGroup) {
                    return (
                      <tr
                        key={row.id}
                        className="bg-slate-50 font-semibold"
                        data-testid={`bg2-group-${orig.groupKey}`}
                      >
                        <td className="w-8" />
                        {row.getVisibleCells().map((cell) => (
                          <td
                            key={cell.id}
                            className="px-3 py-2"
                          >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    );
                  }
                  // Line row — sortable wrapper for drag-reorder.
                  const lineExpanded = expandedLineSet.has(orig.id);
                  const panelId = `bg2-expanded-panel-${orig.id}`;
                  return (
                    <Fragment key={row.id}>
                      <SortableLineRowBody
                        row={row}
                        lineId={orig.id}
                        dragDisabled={dragDisabled}
                      >
                        <td className="w-8 px-2">
                          <button
                            type="button"
                            onClick={() => toggleExpandedLine(orig.id)}
                            aria-expanded={lineExpanded}
                            aria-controls={panelId}
                            aria-label={lineExpanded
                              ? 'Collapse line details'
                              : 'Expand line details'}
                            className="inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 hover:bg-slate-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-teal"
                            data-testid={`bg2-line-expand-${orig.id}`}
                          >
                            <span aria-hidden="true">
                              {lineExpanded ? '▼' : '▶'}
                            </span>
                          </button>
                          <LineDragHandle
                            lineId={orig.id}
                            disabled={dragDisabled}
                          />
                        </td>
                        {row.getVisibleCells().map((cell) => (
                          <td
                            key={cell.id}
                            className="px-3 py-2"
                          >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </SortableLineRowBody>
                      {lineExpanded && (
                        <tr
                          id={panelId}
                          className="bg-slate-50"
                          data-testid={`bg2-expanded-row-${orig.id}`}
                        >
                          <td
                            colSpan={row.getVisibleCells().length + 1}
                            className="p-0"
                          >
                            <BudgetLineExpandedRow
                              line={orig}
                              budget={budget}
                              projectId={projectId}
                              canEdit={canEdit}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {sortedGrouped.length === 0 && (
                  <tr>
                    <td
                      colSpan={columns.length + 1}
                      className="p-10 text-center text-slate-500"
                      data-testid="bg2-empty"
                    >
                      No lines match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </SortableContext>
          </DndContext>
        </table>
      </div>

      <LineDrawer
        budget={budget}
        projectId={projectId}
        lineId={openLineId}
        focus={drawerFocus}
        onClose={() => { setOpenLineId(null); setDrawerFocus(null); }}
      />

      <SaveViewDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        payload={{ columnVisibility, columnOrder, sorting, filters }}
      />
      <ManageViewsDialog
        open={manageOpen}
        onOpenChange={setManageOpen}
      />
    </div>
  );
}
