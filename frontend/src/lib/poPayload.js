/**
 * PO line payload mapping + completeness validation — B107 §5.2 / §1.1 / §10.5.
 *
 * Cost-code-first: each line sends `cost_code_id` (the underlying
 * cost_codes.id — see B107 §0.4), NEVER `budget_line_id`. The optional
 * second key `cost_code_subcategory_id` is omitted when empty (B107 ships
 * cost-code-only, §7.3).
 *
 * Blank qty/unit_rate are treated as MISSING and OMITTED — never coerced to
 * 0 (the §10.5 defect: `Number('') === 0` silently created a £0 line). The
 * form gates on `validatePoLines` before create/submit so an incomplete
 * line can't reach the wire as a phantom zero in the first place.
 */
export function mapLinesToPayload(lines = []) {
  return lines.map((l) => {
    const out = {
      cost_code_id: l.cost_code_id || null,
      description: l.description ? l.description : null,
      vat_rate: Number(l.vat_rate ?? 20),
    };
    if (l.cost_code_subcategory_id) {
      out.cost_code_subcategory_id = l.cost_code_subcategory_id;
    }
    if (l.quantity !== '' && l.quantity != null) {
      out.quantity = Number(l.quantity);
    }
    if (l.unit_rate !== '' && l.unit_rate != null) {
      out.unit_rate = Number(l.unit_rate);
    }
    return out;
  });
}

/**
 * Completeness guard for PO lines (B107 §10.5). A blank/empty quantity or
 * unit_rate is MISSING (not 0). Mirrors the backend rule: quantity > 0,
 * unit_rate >= 0. Returns a human message naming the FIRST offending
 * (1-based) line, or null when every line is complete.
 */
export function validatePoLines(lines = []) {
  for (let i = 0; i < lines.length; i += 1) {
    const l = lines[i] || {};
    const qtyBlank = l.quantity === '' || l.quantity === null || l.quantity === undefined;
    const qty = Number(l.quantity);
    if (qtyBlank || !Number.isFinite(qty) || qty <= 0) {
      return `Line ${i + 1}: quantity is required and must be greater than 0.`;
    }
    const rateBlank = l.unit_rate === '' || l.unit_rate === null || l.unit_rate === undefined;
    const rate = Number(l.unit_rate);
    if (rateBlank || !Number.isFinite(rate) || rate < 0) {
      return `Line ${i + 1}: unit price is required and cannot be negative.`;
    }
  }
  return null;
}

export default mapLinesToPayload;
