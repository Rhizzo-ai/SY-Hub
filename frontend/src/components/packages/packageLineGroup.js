/**
 * packageLineGroup.js — B88 Pack 3.5 §5.2.
 *
 * Group an array of package lines by their cost_code, returning groups
 * sorted in DOTTED-CODE order (i.e. as numeric arrays per segment, so
 * "4.02" precedes "4.10" and "4.10" precedes "4.2"). Each group carries
 * its lines (in line_number order) plus a derived net subtotal.
 *
 * The grouping key is the line's `cost_code` STRING; the human label
 * comes from the backend `cost_code_name` enrichment landed in Pack 3.5
 * §5.1. When `cost_code_name` is absent (older API, or sensitive-field
 * stripped), the group renders with the code alone as its header label.
 *
 * Money discipline: subtotals are computed via decimal-string sum (the
 * server is the authority on per-line nets; we never re-multiply qty*rate
 * here).
 *
 * Returns:
 *   Array<{
 *     code: string,          // raw cost_code, e.g. "4.02"
 *     name: string|null,     // human label from cost_code_name
 *     lines: PackageLine[],  // sorted by line_number ascending
 *     subtotalNet: string,   // decimal string, e.g. "12345.67"
 *   }>
 *
 * Build Pack §5.2 — dotted-code sort uses a per-segment numeric compare
 * so "4.02" sorts before "4.10".
 */

/**
 * Split a dotted code like "4.02.1" into [4, 2, 1]. Non-numeric
 * segments fall back to their character code so the sort stays total.
 */
export function dottedCodeKey(code) {
  if (code == null) return [Number.POSITIVE_INFINITY];
  return String(code).split('.').map((seg) => {
    const n = Number.parseInt(seg, 10);
    if (Number.isFinite(n)) return n;
    // Fall back to a string-derived sentinel so non-numeric segments
    // still sort deterministically (after all numeric ones).
    return Number.MAX_SAFE_INTEGER - 1;
  });
}

export function compareDottedCodes(a, b) {
  const ka = dottedCodeKey(a);
  const kb = dottedCodeKey(b);
  const n = Math.max(ka.length, kb.length);
  for (let i = 0; i < n; i += 1) {
    const va = ka[i] ?? -1;
    const vb = kb[i] ?? -1;
    if (va !== vb) return va - vb;
  }
  return 0;
}

function sumDecimalStrings(strs) {
  // Sum as integer pennies to avoid FP drift, then format back.
  let pennies = 0n;
  for (const s of strs) {
    if (s == null) continue;
    const str = String(s);
    const neg = str.startsWith('-');
    const abs = neg ? str.slice(1) : str;
    const [whole, frac = ''] = abs.split('.');
    const fracPadded = (frac + '00').slice(0, 2);
    const intPart = BigInt(whole.replace(/[^0-9]/g, '') || '0');
    const fracPart = BigInt(fracPadded.replace(/[^0-9]/g, '') || '0');
    const value = intPart * 100n + fracPart;
    pennies += neg ? -value : value;
  }
  const neg = pennies < 0n;
  if (neg) pennies = -pennies;
  const whole = pennies / 100n;
  const frac = (pennies % 100n).toString().padStart(2, '0');
  return `${neg ? '-' : ''}${whole.toString()}.${frac}`;
}

export function groupPackageLinesByCostCode(lines) {
  if (!Array.isArray(lines) || lines.length === 0) return [];

  // Bucket by string code (preserves dotted notation as-is).
  const buckets = new Map();
  for (const ln of lines) {
    const code = ln?.cost_code ?? '';
    if (!buckets.has(code)) {
      buckets.set(code, {
        code,
        name: ln?.cost_code_name ?? null,
        lines: [],
      });
    } else if (
      buckets.get(code).name == null && ln?.cost_code_name != null
    ) {
      // Pick the first non-null name we see — they should be uniform.
      buckets.get(code).name = ln.cost_code_name;
    }
    buckets.get(code).lines.push(ln);
  }

  const groups = Array.from(buckets.values());
  // Lines: sort by line_number ascending inside each group.
  groups.forEach((g) => {
    g.lines.sort(
      (a, b) => (a?.line_number ?? 0) - (b?.line_number ?? 0),
    );
    g.subtotalNet = sumDecimalStrings(
      g.lines.map((l) => l.budgeted_net_amount),
    );
  });
  // Groups: dotted-code sort.
  groups.sort((a, b) => compareDottedCodes(a.code, b.code));
  return groups;
}
