/**
 * <CertifyValuationDialog/> — Chat 48 (Build Pack 2.8-FE-ii §R4.4).
 *
 * The CAREFUL one. This dialog enforces the platform's hardest
 * financial-correctness rail: a valuation cannot be certified without
 * an explicit budget-line selection. The backend REFUSES to guess.
 *
 * Body (verified ValuationCertifyBody):
 *   { budget_line_id  (uuid, REQUIRED),
 *     transaction_date (date | null),
 *     description     (str | null, <= 500) }
 *
 * UX hardening (Build Pack §R4.4):
 *   - Confirm button is DISABLED until a budget line is selected.
 *   - If the reused <BudgetLinePicker/> renders its
 *     `budget-line-picker-empty` state (no Active/Locked budget on
 *     this project), the confirm stays disabled and we show a clear
 *     message — the picker itself displays the empty-budget hint, we
 *     just don't allow the user to bash the button.
 *   - 422 from the server (the certify maths guards — gross went
 *     backwards, labour+materials mismatch, net negative) is
 *     surfaced VERBATIM. Those messages are user-meaningful, name
 *     the figures, and tell the user exactly what's wrong.
 *   - 409 (state error: not Submitted, or budget_line not on the
 *     project) is surfaced and the hook invalidates so the badge
 *     resyncs.
 *
 * Reuse:
 *   - <BudgetLinePicker/> from components/actuals/BudgetLinePicker.jsx
 *     (Chat 19B §R3.1). Wraps useProjectBudgets + useBudget
 *     (hooks/budgets.js) which hit /v1/projects/{id}/budgets and
 *     /v1/budgets/{id} — verified paths, not hand-rolled.
 *   - Filtered to the SUBCONTRACT'S project_id (backend rule:
 *     "budget_line is not on the subcontract's project" → 409).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useCertifyValuation } from '@/hooks/subcontractValuations';
import { BudgetLinePicker } from '@/components/actuals/BudgetLinePicker';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';


export default function CertifyValuationDialog({
  open, onOpenChange, valuationId, projectId,
}) {
  const certify = useCertifyValuation(valuationId);

  const [budgetLineId, setBudgetLineId] = useState(null);
  const [txDate, setTxDate]             = useState('');
  const [description, setDescription]   = useState('');

  useEffect(() => {
    if (!open) return;
    setBudgetLineId(null);
    setTxDate('');
    setDescription('');
  }, [open]);

  // Confirm is enabled ONLY when a budget line is chosen. This is the
  // hard client-side rail behind the backend's REQUIRED budget_line_id
  // rule — the dialog must make it impossible for the user to POST a
  // certify call without a line. The backend 409s as a backstop.
  const canConfirm = useMemo(() => {
    if (!budgetLineId) return false;
    if (description && description.length > 500) return false;
    return true;
  }, [budgetLineId, description]);

  const onConfirm = async () => {
    if (!canConfirm) return;
    try {
      // Build the body explicitly — only include the keys we want on
      // the wire. transaction_date and description go as null when
      // blank (Pydantic accepts either; null is the documented value).
      const body = {
        budget_line_id: budgetLineId,
        transaction_date: txDate || null,
        description: description.trim() || null,
      };
      await certify.mutateAsync(body);
      toast.success('Valuation certified — a payment notice has been issued');
      onOpenChange(false);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Certify failed';
      const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
      if (status === 409) {
        // STATE error: not Submitted, budget_line not on project, or
        // (backstop) missing budget_line_id. The hook's onSettled
        // already invalidates so the badge resyncs after the toast.
        toast.error(text);
      } else if (status === 422) {
        // The maths guards — show server detail verbatim. These name
        // figures and are user-meaningful.
        toast.error(text);
      } else if (status === 403) {
        toast.error('You don\u2019t have permission to do that.');
      } else if (status === 404) {
        toast.error('That valuation no longer exists.');
        onOpenChange(false);
      } else {
        toast.error(text);
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="valuation-certify-dialog">
        <DialogHeader>
          <DialogTitle>Certify this valuation</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-sy-grey-700">
            Certifying records the increment as an actual cost on the
            selected budget line and issues a payment notice. The server
            computes retention, CIS and net payable.
          </p>

          <div className="block text-sm">
            <span className="text-xs text-sy-grey-700 block mb-1">
              Budget line *
            </span>
            <BudgetLinePicker
              projectId={projectId}
              value={budgetLineId}
              onChange={setBudgetLineId}
            />
            {!budgetLineId && (
              <span
                className="text-xs text-sy-grey-600 block mt-1"
                data-testid="valuation-certify-budget-line-required"
              >
                Select a budget line to enable Certify.
              </span>
            )}
          </div>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Transaction date (optional)</span>
            <input
              type="date"
              className="w-full px-2 py-1 border rounded text-sm"
              value={txDate}
              onChange={(e) => setTxDate(e.target.value)}
              data-testid="valuation-certify-tx-date"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">
              Description (optional, max 500 chars)
            </span>
            <Textarea
              rows={2}
              value={description}
              maxLength={500}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="valuation-certify-description"
            />
          </label>
        </div>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="valuation-certify-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!canConfirm || certify.isPending}
            onClick={onConfirm}
            data-testid="valuation-certify-confirm"
          >Certify</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
