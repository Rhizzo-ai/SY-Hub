/**
 * <BCRStatusPill/> — Surface F.
 *
 * Status badge for the 6 BCR states. Slate baseline matches
 * components/budgets/StatusBadge.jsx convention; terminal states get
 * muted styling so the queue visually emphasises Submitted/Approved
 * (the actionable rows).
 */
const STATUS_CLASSES = {
  Draft:     'bg-slate-100 text-slate-700 border-slate-200',
  Submitted: 'bg-amber-50 text-amber-800 border-amber-200',
  Approved:  'bg-sky-50 text-sky-800 border-sky-200',
  Applied:   'bg-emerald-50 text-emerald-700 border-emerald-200',
  Rejected:  'bg-rose-50 text-rose-700 border-rose-200',
  Withdrawn: 'bg-slate-50 text-slate-500 border-slate-200',
};

export default function BCRStatusPill({ status }) {
  const cls = STATUS_CLASSES[status] ?? STATUS_CLASSES.Draft;
  return (
    <span
      data-testid={`bcr-status-pill-${status}`}
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {status}
    </span>
  );
}
