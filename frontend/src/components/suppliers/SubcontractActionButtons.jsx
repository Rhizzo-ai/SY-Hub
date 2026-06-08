/**
 * <SubcontractActionButtons/> — Chat 47 (Build Pack 2.8-FE-i §R4.3).
 *
 * Single source of truth for which lifecycle buttons render on a
 * subcontract detail panel. Mirrors the POActionButtons.jsx pattern.
 *
 * Action matrix (build-pack §R4.3 — valid-transition-only):
 *   Draft       → Activate, Terminate
 *   Active      → Complete, Terminate
 *   Completed   → (terminal — muted line, no buttons)
 *   Terminated  → (terminal — muted line, no buttons)
 *
 * Perm gating (post-FLAG-1b reconciliation, see CHANGELOG §2.8-FE-i):
 *   Activate    → subcontracts.approve              (canActivateSubcontract)
 *   Complete    → subcontracts.edit OR approve      (canCompleteSubcontract)
 *   Terminate   → subcontracts.approve              (canTerminateSubcontract)
 *
 * 409 handling (build-pack §R4.5 + FLAG 2a):
 *   - Activate against an unsigned subcontract returns 409
 *     'Cannot activate an unsigned subcontract …'. We surface a
 *     human-readable message that points the user at the Edit form.
 *   - Other 409s pass through the server `detail` and we still
 *     invalidate (via the hook's onSettled) so the badge resyncs.
 */
