// frontend/src/pages/AICaptureInbox.jsx — Chat 19C §R2.1 / D45
//
// Inbox view for AI capture jobs. Default filter is `Awaiting_Review`
// (the actionable queue); the `__ALL__` sentinel collapses to no status
// param (D40). Page-level perm gate mirrors `BudgetsList.jsx`
// (PASS-2 H3, NO RequirePermission wrapper exists in live code).
//
// PASS-3 C4: ALL hooks above the perm gate to preserve hook order.
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { canViewCaptures } from '@/lib/aiCaptureCapability';
import { useCaptureJobs } from '@/hooks/aiCapture';
import { CaptureJobsTable } from '@/components/ai-capture/CaptureJobsTable';
import { CaptureJobsFilters } from '@/components/ai-capture/CaptureJobsFilters';

export default function AICaptureInbox() {
  const { me } = useAuth();
  const [status, setStatus] = useState('Awaiting_Review');
  const navigate = useNavigate();

  const filters = useMemo(
    () => ({ status: status === '__ALL__' ? undefined : status }),
    [status],
  );

  const { data, isLoading, error } = useCaptureJobs(filters, {
    enabled: canViewCaptures(me),
  });

  if (!canViewCaptures(me)) {
    return (
      <div
        className="p-6 text-sm text-slate-500"
        data-testid="capture-jobs-no-perm"
      >
        You don't have permission to view the AI Capture inbox.
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6" data-testid="capture-jobs-list-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl text-slate-900">AI Capture Inbox</h1>
      </div>

      <CaptureJobsFilters status={status} onStatusChange={setStatus} />

      {isLoading && (
        <div className="text-sm text-slate-500" data-testid="capture-jobs-loading">
          Loading capture queue…
        </div>
      )}

      {error && (
        <div className="text-sm text-rose-600" data-testid="capture-jobs-error">
          {error?.response?.data?.detail || error?.message || 'Failed to load'}
        </div>
      )}

      {data && (
        <CaptureJobsTable
          jobs={data.items}
          total={data.total}
          onRowClick={(job) => navigate(`/ai-capture/${job.id}`)}
        />
      )}
    </div>
  );
}
