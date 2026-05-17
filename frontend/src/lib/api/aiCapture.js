// frontend/src/lib/api/aiCapture.js — Chat 19C §R1.2
//
// API client for the AI capture admin surface.
//
// Verified against the 19B `lib/api/budgets.js` pattern: `lib/api.js`
// baseURL is `/api`, so every path here MUST prepend `/v1/`. Adopts the
// `parseOrThrow` helper from §R1.2 H2 so schema drift surfaces as a
// user-tagged Error rather than a raw ZodError.
import { api } from '@/lib/api';
import {
  AICaptureJobSchema,
  CaptureJobsListResponseSchema,
} from '@/lib/schemas/aiCapture';
import { CaptureStatsResponseSchema } from '@/lib/schemas/aiCaptureStats';

const BASE = '/v1/ai-capture-jobs';

function parseOrThrow(schema, data, endpoint) {
  const result = schema.safeParse(data);
  if (!result.success) {
    const issues = result.error.issues
      .slice(0, 3)
      .map((i) => `${i.path.join('.') || '<root>'}: ${i.message}`)
      .join('; ');
    const err = new Error(`Schema drift @ ${endpoint}: ${issues}`);
    err.zodIssues = result.error.issues;
    err.endpoint = endpoint;
    throw err;
  }
  return result.data;
}

export async function listCaptureJobs(
  { status, limit = 100, offset = 0 } = {},
  { signal } = {},
) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  const { data } = await api.get(`${BASE}?${params.toString()}`, { signal });
  return parseOrThrow(CaptureJobsListResponseSchema, data, 'GET /ai-capture-jobs');
}

export async function getCaptureJob(jobId, { signal } = {}) {
  const { data } = await api.get(`${BASE}/${jobId}`, { signal });
  return parseOrThrow(AICaptureJobSchema, data, 'GET /ai-capture-jobs/:id');
}

export async function promoteCaptureJob(jobId, payload) {
  const { data } = await api.post(`${BASE}/${jobId}/promote`, payload);
  // Response shape: { job, actual_id, actual_status } — not a bare job
  return {
    job: parseOrThrow(AICaptureJobSchema, data.job, 'POST .../promote (job)'),
    actualId: data.actual_id,
    actualStatus: data.actual_status,
  };
}

export async function discardCaptureJob(jobId, { reason }) {
  const { data } = await api.post(`${BASE}/${jobId}/discard`, { reason });
  return parseOrThrow(AICaptureJobSchema, data, 'POST .../discard');
}

export async function retryCaptureJob(jobId) {
  const { data } = await api.post(`${BASE}/${jobId}/retry`, {});
  return parseOrThrow(AICaptureJobSchema, data, 'POST .../retry');
}

// AttachmentPreview: returns a Blob URL the caller is responsible for revoking.
// Verified against §R4 H7 — must include credentials (cookies) for the
// HttpOnly access_token to ride along.
export async function fetchCaptureAttachment(jobId, { signal } = {}) {
  const { data } = await api.get(`${BASE}/${jobId}/attachment`, {
    responseType: 'blob',
    signal,
  });
  return data; // Blob — callers wrap with URL.createObjectURL
}

// Chat 20 §R2.2 (B38) — aggregated cost / token / volume stats.
export async function getCaptureCostStats({ fromDate, toDate, signal } = {}) {
  const params = {};
  if (fromDate) params.from_date = fromDate;
  if (toDate) params.to_date = toDate;
  const { data } = await api.get('/v1/ai-capture-jobs/stats', {
    params, signal,
  });
  return parseOrThrow(
    CaptureStatsResponseSchema, data, 'GET /ai-capture-jobs/stats',
  );
}
