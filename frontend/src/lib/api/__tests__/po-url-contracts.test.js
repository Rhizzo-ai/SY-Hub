/**
 * URL-contract pins for the suppliers + purchase orders + receipts +
 * number-prefixes API client — Chat 24 §R5.7.
 *
 * Build Pack Future_Tasks §11: every new endpoint MUST land with a Jest
 * test that asserts the exact URL path string. This prevents the
 * "frontend silently calls /api/foo while backend mounts /api/v1/foo"
 * class of regression that bit chat-20 PromoteForm.
 *
 * 12+ pins required for R5. We pin every call site.
 */
import * as suppliersApi from '@/lib/api/suppliers';
import * as poApi from '@/lib/api/purchaseOrders';
import * as prefixApi from '@/lib/api/numberPrefixes';

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
  api.delete.mockResolvedValue({ data: null });
});


describe('Suppliers URL contracts', () => {
  test('listSuppliers → /v1/suppliers', async () => {
    await suppliersApi.listSuppliers({ params: { status: 'Active' } });
    expect(api.get).toHaveBeenCalledWith('/v1/suppliers', {
      params: { status: 'Active' }, signal: undefined,
    });
  });

  test('getSupplier → /v1/suppliers/{id}', async () => {
    await suppliersApi.getSupplier('S1');
    expect(api.get).toHaveBeenCalledWith('/v1/suppliers/S1', { signal: undefined });
  });

  test('createSupplier → POST /v1/suppliers', async () => {
    await suppliersApi.createSupplier({ name: 'ACME' });
    expect(api.post).toHaveBeenCalledWith('/v1/suppliers', { name: 'ACME' });
  });

  test('patchSupplier → PATCH /v1/suppliers/{id}', async () => {
    await suppliersApi.patchSupplier('S1', { notes: 'x' });
    expect(api.patch).toHaveBeenCalledWith('/v1/suppliers/S1', { notes: 'x' });
  });

  test('archiveSupplier → POST /v1/suppliers/{id}/archive', async () => {
    await suppliersApi.archiveSupplier('S1');
    expect(api.post).toHaveBeenCalledWith('/v1/suppliers/S1/archive', {});
  });

  test('restoreSupplier → POST /v1/suppliers/{id}/restore', async () => {
    await suppliersApi.restoreSupplier('S1');
    expect(api.post).toHaveBeenCalledWith('/v1/suppliers/S1/restore', {});
  });
});


describe('Purchase Orders URL contracts', () => {
  test('listProjectPOs → /v1/projects/{id}/purchase-orders', async () => {
    await poApi.listProjectPOs('P1', { params: { status: 'issued' } });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/projects/P1/purchase-orders',
      { params: { status: 'issued' }, signal: undefined },
    );
  });

  test('getPO → /v1/purchase-orders/{id}', async () => {
    await poApi.getPO('PO1');
    expect(api.get).toHaveBeenCalledWith('/v1/purchase-orders/PO1', { signal: undefined });
  });

  test('createPO → POST /v1/projects/{id}/purchase-orders', async () => {
    await poApi.createPO('P1', { supplier_id: 'S1' });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/projects/P1/purchase-orders', { supplier_id: 'S1' },
    );
  });

  test('patchPO → PATCH /v1/purchase-orders/{id}', async () => {
    await poApi.patchPO('PO1', { notes: 'x' });
    expect(api.patch).toHaveBeenCalledWith('/v1/purchase-orders/PO1', { notes: 'x' });
  });

  test('deletePO → DELETE /v1/purchase-orders/{id}', async () => {
    await poApi.deletePO('PO1');
    expect(api.delete).toHaveBeenCalledWith('/v1/purchase-orders/PO1');
  });

  test('submitPO → POST /v1/purchase-orders/{id}/submit', async () => {
    await poApi.submitPO('PO1');
    expect(api.post).toHaveBeenCalledWith('/v1/purchase-orders/PO1/submit', {});
  });

  test('approvePO → POST /v1/purchase-orders/{id}/approve', async () => {
    await poApi.approvePO('PO1', { note: 'ok' });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/purchase-orders/PO1/approve', { note: 'ok' },
    );
  });

  test('rejectPO → POST /v1/purchase-orders/{id}/reject', async () => {
    await poApi.rejectPO('PO1', { reason: 'nope' });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/purchase-orders/PO1/reject', { reason: 'nope' },
    );
  });

  test('issuePO → POST /v1/purchase-orders/{id}/issue', async () => {
    await poApi.issuePO('PO1');
    expect(api.post).toHaveBeenCalledWith('/v1/purchase-orders/PO1/issue', {});
  });

  test('voidPO → POST /v1/purchase-orders/{id}/void', async () => {
    await poApi.voidPO('PO1', { reason: 'dup' });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/purchase-orders/PO1/void', { reason: 'dup' },
    );
  });

  test('closePO → POST /v1/purchase-orders/{id}/close', async () => {
    await poApi.closePO('PO1');
    expect(api.post).toHaveBeenCalledWith('/v1/purchase-orders/PO1/close', {});
  });
});


describe('Receipts URL contracts', () => {
  test('listReceipts → /v1/purchase-orders/{id}/receipts', async () => {
    await poApi.listReceipts('PO1');
    expect(api.get).toHaveBeenCalledWith(
      '/v1/purchase-orders/PO1/receipts', { signal: undefined },
    );
  });

  test('createReceipt → POST /v1/purchase-orders/{id}/receipts', async () => {
    await poApi.createReceipt('PO1', { received_date: '2026-02-20', lines: [] });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/purchase-orders/PO1/receipts',
      { received_date: '2026-02-20', lines: [] },
    );
  });

  test('patchReceipt → PATCH /v1/receipts/{id}', async () => {
    await poApi.patchReceipt('R1', { notes: 'y' });
    expect(api.patch).toHaveBeenCalledWith('/v1/receipts/R1', { notes: 'y' });
  });

  test('deleteReceipt → DELETE /v1/receipts/{id}', async () => {
    await poApi.deleteReceipt('R1');
    expect(api.delete).toHaveBeenCalledWith('/v1/receipts/R1');
  });
});


describe('Number Prefix URL contracts', () => {
  test('listPrefixes → /v1/projects/{id}/number-prefixes', async () => {
    await prefixApi.listPrefixes('P1', { params: { document_type: 'PO' } });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/projects/P1/number-prefixes',
      { params: { document_type: 'PO' }, signal: undefined },
    );
  });

  test('createPrefix → POST /v1/projects/{id}/number-prefixes', async () => {
    await prefixApi.createPrefix('P1', { suffix: 'PO' });
    expect(api.post).toHaveBeenCalledWith(
      '/v1/projects/P1/number-prefixes', { suffix: 'PO' },
    );
  });

  test('patchPrefix → PATCH /v1/number-prefixes/{id}', async () => {
    await prefixApi.patchPrefix('NP1', { suffix: 'PO2' });
    expect(api.patch).toHaveBeenCalledWith('/v1/number-prefixes/NP1', { suffix: 'PO2' });
  });

  test('deletePrefix → DELETE /v1/number-prefixes/{id}', async () => {
    await prefixApi.deletePrefix('NP1');
    expect(api.delete).toHaveBeenCalledWith('/v1/number-prefixes/NP1');
  });
});
