/**
 * VarianceCell — Chat 23 R3.4.
 *
 * Heat-map cell for the Variance-to-budget column. Uses Tailwind's
 * semantic colour families (emerald/amber/rose), NOT the brand
 * sy-teal / sy-orange tokens. Status maps to background tint + text
 * colour. Falls back to a neutral slate cell when status is null.
 *
 * Brand-token convention (carried over from Chat 17):
 *   bg-sy-teal     -> primary CTAs only
 *   bg-sy-orange   -> destructive confirms only
 *   emerald/amber/rose -> semantic status (variance, alerts)
 */
import { formatMoney } from '@/lib/format';

const STATUS_CLASSES = {
  Green: 'bg-emerald-50 text-emerald-800',
  Amber: 'bg-amber-50 text-amber-800',
  Red:   'bg-rose-50 text-rose-800',
};

export function VarianceCell({ value, status, pct }) {
  const klass = STATUS_CLASSES[status] ?? 'bg-slate-50 text-slate-700';
  const pctNum = pct == null ? null : Number(pct);
  return (
    <span
      className={`inline-flex items-baseline gap-2 rounded px-2 py-1 ${klass}`}
      data-variance-status={status ?? 'Unknown'}
      data-testid="variance-cell"
    >
      <span className="font-medium tabular-nums">{formatMoney(value)}</span>
      {pctNum != null && Number.isFinite(pctNum) && (
        <span className="text-xs opacity-70 tabular-nums">
          ({pctNum.toFixed(1)}%)
        </span>
      )}
    </span>
  );
}
