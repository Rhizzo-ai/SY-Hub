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
import { useMemo, useState, Fragment } from 'react';
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
  useReorderBudgetLines, usePatchBudgetLine,
} from '@/hooks/budgets';
import { useCostCodes, buildCostCodeMap } from '@/hooks/costCodes';
import { isBudgetEditable, canEditLines } from '@/lib/budgetCapability';
import { buildReorderedIds } from '@/lib/buildReorderedIds';
import { groupLinesByCategory } from '@/lib/budgetCategoryGroup';

import { LineDrawer } from '../LineDrawer';
import { BudgetGridToolbar } from './BudgetGridToolbar';
import { BudgetGridHeaderTiles } from './BudgetGridHeaderTiles';
import { BudgetGridDrilldown } from './BudgetGridDrilldown';
import {
  makeColumns, INITIAL_COLUMN_VISIBILITY,
} from './BudgetGridColumns';
import { SORT_KEY_MAP, computedLineValue } from './SORT_KEY_MAP';

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
  const patchMut = usePatchBudgetLine(budget.id);
  const onUpdateNotes = (lineId, value) =>
    patchMut.mutate({ lineId, body: { notes: value } });

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

  // ----- Default expansion (R3.6): categories open, items closed -----
  const [expanded, setExpanded] = useState(() =>
    Object.fromEntries(grouped.map((g) => [g.groupKey, true])),
  );

  // ----- Columns -----
  const columns = useMemo(
    () => makeColumns({
      costCodeMap, canEdit, canViewSensitive,
      onOpenDrawer: openDrawer, onUpdateNotes,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [costCodeMap, canEdit, canViewSensitive],
  );

  // ----- TanStack Table instance -----
  const table = useReactTable({
    data: sortedGrouped,
    columns,
    state: {
      sorting, columnVisibility, columnOrder, expanded, rowSelection,
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: setColumnOrder,
    onExpandedChange: setExpanded,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getSubRows: (row) => row.subRows,
    // Allow group rows AND line rows to be expandable. Line rows have
    // no subRows themselves — their "expansion" renders the drilldown
    // panel as an injected colspan row directly under the line.
    getRowCanExpand: (row) =>
      row.original.isGroup || (!row.original.isItem && !!row.original.id),
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
                  const expanded = row.getIsExpanded();
                  return (
                    <Fragment key={row.id}>
                      <SortableLineRowBody
                        row={row}
                        lineId={orig.id}
                        dragDisabled={dragDisabled}
                      >
                        <td className="w-8 px-2">
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
                      {expanded && (
                        <tr
                          className="bg-slate-50"
                          data-testid={`bg2-drilldown-row-${orig.id}`}
                        >
                          <td
                            colSpan={row.getVisibleCells().length + 1}
                            className="p-0"
                          >
                            <BudgetGridDrilldown
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
    </div>
  );
}
