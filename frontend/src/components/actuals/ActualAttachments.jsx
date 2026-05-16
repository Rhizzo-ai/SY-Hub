/**
 * ActualAttachments (Chat 19B §R4.4).
 *
 * List + uploader + per-row delete with confirm. Uses the trigger-based
 * `ConfirmDialog` (chat-17) which owns its own open state — so no
 * useState here.
 */
import { toast } from 'sonner';
import { format } from 'date-fns';
import { useActualAttachments, useDeleteAttachment } from '@/hooks/actuals';
import {
  canAttach, canDeleteAttachment,
} from '@/lib/actualCapability';
import { AttachmentUploader } from './AttachmentUploader';
import { ConfirmDialog } from '@/components/budgets/ConfirmDialog';
import { Button } from '@/components/ui/button';

const fmtBytes = (n) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
};

export function ActualAttachments({ actual, me, isDesktop }) {
  const { data, isLoading } = useActualAttachments(actual.id);
  const deleteMut = useDeleteAttachment(actual.id);

  const canUpload = canAttach(actual, me, isDesktop);
  const canDelete = canDeleteAttachment(actual, me, isDesktop);

  return (
    <section
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      data-testid="actual-attachments"
    >
      <h2 className="font-heading text-lg text-slate-900">Attachments</h2>

      {canUpload && (
        <AttachmentUploader actualId={actual.id} disabled={!canUpload} />
      )}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading attachments…</p>
      ) : (data?.length ?? 0) === 0 ? (
        <p className="text-sm text-slate-500" data-testid="attachments-empty">
          No attachments yet.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {data.map((att) => (
            <li
              key={att.id}
              data-testid={`attachment-row-${att.id}`}
              className="flex items-center justify-between gap-3 py-2"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-900">
                  {att.original_filename}
                </div>
                <div className="text-xs text-slate-500">
                  {att.file_type} · {fmtBytes(att.file_size_bytes)} ·
                  uploaded {att.uploaded_at
                    ? format(new Date(att.uploaded_at), 'd MMM yyyy')
                    : '—'}
                  {att.source !== 'Manual_Upload' &&
                    ` · via ${att.source.replace(/_/g, ' ')}`}
                </div>
              </div>
              {canDelete && (
                <ConfirmDialog
                  title="Delete this attachment?"
                  description={`Removes “${att.original_filename}” permanently.`}
                  confirmLabel="Delete"
                  variant="destructive"
                  isPending={deleteMut.isPending}
                  testId={`attachment-delete-${att.id}-dialog`}
                  onConfirm={() =>
                    new Promise((resolve, reject) => {
                      deleteMut.mutate(att.id, {
                        onSuccess: () => {
                          toast.success('Attachment deleted');
                          resolve();
                        },
                        onError: (err) => {
                          const detail = err?.response?.data?.detail;
                          const msg = typeof detail === 'string'
                            ? detail
                            : detail?.message ?? err?.message ?? 'Delete failed';
                          toast.error(msg);
                          reject(err);
                        },
                      });
                    })
                  }
                  trigger={
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-700 hover:bg-rose-50"
                      data-testid={`attachment-delete-${att.id}`}
                    >
                      Delete
                    </Button>
                  }
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
