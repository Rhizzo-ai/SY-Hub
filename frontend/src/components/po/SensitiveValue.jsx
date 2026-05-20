/**
 * <SensitiveValue/> — Chat 24 §R5 (Build Pack §5.5).
 *
 * Renders a stable em-dash placeholder when the caller lacks the
 * relevant `view_sensitive` permission. Backend returns `null` (or an
 * absent field) for sensitive columns in that case; this component
 * keeps the table/grid layout stable.
 *
 * Usage:
 *   <SensitiveValue value={po.unit_rate} format={money} hidden={!canSensitive} />
 *
 * The `hidden` prop wins: if the caller knows the value is sensitive
 * for this user we show "—" regardless of whether the value is present
 * (defence in depth). Otherwise we render the formatted value or "—"
 * when null.
 */
import React from 'react';

const DEFAULT_FORMAT = (v) => (v === null || v === undefined ? null : String(v));

export function SensitiveValue({
  value, format = DEFAULT_FORMAT, hidden = false,
  emptyLabel = '—',
  className = 'tabular-nums',
  testid,
}) {
  let display;
  if (hidden) {
    display = emptyLabel;
  } else {
    const fmt = format(value);
    display = (fmt === null || fmt === undefined || fmt === '') ? emptyLabel : fmt;
  }
  return (
    <span className={className} data-testid={testid}>
      {display}
    </span>
  );
}

export default SensitiveValue;
