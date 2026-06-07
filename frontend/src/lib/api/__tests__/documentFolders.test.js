/**
 * Document-folders API client tests — Build Pack 2.7-DOCS-FE §R6.
 *
 * Mirrors `lib/api/__tests__/supplierDocuments.test.js`: mock the shared
 * axios instance, assert each call hits the right URL + verb + body /
 * params. Chat 44 lesson: a component test that mocks the hooks can
 * never catch a wire-level mistake — the api client must be exercised
 * directly.
 */
import * as foldersApi from '@/lib/api/documentFolders';
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
const { api } = jest.requireMock('@/lib/api');

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
  api.get.mockResolvedValue({ data: { items: [] } });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
});


describe('listFolderTree — GET /v1/document-folders', () => {
  test('forwards owner_type + owner_id', async () => {
    await foldersApi.listFolderTree('supplier', 'SUP-1');
    expect(api.get).toHaveBeenCalledWith('/v1/document-folders', {
      signal: undefined,
      params: {
        owner_type: 'supplier',
        owner_id: 'SUP-1',
        include_archived: undefined,
      },
    });
  });

  test('forwards include_archived only when truthy', async () => {
    await foldersApi.listFolderTree('supplier', 'SUP-1', { includeArchived: true });
    expect(api.get).toHaveBeenCalledWith('/v1/document-folders', {
      signal: undefined,
      params: {
        owner_type: 'supplier',
        owner_id: 'SUP-1',
        include_archived: true,
      },
    });
  });

  test('returns data.items (unwraps the envelope)', async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [{ id: 'F1', name: 'Compliance', children: [] }] },
    });
    const out = await foldersApi.listFolderTree('supplier', 'SUP-1');
    expect(out).toEqual([{ id: 'F1', name: 'Compliance', children: [] }]);
  });

  test('forwards a passed AbortSignal', async () => {
    const signal = new AbortController().signal;
    await foldersApi.listFolderTree('supplier', 'SUP-1', { signal });
    expect(api.get).toHaveBeenCalledWith('/v1/document-folders',
      expect.objectContaining({ signal }));
  });
});


describe('getFolder — GET /v1/document-folders/{id}', () => {
  test('hits the right path', async () => {
    await foldersApi.getFolder('F1');
    expect(api.get).toHaveBeenCalledWith('/v1/document-folders/F1', { signal: undefined });
  });
});


describe('createFolder — POST /v1/document-folders', () => {
  test('passes the body through verbatim (owner_type / owner_id / name / parent_id)', async () => {
    await foldersApi.createFolder({
      owner_type: 'supplier', owner_id: 'SUP-1',
      name: 'Insurance', parent_id: 'F0',
    });
    expect(api.post).toHaveBeenCalledWith('/v1/document-folders', {
      owner_type: 'supplier', owner_id: 'SUP-1',
      name: 'Insurance', parent_id: 'F0',
    });
  });
});


describe('renameFolder — PATCH /v1/document-folders/{id}', () => {
  test('sends body {name}', async () => {
    await foldersApi.renameFolder('F1', 'Renamed');
    expect(api.patch).toHaveBeenCalledWith('/v1/document-folders/F1', { name: 'Renamed' });
  });
});


describe('moveFolder — POST /v1/document-folders/{id}/move', () => {
  test('passes new_parent_id', async () => {
    await foldersApi.moveFolder('F1', 'F2');
    expect(api.post).toHaveBeenCalledWith(
      '/v1/document-folders/F1/move', { new_parent_id: 'F2' },
    );
  });

  test('null new_parent_id → root', async () => {
    await foldersApi.moveFolder('F1', null);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/document-folders/F1/move', { new_parent_id: null },
    );
  });

  test('undefined → null (move-to-root)', async () => {
    await foldersApi.moveFolder('F1');
    expect(api.post).toHaveBeenCalledWith(
      '/v1/document-folders/F1/move', { new_parent_id: null },
    );
  });
});


describe('archiveFolder / unarchiveFolder', () => {
  test('archive POSTs to /archive with an empty body', async () => {
    await foldersApi.archiveFolder('F1');
    expect(api.post).toHaveBeenCalledWith('/v1/document-folders/F1/archive', {});
  });
  test('unarchive POSTs to /unarchive with an empty body', async () => {
    await foldersApi.unarchiveFolder('F1');
    expect(api.post).toHaveBeenCalledWith('/v1/document-folders/F1/unarchive', {});
  });
});


// ---------------------------------------------------------------------------
// moveDocument (added to supplierDocuments.js — pin its wire shape here so
// the contract has a dedicated guard).
// ---------------------------------------------------------------------------

describe('moveDocument — POST /v1/supplier-documents/{id}/move', () => {
  test('passes folder_id', async () => {
    await docsApi.moveDocument('D1', 'F1');
    expect(api.post).toHaveBeenCalledWith(
      '/v1/supplier-documents/D1/move', { folder_id: 'F1' },
    );
  });

  test('null folder_id → unfiled', async () => {
    await docsApi.moveDocument('D1', null);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/supplier-documents/D1/move', { folder_id: null },
    );
  });

  test('undefined folder_id → unfiled (consistent with moveFolder)', async () => {
    await docsApi.moveDocument('D1');
    expect(api.post).toHaveBeenCalledWith(
      '/v1/supplier-documents/D1/move', { folder_id: null },
    );
  });

  test('returns the server response body', async () => {
    api.post.mockResolvedValueOnce({
      data: { id: 'D1', folder_id: 'F1', supplier_id: 'SUP-1' },
    });
    const out = await docsApi.moveDocument('D1', 'F1');
    expect(out).toEqual({ id: 'D1', folder_id: 'F1', supplier_id: 'SUP-1' });
  });
});
