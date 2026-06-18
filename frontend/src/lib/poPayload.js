/**
 * PO line payload mapping — B107 §5.2 / §1.1.
 *
 * Cost-code-first: each line sends `cost_code_id` (the underlying
 * cost_codes.id — see B107 §0.4), NEVER `budget_line_id`. The optional
 * second key `cost_code_subcategory_id` is omitted when empty (B107 ships
 * cost-code-only, §7.3). quantity / unit_rate are sent only when entered
 * so a Draft can persist incomplete lines (the submit gate enforces
 * completeness, not create).
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

export default mapLinesToPayload;
