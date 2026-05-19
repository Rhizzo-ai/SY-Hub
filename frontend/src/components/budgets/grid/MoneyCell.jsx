/**
 * MoneyCell — right-aligned tabular money. Optional `tintByStatus`
 * applies a 40%-opacity variance heat-map tint for the Forecast cost
 * column (R3.4). Brand tokens NOT used here — semantic emerald/amber/
 * rose only.
 */
import { formatMoney } from '@/lib/format';

const TINT_CLASSES = {
  Green: 'bg-emerald-50/40',
  Amber: 'bg-amber-50/40',
  Red:   'bg-rose-50/40',
};

export function MoneyCell({ value, tintByStatus }) {
  const tint = tintByStatus ? (TINT_CLASSES[tintByStatus] ?? '') : '';
  return (
    <span
      className={`block text-right font-mono tabular-nums ${tint}`}
      data-testid="money-cell"
    >
      {formatMoney(value)}
    </span>
  );
}
