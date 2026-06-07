/**
 * Document-folder hooks — Build Pack 2.7-DOCS-FE §R3.3 (Chat 46, B79-FE).
 *
 * TanStack Query wrappers around `lib/api/documentFolders.js`. Mirrors
 * the conventions in `hooks/supplierDocuments.js` exactly:
 *   - query keys are arrays starting with the resource name + owner tuple,
 *   - the list query is keyed by include-archived so toggling the filter
 *     doesn't share cache with the unfiltered view,
 *   - mutations invalidate the broad owner-tree key (covers both filtered
 *     and unfiltered views).
 *
 * Cross-resource invalidation: folder mutations that change `file_count`
 * (no current ones do — files don't auto-attach on folder ops) leave the
 * docs cache alone; doc-MOVE invalidates BOTH (see hooks/supplierDocuments
 * `useMoveDocument`). Folder ARCHIVE doesn't touch docs (the backend
 * blocks archive when docs are present) but we still invalidate the docs
 * list because an unarchive may flip a doc's effective filed state.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as foldersApi from '@/lib/api/documentFolders';
import { docsKeys } from '@/hooks/supplierDocuments';


export const folderKeys = {
  tree: (ownerType, ownerId, params = {}) =>
    ['document-folders', ownerType, ownerId, params],
  all: (ownerType, ownerId) =>
    ['document-folders', ownerType, ownerId],
};


export function useFolderTree(
  ownerType, ownerId, { includeArchived = false, enabled = true } = {},
) {
  return useQuery({
    queryKey: folderKeys.tree(ownerType, ownerId, { includeArchived }),
    queryFn: ({ signal }) =>
      foldersApi.listFolderTree(ownerType, ownerId, { signal, includeArchived }),
    enabled: enabled && !!ownerType && !!ownerId,
  });
}


function invalidateOwnerTree(qc, ownerType, ownerId) {
  qc.invalidateQueries({ queryKey: folderKeys.all(ownerType, ownerId) });
}

// Folder mutations may affect file_count on RE-FILING (move) and on
// any archive/unarchive (the docs list rendering can pivot on
// folder visibility). The supplierId derives from the owner_id for
// supplier-typed folders; for other owner_types the docs cache is
// scoped differently and this helper is a no-op.
function invalidateOwnerDocs(qc, ownerType, ownerId) {
  if (ownerType === 'supplier') {
    qc.invalidateQueries({ queryKey: docsKeys.all(ownerId) });
  }
}


export function useCreateFolder(ownerType, ownerId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      foldersApi.createFolder({
        owner_type: ownerType,
        owner_id: ownerId,
        ...body,
      }),
    onSuccess: () => invalidateOwnerTree(qc, ownerType, ownerId),
  });
}


export function useRenameFolder(ownerType, ownerId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }) => foldersApi.renameFolder(id, name),
    onSuccess: () => invalidateOwnerTree(qc, ownerType, ownerId),
  });
}


export function useMoveFolder(ownerType, ownerId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, newParentId }) =>
      foldersApi.moveFolder(id, newParentId),
    onSuccess: () => invalidateOwnerTree(qc, ownerType, ownerId),
  });
}


export function useArchiveFolder(ownerType, ownerId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => foldersApi.archiveFolder(id),
    onSuccess: () => {
      invalidateOwnerTree(qc, ownerType, ownerId);
      invalidateOwnerDocs(qc, ownerType, ownerId);
    },
  });
}


export function useUnarchiveFolder(ownerType, ownerId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => foldersApi.unarchiveFolder(id),
    onSuccess: () => {
      invalidateOwnerTree(qc, ownerType, ownerId);
      invalidateOwnerDocs(qc, ownerType, ownerId);
    },
  });
}
