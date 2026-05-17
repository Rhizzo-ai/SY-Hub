// frontend/src/pages/CaptureJobDetail.jsx — Chat 19C §R2.2
//
// Detail view for a single AI capture job. Lays out attachment preview +
// extracted fields panel + Promote/Discard/Retry actions. The Promote
// form is only rendered when the job is in `Awaiting_Review` AND the
// current user has actuals.admin (canPromote).
//
// PASS-2 H1: `onPromoted` reads `projectId` from the form result
// (the operator's choice), NOT from stale `job.suggested_project_id`.
// PASS-3 C4: useCaptureJob lives above the perm gate.
import { useParams, useNavigate } from 'react-router-dom';
import { useCaptureJob } from '@/hooks/aiCapture';
import { useAuth } from '@/context/AuthContext';
import { canViewCaptures, canPromote } from '@/lib/aiCaptureCapability';
import { CaptureStatusBadge } from '@/components/ai-capture/CaptureStatusBadge';
import { AttachmentPreview } from '@/components/ai-capture/AttachmentPreview';
import { ExtractedFieldsPanel } from '@/components/ai-capture/ExtractedFieldsPanel';
import { PromoteForm } from '@/components/ai-capture/PromoteForm';
import { CaptureActions } from '@/components/ai-capture/CaptureActions';

export default function CaptureJobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();

  const { data: job, isLoading, error } = useCaptureJob(jobId, {
    enabled: !!jobId && canViewCaptures(me),
  });

  if (!canViewCaptures(me)) {
    return (
      <div
        className="p-6 text-sm text-slate-500"
        data-testid="capture-detail-no-perm"
      >
        You don't have permission to view AI Capture jobs.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-slate-500" data-testid="capture-detail-loading">
        Loading…
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="p-6 text-sm text-rose-600" data-testid="capture-detail-error">
        {error?.response?.data?.detail || 'Job not found'}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4" data-testid="capture-detail-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/ai-capture')}
            className="text-sm text-slate-500 hover:text-slate-700"
            data-testid="capture-detail-back"
          >
            ← Inbox
          </button>
          <h1 className="font-heading text-xl text-slate-900">Capture job</h1>
          <CaptureStatusBadge status={job.status} />
        </div>
        <CaptureActions
          job={job}
          me={me}
          onAfterAction={() => navigate('/ai-capture')}
        />
      </div>

      {job.status === 'Failed' && job.last_error_message && (
        <div
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
          data-testid="capture-detail-error-banner"
        >
          <span className="font-medium">Extraction failed:</span> {job.last_error_message}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AttachmentPreview job={job} />
        <div className="space-y-4">
          <ExtractedFieldsPanel job={job} />
          {job.status === 'Awaiting_Review' && canPromote(me, job) && (
            <PromoteForm
              job={job}
              onPromoted={({ actualId, projectId }) =>
                navigate(`/projects/${projectId}/actuals/${actualId}`)
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
