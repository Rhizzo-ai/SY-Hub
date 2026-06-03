/**
 * Suppliers API client — D4 regression pin (Chat 40 §R5 #9).
 *
 * Build Pack 2.7-FE §R2 D4: the 2.5 client wrote
 * `POST /v1/suppliers/{id}/restore` against a backend that mounts
 * `/unarchive`, so every "restore archived supplier" click silently
 * 404'd. This file is the named regression: if anyone ever flips the
 * route or function name back, jest fails before it reaches a user.
 */
import * as suppliersApi from '@/lib/api/suppliers';

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));
const { api } = jest.requireMock('@/lib/api');

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
  api.delete.mockReset();
  api.get.mockResolvedValue({ data: { items: [] } });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
});

describe('Suppliers API — Chat 40 §R2 D4 regression', () => {
  test('exports `unarchiveSupplier` (not `restoreSupplier`)', () => {
    expect(typeof suppliersApi.unarchiveSupplier).toBe('function');
    expect(suppliersApi.restoreSupplier).toBeUndefined();
  });

  test('unarchiveSupplier hits /unarchive, NOT /restore', async () => {
    await suppliersApi.unarchiveSupplier('S1');
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith('/v1/suppliers/S1/unarchive', {});
    // Defence in depth: confirm `/restore` is never touched.
    const calls = api.post.mock.calls.map(([url]) => url);
    expect(calls).not.toContain('/v1/suppliers/S1/restore');
  });

  test('archiveSupplier still routes to /archive (unchanged by D4)', async () => {
    await suppliersApi.archiveSupplier('S2');
    expect(api.post).toHaveBeenCalledWith('/v1/suppliers/S2/archive', {});
  });
});
