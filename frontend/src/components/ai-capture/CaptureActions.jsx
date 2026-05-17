// frontend/src/components/ai-capture/CaptureActions.jsx — Chat 19C §R4.1
//
// Header actions for the detail page: Retry (Failed jobs only) + Discard
// (any non-terminal job). Discard surfaces a ConfirmDialog with a
// required reason (audit-logged on the backend). The confirm button uses
// rose-600 — a step warmer than the global sy-orange so the destructive
// nature is unambiguous on the AI Capture surface (§R4.1 H10).
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/budgets/ConfirmDialog';
import { useDiscardCapture, useRetryCapture } from '@/hooks/aiCapture';
import { canDiscard, canRetry } from '@/lib/aiCaptureCapability';

export function CaptureActions({ job, me, onAfterAction }) {
  const discard = useDiscardCapture(job.id);
  const retry = useRetryCapture(job.id);

  const showDiscard = canDiscard(me, job);
  const showRetry = canRetry(me, job);

  if (!showDiscard && !showRetry) return null;

  return (
    <div className="flex items-center gap-2" data-testid="capture-actions">
      {showRetry && (
        <Button
          variant="outline"
          disabled={retry.isPending}
          onClick={async () => {
            try {
              await retry.mutateAsync();
              onAfterAction?.();
            } catch {
              /* toast via hook */
            }
          }}
          data-testid="capture-retry-button"
        >
          {retry.isPending ? 'Retrying…' : 'Retry'}
        </Button>
      )}
      {showDiscard && (
        <ConfirmDialog
          title="Discard this capture job?"
          description="The job will be marked Discarded and removed from the inbox. This is audit-logged."
          confirmLabel="Discard"
          requireReason
          // PASS-4 H10: ConfirmDialog accepts confirmClass override (Tailwind class string)
          confirmClass="bg-rose-600 text-white hover:bg-rose-700"
          isPending={discard.isPending}
          testId="capture-discard-dialog"
          onConfirm={async (reason) => {
            await discard.mutateAsync({ reason });
            onAfterAction?.();
          }}
          trigger={
            <Button
              className="bg-sy-orange text-white hover:brightness-110"
              disabled={discard.isPending}
              data-testid="capture-discard-button"
            >
              Discard
            </Button>
          }
        />
      )}
    </div>
  );
}
