/**
 * LifecycleActions — Prompt 2.4B-i §R5.3.
 *
 * Lifecycle buttons gated by:
 *   1. desktop (useIsDesktop — mobile floor is read-only)
 *   2. status (per backend transitions, see lib/budgetCapability.js)
 *   3. permission (budgets.edit for activate/lock/close/new-version;
 *      budgets.admin for unlock — per backend deps verified 2026-05-10)
 *
 * Brand convention (locked decision 8):
 *   - Activate / Lock        → bg-sy-teal text-white hover:brightness-110
 *   - Unlock / Close / NewV  → bg-sy-orange text-white hover:brightness-110
 *
 * Lock without confirm (§R5.6 pushback) is the chosen default: locking
 * is reversible by admin Unlock; over-confirming trains click-through.
 *
 * New Version requires a `version_label` (backend constraint) in addition
 * to the audit reason; we render an extra input via ConfirmDialog's
 * `renderExtraFields` render-prop.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import {
  useActivateBudget,
  useLockBudget,
  useUnlockBudget,
  useCloseBudget,
  useCreateNewBudgetVersion,
} from '@/hooks/budgets';
import {
  canActivate, canLock, canUnlock, canClose, canCreateNewVersion,
} from '@/lib/budgetCapability';
import { ConfirmDialog } from './ConfirmDialog';

const TEAL = 'bg-sy-teal text-white hover:brightness-110 active:brightness-95';
const ORNG = 'bg-sy-orange text-white hover:brightness-110 active:brightness-95';

export function LifecycleActions({ budget, projectId }) {
  const { me } = useAuth();
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();

  const activate = useActivateBudget(budget.id, projectId);
  const lock     = useLockBudget(budget.id, projectId);
  const unlock   = useUnlockBudget(budget.id, projectId);
  const close    = useCloseBudget(budget.id, projectId);
  const newVer   = useCreateNewBudgetVersion(budget.id, projectId);

  // Track new-version-only form state via closure (ConfirmDialog
  // doesn't own the field; we keep it here so `extraValid` can read it).
  const [newVersionLabel, setNewVersionLabel] = useState(
    `v${(budget.version_number ?? 0) + 1}`,
  );

  // Mobile floor: no actions at all.
  if (!isDesktop) return null;

  const showActivate = canActivate(me, budget.status);
  const showLock     = canLock(me, budget.status);
  const showUnlock   = canUnlock(me, budget.status);
  const showClose    = canClose(me, budget.status);
  const showNewVer   = canCreateNewVersion(me, budget.status);

  if (!showActivate && !showLock && !showUnlock && !showClose && !showNewVer) {
    return null;
  }

  const isPending = activate.isPending || lock.isPending
    || unlock.isPending || close.isPending || newVer.isPending;

  return (
    <div
      data-testid="lifecycle-actions"
      className="flex flex-wrap items-center gap-2"
    >
      {showActivate && (
        <Button
          className={TEAL}
          disabled={isPending}
          onClick={() => activate.mutate({})}
          data-testid="lifecycle-activate"
        >
          {activate.isPending ? 'Activating…' : 'Activate'}
        </Button>
      )}

      {showLock && (
        <Button
          className={TEAL}
          disabled={isPending}
          onClick={() => lock.mutate({})}
          data-testid="lifecycle-lock"
        >
          {lock.isPending ? 'Locking…' : 'Lock'}
        </Button>
      )}

      {showUnlock && (
        <ConfirmDialog
          title="Unlock budget?"
          description="Unlocking returns the budget to Active and reopens lines for edit. The action is audit-logged with the reason."
          confirmLabel="Unlock"
          requireReason
          variant="destructive"
          isPending={unlock.isPending}
          testId="lifecycle-unlock-dialog"
          onConfirm={() => unlock.mutateAsync({})}
          trigger={
            <Button
              className={ORNG}
              disabled={isPending}
              data-testid="lifecycle-unlock"
            >
              Unlock
            </Button>
          }
        />
      )}

      {showClose && (
        <ConfirmDialog
          title="Close budget?"
          description="Closing freezes the budget permanently. No further edits or version bumps from this version."
          confirmLabel="Close budget"
          requireReason
          variant="destructive"
          isPending={close.isPending}
          testId="lifecycle-close-dialog"
          onConfirm={() => close.mutateAsync({})}
          trigger={
            <Button
              className={ORNG}
              disabled={isPending}
              data-testid="lifecycle-close"
            >
              Close
            </Button>
          }
        />
      )}

      {showNewVer && (
        <ConfirmDialog
          title="Create new version?"
          description="A new Draft will be created with current lines and items cloned. This budget will be marked Superseded."
          confirmLabel="Create new version"
          requireReason
          variant="destructive"
          isPending={newVer.isPending}
          testId="lifecycle-newver-dialog"
          extraValid={() => newVersionLabel.trim().length > 0
            && newVersionLabel.trim().length <= 50}
          renderExtraFields={({ disabled }) => (
            <div className="space-y-1">
              <Label htmlFor="lifecycle-newver-label">
                New version label
              </Label>
              <Input
                id="lifecycle-newver-label"
                data-testid="lifecycle-newver-label-input"
                value={newVersionLabel}
                maxLength={50}
                disabled={disabled}
                onChange={(e) => setNewVersionLabel(e.target.value)}
                placeholder="e.g. v2 — post-tender"
              />
            </div>
          )}
          onConfirm={async (reason) => {
            const label = newVersionLabel.trim();
            const newDraft = await newVer.mutateAsync({
              version_label: label,
              notes: reason || undefined,
            });
            if (newDraft?.id) {
              navigate(`/projects/${projectId}/budgets/${newDraft.id}`);
            }
          }}
          trigger={
            <Button
              className={ORNG}
              disabled={isPending}
              data-testid="lifecycle-newver"
            >
              New version
            </Button>
          }
        />
      )}
    </div>
  );
}
