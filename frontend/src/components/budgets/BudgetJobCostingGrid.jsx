/**
 * BudgetJobCostingGrid — B88 Pack 2 §7.2 / Chat 51 §R7.2.
 *
 * Buildertrend-class grouped grid for the Job-Costing surface.
 * Renders the `/budgets/:id/grid` response: group → subgroup → lines,
 * with rolled-up subtotals + variance heat-map + column picker + a
 * persistent (localStorage) optional-column visibility set.
 *
 * Scope is server-driven: the caller's effective scope is reported in
 * `data.budget.scope`. Tier-1-only columns (allocated sale price /
 * projected profit / projected margin %) are absent from the picker
 * on construction-scope responses.
 *
 * Replaces the legacy flat `BudgetGridV2`. The legacy component is
 * left in place but unreferenced (operator deprecation decision).
 */
import { useMemo, useState } from 'react';
import { useBudgetGrid, useBudget } from '@/hooks/budgets';
import { useAuth } from '@/context/AuthContext';
import { isBudgetEditable } from '@/lib/budgetCapability';
import { LineDrawer } from '@/components/budgets/LineDrawer';
import { ChevronRight, ChevronDown, AlertCircle, Columns3 } from 'lucide-react';

const BRAND = { primary: '#0F6A7A', accent: '#FC7827', neutral: '#CECECE' };

// Column registry. `tier1Only=true` columns are hidden from the picker
// on construction-scope responses (and absent from the row data anyway).
const ALL_COLUMNS = [
  { id: 'code',         label: 'Code',        defaultOn: true,  alwaysOn: true,  sticky: true },
  { id: 'description',  label: 'Description', defaultOn: true,  alwaysOn: true,  sticky: true },
  { id: 'original_budget',           label: 'Original budget',    defaultOn: true,  align: 'right' },
  { id: 'approved_changes',          label: 'Approved changes',   defaultOn: true,  align: 'right' },
  { id: 'current_budget',            label: 'Current budget',     defaultOn: true,  align: 'right' },
  { id: 'committed_value',           label: 'Committed',          defaultOn: true,  align: 'right' },
  { id: 'invoiced_against_commitment', label: 'Invoiced against commitment', defaultOn: false, align: 'right' },
  { id: 'committed_not_invoiced',    label: 'Committed not invoiced',  defaultOn: false, align: 'right' },
  { id: 'actuals_to_date',           label: 'Actuals to date',    defaultOn: true,  align: 'right' },
  { id: 'actuals_this_period',       label: 'Actuals this period', defaultOn: false, align: 'right' },
  { id: 'forecast_to_complete',      label: 'Forecast to complete', defaultOn: true, align: 'right' },
  { id: 'forecast_final_cost',       label: 'Forecast final cost', defaultOn: true,  align: 'right' },
  { id: 'variance_value',            label: 'Variance £',         defaultOn: true,  align: 'right', heatmap: true },
  { id: 'variance_pct',              label: 'Variance %',         defaultOn: true,  align: 'right', heatmap: true },
  { id: 'percentage_complete',       label: '% complete',         defaultOn: true,  align: 'right' },
  { id: '_allocated_sale_price_provisional', label: 'Allocated sale price (provisional)', defaultOn: false, align: 'right', tier1Only: true },
  { id: '_projected_profit',         label: 'Projected profit (provisional)', defaultOn: false, align: 'right', tier1Only: true, computed: true },
  { id: '_projected_margin_pct',     label: 'Projected margin % (provisional)', defaultOn: false, align: 'right', tier1Only: true, computed: true },
];

// ──────────────────────────────────────────────────────────────────────
// Formatters
// ──────────────────────────────────────────────────────────────────────

function fmtMoney(v) {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const abs = Math.abs(n).toLocaleString('en-GB', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return n < 0 ? `(£${abs})` : `£${abs}`;
}

function fmtPct(v) {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return `${n.toFixed(1)}%`;
}

function heatmapClass(status) {
  if (status === 'Red') return 'bg-rose-50 text-rose-700';
  if (status === 'Amber') return 'bg-amber-50 text-amber-800';
  if (status === 'Green') return 'bg-emerald-50 text-emerald-700';
  return '';
}

// Per-line derived columns (full scope only).
function computeProjected(line) {
  const alloc = line._allocated_sale_price_provisional;
  const ffc = line.forecast_final_cost;
  if (alloc == null || ffc == null) return { profit: null, margin: null };
  const a = Number(alloc); const f = Number(ffc);
  if (!Number.isFinite(a) || !Number.isFinite(f) || a === 0) {
    return { profit: null, margin: null };
  }
  const profit = a - f;
  const margin = (profit / a) * 100;
  return { profit, margin };
}

// ──────────────────────────────────────────────────────────────────────
// Column picker
// ──────────────────────────────────────────────────────────────────────

const STORAGE_KEY_PREFIX = 'sy-hub.budget-grid.columns.';

function loadVisibleColumns(scope, defaults) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_PREFIX + scope);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return defaults;
    return new Set(parsed);
  } catch (_) {
    return defaults;
  }
}

