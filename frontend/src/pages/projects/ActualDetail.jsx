/**
 * ActualDetail page (Chat 19B §R2 stub; full impl in §R4).
 *
 * Read-only detail view; §R4 adds the state-machine actions, attachments
 * list, and timeline.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useActual } from '@/hooks/actuals';
import { ActualStatusBadge } from '@/components/actuals/ActualStatusBadge';
import { fmtGBP } from '@/lib/format';

export default function ActualDetail() {
  const { projectId, actualId } = useParams();
  const navigate = useNavigate();
  const { data: actual, isLoading, isError, error } = useActual(actualId);

  return (
    <div className="space-y-4 p-4 md:p-6" data-testid="actual-detail-page">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-heading text-2xl text-slate-900">Actual</h1>
        <Button
          variant="outline"
          onClick={() => navigate(`/projects/${projectId}/actuals`)}
          data-testid="actual-detail-back"
        >
          ← Back to list
        </Button>
      </div>

      {isLoading && (
        <div className="rounded-lg border border-slate-200 p-12 text-center text-slate-500">
          Loading…
        </div>
      )}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700">
          Failed to load: {error?.message ?? 'unknown error'}
        </div>
      )}
      {actual && (
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <div className="mb-3 flex items-center gap-3">
            <ActualStatusBadge status={actual.status} />
            <span className="text-sm text-slate-500">{actual.transaction_date}</span>
          </div>
          <h2 className="font-heading text-xl text-slate-900">
            {actual.supplier_name_snapshot}
          </h2>
          <p className="mt-2 text-sm text-slate-700">{actual.description}</p>
          <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-xs text-slate-500">Net</p>
              <p className="tabular font-medium">{fmtGBP(actual.net_amount)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">VAT</p>
              <p className="tabular text-slate-700">{fmtGBP(actual.vat_amount)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Gross</p>
              <p className="tabular font-medium">{fmtGBP(actual.gross_amount)}</p>
            </div>
          </div>
        </div>
      )}
      <div
        data-testid="actual-detail-placeholder"
        className="rounded-md border border-dashed border-slate-300 p-6 text-sm text-slate-500"
      >
        State-machine actions, attachments, and timeline land in §R4.
      </div>
    </div>
  );
}
