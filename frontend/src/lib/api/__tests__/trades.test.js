/**
 * Trades API client tests — Chat 41 §R8 (Build Pack 2.7-FE-revision).
 *
 * Pins the GET shape + the POST body contract. Mirrors the
 * lib/api/__tests__/suppliers.test.js mock convention.
 */
import * as tradesApi from '@/lib/api/trades';

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
  api.get.mockResolvedValue({ data: { items: [], total: 0, limit: 50, offset: 0 } });
  api.post.mockResolvedValue({ data: {} });
});

describe('Trades API — Chat 41 §R1.1', () => {
  test('listTrades hits GET /v1/trades and returns the {items,total,limit,offset} shape', async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [{ id: 'T1', name: 'Groundworks' }], total: 1, limit: 50, offset: 0 },
    });
    const out = await tradesApi.listTrades();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith('/v1/trades', expect.objectContaining({ params: undefined }));
    expect(out).toEqual({ items: [{ id: 'T1', name: 'Groundworks' }], total: 1, limit: 50, offset: 0 });
  });

  test('listTrades forwards params (q + include_archived)', async () => {
    await tradesApi.listTrades({ params: { q: 'grou', include_archived: false } });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/trades',
      expect.objectContaining({ params: { q: 'grou', include_archived: false } }),
    );
  });

  test('createTrade POSTs /v1/trades with a `{ name }` body', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 'T9', name: 'Roofing' } });
    const row = await tradesApi.createTrade('Roofing');
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith('/v1/trades', { name: 'Roofing' });
    expect(row).toEqual({ id: 'T9', name: 'Roofing' });
  });
});
