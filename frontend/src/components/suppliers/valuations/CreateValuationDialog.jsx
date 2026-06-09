/**
 * <CreateValuationDialog/> — Chat 48 (Build Pack 2.8-FE-ii §R4.8).
 *
 * Create a Draft valuation for a parent subcontract. Money fields are
 * STRINGS on the wire (Pydantic Decimal); the form NEVER does float
 * maths and NEVER previews server-computed figures (retention, CIS,
 * net payable). It collects raw inputs and lets the server certify
 * later.
 *
 * Body (verified ValuationCreateBody):
 *   { subcontract_id, gross_applied_to_date, labour_portion,
 *     materials_portion, period_start?, period_end? }
 *
 * Validation strategy (mirrors the 2.8-FE-i money-input idiom):
 *   - Money: digits + up to one decimal point + at most 2dp (regex).
 *     Client-side guard is a UX nicety; the server is authoritative.
 *   - 422 surfaces from the server are shown verbatim — they carry
 *     the maths messages (e.g. "gross_applied_to_date must be >= 0").
 *   - 409 (parent subcontract Draft/Terminated) shouldn't normally
 *     happen because <ValuationsSection/> hides the "New valuation"
 *     button outside {Active, Completed} — but if a race happens, we
 *     surface the server detail.
 *
 * UX note on labour + materials (Build Pack §R4.4 / §R4.8): the helper
 * text under those fields tells the user the split should reflect the
 * NEW-this-cert gross (the increment), not the cumulative. The form
 * does NOT enforce this — it's the certify-time guard. Plain guidance.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useCreateValuation } from '@/hooks/subcontractValuations';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';


// Money — string in, validated to ≤2dp. Mirrors SubcontractFormDialog.
const MONEY_RE = /^\d+(\.\d{1,2})?$/;
function isValidMoney(s) {
  if (s == null) return false;
  const t = String(s).trim();
  if (t === '') return false;
  return MONEY_RE.test(t);
}


export default function CreateValuationDialog({
  open, onOpenChange, subcontractId,
}) {
  const create = useCreateValuation();

  const [gross, setGross]         = useState('0');
  const [labour, setLabour]       = useState('0');
  const [materials, setMaterials] = useState('0');
  const [periodStart, setPeriodStart] = useState('');
  const [periodEnd,   setPeriodEnd]   = useState('');

  useEffect(() => {
    if (!open) return;
    setGross('0');
    setLabour('0');
    setMaterials('0');
    setPeriodStart('');
    setPeriodEnd('');
  }, [open]);

  const errors = useMemo(() => {
    const e = {};
    if (!isValidMoney(gross))      e.gross = 'Enter a non-negative amount (up to 2 decimal places).';
    if (!isValidMoney(labour))     e.labour = 'Enter a non-negative amount (up to 2 decimal places).';
    if (!isValidMoney(materials))  e.materials = 'Enter a non-negative amount (up to 2 decimal places).';
    if (periodStart && periodEnd && periodEnd < periodStart) {
      e.periodEnd = 'Period end must be on or after period start.';
    }
    return e;
  }, [gross, labour, materials, periodStart, periodEnd]);

  const isValid = Object.keys(errors).length === 0;

  const onSubmit = async () => {
    if (!isValid) return;
    try {
      await create.mutateAsync({
        subcontract_id: subcontractId,
        gross_applied_to_date: gross.trim(),
        labour_portion: labour.trim(),
        materials_portion: materials.trim(),
        period_start: periodStart || null,
        period_end: periodEnd || null,
      });
      toast.success('Valuation created');
      onOpenChange(false);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Save failed';
      const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
      if (status === 409) {
        // Build-pack §R4.5 — state error (parent subcontract not in
        // {Active, Completed}). The hook's onSettled invalidates the
        // list namespace so the displayed status resyncs.
        toast.error(text);
      } else if (status === 422) {
        // Server maths messages — show verbatim.
        toast.error(text);
      } else if (status === 403) {
        toast.error('You don\u2019t have permission to do that.');
      } else if (status === 404) {
        toast.error('That subcontract no longer exists.');
        onOpenChange(false);
      } else {
        toast.error(text);
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="valuation-create-dialog">
        <DialogHeader>
          <DialogTitle>New valuation</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">
              Gross applied to date (£)
            </span>
            <input
              type="text"
              inputMode="decimal"
              className="w-full px-2 py-1 border rounded text-sm tabular-nums"
              value={gross}
              onChange={(e) => setGross(e.target.value)}
              placeholder="0.00"
              data-testid="valuation-create-gross"
            />
            {errors.gross && (
              <span
                className="text-xs text-red-700"
                data-testid="valuation-create-error-gross"
              >{errors.gross}</span>
            )}
            <span className="block text-xs text-sy-grey-600 mt-1">
              Cumulative gross applied so far (including any previously
              certified valuations).
            </span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Labour portion (£)</span>
              <input
                type="text"
                inputMode="decimal"
                className="w-full px-2 py-1 border rounded text-sm tabular-nums"
                value={labour}
                onChange={(e) => setLabour(e.target.value)}
                placeholder="0.00"
                data-testid="valuation-create-labour"
              />
              {errors.labour && (
                <span
                  className="text-xs text-red-700"
                  data-testid="valuation-create-error-labour"
                >{errors.labour}</span>
              )}
            </label>
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Materials portion (£)</span>
              <input
                type="text"
                inputMode="decimal"
                className="w-full px-2 py-1 border rounded text-sm tabular-nums"
                value={materials}
                onChange={(e) => setMaterials(e.target.value)}
                placeholder="0.00"
                data-testid="valuation-create-materials"
              />
              {errors.materials && (
                <span
                  className="text-xs text-red-700"
                  data-testid="valuation-create-error-materials"
                >{errors.materials}</span>
              )}
            </label>
            <span className="col-span-2 text-xs text-sy-grey-600">
              Labour + materials should equal the value being certified
              this period (the increase since the last certified
              valuation). The server checks this at certify time.
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Period start</span>
              <input
                type="date"
                className="w-full px-2 py-1 border rounded text-sm"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                data-testid="valuation-create-period-start"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Period end</span>
              <input
                type="date"
                className="w-full px-2 py-1 border rounded text-sm"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                data-testid="valuation-create-period-end"
              />
              {errors.periodEnd && (
                <span
                  className="text-xs text-red-700"
                  data-testid="valuation-create-error-period-end"
                >{errors.periodEnd}</span>
              )}
            </label>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="valuation-create-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!isValid || create.isPending}
            onClick={onSubmit}
            data-testid="valuation-create-submit"
          >Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
