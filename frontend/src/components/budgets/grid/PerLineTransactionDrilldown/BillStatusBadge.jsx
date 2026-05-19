/**
 * BillStatusBadge — Chat 23 R4.4.
 *
 * Small pill rendering one of the 5 actuals statuses (Draft / Posted /
 * Paid / Disputed / Void). Semantic colour mapping per Build Pack
 * §R4.4 status colour map. NOT brand tokens — same semantic palette
 * (slate / sky / emerald / rose / zinc) as the rest of the grid.
 */
const STATUS_CLASS = {
  Draft:    'bg-slate-100 text-slate-700',
  Posted:   'bg-sky-50 text-sky-800',
  Paid:     'bg-emerald-50 text-emerald-800',
  Disputed: 'bg-rose-50 text-rose-800',
  Void:     'bg-zinc-100 text-zinc-500',
};

export function BillStatusBadge({ status }) {
  const klass = STATUS_CLASS[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${klass}`}
      data-testid={`bg2-bill-status-${status ?? 'unknown'}`}
    >
      {status ?? '—'}
    </span>
  );
}
