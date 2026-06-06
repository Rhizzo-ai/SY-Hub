/**
 * Supplier-documents API client — Chat 40 §R3 #9 / Chat 43 §R3 (file upload).
 *
 * Endpoints (verified on origin/main, §R0 coverage map):
 *   GET    /v1/supplier-documents?supplier_id=&include_archived=
 *   POST   /v1/supplier-documents
 *   PATCH  /v1/supplier-documents/{id}
 *   POST   /v1/supplier-documents/{id}/archive
 *   POST   /v1/supplier-documents/{id}/unarchive
 *   POST   /v1/supplier-documents/{id}/file        (multipart; rev-B)
 *   GET    /v1/supplier-documents/{id}/file        (StreamingResponse; rev-B)
 *
 * GET single (`/v1/supplier-documents/{id}`) intentionally NOT surfaced
 * (§R0: list already returns full rows; edit uses the cached row).
 *
 * Backend strips `file_ref` + `notes` for callers without
 * `supplier_documents.view_sensitive`. `file_ref` is SYSTEM-OWNED — it is
 * set by the `/file` upload endpoint and is no longer accepted on
 * create/patch payloads. The free-text input is gone (Chat 43 §R1).
 *
 * Downloads go via `authedFetch` (cookie-aware) — never through axios —
 * because we need the binary `Response`/blob, not a JSON envelope.
 * The SharePoint URL never reaches the client; the backend proxies the
 * bytes.
 */
import { api, API_BASE, authedFetch } from '@/lib/api';

export async function listDocuments(supplierId, { signal, includeArchived } = {}) {
  const { data } = await api.get('/v1/supplier-documents', {
    signal,
    params: {
      supplier_id: supplierId,
      include_archived: includeArchived || undefined,
    },
  });
  return data;
}

export async function createDocument(body) {
  const { data } = await api.post('/v1/supplier-documents', body);
  return data;
}

export async function patchDocument(id, body) {
  const { data } = await api.patch(`/v1/supplier-documents/${id}`, body);
  return data;
}

export async function archiveDocument(id) {
  const { data } = await api.post(`/v1/supplier-documents/${id}/archive`, {});
  return data;
}

export async function unarchiveDocument(id) {
  const { data } = await api.post(`/v1/supplier-documents/${id}/unarchive`, {});
  return data;
}

// ---------------------------------------------------------------------------
// File upload / download (Build Pack 2.7-FE-docupload §R3, rev-B endpoints).
//
// Upload: multipart POST under the field name `file` via the shared axios
// `api` instance (cookies via withCredentials). The server returns the
// serialised doc with `has_file=true` plus sensitive file metadata
// (file_name, file_size, file_content_type). Replace re-uses this same
// endpoint — a second upload supersedes the first (backend-confirmed).
//
// Download: streamed bytes (StreamingResponse). MUST go via authedFetch,
// NOT axios — we want the raw Response/Blob, not a JSON envelope, and
// fetch needs the cookie-aware wrapper (plain fetch drops withCredentials).
// The SharePoint URL never reaches the client; the backend proxies the
// bytes. Caller saves the blob; we also return the filename parsed from
// Content-Disposition (RFC-5987 `filename*` preferred, then `filename`).
// ---------------------------------------------------------------------------

export async function uploadDocumentFile(id, file) {
  const fd = new FormData();
  fd.append('file', file);
  // Build Pack 2.7-FE-docfix B78 Gate-2 follow-up — multipart boundary fix.
  //
  // The shared `api` instance in lib/api.js declares an instance-level
  // default `Content-Type: application/json`. That default short-circuits
  // axios 1.x's FormData auto-detection: instead of stripping the
  // Content-Type and letting the browser fill in
  // `multipart/form-data; boundary=…`, axios ships the request as JSON
  // with an unserialised FormData body. The server then sees no `file`
  // field and 422s with
  //   {type:"missing", loc:["body","file"], msg:"Field required"}.
  //
  // Setting Content-Type to `undefined` on THIS request (only) tells
  // axios to remove it from the merged headers, allowing the browser to
  // generate the correct multipart Content-Type WITH a boundary. The
  // shared `api` default (JSON) stays intact for the rest of the app.
  // Use `undefined` — NOT the bare string 'multipart/form-data', which
  // would omit the boundary and misfire identically.
  const { data } = await api.post(
    `/v1/supplier-documents/${id}/file`,
    fd,
    { headers: { 'Content-Type': undefined } },
  );
  return data;
}

/**
 * Parse a filename from a Content-Disposition header.
 *
 * RFC-5987 `filename*=UTF-8''…` (percent-encoded) wins over the plain
 * `filename="…"` form when both are present, mirroring how browsers
 * behave for `<a download>`-style saves. Returns `null` if neither form
 * is parseable so the caller can fall back to a sensible default.
 */
export function parseContentDispositionFilename(header) {
  if (!header || typeof header !== 'string') return null;
  // RFC-5987 form: filename*=UTF-8''percent%20encoded.pdf
  const star = header.match(/filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i);
  if (star && star[2]) {
    try { return decodeURIComponent(star[2].trim()); } catch (_) { /* fall through */ }
  }
  // Plain form: filename="something.pdf"   OR   filename=something.pdf
  const plain = header.match(/filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;]+)/i);
  if (plain) {
    const raw = (plain[1] ?? plain[2] ?? '').trim();
    return raw || null;
  }
  return null;
}

export async function downloadDocumentFile(id) {
  const res = await authedFetch(`${API_BASE}/v1/supplier-documents/${id}/file`);
  if (!res.ok) {
    // Hand the caller back a structured failure so the component can map
    // status → toast per Build Pack §R0.2. We deliberately do NOT throw
    // a raw fetch error — keep the surface ergonomic.
    let detail = null;
    try { detail = (await res.json())?.detail ?? null; } catch (_) { /* not JSON */ }
    const err = new Error(detail || `Download failed (${res.status})`);
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  const blob = await res.blob();
  const filename = parseContentDispositionFilename(res.headers.get('Content-Disposition'));
  return { blob, filename };
}