function saveVisibleColumns(scope, set) {
  try {
    localStorage.setItem(STORAGE_KEY_PREFIX + scope, JSON.stringify([...set]));
  } catch (_) { /* localStorage unavailable */ }
}

function ColumnPicker({ scope, visible, setVisible, availableColumns }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative" data-testid="budget-grid-column-picker">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
        data-testid="budget-grid-column-picker-toggle"
      >
        <Columns3 size={14} /> Columns
      </button>
      {open ? (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            data-testid="budget-grid-column-picker-backdrop"
          />
          <div
            className="absolute right-0 z-50 mt-1 w-64 rounded-md border border-slate-200 bg-white p-2 shadow-lg"
            data-testid="budget-grid-column-picker-menu"
            role="menu"
          >
            <ul className="max-h-72 overflow-auto">
              {availableColumns.filter((c) => !c.alwaysOn).map((c) => (
                <li key={c.id}>
                  <label className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={visible.has(c.id)}
                      onChange={(e) => {
                        const next = new Set(visible);
                        if (e.target.checked) next.add(c.id);
                        else next.delete(c.id);
                        setVisible(next);
                        saveVisibleColumns(scope, next);
                      }}
                      data-testid={`budget-grid-column-picker-${c.id}`}
                    />
                    {c.label}
                  </label>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Cell renderers
// ──────────────────────────────────────────────────────────────────────

function renderCell(col, source, varianceStatus) {
  let raw;
  if (col.id === 'code') {
    raw = source._cost_code_code || source.code || '';
  } else if (col.id === 'description') {
    raw = source.line_description || source.name || '';
  } else if (col.id === '_projected_profit') {
    raw = source._projected_profit;
    return fmtMoney(raw);
  } else if (col.id === '_projected_margin_pct') {
    raw = source._projected_margin_pct;
    return raw == null ? '—' : `${Number(raw).toFixed(1)}%`;
  } else if (col.id === 'variance_pct' || col.id === 'percentage_complete') {
    raw = source[col.id];
    return fmtPct(raw);
  } else if (col.id === 'variance_value' || col.id.includes('budget')
      || col.id.includes('actuals') || col.id.includes('committed')
      || col.id.includes('forecast') || col.id.includes('invoiced')
      || col.id.includes('allocated')) {
    raw = source[col.id];
    return fmtMoney(raw);
  } else {
    raw = source[col.id];
    return raw == null ? '—' : String(raw);
  }

  // Code + description fallthrough
  return raw;
}

// ──────────────────────────────────────────────────────────────────────
// Line + group rows
// ──────────────────────────────────────────────────────────────────────

function LineRow({ line, columns, costCodeLabel, onLineClick }) {
  const projected = useMemo(() => computeProjected(line), [line]);
  const enriched = {
    ...line,
    _cost_code_code: costCodeLabel,
    _projected_profit: projected.profit,
    _projected_margin_pct: projected.margin,
  };
  const clickable = !!onLineClick;
  return (
    <tr
      className={`border-b border-slate-100 ${clickable ? 'cursor-pointer hover:bg-sy-teal-50' : 'hover:bg-slate-50'}`}
      data-testid={`budget-grid-line-${line.id}`}
      onClick={clickable ? () => onLineClick(line.id) : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onLineClick(line.id);
        }
      } : undefined}
    >
      {columns.map((c, i) => {
        const heat = c.heatmap ? heatmapClass(line.variance_status) : '';
        return (
          <td
            key={c.id}
            className={`px-3 py-2 text-sm text-slate-900 ${
              c.align === 'right' ? 'text-right tabular-nums' : ''
            } ${heat} ${c.sticky ? 'sticky left-0 bg-white' : ''}`}
            style={c.sticky ? { left: i === 0 ? 0 : 120 } : undefined}
            data-testid={`budget-grid-cell-${line.id}-${c.id}`}
          >
            {c.id === 'description' && line.requires_attention ? (
              <span className="inline-flex items-center gap-1">
                <AlertCircle size={12} style={{ color: BRAND.accent }} />
                {renderCell(c, enriched, line.variance_status)}
              </span>
            ) : renderCell(c, enriched, line.variance_status)}
          </td>
        );
      })}
    </tr>
  );
}

function SubtotalRow({ node, columns, depth, expanded, onToggle, label }) {
  const chev = expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />;
  return (
    <tr
      className="bg-slate-50 font-semibold"
      data-testid={`budget-grid-group-${node.section_id || 'unassigned'}`}
    >
      {columns.map((c, i) => {
        if (i === 0) {
          return (
            <td
              key={c.id}
              className="sticky left-0 bg-slate-50 px-3 py-2 text-sm"
              style={{ paddingLeft: 8 + depth * 16 }}
            >
              <button
                type="button"
                onClick={onToggle}
                className="inline-flex items-center gap-1.5 text-left hover:text-sy-teal-700"
                data-testid={`budget-grid-group-toggle-${node.section_id || 'unassigned'}`}
                style={{ color: BRAND.primary }}
              >
                {chev}
                <span>{label}</span>
              </button>
            </td>
          );
        }
        if (c.id === 'description' && i === 1) {
          return (
            <td key={c.id} className="sticky bg-slate-50 px-3 py-2 text-xs text-slate-500" style={{ left: 120 }}>
              {node.name}
            </td>
          );
        }
        const totals = node.subtotals || {};
        const heat = c.heatmap ? heatmapClass(totals.variance_status) : '';
        let val = '';
        if (c.id === 'variance_pct' || c.id === 'percentage_complete') {
          val = fmtPct(totals[c.id]);
        } else if (totals[c.id] !== undefined) {
          val = fmtMoney(totals[c.id]);
        }
        return (
          <td
            key={c.id}
            className={`px-3 py-2 text-sm tabular-nums ${
              c.align === 'right' ? 'text-right' : ''
            } ${heat}`}
          >
            {val}
          </td>
        );
      })}
    </tr>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Top-level grid
// ──────────────────────────────────────────────────────────────────────

export function BudgetJobCostingGrid({ budgetId, scope, projectId }) {
  const { data, isLoading, isError, error } = useBudgetGrid(budgetId, { scope });
  const effectiveScope = data?.budget?.scope || scope || 'full';

  // B88 Pack 2 §7.2 — row-click line edit reuses the EXISTING LineDrawer
  // (not a rebuild). Gating mirrors the legacy grid: caller must hold
  // `budgets.edit` AND the budget status must be editable. Otherwise
  // rows are not clickable (consistent with Locked/Closed/Superseded).
  const { me } = useAuth();
  const canEdit = !!me?.permissions?.includes('budgets.edit');
  const budgetStatus = data?.budget?.status;
  const rowsClickable = canEdit && isBudgetEditable(budgetStatus);

  const [drawerLineId, setDrawerLineId] = useState(null);
  // Load the full budget detail on demand so LineDrawer has `budget.lines`.
  const { data: budgetDetail } = useBudget(budgetId, {
    enabled: !!drawerLineId,
  });

  const availableColumns = useMemo(
    () => ALL_COLUMNS.filter((c) => !(c.tier1Only && effectiveScope !== 'full')),
    [effectiveScope],
  );

  const [visible, setVisible] = useState(() => {
    const defaults = new Set(
      ALL_COLUMNS.filter((c) => c.defaultOn).map((c) => c.id),
    );
    return loadVisibleColumns(effectiveScope, defaults);
  });

  const columns = useMemo(
    () => availableColumns.filter((c) => c.alwaysOn || visible.has(c.id)),
    [availableColumns, visible],
  );

  const [expanded, setExpanded] = useState({});
  const toggle = (key) => setExpanded((m) => ({ ...m, [key]: !(m[key] ?? true) }));

  if (isLoading) {
    return (
      <div
        className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
        data-testid="budget-grid-loading"
      >
        Loading job-costing grid…
      </div>
    );
  }
  if (isError) {
    return (
      <div
        className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
        data-testid="budget-grid-error"
      >
        Failed to load grid: {error?.message || 'Unknown error.'}
      </div>
    );
  }
  if (!data) return null;

  const groups = data.groups || [];
  const isEmpty = groups.length === 0;

  return (
    <div className="space-y-3" data-testid="budget-grid">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-600">
          <span
            className="rounded-full px-2 py-0.5 text-xs font-semibold"
            style={{ background: BRAND.primary, color: 'white' }}
            data-testid="budget-grid-scope-badge"
          >
            {effectiveScope === 'full' ? 'Full Budget' : 'Construction Budget'}
          </span>
        </div>
        <ColumnPicker
          scope={effectiveScope}
          visible={visible}
          setVisible={setVisible}
          availableColumns={availableColumns}
        />
      </div>

      {/* Grid */}
      {isEmpty ? (
        <div
          className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
          data-testid="budget-grid-empty"
        >
          No budget lines for this scope.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full border-collapse" data-testid="budget-grid-table">
            <thead className="sticky top-0 z-10 bg-white shadow-sm">
              <tr>
                {columns.map((c, i) => (
                  <th
                    key={c.id}
                    className={`border-b border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600 ${
                      c.align === 'right' ? 'text-right' : 'text-left'
                    } ${c.sticky ? 'sticky left-0 bg-white' : ''}`}
                    style={c.sticky ? { left: i === 0 ? 0 : 120 } : undefined}
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                const gKey = g.section_id || `unassigned-${g.code}`;
                const gOpen = expanded[gKey] ?? true;
                return (
                  <RenderGroup
                    key={gKey}
                    group={g}
                    gKey={gKey}
                    gOpen={gOpen}
                    expanded={expanded}
                    toggle={toggle}
                    columns={columns}
                    onLineClick={rowsClickable ? setDrawerLineId : null}
                  />
                );
              })}
              {/* Footer: budget totals */}
              <tr className="bg-slate-100 font-bold" data-testid="budget-grid-totals">
                {columns.map((c, i) => {
                  if (i === 0) {
                    return (
                      <td key={c.id} className="sticky left-0 bg-slate-100 px-3 py-2 text-sm" style={{ color: BRAND.primary }}>
                        Budget total
                      </td>
                    );
                  }
                  const t = data.budget?.totals || {};
                  const val =
                    c.id === 'variance_pct' ? fmtPct(t.variance_pct)
                      : t[c.id] !== undefined ? fmtMoney(t[c.id])
                        : '';
                  const heat = c.heatmap ? heatmapClass(t.variance_status) : '';
                  return (
                    <td
                      key={c.id}
                      className={`px-3 py-2 text-sm tabular-nums ${
                        c.align === 'right' ? 'text-right' : ''
                      } ${heat}`}
                    >
                      {val}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* B88 Pack 2 §7.2 — row click reuses the existing LineDrawer.
          Only mounts when a line is clicked AND budget detail is loaded. */}
      {drawerLineId && budgetDetail ? (
        <LineDrawer
          budget={budgetDetail}
          projectId={projectId}
          lineId={drawerLineId}
          focus={null}
          onClose={() => setDrawerLineId(null)}
        />
      ) : null}
    </div>
  );
}

function RenderGroup({ group, gKey, gOpen, expanded, toggle, columns, onLineClick }) {
  return (
    <>
      <SubtotalRow
        node={group}
        columns={columns}
        depth={0}
        expanded={gOpen}
        onToggle={() => toggle(gKey)}
        label={`${group.code} · ${group.name}`}
      />
      {gOpen ? (
        <>
          {(group.subgroups || []).map((sg) => {
            const sKey = sg.section_id;
            const sOpen = expanded[sKey] ?? true;
            return (
              <RenderSubgroup
                key={sKey}
                subgroup={sg}
                sKey={sKey}
                sOpen={sOpen}
                toggle={toggle}
                columns={columns}
                onLineClick={onLineClick}
              />
            );
          })}
          {(group.lines || []).map((ln) => (
            <LineRow
              key={ln.id}
              line={ln}
              columns={columns}
              costCodeLabel={ln.cost_code?.code}
              onLineClick={onLineClick}
            />
          ))}
        </>
      ) : null}
    </>
  );
}

function RenderSubgroup({ subgroup, sKey, sOpen, toggle, columns, onLineClick }) {
  return (
    <>
      <SubtotalRow
        node={subgroup}
        columns={columns}
        depth={1}
        expanded={sOpen}
        onToggle={() => toggle(sKey)}
        label={`${subgroup.code} · ${subgroup.name}`}
      />
      {sOpen
        ? (subgroup.lines || []).map((ln) => (
            <LineRow
              key={ln.id}
              line={ln}
              columns={columns}
              costCodeLabel={ln.cost_code?.code}
              onLineClick={onLineClick}
            />
          ))
        : null}
    </>
  );
}

export default BudgetJobCostingGrid;
