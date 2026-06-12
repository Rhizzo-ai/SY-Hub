/**
 * Review & Save modal — B83 §R4 (D8/D9).
 *
 * Lists per-role adds (green) and removes (red); sensitive adds are
 * highlighted orange with their consequence line; any role ending at
 * ZERO permissions requires an explicit checkbox confirm (3A guard ii).
 *
 * Save = ONE transactional batch call owned by the page. On ANY error the
 * page keeps the draft intact and passes the message down — it renders
 * inline here (plus a toast at the call site). No silent onError.
 */
import React, { useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Plus, Minus } from 'lucide-react';
import { consequenceFor } from '@/components/admin/permissionConsequences';

export default function RoleReviewModal({
  open, onOpenChange, diffs, permsByCode, saving, saveError, onConfirm,
}) {
  // diffs: [{ role, adds: [codes], removes: [codes], endsAtZero: bool }]
  const zeroRoles = diffs.filter((d) => d.endsAtZero);
  // Mounted fresh on each open (parent renders conditionally).
  const [zeroConfirmed, setZeroConfirmed] = useState(false);

  const totalChanges = diffs.reduce(
    (n, d) => n + d.adds.length + d.removes.length, 0,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-2xl max-h-[85vh] overflow-y-auto max-sm:h-full max-sm:max-h-full max-sm:w-full max-sm:max-w-full max-sm:rounded-none"
        data-testid="review-modal"
      >
        <DialogHeader>
          <DialogTitle>Review changes</DialogTitle>
          <DialogDescription>
            {totalChanges} change{totalChanges === 1 ? '' : 's'} across{' '}
            {diffs.length} role{diffs.length === 1 ? '' : 's'}. Saved as one
            all-or-nothing batch.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {diffs.map((d) => (
            <div key={d.role.id} className="rounded-lg border border-slate-200 p-3" data-testid={`review-role-${d.role.code}`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-sm text-slate-900">{d.role.name}</span>
                <span className="font-mono text-xs text-slate-500">{d.role.code}</span>
              </div>
              <ul className="space-y-1">
                {d.adds.map((code) => {
                  const perm = permsByCode[code];
                  const consequence = consequenceFor(perm);
                  return (
                    <li key={`add-${code}`} className="text-sm" data-testid={`review-add-${d.role.code}-${code}`}>
                      <span className={`inline-flex items-center gap-1.5 ${perm?.is_sensitive ? 'text-[#FC7827] font-medium' : 'text-emerald-700'}`}>
                        <Plus size={13} />
                        <span className="font-mono text-xs">{code}</span>
                        {perm?.is_sensitive && (
                          <AlertTriangle size={13} className="text-[#FC7827]" />
                        )}
                      </span>
                      {consequence && (
                        <div className="ml-6 text-xs text-[#FC7827]" data-testid={`review-consequence-${code}`}>
                          {consequence}
                        </div>
                      )}
                    </li>
                  );
                })}
                {d.removes.map((code) => (
                  <li key={`rm-${code}`} className="text-sm" data-testid={`review-remove-${d.role.code}-${code}`}>
                    <span className="inline-flex items-center gap-1.5 text-rose-700">
                      <Minus size={13} />
                      <span className="font-mono text-xs">{code}</span>
                    </span>
                  </li>
                ))}
              </ul>
              {d.endsAtZero && (
                <div className="mt-2 flex items-start gap-2 rounded-md border border-[#FC7827]/40 bg-orange-50 px-3 py-2 text-xs text-orange-900" data-testid={`review-zero-warning-${d.role.code}`}>
                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[#FC7827]" />
                  <span>
                    <strong>{d.role.name}</strong> will end with ZERO
                    permissions — holders of this role will lose all access.
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>

        {zeroRoles.length > 0 && (
          <label className="flex items-start gap-2 text-sm text-slate-800 cursor-pointer select-none" data-testid="review-zero-confirm-label">
            <input
              type="checkbox"
              className="mt-0.5 accent-[#FC7827]"
              checked={zeroConfirmed}
              onChange={(e) => setZeroConfirmed(e.target.checked)}
              data-testid="review-zero-confirm"
            />
            <span>
              I understand {zeroRoles.length === 1
                ? `“${zeroRoles[0].role.name}” will be left`
                : `${zeroRoles.length} roles will be left`} with no
              permissions at all.
            </span>
          </label>
        )}

        {saveError && (
          <div
            className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800"
            role="alert"
            data-testid="review-save-error"
          >
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>
              <strong>Save failed — nothing was applied.</strong> {saveError}
              <br />
              Your draft is preserved; fix the issue and save again.
            </span>
          </div>
        )}

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving}
            data-testid="review-cancel"
          >
            Back
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={saving || (zeroRoles.length > 0 && !zeroConfirmed)}
            className="bg-[#0F6A7A] hover:bg-[#0c5563] text-white"
            data-testid="review-confirm-save"
          >
            {saving ? 'Saving…' : `Save ${totalChanges} change${totalChanges === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
