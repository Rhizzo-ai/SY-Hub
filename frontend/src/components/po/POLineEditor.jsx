/**
 * <POLineEditor/> — Chat 24 §R5.
 *
 * Inline editor for a list of PO lines. Each row computes net = qty × rate
 * and VAT = net × vat_rate live. Net + VAT + gross are surfaced read-only
 * underneath the table so the user sees totals without an extra click.
 *
 * Sensitive callers (without pos.view_sensitive) shouldn't see this
 * editor at all — pages gate the whole form on canEditPO + canViewSensitive
 * before rendering. We don't try to half-hide editable inputs.
 */
import React from 'react';
import { computeNet, computeVat, fmtGBP } from '@/lib/poFormat';
import { CostCodePicker } from '@/components/budgets/CostCodePicker';

const BLANK_LINE = {
  cost_code_id: '',
  cost_code_subcategory_id: '',
  description: '',
  quantity: '',
  unit_rate: '',
  vat_rate: '20',
};

export function POLineEditor({
  lines, onChange, projectId, existingCostCodeIds = null, floor,
  testid = 'po-line-editor',
}) {
  const setLine = (idx, patch) => {
    const next = lines.map((l, i) => (i === idx ? { ...l, ...patch } : l));
    onChange?.(next);
  };
  const removeLine = (idx) => onChange?.(lines.filter((_, i) => i !== idx));
  const addLine = () => onChange?.([...lines, { ...BLANK_LINE }]);

  const totals = lines.reduce(
    (acc, l) => {
      const net = Number(computeNet(l.quantity, l.unit_rate)) || 0;
      const vat = Number(computeVat(net, l.vat_rate)) || 0;
      acc.net += net;
      acc.vat += vat;
      return acc;
    },
    { net: 0, vat: 0 },
  );
  const gross = totals.net + totals.vat;

  // B107 §7.4 (full variant) — flag lines whose chosen cost code has no
  // existing budget line on this budget (a mint will happen). When the
  // budget's existing-line set isn't available (not loaded / forbidden),
  // fall back to the lighter always-visible generic hint.
  const floorLabel = fmtGBP(floor) ?? '£' + Number(floor ?? 1000).toLocaleString();
  const mintHintFor = (line) => {
    if (existingCostCodeIds instanceof Set) {
      if (line.cost_code_id && !existingCostCodeIds.has(line.cost_code_id)) {
        return `New cost code for this budget — a line will be created. `
          + `If committed spend reaches the sign-off floor (${floorLabel}) `
          + `it will need director approval before submit.`;
      }
      return null;
    }
    // Generic fallback (budget lines unavailable).
    return 'Choosing a cost code with no budget line will create one '
      + '(may need director sign-off if large).';
  };

  return (
    <div className="space-y-2" data-testid={testid}>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs text-sy-grey-700 border-b">
            <th className="py-1 pr-2">Cost code</th>
            <th className="py-1 pr-2">Description</th>
            <th className="py-1 pr-2 w-20">Qty</th>
            <th className="py-1 pr-2 w-24">Rate</th>
            <th className="py-1 pr-2 w-20">VAT %</th>
            <th className="py-1 pr-2 w-28 tabular-nums">Net</th>
            <th className="py-1 pr-2 w-8"></th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, idx) => {
            const net = computeNet(line.quantity, line.unit_rate);
            return (
              <tr key={idx} data-testid={`${testid}-row-${idx}`}>
                <td className="py-1 pr-2 align-top" style={{ minWidth: 220 }}>
                  <CostCodePicker
                    projectId={projectId}
                    value={line.cost_code_id}
                    onChange={(v) => setLine(idx, { cost_code_id: v })}
                    testid={`${testid}-cc-${idx}`}
                  />
                  {mintHintFor(line) && (
                    <p
                      className="mt-1 text-xs text-amber-700"
                      data-testid={`cost-code-mint-hint-${idx}`}
                    >
                      {mintHintFor(line)}
                    </p>
                  )}
                </td>
                <td className="py-1 pr-2">
                  <input
                    type="text"
                    className="w-full px-1 py-0.5 border rounded text-sm"
                    value={line.description ?? ''}
                    onChange={(e) => setLine(idx, { description: e.target.value })}
                    data-testid={`${testid}-desc-${idx}`}
                  />
                </td>
                <td className="py-1 pr-2">
                  <input
                    type="number" min="0" step="0.01"
                    className="w-full px-1 py-0.5 border rounded text-sm tabular-nums"
                    value={line.quantity ?? ''}
                    onChange={(e) => setLine(idx, { quantity: e.target.value })}
                    data-testid={`${testid}-qty-${idx}`}
                  />
                </td>
                <td className="py-1 pr-2">
                  <input
                    type="number" min="0" step="0.01"
                    className="w-full px-1 py-0.5 border rounded text-sm tabular-nums"
                    value={line.unit_rate ?? ''}
                    onChange={(e) => setLine(idx, { unit_rate: e.target.value })}
                    data-testid={`${testid}-rate-${idx}`}
                  />
                </td>
                <td className="py-1 pr-2">
                  <input
                    type="number" min="0" step="0.01"
                    className="w-full px-1 py-0.5 border rounded text-sm tabular-nums"
                    value={line.vat_rate ?? ''}
                    onChange={(e) => setLine(idx, { vat_rate: e.target.value })}
                    data-testid={`${testid}-vat-${idx}`}
                  />
                </td>
                <td className="py-1 pr-2 tabular-nums" data-testid={`${testid}-net-${idx}`}>
                  {fmtGBP(net) ?? '—'}
                </td>
                <td className="py-1 pr-0">
                  <button
                    type="button"
                    onClick={() => removeLine(idx)}
                    className="text-red-600 text-xs"
                    aria-label={`Remove line ${idx + 1}`}
                    data-testid={`${testid}-remove-${idx}`}
                  >
                    ×
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <button
        type="button"
        onClick={addLine}
        className="text-xs underline text-sy-teal-700"
        data-testid={`${testid}-add`}
      >
        + Add line
      </button>

      <div className="text-sm grid grid-cols-3 gap-2 max-w-md pt-2 border-t">
        <div data-testid={`${testid}-total-net`}>
          <div className="text-xs text-sy-grey-600">Net</div>
          <div className="tabular-nums">{fmtGBP(totals.net) ?? '—'}</div>
        </div>
        <div data-testid={`${testid}-total-vat`}>
          <div className="text-xs text-sy-grey-600">VAT</div>
          <div className="tabular-nums">{fmtGBP(totals.vat) ?? '—'}</div>
        </div>
        <div data-testid={`${testid}-total-gross`}>
          <div className="text-xs text-sy-grey-600">Gross</div>
          <div className="tabular-nums font-semibold">{fmtGBP(gross) ?? '—'}</div>
        </div>
      </div>
    </div>
  );
}

export default POLineEditor;