import React, { useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import {
  useActivateSubcontract,
  useCompleteSubcontract,
  useTerminateSubcontract,
} from '@/hooks/subcontracts';
import {
  canActivateSubcontract,
  canCompleteSubcontract,
  canTerminateSubcontract,
} from '@/lib/poCapability';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

const BTN_BASE     = 'px-3 py-1.5 rounded text-sm';
const BTN_PRIMARY  = `${BTN_BASE} bg-sy-teal-600 text-white`;
const BTN_OUTLINE  = `${BTN_BASE} border`;
const BTN_DANGER   = `${BTN_BASE} border text-red-700`;

// FLAG 2a — the activate 409 message we re-write into something the
// user can actually act on. Matches the literal string the backend
// raises in services/subcontracts.py:524-526 (kept loose with
// `includes` so a small backend tweak doesn't break this guard).
const UNSIGNED_HINT = /unsigned/i;
function friendlyActivateError(err) {
  const detail =
    err?.response?.data?.detail?.message ??
    err?.response?.data?.detail ??
    err?.message ?? 'Activation failed';
  const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
  if (UNSIGNED_HINT.test(text)) {
    return 'A signed date is required before this subcontract can be activated. Edit the subcontract to set it.';
  }
  return text;
}

function friendlyError(err, fallback = 'Action failed') {
  const detail =
    err?.response?.data?.detail?.message ??
    err?.response?.data?.detail ??
    err?.message ?? fallback;
  return typeof detail === 'string' ? detail : JSON.stringify(detail);
}


export default function SubcontractActionButtons({ subcontract, onChanged }) {
  const { me } = useAuth();
  const status = subcontract?.status;

  const activate  = useActivateSubcontract(subcontract?.id);
  const complete  = useCompleteSubcontract(subcontract?.id);
  const terminate = useTerminateSubcontract(subcontract?.id);

  const [confirmOpen, setConfirmOpen] = useState(null); // 'activate'|'complete'|'terminate'|null

  const isDraft     = status === 'Draft';
  const isActive    = status === 'Active';
  const isTerminal  = status === 'Completed' || status === 'Terminated';

  const showActivate  = isDraft  && canActivateSubcontract(me);
  const showComplete  = isActive && canCompleteSubcontract(me);
  const showTerminate = (isDraft || isActive) && canTerminateSubcontract(me);

  const runAction = async (verb) => {
    try {
      if (verb === 'activate') {
        await activate.mutateAsync();
        toast.success('Subcontract activated');
      } else if (verb === 'complete') {
        await complete.mutateAsync();
        toast.success('Subcontract completed');
      } else if (verb === 'terminate') {
        await terminate.mutateAsync();
        toast.success('Subcontract terminated');
      }
      onChanged?.();
    } catch (err) {
      // Build-pack §R4.5 — 409 = state error, treat distinctly from 422.
      // The hook's onSettled has already invalidated the detail+list so
      // the displayed status will resync once the user dismisses the
      // toast — that's the build-pack 'refetch to resync' contract.
      const status409 = err?.response?.status === 409;
      let msg;
      if (verb === 'activate') {
        msg = friendlyActivateError(err);
      } else if (status409) {
        msg = friendlyError(err, 'Action not allowed in current status');
      } else {
        msg = friendlyError(err);
      }
      toast.error(msg);
    } finally {
      setConfirmOpen(null);
    }
  };

  // ── Terminal line (no buttons) ──────────────────────────────────
  if (isTerminal) {
    return (
      <p
        className="text-sm text-sy-grey-600 italic"
        data-testid="subcontract-actions-terminal-line"
      >
        This subcontract is {status}.
      </p>
    );
  }

  return (
    <>
      <div className="flex flex-wrap gap-2" data-testid="subcontract-actions">
        {showActivate && (
          <button
            type="button"
            onClick={() => setConfirmOpen('activate')}
            disabled={activate.isPending}
            className={BTN_PRIMARY}
            data-testid="subcontract-actions-activate-btn"
          >Activate</button>
        )}
        {showComplete && (
          <button
            type="button"
            onClick={() => setConfirmOpen('complete')}
            disabled={complete.isPending}
            className={BTN_PRIMARY}
            data-testid="subcontract-actions-complete-btn"
          >Complete</button>
        )}
        {showTerminate && (
          <button
            type="button"
            onClick={() => setConfirmOpen('terminate')}
            disabled={terminate.isPending}
            className={BTN_DANGER}
            data-testid="subcontract-actions-terminate-btn"
          >Terminate</button>
        )}
      </div>

      {/* Activate confirm */}
      <Dialog
        open={confirmOpen === 'activate'}
        onOpenChange={(o) => !o && setConfirmOpen(null)}
      >
        <DialogContent data-testid="subcontract-activate-dialog">
          <DialogHeader>
            <DialogTitle>Activate this subcontract?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            Activating moves the subcontract from <b>Draft</b> to
            <b> Active</b>. The signed date must already be set on the
            contract; if it isn’t, you’ll be prompted to set it via Edit.
          </p>
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setConfirmOpen(null)}
              data-testid="subcontract-activate-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={activate.isPending}
              onClick={() => runAction('activate')}
              data-testid="subcontract-activate-confirm"
            >Activate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Complete confirm */}
      <Dialog
        open={confirmOpen === 'complete'}
        onOpenChange={(o) => !o && setConfirmOpen(null)}
      >
        <DialogContent data-testid="subcontract-complete-dialog">
          <DialogHeader>
            <DialogTitle>Complete this subcontract?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            Completing moves the subcontract from <b>Active</b> to
            <b> Completed</b>. This is a terminal status — no further
            edits or transitions will be possible.
          </p>
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setConfirmOpen(null)}
              data-testid="subcontract-complete-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={complete.isPending}
              onClick={() => runAction('complete')}
              data-testid="subcontract-complete-confirm"
            >Complete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Terminate confirm */}
      <Dialog
        open={confirmOpen === 'terminate'}
        onOpenChange={(o) => !o && setConfirmOpen(null)}
      >
        <DialogContent data-testid="subcontract-terminate-dialog">
          <DialogHeader>
            <DialogTitle>Terminate this subcontract?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            Termination is a <b>terminal</b> status. The subcontract
            cannot be reopened afterwards.
          </p>
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setConfirmOpen(null)}
              data-testid="subcontract-terminate-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={terminate.isPending}
              onClick={() => runAction('terminate')}
              className="bg-red-600 hover:bg-red-700 text-white"
              data-testid="subcontract-terminate-confirm"
            >Terminate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
