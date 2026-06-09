/**
 * <PaymentNoticesPanel/> — Chat 48 (Build Pack 2.8-FE-ii §R4.6).
 *
 * Lists the payment notices for a Certified valuation. Shows the
 * auto-created 'Payment' notice (issued by the backend at certify
 * time) and any 'PayLess' notices issued against it.
 *
 * Permission gating:
 *   - View list:   `payment_notices.view`     (canViewPaymentNotices)
 *   - Issue PayLess: `payment_notices.create` (canCreatePayLess)
 *
 * Backend gating note (verified routers/payment_notices.py): the
 * notice serialiser itself has NO sensitive field gating — view is
 * route-level. All amounts show to anyone with the view perm.
 *
 * The "Issue PayLess" button is only shown when the parent valuation
 * is Certified (state); the backend 409s on a non-Certified one as
 * a backstop.
 */
import React, { useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { usePaymentNotices } from '@/hooks/paymentNotices';
import {
  canViewPaymentNotices, canCreatePayLess,
} from '@/lib/poCapability';
import { fmtGBP } from '@/lib/format';
import { formatDate } from '@/lib/cisFormat';

import PayLessNoticeDialog from './PayLessNoticeDialog';


function NoticeTypeBadge({ type }) {
  const cls = type === 'PayLess'
    ? 'bg-red-100 text-red-800'
    : 'bg-sy-teal-100 text-sy-teal-800';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}
      data-testid={`notice-type-${type}`}
    >
      {type}
    </span>
  );
}


export default function PaymentNoticesPanel({ valuationId, valuationStatus }) {
  const { me } = useAuth();
  const canView = canViewPaymentNotices(me);
  const canPayless = canCreatePayLess(me) && valuationStatus === 'Certified';

  const [payLessOpen, setPayLessOpen] = useState(false);

  const isCertified = valuationStatus === 'Certified';

  const noticesQ = usePaymentNotices(valuationId, {
    enabled: canView && isCertified,
  });

  if (!canView) {
    return null;  // silent — the section above already shows the valuation
  }

  if (!isCertified) {
    return null;  // notices only meaningful for Certified valuations
  }

  const items = noticesQ.data?.items ?? [];

  return (
    <section
      className="space-y-2 pt-3 border-t"
      data-testid="payment-notices-panel"
    >
      <header className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold">Payment notices</h4>
        {canPayless && (
          <button
            type="button"
            className="px-3 py-1.5 rounded border text-sm"
            onClick={() => setPayLessOpen(true)}
            data-testid="payment-notices-payless-btn"
          >
            + Issue PayLess notice
          </button>
        )}
      </header>

      <div className="border rounded min-w-0 overflow-x-auto" data-testid="payment-notices-table-wrap">
        {noticesQ.isLoading && (
          <div className="p-3 text-sm" data-testid="payment-notices-loading">
            {'Loading\u2026'}
          </div>
        )}
        {noticesQ.isError && (
          <div className="p-3 text-sm text-red-700" data-testid="payment-notices-error">
            Failed to load notices.
          </div>
        )}
        {!noticesQ.isLoading && !noticesQ.isError && (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-xs text-sy-grey-700 border-b">
                <th className="py-2 px-2 w-28">Reference</th>
                <th className="py-2 px-2 w-24">Type</th>
                <th className="py-2 px-2 text-right">Gross certified</th>
                <th className="py-2 px-2 text-right">Retention</th>
                <th className="py-2 px-2 text-right">CIS</th>
                <th className="py-2 px-2 text-right">Net due</th>
                <th className="py-2 px-2 w-28">Due date</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="py-3 px-2 text-sy-grey-500"
                    data-testid="payment-notices-empty"
                  >
                    No payment notices yet.
                  </td>
                </tr>
              )}
              {items.map((n) => (
                <tr key={n.id} className="border-b last:border-0" data-testid={`payment-notice-row-${n.id}`}>
                  <td className="py-2 px-2 tabular-nums">{n.reference ?? '\u2014'}</td>
                  <td className="py-2 px-2"><NoticeTypeBadge type={n.notice_type} /></td>
                  <td className="py-2 px-2 text-right tabular-nums">{fmtGBP(n.gross_certified) ?? '\u2014'}</td>
                  <td className="py-2 px-2 text-right tabular-nums">{fmtGBP(n.retention) ?? '\u2014'}</td>
                  <td className="py-2 px-2 text-right tabular-nums">{fmtGBP(n.cis_deducted) ?? '\u2014'}</td>
                  <td className="py-2 px-2 text-right tabular-nums font-semibold" data-testid={`payment-notice-row-${n.id}-net-due`}>
                    {fmtGBP(n.net_due) ?? '\u2014'}
                  </td>
                  <td className="py-2 px-2">{formatDate(n.due_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <PayLessNoticeDialog
        open={payLessOpen}
        onOpenChange={setPayLessOpen}
        valuationId={valuationId}
      />
    </section>
  );
}
