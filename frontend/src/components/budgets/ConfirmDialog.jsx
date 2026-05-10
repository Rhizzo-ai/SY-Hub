/**
 * ConfirmDialog — Prompt 2.4B-i §R5.4.
 *
 * AlertDialog wrapper with optional reason capture + brand-fixed confirm
 * button. The `variant` controls the confirm tint:
 *   default      → bg-sy-teal text-white hover:brightness-110
 *   destructive  → bg-sy-orange text-white hover:brightness-110
 *
 * Special slot `extraFields` lets the caller inject additional inputs
 * inside the dialog body (used by NewVersion to collect `version_label`).
 *
 * `requireReason` enforces non-empty reason before enabling confirm;
 * the reason is passed as the first arg to `onConfirm(reason, extras)`.
 *
 * Closing via Cancel / Escape / outside click clears local form state
 * (B2 fix from v1).
 */
import { useState } from 'react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  trigger,
  requireReason = false,
  isPending = false,
  variant = 'default',
  onConfirm,
  testId = 'confirm-dialog',
  // Optional render-prop for extra form fields (e.g. version_label).
  // Receives `{ disabled }` and should return JSX; the caller is also
  // responsible for tracking its own form state via closure.
  renderExtraFields = null,
  // Optional extraValid callback: returning false disables Confirm even
  // when reason is filled. Used by callers with renderExtraFields.
  extraValid = null,
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');

  const confirmClass =
    variant === 'destructive'
      ? 'bg-sy-orange text-white hover:brightness-110 active:brightness-95'
      : 'bg-sy-teal text-white hover:brightness-110 active:brightness-95';

  const reasonValid = !requireReason || !!reason.trim();
  const extrasValid = extraValid ? !!extraValid() : true;
  const canConfirm = reasonValid && extrasValid && !isPending;

  async function handleConfirm(evt) {
    // AlertDialog's Action closes by default; prevent so we can await
    // the mutation and surface errors.
    evt?.preventDefault?.();
    if (!canConfirm) return;
    try {
      await onConfirm(reason.trim());
      setOpen(false);
      setReason('');
    } catch {
      // The caller's hook surfaces toasts; keep dialog open so user
      // sees pending=false and can retry.
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setReason('');
      }}
    >
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent data-testid={testId}>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>

        {renderExtraFields ? (
          <div className="space-y-3">
            {renderExtraFields({ disabled: isPending })}
          </div>
        ) : null}

        {requireReason && (
          <div className="space-y-1">
            <Label htmlFor={`${testId}-reason`}>Reason (audit-logged)</Label>
            <Textarea
              id={`${testId}-reason`}
              data-testid={`${testId}-reason-input`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              placeholder="Why are you taking this action?"
              disabled={isPending}
            />
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel
            disabled={isPending}
            data-testid={`${testId}-cancel`}
          >
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            className={confirmClass}
            disabled={!canConfirm}
            onClick={handleConfirm}
            data-testid={`${testId}-confirm`}
          >
            {isPending ? 'Working…' : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
