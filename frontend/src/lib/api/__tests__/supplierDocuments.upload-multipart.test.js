/**
 * Wire-level multipart contract test for uploadDocumentFile — Build Pack
 * 2.7-FE-docfix B78 Gate-2 follow-up.
 *
 * The original §R3 API-layer test (supplierDocuments.test.js) mocks
 * `@/lib/api` entirely and asserts the *call* to `api.post` — it never
 * exercises the real axios instance defined in lib/api.js. That blind
 * spot let the live 422 bug ship green:
 *
 *   - The shared `api` instance declares
 *       headers: { 'Content-Type': 'application/json' }
 *     at instance creation.
 *   - axios 1.x normally auto-detects FormData and strips the
 *     Content-Type so the browser fills in
 *       multipart/form-data; boundary=…
 *     — but only if the merged headers do NOT already specify
 *     Content-Type. The instance default short-circuits that.
 *   - Result: the upload request ships with Content-Type:
 *     application/json and a FormData body axios cannot serialise →
 *     the server sees no `file` field and responds 422 with
 *       { type:"missing", loc:["body","file"], msg:"Field required" }.
 *
 * This file pins the wire-level fix by routing through the REAL axios
 * `api` instance and capturing the merged config via a custom adapter.
 * No real network, no new packages. Run alongside the existing api +
 * hook tests; do NOT consolidate.
 */
import axios from 'axios';

// IMPORTANT: do NOT jest.mock('@/lib/api', …) — this whole file's purpose
// is to exercise the REAL `api` instance and its default headers.

import { api, API_BASE } from '@/lib/api';
import { uploadDocumentFile } from '@/lib/api/supplierDocuments';

// Capture both at request-interceptor time (after mergeConfig, BEFORE
// axios' transformRequest mutates headers further) and at adapter time
// (the final wire shape). The two views answer two different questions:
//
//   - interceptor view  : did the per-request override strip the JSON
//                         default during mergeConfig? → MUST be undefined
//                         when the fix is in place; would be
//                         'application/json' if the bug were back.
//   - adapter view      : the post-transform shape — informational; in
//                         jsdom, axios writes 'application/x-www-form-
//                         urlencoded' here because browser FormData isn't
//                         the same code path as Node's form-data package.
//                         The real browser at runtime hits the auto-
//                         multipart-with-boundary path; jsdom does not.
//                         What MATTERS for this bug is that this value is
//                         NOT 'application/json'.

let originalAdapter;
let interceptorId;
let capturedAtInterceptor;
let capturedAtAdapter;

