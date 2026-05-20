/**
 * Money / number formatting — Chat 24 §R5.
 *
 * Plain GBP for the PO surface. Build Pack §5 says "tabular-nums".
 * Functions return null when input is null/undefined so SensitiveValue
 * can render its em-dash placeholder.
 */
export function fmtGBP(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString('en-GB', {
    style: 'currency', currency: 'GBP', minimumFractionDigits: 2,
  });
}

export function fmtNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString('en-GB', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}

/** qty × rate → 2-dp net total as a string (avoids float-noise display). */
export function computeNet(qty, rate) {
  if (qty === '' || qty === null || qty === undefined) return '';
  if (rate === '' || rate === null || rate === undefined) return '';
  const q = Number(qty), r = Number(rate);
  if (!Number.isFinite(q) || !Number.isFinite(r)) return '';
  return (q * r).toFixed(2);
}

/** net × vat% → 2-dp VAT amount. */
export function computeVat(net, vatPct) {
  if (net === '' || net === null || net === undefined) return '';
  if (vatPct === '' || vatPct === null || vatPct === undefined) return '';
  const n = Number(net), v = Number(vatPct);
  if (!Number.isFinite(n) || !Number.isFinite(v)) return '';
  return (n * (v / 100)).toFixed(2);
}
