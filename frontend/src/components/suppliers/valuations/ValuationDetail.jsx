/**
 * <ValuationDetail/> — Chat 48 (Build Pack 2.8-FE-ii §R4.3).
 *
 * Detail panel for a selected valuation. Shows non-sensitive fields
 * always and the 5 SENSITIVE money fields only with
 * `subcontract_valuations.view_sensitive` (the backend nulls the keys
 * without the perm; we defence-in-depth check both the perm AND the
 * value being non-null).
 *
 * Sensitive (gated):  previous_certified_net, retention_this_cert,
 *                     cis_rate_pct, cis_deduction_this_cert,
 *                     net_payable_this_cert
 * Non-sensitive:      everything else, INCLUDING `retention_rate_pct`
 *                     and `over_claim_flag` — they're in the
 *                     SENSITIVE_FIELDS constant server-side but
 *                     emitted in the non-sensitive base block (see
 *                     Build Pack §R0.3 note). Treat them as visible
 *                     to all view users.
 *
 * Lifecycle action buttons (Build Pack §R4.3 — valid-transition-only):
 *   Draft       → Submit         (gated canSubmitValuation = .create)
 *   Submitted   → Certify, Reject (both gated canCertifyValuation = .certify)
 *   Certified   → no lifecycle buttons (terminal); PayLess via the
 *                 PaymentNoticesPanel which renders the "+ Issue PayLess"
 *                 button gated by `payment_notices.create`.
 *   Rejected    → no lifecycle buttons; show `rejection_reason`.
 *
 * 409 handling: each transition mutates via the hook (onSettled
 * invalidates so the badge resyncs); the dialog wrappers surface the
 * server `detail`. 422 surfaces server `detail` verbatim (those are
 * the maths messages — the certify guard).
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import {
  useValuation, useSubmitValuation,
} from '@/hooks/subcontractValuations';
import {
  canViewValuationSums,
  canSubmitValuation,
  canCertifyValuation,
  canRejectValuation,
  nextActionsForValuationStatus,
} from '@/lib/poCapability';
import { fmtGBP } from '@/lib/format';
import { formatDate } from '@/lib/cisFormat';

import ValuationStatusPill from './ValuationStatusPill';
import CertifyValuationDialog from './CertifyValuationDialog';
import RejectValuationDialog from './RejectValuationDialog';
import PaymentNoticesPanel from './PaymentNoticesPanel';


function Field({ label, value, className = '', testid }) {
  return (
    <div className={`text-sm ${className}`}>
      <div className="text-xs text-sy-grey-700">{label}</div>
      <div className="tabular-nums" data-testid={testid}>{value}</div>
    </div>
  );
}

function fmtPct(p) {
  if (p == null) return '\u2014';
  const n = Number(p);
  if (!Number.isFinite(n)) return '\u2014';
  return `${n}%`;
}


export default function ValuationDetail({ valuationId, projectId }) {
  const { me } = useAuth();
  const canSensitive = canViewValuationSums(me);

  // Keep detail fresh — hook key is per-id; invalidation by the
  // lifecycle mutations resyncs the displayed status.
  const detailQ = useValuation(valuationId, { enabled: !!valuationId });
  const v = detailQ.data;

  // ─── Lifecycle dialogs ────────────────────────────────────────────
  const submit = useSubmitValuation(valuationId);
  const [certifyOpen, setCertifyOpen] = useState(false);
  const [rejectOpen,  setRejectOpen]  = useState(false);

  // Close dialogs if the underlying valuation changes (selection swap).
  useEffect(() => {
    setCertifyOpen(false);
    setRejectOpen(false);
  }, [valuationId]);

  if (!valuationId) {
    return (
      <div
        className="p-4 text-sm text-sy-grey-600 border rounded"
        data-testid="valuation-detail-empty"
      >
        Select a valuation to view its details.
      </div>
    );
  }

  if (detailQ.isLoading) {
    return (
      <div className="p-4 text-sm" data-testid="valuation-detail-loading">
        {'Loading valuation\u2026'}
      </div>
    );
  }

  if (detailQ.isError || !v) {
    return (
      <div className="p-4 text-sm text-red-700" data-testid="valuation-detail-error">
        Failed to load this valuation.
      </div>
    );
  }

  const allowed = nextActionsForValuationStatus(v.status);
  const showSubmit  = allowed.includes('submit')  && canSubmitValuation(me);
  const showCertify = allowed.includes('certify') && canCertifyValuation(me);
  const showReject  = allowed.includes('reject')  && canRejectValuation(me);

  const onSubmitClick = async () => {
    try {
      await submit.mutateAsync();
      toast.success('Valuation submitted');
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Submit failed';
      const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
      if (status === 409) {
        toast.error(text);
      } else if (status === 422) {
        toast.error(text);
      } else if (status === 403) {
        toast.error('You don\u2019t have permission to do that.');
      } else if (status === 404) {
        toast.error('That valuation no longer exists.');
      } else {
        toast.error(text);
      }
    }
  };

  return (
    <div
      className="p-4 border rounded space-y-4 min-w-0"
      data-testid={`valuation-detail-${v.id}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-sy-grey-700">
            {v.reference ?? '\u2014'} (#{v.valuation_number ?? '\u2014'})
          </div>
          <h4 className="text-base font-semibold">
            Valuation
          </h4>
          <div className="mt-1">
            <ValuationStatusPill
              status={v.status}
              testid="valuation-detail-status"
            />
          </div>
        </div>
      </header>

      {/* Over-claim warning — non-sensitive, visible to all view users. */}
      {v.over_claim_flag && (
        <div
          className="p-2 border border-amber-300 bg-amber-50 rounded text-sm"
          data-testid="valuation-detail-overclaim-banner"
        >
          <div className="font-semibold text-amber-900">Over-claim flagged</div>
          {v.over_claim_note && (
            <div className="text-amber-900">{v.over_claim_note}</div>
          )}
        </div>
      )}

      <section className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Field
          label="Period"
          value={
            v.period_start || v.period_end
              ? `${formatDate(v.period_start)} \u2013 ${formatDate(v.period_end)}`
              : '\u2014'
          }
          testid="valuation-detail-period"
        />
        <Field
          label="Retention rate"
          value={fmtPct(v.retention_rate_pct)}
          testid="valuation-detail-retention-rate"
        />
        <Field
          label="Gross applied to date"
          value={fmtGBP(v.gross_applied_to_date) ?? '\u2014'}
          testid="valuation-detail-gross-applied"
        />
        <Field
          label="Labour portion"
          value={fmtGBP(v.labour_portion) ?? '\u2014'}
          testid="valuation-detail-labour"
        />
        <Field
          label="Materials portion"
          value={fmtGBP(v.materials_portion) ?? '\u2014'}
          testid="valuation-detail-materials"
        />
        <Field
          label="Gross this cert"
          value={fmtGBP(v.gross_this_cert) ?? '\u2014'}
          testid="valuation-detail-gross-this-cert"
        />

        {/* ─── Sensitive (5 fields) ─────────────────────────────────
            Backend nulls these keys without the perm; we
            defence-in-depth check the perm AND value being non-null. */}
        <Field
          label="Previous certified net"
          value={
            (canSensitive && v.previous_certified_net != null)
              ? (fmtGBP(v.previous_certified_net) ?? '\u2014')
              : '\u2014'
          }
          testid="valuation-detail-prev-net"
        />
        <Field
          label="Retention this cert"
          value={
            (canSensitive && v.retention_this_cert != null)
              ? (fmtGBP(v.retention_this_cert) ?? '\u2014')
              : '\u2014'
          }
          testid="valuation-detail-retention"
        />
        <Field
          label="CIS rate"
          value={
            (canSensitive && v.cis_rate_pct != null)
              ? fmtPct(v.cis_rate_pct)
              : '\u2014'
          }
          testid="valuation-detail-cis-rate"
        />
        <Field
          label="CIS deduction"
          value={
            (canSensitive && v.cis_deduction_this_cert != null)
              ? (fmtGBP(v.cis_deduction_this_cert) ?? '\u2014')
              : '\u2014'
          }
          testid="valuation-detail-cis-deduction"
        />
        <Field
          label="Net payable this cert"
          className="col-span-2 md:col-span-3"
          value={
            (canSensitive && v.net_payable_this_cert != null)
              ? <span className="text-base font-semibold">{fmtGBP(v.net_payable_this_cert) ?? '\u2014'}</span>
              : '\u2014'
          }
          testid="valuation-detail-net-payable"
        />
      </section>

      {/* Rejected → show the rejection_reason. */}
      {v.status === 'Rejected' && v.rejection_reason && (
        <div
          className="p-2 border border-red-200 bg-red-50 rounded text-sm"
          data-testid="valuation-detail-rejection-reason"
        >
          <div className="font-semibold text-red-800">Rejected</div>
          <div className="text-red-900 whitespace-pre-wrap">{v.rejection_reason}</div>
        </div>
      )}

      {/* ─── Lifecycle action buttons — valid-transition-only ────────── */}
      {(showSubmit || showCertify || showReject) && (
        <section
          className="flex flex-wrap gap-2 pt-3 border-t"
          data-testid="valuation-actions"
        >
          {showSubmit && (
            <button
              type="button"
              onClick={onSubmitClick}
              disabled={submit.isPending}
              className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
              data-testid="valuation-actions-submit-btn"
            >Submit</button>
          )}
          {showCertify && (
            <button
              type="button"
              onClick={() => setCertifyOpen(true)}
              className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
              data-testid="valuation-actions-certify-btn"
            >Certify</button>
          )}
          {showReject && (
            <button
              type="button"
              onClick={() => setRejectOpen(true)}
              className="px-3 py-1.5 rounded border text-red-700 text-sm"
              data-testid="valuation-actions-reject-btn"
            >Reject</button>
          )}
        </section>
      )}

      {/* Certified → no lifecycle buttons; show notices + PayLess. */}
      <PaymentNoticesPanel
        valuationId={v.id}
        valuationStatus={v.status}
      />

      {/* Dialogs (mounted lazily via open prop). */}
      <CertifyValuationDialog
        open={certifyOpen}
        onOpenChange={setCertifyOpen}
        valuationId={v.id}
        projectId={projectId}
      />
      <RejectValuationDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        valuationId={v.id}
      />
    </div>
  );
}
