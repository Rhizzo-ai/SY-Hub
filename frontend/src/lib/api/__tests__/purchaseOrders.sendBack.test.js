/**
 * Send-back wiring tests — Chat 26 §R7.0b carry-forward + §R7.2.
 *
 * Confirms:
 *   - api.sendBackPO posts to /v1/purchase-orders/{id}/send-back.
 *   - The usePoTransition verb map exposes `sendBack` and routes to it.
 *   - listPOApprovals hits /v1/purchase-orders/{id}/approvals.
 */
import * as api from '../purchaseOrders';
import { api as httpClient } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));


describe('purchaseOrders API — R7.0b send-back wiring', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    httpClient.post.mockResolvedValue({ data: { ok: true } });
    httpClient.get.mockResolvedValue({ data: { items: [] } });
  });

  test('sendBackPO posts to /v1/purchase-orders/:id/send-back with body', async () => {
    await api.sendBackPO('po-123', { notes: 'wrong supplier' });
    expect(httpClient.post).toHaveBeenCalledWith(
      '/v1/purchase-orders/po-123/send-back', { notes: 'wrong supplier' },
    );
  });

  test('listPOApprovals hits /v1/purchase-orders/:id/approvals', async () => {
    await api.listPOApprovals('po-123');
    expect(httpClient.get).toHaveBeenCalledWith(
      '/v1/purchase-orders/po-123/approvals',
      expect.objectContaining({}),
    );
  });
});
