/**
 * VarianceBadge — Prompt 2.4B-i §R4.2.
 *
 * The backend exposes `variance_status` on the **line** level, not on the
 * budget summary header (per E7). At the header we synthesise a derived
 * status from `variance_pct` for the visual: Green |pct|≤2, Amber 2<|pct|≤10,
 * Red >10. Pure presentation — no data leakage when sensitive fields are
 * stripped (we render "—" via the badge's caller in that case).
 */
import { formatMoney, formatPercent } from '@/lib/format';

const VARIANCE_CLASSES = {
  Green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  Amber: 'bg-amber-50 text-amber-700 border-amber-200',
  Red:   'bg-rose-50 text-rose-700 border-rose-200',
};

export function deriveVarianceStatus(pct) {
  if (pct == null || !Number.isFinite(pct)) return null;
  const abs = Math.abs(pct);
  if (abs <= 2) return 'Green';
  if (abs <= 10) return 'Amber';
  return 'Red';
}

export function VarianceBadge({ status, value, pct }) {
  if (!status) return <span className="text-xs text-slate-400">—</span>;
  const cls = VARIANCE_CLASSES[status] ?? VARIANCE_CLASSES.Green;
  const valLabel = value != null ? formatMoney(value) : '—';
  const pctLabel = pct != null ? ` (${formatPercent(pct)})` : '';
  return (
    <span
      data-testid={`variance-badge-${status}`}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
      title={`Variance ${valLabel}${pctLabel}`}
    >
      <span aria-hidden>●</span>
      {status}
    </span>
  );
}
