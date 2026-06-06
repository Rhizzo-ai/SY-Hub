/**
 * Supplier-documents hooks tests — Build Pack 2.7-FE-docupload §R5 / §R6
 * (Gate 1 hook coverage).
 *
 * Pins:
 *   1. useSupplierDocuments — query key is supplier-scoped + tagged with
 *      the include-archived flag so the unfiltered vs filtered lists
 *      don't share cache.
 *   2. useCreateDocument / usePatchDocument / useArchiveDocument /
 *      useUnarchiveDocument — call the right API fn AND invalidate the
 *      docs list for this supplier on success.
 *   3. useUploadDocumentFile — calls docsApi.uploadDocumentFile with
 *      `{ id, file }`, invalidates the docs list on success (so the row
 *      flips to file-present). Mirror of useCreateDocument by design.
 *
 * Coarse invalidation (docsKeys.all) is the contract: BOTH the
 * filtered and unfiltered list views need to refresh after a write.
 */
import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('@/lib/api/supplierDocuments', () => ({
  listDocuments: jest.fn(),
  createDocument: jest.fn(),
  patchDocument: jest.fn(),
  archiveDocument: jest.fn(),
  unarchiveDocument: jest.fn(),
  uploadDocumentFile: jest.fn(),
}));

// eslint-disable-next-line import/first
import * as docsApi from '@/lib/api/supplierDocuments';
// eslint-disable-next-line import/first
import {
  docsKeys,
  useSupplierDocuments,
  useCreateDocument,
  usePatchDocument,
  useArchiveDocument,
  useUnarchiveDocument,
  useUploadDocumentFile,
} from '@/hooks/supplierDocuments';

const SUPPLIER_ID = 'SUP-1';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper, invalidateSpy };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('useSupplierDocuments — query-key contract', () => {
  test('keys by supplierId + include_archived flag (filtered ≠ unfiltered cache)', async () => {
    docsApi.listDocuments.mockResolvedValue([]);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useSupplierDocuments(SUPPLIER_ID, { includeArchived: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(docsApi.listDocuments).toHaveBeenCalledWith(
      SUPPLIER_ID,
      expect.objectContaining({ includeArchived: true }),
    );
  });

  test('is disabled when supplierId is falsy', () => {
    const { wrapper } = makeWrapper();
    renderHook(() => useSupplierDocuments(null), { wrapper });
    expect(docsApi.listDocuments).not.toHaveBeenCalled();
  });

  test('exposes a stable key shape via docsKeys.list/all', () => {
    expect(docsKeys.all(SUPPLIER_ID)).toEqual(['supplier-documents', SUPPLIER_ID]);
    expect(docsKeys.list(SUPPLIER_ID, { includeArchived: true })).toEqual([
      'supplier-documents', SUPPLIER_ID, { includeArchived: true },
    ]);
  });
});

describe('useCreateDocument — invalidates on success', () => {
  test('calls createDocument with supplier_id mixed into body, invalidates docs list', async () => {
    docsApi.createDocument.mockResolvedValueOnce({ id: 'D1' });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCreateDocument(SUPPLIER_ID), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ doc_type: 'insurance' });
    });

    expect(docsApi.createDocument).toHaveBeenCalledWith({
      doc_type: 'insurance',
      supplier_id: SUPPLIER_ID,
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: docsKeys.all(SUPPLIER_ID),
    });
  });
});

describe('usePatchDocument / useArchiveDocument / useUnarchiveDocument', () => {
  test('patch invalidates docs list', async () => {
    docsApi.patchDocument.mockResolvedValueOnce({ id: 'D1' });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => usePatchDocument(SUPPLIER_ID), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ id: 'D1', body: { notes: 'x' } });
    });

    expect(docsApi.patchDocument).toHaveBeenCalledWith('D1', { notes: 'x' });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: docsKeys.all(SUPPLIER_ID),
    });
  });

  test('archive invalidates docs list', async () => {
    docsApi.archiveDocument.mockResolvedValueOnce({ id: 'D1' });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useArchiveDocument(SUPPLIER_ID), { wrapper });

    await act(async () => { await result.current.mutateAsync('D1'); });

    expect(docsApi.archiveDocument).toHaveBeenCalledWith('D1');
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: docsKeys.all(SUPPLIER_ID),
    });
  });

  test('unarchive invalidates docs list', async () => {
    docsApi.unarchiveDocument.mockResolvedValueOnce({ id: 'D1' });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUnarchiveDocument(SUPPLIER_ID), { wrapper });

    await act(async () => { await result.current.mutateAsync('D1'); });

    expect(docsApi.unarchiveDocument).toHaveBeenCalledWith('D1');
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: docsKeys.all(SUPPLIER_ID),
    });
  });
});

describe('useUploadDocumentFile — §R4.1', () => {
  test('calls uploadDocumentFile(id, file) and invalidates docs on success', async () => {
    const file = new File(['hello'], 'cert.pdf', { type: 'application/pdf' });
    docsApi.uploadDocumentFile.mockResolvedValueOnce({
      id: 'D1', has_file: true, file_name: 'cert.pdf',
      file_size: 5, file_content_type: 'application/pdf',
    });

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(
      () => useUploadDocumentFile(SUPPLIER_ID),
      { wrapper },
    );

    let returned;
    await act(async () => {
      returned = await result.current.mutateAsync({ id: 'D1', file });
    });

    expect(docsApi.uploadDocumentFile).toHaveBeenCalledTimes(1);
    expect(docsApi.uploadDocumentFile).toHaveBeenCalledWith('D1', file);
    expect(returned.has_file).toBe(true);

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: docsKeys.all(SUPPLIER_ID),
    });
  });

  test('does NOT invalidate when upload rejects (e.g. 413/422/502)', async () => {
    const file = new File(['x'], 'big.pdf', { type: 'application/pdf' });
    docsApi.uploadDocumentFile.mockRejectedValueOnce(
      Object.assign(new Error('boom'), { response: { status: 413 } }),
    );

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(
      () => useUploadDocumentFile(SUPPLIER_ID),
      { wrapper },
    );

    await act(async () => {
      await expect(
        result.current.mutateAsync({ id: 'D1', file }),
      ).rejects.toMatchObject({ response: { status: 413 } });
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
