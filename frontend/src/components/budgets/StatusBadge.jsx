/**
 * StatusBadge — Prompt 2.4B-i §R4.2.
 * Slate baseline (brand colours reserved for actions).
 */
const STATUS_CLASSES = {
  Draft:      'bg-slate-100 text-slate-700 border-slate-200',
  Active:     'bg-emerald-50 text-emerald-700 border-emerald-200',
  Locked:     'bg-blue-50 text-blue-700 border-blue-200',
  Closed:     'bg-slate-100 text-slate-500 border-slate-200',
  Superseded: 'bg-slate-50 text-slate-400 border-slate-200',
};

export function StatusBadge({ status }) {
  const cls = STATUS_CLASSES[status] ?? STATUS_CLASSES.Draft;
  return (
    <span
      data-testid={`budget-status-badge-${status}`}
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {status}
    </span>
  );
}
