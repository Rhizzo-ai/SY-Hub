/**
 * ActualStatusBadge — Five status pill variants (Chat 19B §R2.5).
 * Slate / blue / green / amber / red.
 */
const STYLES = {
  Draft:    'bg-slate-100 text-slate-700 ring-slate-200',
  Posted:   'bg-blue-100 text-blue-800 ring-blue-200',
  Paid:     'bg-emerald-100 text-emerald-800 ring-emerald-200',
  Disputed: 'bg-amber-100 text-amber-800 ring-amber-200',
  Void:     'bg-rose-100 text-rose-800 ring-rose-200',
};

export function ActualStatusBadge({ status }) {
  const cls = STYLES[status] ?? 'bg-slate-100 text-slate-700 ring-slate-200';
  return (
    <span
      data-testid={`actual-status-${status}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {status}
    </span>
  );
}