beforeEach(() => {
  originalAdapter = api.defaults.adapter;
  capturedAtInterceptor = [];
  capturedAtAdapter = [];

  // Request interceptor — runs after mergeConfig, before transformRequest.
  interceptorId = api.interceptors.request.use((config) => {
    // AxiosHeaders may be a class instance in 1.x — snapshot via .toJSON()
    // when available so the captured shape is stable across versions.
    const headersSnap =
      config.headers && typeof config.headers.toJSON === 'function'
        ? config.headers.toJSON()
        : { ...config.headers };
    capturedAtInterceptor.push({
      method: config.method,
      url: config.url,
      baseURL: config.baseURL,
      withCredentials: config.withCredentials,
      headers: headersSnap,
      data: config.data,
    });
    return config;
  });

  // Custom adapter — receives the FULLY MERGED + TRANSFORMED request
  // config. Resolves to a synthetic 200 so axios never tries the network.
  api.defaults.adapter = (config) => {
    capturedAtAdapter.push(config);
    return Promise.resolve({
      data: { id: 'D1', has_file: true,
              file_name: 'cert.pdf', file_size: 5,
              file_content_type: 'application/pdf' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    });
  };
});

afterEach(() => {
  api.defaults.adapter = originalAdapter;
  if (interceptorId !== undefined) {
    api.interceptors.request.eject(interceptorId);
    interceptorId = undefined;
  }
});

// ---------------------------------------------------------------------------
// Sanity: the shared api instance still defaults to JSON. Acts as a
// regression guard — if someone "fixes" the bug by changing the default
// on the shared instance, the rest of the app silently loses its
// declared Content-Type and this catches it.
// ---------------------------------------------------------------------------

describe('lib/api shared `api` instance defaults (regression guard)', () => {
  test('instance default Content-Type is still application/json (NOT changed by this fix)', () => {
    const defaults = api.defaults.headers;
    const ct =
      defaults['Content-Type'] ??
      defaults.common?.['Content-Type'] ??
      defaults.post?.['Content-Type'];
    expect(ct).toBe('application/json');
  });
});

// ---------------------------------------------------------------------------
// The actual wire-level contract for uploadDocumentFile.
// ---------------------------------------------------------------------------

describe('uploadDocumentFile — axios wire contract (B78 Gate-2 multipart fix)', () => {
  function pickContentType(headers) {
    if (!headers) return undefined;
    if (typeof headers.get === 'function') return headers.get('Content-Type');
    return (
      headers['Content-Type'] ??
      headers['content-type'] ??
      undefined
    );
  }

  test('POSTs to /v1/supplier-documents/{id}/file with FormData body and overrides Content-Type to undefined per request — the JSON default does NOT survive merge', async () => {
    const file = new File(['hello'], 'cert.pdf', { type: 'application/pdf' });

    const out = await uploadDocumentFile('D1', file);

    // Both capture points fired exactly once.
    expect(capturedAtInterceptor).toHaveLength(1);
    expect(capturedAtAdapter).toHaveLength(1);
    const before = capturedAtInterceptor[0];
    const after = capturedAtAdapter[0];

    // Verb + URL — axios merges baseURL + url, so check both shapes.
    expect(before.method).toBe('post');
    expect(before.url).toBe('/v1/supplier-documents/D1/file');
    expect(before.baseURL).toBe(API_BASE);

    // Body MUST be a FormData carrying the File on field "file".
    expect(before.data).toBeInstanceOf(FormData);
    expect(before.data.get('file')).toBe(file);

    // ─── THE SMOKING GUN ──────────────────────────────────────────────
    // At request-interceptor time (post-merge, pre-transform), the
    // per-request `headers: { 'Content-Type': undefined }` MUST have
    // stripped the instance default. If the bug were back, this value
    // would be 'application/json'.
    expect(pickContentType(before.headers)).toBeUndefined();

    // Defence in depth: scan EVERY casing/bucket in the merged header
    // snapshot — none of them may carry 'application/json' on this
    // specific upload.
    for (const [k, v] of Object.entries(before.headers)) {
      if (String(k).toLowerCase() === 'content-type') {
        expect(v).not.toBe('application/json');
      }
    }

    // Adapter-time view — informational, but the JSON default MUST NOT
    // resurrect here either. (In jsdom this resolves to
    // 'application/x-www-form-urlencoded' because browser FormData
    // doesn't hit axios' Node form-data path; in a real browser it
    // would be deleted and replaced by 'multipart/form-data; boundary=…'
    // at XHR.send() time.)
    expect(pickContentType(after.headers)).not.toBe('application/json');

    // Server response made it back through the function.
    expect(out).toEqual({
      id: 'D1', has_file: true, file_name: 'cert.pdf',
      file_size: 5, file_content_type: 'application/pdf',
    });
  });

  test('cookies still ride along — instance is withCredentials:true (proves we did not nuke the shared instance config)', async () => {
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    await uploadDocumentFile('D2', file);

    expect(capturedAtInterceptor[0].withCredentials).toBe(true);
  });

  test('the shared `api` default Content-Type remains application/json AFTER this upload (no blast radius on other callers)', async () => {
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    await uploadDocumentFile('D3', file);

    // The shared instance must be untouched by this per-request override.
    const ct =
      api.defaults.headers['Content-Type'] ??
      api.defaults.headers.common?.['Content-Type'] ??
      api.defaults.headers.post?.['Content-Type'];
    expect(ct).toBe('application/json');
  });

  test('axios version sanity (1.x — the FormData auto-detection path this fix relies on)', () => {
    // Tag the test with the axios major. If a future bump regresses the
    // header-merge semantics, this test surfaces it in the failure log.
    expect(Number(axios.VERSION?.split('.')[0])).toBeGreaterThanOrEqual(1);
  });
});
