// frontend/src/hooks/aiCapture.js — Chat 19C §R1.3
//
// TanStack Query hooks for the AI capture review surface. Mirrors the
// shape used in `hooks/actuals.js` (queryKey factory + targeted
// invalidation). Cross-domain invalidation (capture jobs + actuals) on
// promote is per §R1.3 I12 — promoting a job creates a Draft actual
// that must appear immediately in the actuals list page.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  listCaptureJobs, getCaptureJob, promoteCaptureJob,
  discardCaptureJob, retryCaptureJob, getCaptureCostStats,
} from '@/lib/api/aiCapture';
import { actualsKeys } from '@/hooks/actuals';

export const aiCaptureKeys = {
  all: ['ai-capture'],
  lists: () => [...aiCaptureKeys.all, 'list'],
  list: (filters) => [...aiCaptureKeys.lists(), filters],
  details: () => [...aiCaptureKeys.all, 'detail'],
  detail: (id) => [...aiCaptureKeys.details(), id],
  // Chat 20 §R2.3 (B38) — stats factory under .all so promote/discard/retry
  // mutations' existing aiCaptureKeys.all-prefix invalidation also picks up
  // an open cost dashboard. (I12, in-domain.)
  stats: (filters) => [...aiCaptureKeys.all, 'stats', filters],
};

function _invalidateAll(qc) {
  qc.invalidateQueries({ queryKey: aiCaptureKeys.all });
}

function _invalidateAllAcrossDomains(qc) {
  // Promote creates a new Draft Actual. Invalidate both domains. (I12)
  qc.invalidateQueries({ queryKey: aiCaptureKeys.all });
  qc.invalidateQueries({ queryKey: actualsKeys.all });
}

export function useCaptureJobs(filters = {}, opts = {}) {
  return useQuery({
    queryKey: aiCaptureKeys.list(filters),
    queryFn: () => listCaptureJobs(filters),
    staleTime: 10_000,
    ...opts,
  });
}

export function useCaptureJob(jobId, opts = {}) {
  return useQuery({
    queryKey: aiCaptureKeys.detail(jobId),
    queryFn: () => getCaptureJob(jobId),
    enabled: !!jobId,
    ...opts,
  });
}

export function usePromoteCapture(jobId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => promoteCaptureJob(jobId, payload),
    onSuccess: ({ actualId }) => {
      toast.success('Promoted to Draft actual');
      _invalidateAllAcrossDomains(qc);
      return { actualId };
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || err?.friendlyMessage || 'Promote failed');
    },
  });
}

export function useDiscardCapture(jobId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reason }) => discardCaptureJob(jobId, { reason }),
    onSuccess: () => {
      toast.success('Job discarded');
      _invalidateAll(qc);
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || err?.friendlyMessage || 'Discard failed');
    },
  });
}

export function useRetryCapture(jobId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => retryCaptureJob(jobId),
    onSuccess: () => {
      toast.success('Retry queued');
      _invalidateAll(qc);
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || err?.friendlyMessage || 'Retry failed');
    },
  });
}

// Chat 20 §R2.3 (B38) — cost dashboard query hook. Slightly stale-tolerant
// (dashboard refresh expectation differs from the inbox table).
export function useCaptureCostStats(filters = {}, opts = {}) {
  return useQuery({
    queryKey: aiCaptureKeys.stats(filters),
    queryFn: ({ signal }) => getCaptureCostStats({ ...filters, signal }),
    staleTime: 60_000,
    ...opts,
  });
}
