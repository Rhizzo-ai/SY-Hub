/**
 * ActualDetail page (Chat 19B §R4.1).
 *
 * Composes ActualHeader / ActualStateActions / ActualAttachments /
 * ActualHistory. Delete-Draft is a top-right ghost button gated by
 * `canDeleteDraft` (Draft + actuals.edit + desktop only).
 */
import { useParams, useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { useActual, useDeleteActual } from '@/hooks/actuals';
import {
  canViewSensitive, canDeleteDraft,
} from '@/lib/actualCapability';
import { ActualHeader } from '@/components/actuals/ActualHeader';
import { ActualStateActions } from '@/components/actuals/ActualStateActions';
import { ActualAttachments } from '@/components/actuals/ActualAttachments';
import { ActualHistory } from '@/components/actuals/ActualHistory';
import { ConfirmDialog } from '@/components/budgets/ConfirmDialog';
import { Button } from '@/components/ui/button';

export default function ActualDetail() {
  const { projectId, actualId } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const isDesktop = useIsDesktop();
  const { data: actual, isLoading, isError, error } = useActual(actualId);
  const deleteMut = useDeleteActual(actualId, projectId);

  const includeSensitive = canViewSensitive(me);
  const canDelete = canDeleteDraft(actual, me, isDesktop);

  if (isLoading) {
    return (
      <div className="p-6 text-slate-500" data-testid="actual-detail-loading">
        Loading actual…
      </div>
    );
  }
  if (isError || !actual) {
    return (
      <div
        className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
        data-testid="actual-detail-error"
      >
        Failed to load actual: {error?.message ?? 'not found'}
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4 md:p-6" data-testid="actual-detail-page">
      <div className="flex items-center justify-between">
        <Link
          to={`/projects/${projectId}/actuals`}
          className="text-sm text-slate-500 hover:text-slate-700"
          data-testid="actual-detail-back"
        >
          ← Back to actuals
        </Link>
        {canDelete && (
          <ConfirmDialog
            title="Delete this Draft actual?"
            description="This permanently removes the Draft. Attachments and change-log entries will also be removed."
            confirmLabel="Delete"
            variant="destructive"
            isPending={deleteMut.isPending}
            testId="actual-delete-dialog"
            onConfirm={() =>
              new Promise((resolve, reject) => {
                deleteMut.mutate(undefined, {
                  onSuccess: () => {
                    toast.success('Draft actual deleted');
                    resolve();
                    navigate(`/projects/${projectId}/actuals`);
                  },
                  onError: (err) => {
                    const detail = err?.response?.data?.detail;
                    const msg = typeof detail === 'string'
                      ? detail
                      : detail?.message ?? err?.message ?? 'Failed to delete';
                    toast.error(msg);
                    reject(err);
                  },
                });
              })
            }
            trigger={
              <Button
                variant="ghost"
                className="text-rose-700 hover:bg-rose-50"
                data-testid="actual-delete-button"
              >
                Delete Draft
              </Button>
            }
          />
        )}
      </div>

      <ActualHeader actual={actual} includeSensitive={includeSensitive} />

      <ActualStateActions
        actual={actual}
        me={me}
        isDesktop={isDesktop}
      />

      <ActualAttachments
        actual={actual}
        me={me}
        isDesktop={isDesktop}
      />

      <ActualHistory
        actualId={actual.id}
        includeSensitive={includeSensitive}
      />
    </div>
  );
}
