/**
 * Supplier-document hooks — Chat 40 §R3 #11.
 *
 * TanStack Query wrappers around lib/api/supplierDocuments.js. The
 * list query key is keyed by both supplierId and the include-archived
 * flag so toggling the filter doesn't share cache with the unfiltered
 * view.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as docsApi from '@/lib/api/supplierDocuments';

export const docsKeys = {
  list: (supplierId, params = {}) => ['supplier-documents', supplierId, params],
  all: (supplierId) => ['supplier-documents', supplierId],
};

export function useSupplierDocuments(supplierId, { includeArchived = false, enabled = true } = {}) {
  return useQuery({
    queryKey: docsKeys.list(supplierId, { includeArchived }),
    queryFn: ({ signal }) => docsApi.listDocuments(supplierId, { signal, includeArchived }),
    enabled: enabled && !!supplierId,
  });
}

function invalidateDocsAndSuppliers(qc, supplierId) {
  // Coarse — both filtered + unfiltered list views need to refresh.
  qc.invalidateQueries({ queryKey: docsKeys.all(supplierId) });
}

export function useCreateDocument(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => docsApi.createDocument({ ...body, supplier_id: supplierId }),
    onSuccess: () => invalidateDocsAndSuppliers(qc, supplierId),
  });
}

export function usePatchDocument(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => docsApi.patchDocument(id, body),
    onSuccess: () => invalidateDocsAndSuppliers(qc, supplierId),
  });
}

export function useArchiveDocument(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => docsApi.archiveDocument(id),
    onSuccess: () => invalidateDocsAndSuppliers(qc, supplierId),
  });
}

export function useUnarchiveDocument(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => docsApi.unarchiveDocument(id),
    onSuccess: () => invalidateDocsAndSuppliers(qc, supplierId),
  });
}

/**
 * File upload mutation — Build Pack 2.7-FE-docupload §R4.1.
 *
 * Mirrors useCreateDocument: invalidates the docs list on success so the
 * row flips to the file-present state (the server response carries
 * has_file=true + sensitive file metadata). Replace uses the SAME
 * mutation — the backend treats a second upload as supersede.
 *
 * Download is intentionally NOT a hook: it's an imperative action
 * (blob → object URL → click → revoke) that doesn't belong in
 * react-query's cache.
 */
export function useUploadDocumentFile(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }) => docsApi.uploadDocumentFile(id, file),
    onSuccess: () => invalidateDocsAndSuppliers(qc, supplierId),
  });
}
