/**
 * Supplier-documents API client tests — Build Pack 2.7-FE-docupload §R5 / §R6
 * (Gate 1 API-layer coverage).
 *
 * Pins the contracts the new file upload/download layer relies on:
 *
 *   1. Existing endpoints (list/create/patch/archive/unarchive) keep their
 *      verbs + paths — regression pin so no one accidentally re-points them
 *      while wiring the new file endpoints.
 *
 *   2. `uploadDocumentFile(id, file)` POSTs multipart to
 *      `/v1/supplier-documents/{id}/file` with the field name **`file`**
 *      (rev-B contract — backend reads `file: UploadFile = File(...)`).
 *      Goes via the shared axios `api` instance — cookies ride along
 *      via `withCredentials`. Returns the serialised doc payload.
 *
 *   3. `downloadDocumentFile(id)` uses `authedFetch` (cookie-aware) — NEVER
 *      axios — because we want the raw Blob, not a JSON envelope. Calls
 *      `${API_BASE}/v1/supplier-documents/{id}/file`. Returns
 *      `{ blob, filename }` where `filename` is parsed from the
 *      Content-Disposition header.
 *
 *   4. Content-Disposition filename parsing handles BOTH the RFC-5987
 *      `filename*=UTF-8''…` form (preferred, percent-encoded) and the
 *      plain `filename="…"` form (fallback). Returns `null` when neither
 *      is parseable so the caller can default sensibly.
 *
 *   5. Non-2xx downloads throw a structured error carrying `status` and
 *      `detail` so the component can map status → toast per §R0.2 without
 *      reaching into the raw fetch Response.
 */
import * as docsApi from '@/lib/api/supplierDocuments';

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
  },
  API_BASE: 'https://test.example.com/api',
  authedFetch: jest.fn(),
}));
const { api, authedFetch, API_BASE } = jest.requireMock('@/lib/api');

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
  authedFetch.mockReset();
  api.get.mockResolvedValue({ data: [] });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
});

describe('Supplier-documents API — existing endpoints (regression pin)', () => {
  test('listDocuments GETs /v1/supplier-documents with supplier_id', async () => {
    await docsApi.listDocuments('SUP-1');
    expect(api.get).toHaveBeenCalledWith('/v1/supplier-documents', {
      signal: undefined,
      params: { supplier_id: 'SUP-1', include_archived: undefined },
    });
  });

  test('listDocuments forwards include_archived only when truthy', async () => {
    await docsApi.listDocuments('SUP-1', { includeArchived: true });
    expect(api.get).toHaveBeenCalledWith('/v1/supplier-documents', {
      signal: undefined,
      params: { supplier_id: 'SUP-1', include_archived: true },
    });
  });

  test('createDocument POSTs to /v1/supplier-documents', async () => {
    await docsApi.createDocument({ supplier_id: 'SUP-1', doc_type: 'insurance' });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/supplier-documents',
      { supplier_id: 'SUP-1', doc_type: 'insurance' },
    );
  });

  test('patchDocument PATCHes /v1/supplier-documents/{id}', async () => {
    await docsApi.patchDocument('D1', { notes: 'updated' });
    expect(api.patch).toHaveBeenCalledWith(
      '/v1/supplier-documents/D1',
      { notes: 'updated' },
    );
  });

  test('archiveDocument POSTs /archive', async () => {
    await docsApi.archiveDocument('D1');
    expect(api.post).toHaveBeenCalledWith('/v1/supplier-documents/D1/archive', {});
  });

  test('unarchiveDocument POSTs /unarchive', async () => {
    await docsApi.unarchiveDocument('D1');
    expect(api.post).toHaveBeenCalledWith('/v1/supplier-documents/D1/unarchive', {});
  });
});

describe('uploadDocumentFile — §R3.1 multipart contract', () => {
  test('POSTs to /v1/supplier-documents/{id}/file with FormData field "file" and Content-Type:undefined per-request override (B78 Gate-2)', async () => {
    const file = new File(['hello'], 'cert.pdf', { type: 'application/pdf' });
    api.post.mockResolvedValueOnce({
      data: {
        id: 'D1', has_file: true, file_name: 'cert.pdf',
        file_size: 5, file_content_type: 'application/pdf',
      },
    });

    const out = await docsApi.uploadDocumentFile('D1', file);

    expect(api.post).toHaveBeenCalledTimes(1);
    const [url, body, opts] = api.post.mock.calls[0];
    expect(url).toBe('/v1/supplier-documents/D1/file');
    expect(body).toBeInstanceOf(FormData);
    expect(body.get('file')).toBe(file);

    // B78 Gate-2 follow-up: the shared `api` instance defaults to
    // Content-Type: application/json. For multipart, the caller MUST set
    // Content-Type to `undefined` on this request so axios strips it from
    // the merged headers and the browser fills in the multipart boundary.
    // Use `undefined` — NOT 'multipart/form-data' as a literal string,
    // which would omit the boundary and the server would 422 with
    // {loc:["body","file"], type:"missing"}.
    expect(opts).toBeDefined();
    expect(opts.headers).toBeDefined();
    expect(Object.prototype.hasOwnProperty.call(opts.headers, 'Content-Type')).toBe(true);
    expect(opts.headers['Content-Type']).toBeUndefined();

    expect(out).toEqual({
      id: 'D1', has_file: true, file_name: 'cert.pdf',
      file_size: 5, file_content_type: 'application/pdf',
    });
  });

  test('propagates server errors (so the caller can map 413/422/502)', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('Boom'), { response: { status: 413 } }),
    );
    const file = new File(['x'], 'huge.pdf', { type: 'application/pdf' });
    await expect(docsApi.uploadDocumentFile('D1', file)).rejects.toMatchObject({
      response: { status: 413 },
    });
  });
});

