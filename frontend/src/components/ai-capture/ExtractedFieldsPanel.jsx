// frontend/src/components/ai-capture/ExtractedFieldsPanel.jsx — Chat 19C §R3.4
//
// Read-only display of the AI's extracted fields alongside per-field
// confidence pills. Operator uses this panel as the reference while
// filling the Promote form, so each row pairs the AI's guess with its
// confidence so an at-a-glance scan reveals the fields that need
// manual override.
import { fmtGBP } from '@/lib/format';
import { ConfidencePill } from './ConfidencePill';

const FIELDS = [
  { key: 'supplier_name',        label: 'Supplier',     format: (v) => v ?? '—' },
  { key: 'supplier_invoice_ref', label: 'Invoice ref',  format: (v) => v ?? '—' },
  { key: 'invoice_date',         label: 'Invoice date', format: (v) => v ?? '—' },
  { key: 'description',          label: 'Description',  format: (v) => v ?? '—' },
  { key: 'net_amount',           label: 'Net',          format: fmtGBP },
  { key: 'vat_amount',           label: 'VAT',          format: fmtGBP },
  { key: 'gross_amount',         label: 'Gross',        format: fmtGBP },
  { key: 'vat_rate_pct',         label: 'VAT rate',     format: (v) => (v == null ? '—' : `${v}%`) },
];

export function ExtractedFieldsPanel({ job }) {
  const data = job.extracted_data ?? {};
  const conf = job.confidence_scores ?? {};

  return (
    <div
      className="rounded-md border border-slate-200 bg-white p-4"
      data-testid="extracted-fields-panel"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-heading text-base text-slate-900">AI extraction</h2>
        <ConfidencePill value={conf.overall} />
      </div>
      <dl className="grid grid-cols-1 gap-2 text-sm">
        {FIELDS.map((f) => (
          <div
            key={f.key}
            className="grid grid-cols-[140px_1fr_80px] items-center gap-3"
            data-testid={`extracted-row-${f.key}`}
          >
            <dt className="text-slate-500">{f.label}</dt>
            <dd className="text-slate-900">{f.format(data[f.key])}</dd>
            <dd><ConfidencePill value={conf[f.key]} /></dd>
          </div>
        ))}
      </dl>
      {job.model_used && (
        <div className="mt-3 text-xs text-slate-400" data-testid="extracted-model">
          Model: {job.model_used}
          {/* PASS-2 M1: "API cost" label so it can't be confused with the invoice amount */}
          {job.cost_pence != null && ` · API cost: ${fmtGBP(job.cost_pence / 100)}`}
        </div>
      )}
    </div>
  );
}
