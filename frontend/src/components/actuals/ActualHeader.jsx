/**
 * ActualHeader (Chat 19B §R4.2).
 *
 * Identity + money tiles + status-conditional banners (dispute reason,
 * void reason, paid info). Sensitive amounts (CIS) render as "—" when
 * the caller lacks `actuals.view_sensitive`.
 */
import { fmtGBP } from '@/lib/format';
import { ActualStatusBadge } from './ActualStatusBadge';

export function ActualHeader({ actual, includeSensitive }) {
  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-slate-500">
            {actual.source_type.replace(/_/g, ' ')}
            {actual.supplier_invoice_ref && ` · ${actual.supplier_invoice_ref}`}
          </div>
          <h1 className="mt-1 font-heading text-2xl text-slate-900">
            {actual.supplier_name_snapshot}
          </h1>
          <p className="mt-1 text-sm text-slate-600">{actual.description}</p>
          <p className="mt-2 text-xs text-slate-500">
            Transaction date: <span className="tabular">{actual.transaction_date}</span>
            {actual.posting_date && (
              <> · Posting date: <span className="tabular">{actual.posting_date}</span></>
            )}
          </p>
        </div>
        <ActualStatusBadge status={actual.status} />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Net" value={fmtGBP(actual.net_amount)} />
        <Tile label="VAT" value={fmtGBP(actual.vat_amount)} />
        <Tile label="Gross" value={fmtGBP(actual.gross_amount)} primary />
        <Tile
          label="CIS deduction"
          value={includeSensitive ? fmtGBP(actual.cis_deduction_amount) : '—'}
          dim={!includeSensitive}
        />
      </div>

      {actual.status === 'Disputed' && actual.dispute_reason && (
        <div
          data-testid="dispute-reason-banner"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <strong>Dispute reason:</strong> {actual.dispute_reason}
        </div>
      )}
      {actual.status === 'Void' && actual.void_reason && (
        <div
          data-testid="void-reason-banner"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
        >
          <strong>Void reason:</strong> {actual.void_reason}
        </div>
      )}
      {actual.status === 'Paid' && (
        <div
          data-testid="paid-info-banner"
          className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"
        >
          Paid on <span className="tabular">{actual.paid_date}</span>
          {actual.payment_reference && (
            <> · ref: <code className="rounded bg-emerald-100 px-1">{actual.payment_reference}</code></>
          )}
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, primary, dim }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div
        className={`mt-1 tabular text-lg ${
          primary ? 'font-semibold text-slate-900' : dim ? 'text-slate-400' : 'text-slate-800'
        }`}
      >
        {value}
      </div>
    </div>
  );
}
