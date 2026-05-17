// frontend/src/components/ai-capture/AttachmentPreview.jsx — Chat 19C §R5.1
//
// Fetches the attachment file bytes via the new
// `GET /v1/ai-capture-jobs/:id/attachment` endpoint (§R5.1 C1), wraps the
// response Blob in an object URL, and embeds it inline. PDFs use <embed>;
// images use <img>. The blob URL is revoked on unmount / job change to
// prevent memory leak (PASS-2 H7).
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export function AttachmentPreview({ job }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let revoke = null;
    let cancelled = false;
    setBlobUrl(null);
    setErr(null);
    (async () => {
      try {
        // PASS-2 C3: /v1/ prefix per lib/api.js baseURL convention
        const res = await api.get(`/v1/ai-capture-jobs/${job.id}/attachment`, {
          responseType: 'blob',
        });
        if (cancelled) return;
        const url = URL.createObjectURL(res.data);
        revoke = url;
        setBlobUrl(url);
      } catch (e) {
        if (!cancelled) {
          setErr(e?.response?.data?.detail || 'Preview unavailable');
        }
      }
    })();
    return () => {
      cancelled = true;
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [job.id]);

  if (err) {
    return (
      <div
        className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500"
        data-testid="attachment-preview-error"
      >
        {err}
      </div>
    );
  }
  if (!blobUrl) {
    return (
      <div
        className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500"
        data-testid="attachment-preview-loading"
      >
        Loading preview…
      </div>
    );
  }

  const isPdf = job.attachment_path?.toLowerCase().endsWith('.pdf');

  return (
    <div
      className="rounded-md border border-slate-200 bg-white p-2"
      data-testid="attachment-preview"
    >
      {isPdf ? (
        <embed src={blobUrl} type="application/pdf" className="h-[600px] w-full" />
      ) : (
        <img src={blobUrl} alt="Capture attachment" className="max-h-[600px] w-full object-contain" />
      )}
    </div>
  );
}