describe('downloadDocumentFile — §R3.2 blob contract', () => {
  function mockResponse({ ok = true, status = 200, body = 'BYTES', headers = {} } = {}) {
    const headerMap = new Map(
      Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]),
    );
    return {
      ok,
      status,
      headers: { get: (k) => headerMap.get(String(k).toLowerCase()) ?? null },
      blob: jest.fn().mockResolvedValue(new Blob([body])),
      json: jest.fn().mockResolvedValue({}),
    };
  }

  test('calls authedFetch against the absolute API_BASE URL — NOT axios', async () => {
    authedFetch.mockResolvedValueOnce(mockResponse({
      headers: { 'Content-Disposition': 'attachment; filename="cert.pdf"' },
    }));

    await docsApi.downloadDocumentFile('D1');

    expect(authedFetch).toHaveBeenCalledTimes(1);
    expect(authedFetch).toHaveBeenCalledWith(
      `${API_BASE}/v1/supplier-documents/D1/file`,
    );
    // Hard negative — axios MUST NOT be used for the blob stream.
    expect(api.get).not.toHaveBeenCalled();
  });

  test('returns { blob, filename } parsed from a plain Content-Disposition', async () => {
    authedFetch.mockResolvedValueOnce(mockResponse({
      headers: { 'Content-Disposition': 'attachment; filename="insurance-2026.pdf"' },
    }));

    const { blob, filename } = await docsApi.downloadDocumentFile('D1');
    expect(blob).toBeInstanceOf(Blob);
    expect(filename).toBe('insurance-2026.pdf');
  });

  test('prefers RFC-5987 filename*=UTF-8\'\' percent-encoded form', async () => {
    authedFetch.mockResolvedValueOnce(mockResponse({
      headers: {
        'Content-Disposition':
          "attachment; filename=\"fallback.pdf\"; filename*=UTF-8''cert%20%C3%A9t%C3%A9.pdf",
      },
    }));
    const { filename } = await docsApi.downloadDocumentFile('D1');
    expect(filename).toBe('cert été.pdf');
  });

  test('returns filename=null when no Content-Disposition header is present', async () => {
    authedFetch.mockResolvedValueOnce(mockResponse({ headers: {} }));
    const { filename } = await docsApi.downloadDocumentFile('D1');
    expect(filename).toBeNull();
  });

  test('throws structured error with status + detail on non-2xx', async () => {
    const res = {
      ok: false,
      status: 502,
      headers: { get: () => null },
      blob: jest.fn(),
      json: jest.fn().mockResolvedValue({ detail: 'document storage unavailable' }),
    };
    authedFetch.mockResolvedValueOnce(res);

    await expect(docsApi.downloadDocumentFile('D1')).rejects.toMatchObject({
      status: 502,
      detail: 'document storage unavailable',
    });
  });

  test('falls back gracefully when error body is not JSON', async () => {
    const res = {
      ok: false,
      status: 404,
      headers: { get: () => null },
      blob: jest.fn(),
      json: jest.fn().mockRejectedValue(new Error('not json')),
    };
    authedFetch.mockResolvedValueOnce(res);

    await expect(docsApi.downloadDocumentFile('D1')).rejects.toMatchObject({
      status: 404,
    });
  });
});

describe('parseContentDispositionFilename — RFC-5987 helper', () => {
  const { parseContentDispositionFilename } = docsApi;

  test('returns null for empty / missing header', () => {
    expect(parseContentDispositionFilename(null)).toBeNull();
    expect(parseContentDispositionFilename('')).toBeNull();
    expect(parseContentDispositionFilename(undefined)).toBeNull();
  });

  test('parses the plain quoted form', () => {
    expect(
      parseContentDispositionFilename('attachment; filename="report.csv"'),
    ).toBe('report.csv');
  });

  test('parses the bare unquoted form', () => {
    expect(
      parseContentDispositionFilename('attachment; filename=report.csv'),
    ).toBe('report.csv');
  });

  test('prefers RFC-5987 percent-encoded form over the plain form', () => {
    expect(
      parseContentDispositionFilename(
        "attachment; filename=\"plain.pdf\"; filename*=UTF-8''pr%C3%A9cis.pdf",
      ),
    ).toBe('précis.pdf');
  });

  test('returns null for malformed headers', () => {
    expect(parseContentDispositionFilename('attachment;')).toBeNull();
  });
});
