/**
 * BulkDeleteConfirmDialog — Chat 23 §R7.3.
 *
 * Controlled AlertDialog (open/onOpenChange) — the existing
 * `ConfirmDialog` wraps its own trigger and owns local open state, which
 * is the wrong shape for the bulk bar (the bar opens the dialog
 * imperatively). We use the underlying `AlertDialog` primitive directly
 * with the same sy-orange destructive styling, so the visual contract
 * with the rest of the surface is preserved.
 */
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const DESTRUCTIVE_CLASS =
  'bg-sy-orange text-white hover:brightness-110 active:brightness-95';

export function BulkDeleteConfirmDialog({
  open, onOpenChange, count, onConfirm,
}) {
  const noun = count === 1 ? 'line' : 'lines';
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="bg2-bulk-delete-confirm">
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {count} {noun}?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes {count} budget {noun} from the
            current budget. Each delete is audited individually and
            totals will recompute. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="bg2-bulk-delete-confirm-cancel">
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            className={DESTRUCTIVE_CLASS}
            onClick={() => onConfirm?.()}
            data-testid="bg2-bulk-delete-confirm-ok"
          >
            Delete {count} {noun}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
