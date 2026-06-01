/**
 * <BCRLineEditor/> — Surface G.
 *
 * Lines builder used in Create + Edit. Renders a row per delta line:
 *   - budget-line picker (select from parent budget's lines)
 *   - signed delta input (decimal, accepts negatives)
 *   - delete button
 *   - "+ Add line" row at the bottom
 *
 * Live running total displayed at the foot, with type-specific
 * validation hints:
 *   - Transfer / ContingencyDrawdown: net MUST be £0 (≥2 lines)
 *   - Adjustment: net MUST be non-zero
 *
 * The editor is dumb — it owns no mutation. Parent dialog calls
 * `value`/`onChange` and submits the payload.
 */
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { fmtGBP } from '@/lib/poFormat';

function netOf(lines) {
  let total = 0;
  for (const ln of lines) {
    const n = Number(ln.delta);
    if (Number.isFinite(n)) total += n;
  }
  return total;
}

export default function BCRLineEditor({
  value,
  onChange,
  changeType,
  budgetLines = [],
  disabled = false,
}) {
  const lines = Array.isArray(value) ? value : [];
  const net = netOf(lines);
  const isTransfer = changeType === 'Transfer';
  const isContingency = changeType === 'ContingencyDrawdown';
  const isAdjustment = changeType === 'Adjustment';
  const netZeroRequired = isTransfer || isContingency;

  const update = (i, patch) => {
    const next = lines.map((ln, idx) => (idx === i ? { ...ln, ...patch } : ln));
    onChange(next);
  };
  const remove = (i) => onChange(lines.filter((_, idx) => idx !== i));
  const add = () => onChange([...lines, { budget_line_id: '', delta: '' }]);

  const linesById = Object.fromEntries(budgetLines.map((bl) => [bl.id, bl]));

  return (
    <div className="space-y-2" data-testid="bcr-line-editor">
      <div className="grid grid-cols-[1fr_180px_40px] gap-2 text-xs font-medium text-slate-500">
        <div>Budget line</div>
        <div className="text-right">Delta (£)</div>
        <div />
      </div>

      {lines.length === 0 ? (
        <div
          data-testid="bcr-line-editor-empty"
          className="rounded border border-dashed border-slate-200 p-4 text-center text-sm text-slate-500"
        >
          No lines yet. Click <b>+ Add line</b> below to start.
        </div>
      ) : (
        lines.map((ln, i) => {
          const sel = linesById[ln.budget_line_id];
          const isContingencyLine = sel?.is_contingency;
          const numericDelta = Number(ln.delta);
          const isNegative = Number.isFinite(numericDelta) && numericDelta < 0;
          // Contingency-source guard hint (matches backend invariant).
          const contingencyHint =
            isContingency && isNegative && sel && !isContingencyLine;

          return (
            <div
              key={i}
              data-testid={`bcr-line-editor-row-${i}`}
              className="grid grid-cols-[1fr_180px_40px] items-start gap-2"
            >
              <div>
                <Select
                  value={ln.budget_line_id || undefined}
                  onValueChange={(v) => update(i, { budget_line_id: v })}
                  disabled={disabled}
                >
                  <SelectTrigger
                    data-testid={`bcr-line-editor-line-${i}`}
                  >
                    <SelectValue placeholder="Select budget line…" />
                  </SelectTrigger>
                  <SelectContent>
                    {budgetLines.map((bl) => (
                      <SelectItem key={bl.id} value={bl.id}>
                        <span className="font-mono text-xs text-slate-500">
                          {bl.cost_code ?? bl.cost_code_id?.slice(0, 6) ?? '—'}
                        </span>
                        <span className="ml-2">
                          {bl.description || 'Untitled line'}
                        </span>
                        {bl.is_contingency ? (
                          <span className="ml-2 text-xs text-amber-700">
                            (contingency)
                          </span>
                        ) : null}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {contingencyHint ? (
                  <div
                    className="mt-1 text-xs text-rose-700"
                    data-testid={`bcr-line-editor-contingency-warn-${i}`}
                  >
                    Source lines on a ContingencyDrawdown must be flagged
                    is_contingency.
                  </div>
                ) : null}
              </div>
              <Input
                type="number"
                step="0.01"
                value={ln.delta}
                onChange={(e) => update(i, { delta: e.target.value })}
                placeholder="0.00"
                className="text-right"
                disabled={disabled}
                data-testid={`bcr-line-editor-delta-${i}`}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => remove(i)}
                disabled={disabled}
                data-testid={`bcr-line-editor-remove-${i}`}
                aria-label={`Remove line ${i + 1}`}
              >
                <Trash2 className="h-4 w-4 text-rose-600" />
              </Button>
            </div>
          );
        })
      )}

      <div className="flex justify-between pt-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={add}
          disabled={disabled}
          data-testid="bcr-line-editor-add"
        >
          + Add line
        </Button>
        <div className="text-right text-sm">
          <div className="text-xs text-slate-500">Net</div>
          <div
            className="font-mono tabular-nums font-semibold"
            data-testid="bcr-line-editor-net"
          >
            {fmtGBP(net) ?? '£0.00'}
          </div>
          {netZeroRequired && Math.abs(net) > 0.001 ? (
            <div
              className="text-xs text-rose-700"
              data-testid="bcr-line-editor-net-warn"
            >
              {changeType} must net to £0.00
            </div>
          ) : null}
          {isAdjustment && Math.abs(net) < 0.001 ? (
            <div
              className="text-xs text-rose-700"
              data-testid="bcr-line-editor-adjust-warn"
            >
              Adjustment must have non-zero net
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
