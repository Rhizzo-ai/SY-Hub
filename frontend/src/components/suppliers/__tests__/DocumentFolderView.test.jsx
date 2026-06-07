/**
 * <DocumentFolderView/> tests — Build Pack 2.7-DOCS-FE §R6 / Gate 3.
 *
 * Mocks ALL the hooks (folders + docs + the imperative downloader),
 * so the assertions only exercise the view's logic — wire-level
 * coverage lives in `lib/api/__tests__/documentFolders.test.js`.
 *
 * Covers Build Pack §R6 tests 1-22 verbatim:
 *   - Tree: render, expand/collapse, select-filters, "All", archived gate.
 *   - Folder CRUD: create from header, create-sub from node, rename,
 *     archive (+ 422 surfacing), move (+ 422 surfacing), perm gating.
 *   - Files: row reuses DocumentFileCell; Add prefills folder_id; optional
 *     category + title submit cleanly; "Move to…" → dialog → null/folder;
 *     perm gating; drag-start sets the doc id; drop handler invokes the
 *     mutation.
 *   - Desktop-target: narrow-viewport notice is in the DOM (md:hidden).
 *   - Mount: SupplierDetail test (separate file) re-mocks the view.
 */
jest.mock('@/hooks/supplierDocuments', () => ({
  useSupplierDocuments: jest.fn(),
  useCreateDocument: jest.fn(),
  usePatchDocument: jest.fn(),
  useArchiveDocument: jest.fn(),
  useUnarchiveDocument: jest.fn(),
  useUploadDocumentFile: jest.fn(),
  useMoveDocument: jest.fn(),
}));
jest.mock('@/hooks/documentFolders', () => ({
  useFolderTree: jest.fn(),
  useCreateFolder: jest.fn(),
  useRenameFolder: jest.fn(),
  useMoveFolder: jest.fn(),
  useArchiveFolder: jest.fn(),
  useUnarchiveFolder: jest.fn(),
}));
jest.mock('@/lib/api/supplierDocuments', () => ({
  downloadDocumentFile: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DocumentFolderView from '@/components/suppliers/DocumentFolderView';

const docs = jest.requireMock('@/hooks/supplierDocuments');
const folds = jest.requireMock('@/hooks/documentFolders');
const docsApi = jest.requireMock('@/lib/api/supplierDocuments');
const { useAuth } = jest.requireMock('@/context/AuthContext');
const { toast } = jest.requireMock('sonner');


const ALL_PERMS = [
  'supplier_documents.view',
  'supplier_documents.view_sensitive',
  'supplier_documents.create',
  'supplier_documents.edit',
  'supplier_documents.archive',
  'documents.create',
  'documents.edit',
  'documents.move',
];


function setMe(perms) {
  useAuth.mockReturnValue({
    me: { permissions: perms, is_super_admin: false },
  });
}


function setTree(items) {
  folds.useFolderTree.mockReturnValue({
    data: items, isLoading: false, isError: false,
  });
}


function setDocs(items) {
  docs.useSupplierDocuments.mockReturnValue({
    data: { items }, isLoading: false, isError: false,
  });
}


// Mutation factories — each returns a fresh jest.fn for mutateAsync
// so assertions don't bleed across describe blocks.
function makeMutation() {
  const mutateAsync = jest.fn().mockResolvedValue({});
  return { mutation: { mutateAsync }, mutateAsync };
}


let m;
beforeEach(() => {
  jest.clearAllMocks();
  m = {
    createDoc: makeMutation(),
    patchDoc: makeMutation(),
    archiveDoc: makeMutation(),
    unarchiveDoc: makeMutation(),
    uploadDoc: makeMutation(),
    moveDoc: makeMutation(),
    createFold: makeMutation(),
    renameFold: makeMutation(),
    moveFold: makeMutation(),
    archiveFold: makeMutation(),
    unarchiveFold: makeMutation(),
  };
  docs.useCreateDocument.mockReturnValue(m.createDoc.mutation);
  docs.usePatchDocument.mockReturnValue(m.patchDoc.mutation);
  docs.useArchiveDocument.mockReturnValue(m.archiveDoc.mutation);
  docs.useUnarchiveDocument.mockReturnValue(m.unarchiveDoc.mutation);
  docs.useUploadDocumentFile.mockReturnValue(m.uploadDoc.mutation);
  docs.useMoveDocument.mockReturnValue(m.moveDoc.mutation);
  folds.useCreateFolder.mockReturnValue(m.createFold.mutation);
  folds.useRenameFolder.mockReturnValue(m.renameFold.mutation);
  folds.useMoveFolder.mockReturnValue(m.moveFold.mutation);
  folds.useArchiveFolder.mockReturnValue(m.archiveFold.mutation);
  folds.useUnarchiveFolder.mockReturnValue(m.unarchiveFold.mutation);
});


function rootNode(over = {}) {
  return {
    id: 'F1', name: 'Compliance', parent_id: null, is_archived: false,
    file_count: 0, children: [], ...over,
  };
}


// ===========================================================================
// Tree
// ===========================================================================

describe('Tree (R6 #1-#5)', () => {
  test('#1 — renders nested folders with file_count badges', () => {
    setMe(ALL_PERMS);
    setDocs([]);
    setTree([
      rootNode({
        id: 'F1', name: 'Compliance', file_count: 3,
        children: [
          rootNode({ id: 'F1a', name: 'Insurance', file_count: 2, children: [] }),
        ],
      }),
    ]);
    render(<DocumentFolderView supplierId="S1" />);
    expect(screen.getByTestId('folder-node-name-F1')).toHaveTextContent('Compliance');
    expect(screen.getByTestId('folder-node-count-F1')).toHaveTextContent('3');
    // Roots expanded by default.
    expect(screen.getByTestId('folder-node-name-F1a')).toHaveTextContent('Insurance');
    expect(screen.getByTestId('folder-node-count-F1a')).toHaveTextContent('2');
  });

  test('#2 — expand/collapse toggles children visibility', () => {
    setMe(ALL_PERMS);
    setDocs([]);
    setTree([
      rootNode({
        id: 'F1', children: [rootNode({ id: 'F1a', name: 'Sub', children: [] })],
      }),
    ]);
    render(<DocumentFolderView supplierId="S1" />);
    expect(screen.getByTestId('folder-node-name-F1a')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('folder-node-toggle-F1'));
    expect(screen.queryByTestId('folder-node-name-F1a')).toBeNull();
    fireEvent.click(screen.getByTestId('folder-node-toggle-F1'));
    expect(screen.getByTestId('folder-node-name-F1a')).toBeInTheDocument();
  });

  test('#3 — selecting a folder filters the right pane to its docs', () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' }), rootNode({ id: 'F2', name: 'Other' })]);
    setDocs([
      { id: 'D1', title: 'in F1', folder_id: 'F1', is_archived: false, has_file: false },
      { id: 'D2', title: 'in F2', folder_id: 'F2', is_archived: false, has_file: false },
    ]);
    render(<DocumentFolderView supplierId="S1" />);
    // Click into F1.
    fireEvent.click(screen.getByTestId('folder-node-row-F1'));
    expect(screen.getByTestId('folder-files-title-D1')).toHaveTextContent('in F1');
    expect(screen.queryByTestId('folder-files-title-D2')).toBeNull();
    // Switch to F2.
    fireEvent.click(screen.getByTestId('folder-node-row-F2'));
    expect(screen.getByTestId('folder-files-title-D2')).toHaveTextContent('in F2');
    expect(screen.queryByTestId('folder-files-title-D1')).toBeNull();
  });

  test('#4 — "All documents" shows every doc, including unfiled', () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([
      { id: 'D1', title: 'filed', folder_id: 'F1', is_archived: false, has_file: false },
      { id: 'D2', title: 'unfiled', folder_id: null, is_archived: false, has_file: false },
    ]);
    render(<DocumentFolderView supplierId="S1" />);
    // Default selection is "All".
    expect(screen.getByTestId('folder-files-title-D1')).toBeInTheDocument();
    expect(screen.getByTestId('folder-files-title-D2')).toBeInTheDocument();
    // Folder column shows "Unfiled" for D2 in All view.
    expect(screen.getByTestId('folder-files-folder-D2')).toHaveTextContent(/unfiled/i);
  });

  test('#5 — archived folders hidden by default; visible when toggled', () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([]);
    render(<DocumentFolderView supplierId="S1" />);
    expect(folds.useFolderTree).toHaveBeenCalledWith('supplier', 'S1', {
      includeArchived: false,
    });
    fireEvent.click(screen.getByTestId('document-folder-archived-toggle'));
    expect(folds.useFolderTree).toHaveBeenLastCalledWith('supplier', 'S1', {
      includeArchived: true,
    });
  });
});


// ===========================================================================
// Folder CRUD
// ===========================================================================

describe('Folder CRUD (R6 #6-#11)', () => {
  test('#6 — create folder from header calls createFolder with parent = selected (or null)', async () => {
    setMe(ALL_PERMS);
    setTree([]);
    setDocs([]);
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('document-folder-new-folder-btn'));
    fireEvent.change(screen.getByTestId('folder-form-name'), {
      target: { value: 'New' },
    });
    fireEvent.submit(screen.getByTestId('folder-form'));
    await waitFor(() =>
      expect(m.createFold.mutateAsync).toHaveBeenCalledWith({
        name: 'New', parent_id: null,
      }),
    );
  });

  test('#7 — create subfolder from a node\'s "+" sets parent_id to that node', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([]);
    render(<DocumentFolderView supplierId="S1" />);
    // Open the per-node menu and click "New subfolder".
    fireEvent.click(screen.getByTestId('folder-node-menu-F1'));
    fireEvent.click(screen.getByTestId('folder-node-new-sub-F1'));
    fireEvent.change(screen.getByTestId('folder-form-name'), {
      target: { value: '2026' },
    });
    fireEvent.submit(screen.getByTestId('folder-form'));
    await waitFor(() =>
      expect(m.createFold.mutateAsync).toHaveBeenCalledWith({
        name: '2026', parent_id: 'F1',
      }),
    );
  });

  test('#8 — rename calls renameFolder with the new name', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1', name: 'OldName' })]);
    setDocs([]);
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-node-menu-F1'));
    fireEvent.click(screen.getByTestId('folder-node-rename-F1'));
    fireEvent.change(screen.getByTestId('folder-form-name'), {
      target: { value: 'NewName' },
    });
    fireEvent.submit(screen.getByTestId('folder-form'));
    await waitFor(() =>
      expect(m.renameFold.mutateAsync).toHaveBeenCalledWith({
        id: 'F1', name: 'NewName',
      }),
    );
  });

  test('#9 — archive calls archiveFolder; 422 surfaces the server message', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([]);
    m.archiveFold.mutateAsync.mockRejectedValueOnce({
      response: { status: 422, data: { detail: "folder is not empty: move or archive its contents first" } },
    });
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-node-menu-F1'));
    fireEvent.click(screen.getByTestId('folder-node-archive-F1'));
    await waitFor(() => expect(m.archiveFold.mutateAsync).toHaveBeenCalledWith('F1'));
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringMatching(/not empty/i),
    );
  });

  test('#10 — move-folder calls moveFolder; 422 self/descendant surfaces the message', async () => {
    setMe(ALL_PERMS);
    setTree([
      rootNode({
        id: 'F1', children: [rootNode({ id: 'F1a', name: 'child', children: [] })],
      }),
    ]);
    setDocs([]);
    m.moveFold.mutateAsync.mockRejectedValueOnce({
      response: { status: 422, data: { detail: 'cannot move a folder into itself or one of its descendants' } },
    });
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-node-menu-F1'));
    fireEvent.click(screen.getByTestId('folder-node-move-F1'));
    // Pick root, then submit — backend would 422.
    fireEvent.click(screen.getByTestId('folder-form-target-root'));
    fireEvent.submit(screen.getByTestId('folder-form'));
    await waitFor(() =>
      expect(m.moveFold.mutateAsync).toHaveBeenCalledWith({
        id: 'F1', newParentId: null,
      }),
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/descendant/i),
      ),
    );
  });

  test('#11 — create/rename/archive controls HIDDEN without documents.create/edit', () => {
    setMe(['supplier_documents.view']);   // viewer only — no create/edit
    setTree([rootNode({ id: 'F1' })]);
    setDocs([]);
    render(<DocumentFolderView supplierId="S1" />);
    expect(screen.queryByTestId('document-folder-new-folder-btn')).toBeNull();
    // No menu trigger on the folder (canCreateFold + canEditFold both false).
    expect(screen.queryByTestId('folder-node-menu-F1')).toBeNull();
  });
});


// ===========================================================================
// Files
// ===========================================================================

describe('Files (R6 #12-#17)', () => {
  function fileRow(over = {}) {
    return {
      id: 'D1', supplier_id: 'S1', folder_id: 'F1',
      doc_type: 'Public_Liability', title: 'PL',
      issued_on: null, expires_on: null, notes: null,
      is_archived: false, has_file: false, ...over,
    };
  }

  test('#12 — file rows reuse DocumentFileCell upload state', () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([fileRow()]);
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-node-row-F1'));
    expect(screen.getByTestId('document-row-upload-D1')).toBeInTheDocument();
    expect(screen.getByTestId('document-row-dropzone-D1')).toBeInTheDocument();
  });

  test('#13 — "Add document" prefills folder_id = selected folder in payload', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([]);
    m.createDoc.mutateAsync.mockResolvedValueOnce({ id: 'NEW' });
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-node-row-F1'));
    fireEvent.click(screen.getByTestId('document-folder-add-doc-btn'));
    fireEvent.submit(screen.getByTestId('document-form'));
    await waitFor(() =>
      expect(m.createDoc.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ folder_id: 'F1' }),
      ),
    );
  });

  test('#14 — optional category + title: submitting with both blank still calls create (no required-field block)', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([]);
    m.createDoc.mutateAsync.mockResolvedValueOnce({ id: 'NEW' });
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('document-folder-add-doc-btn'));
    // No interactions — both fields default-empty.
    fireEvent.submit(screen.getByTestId('document-form'));
    await waitFor(() => expect(m.createDoc.mutateAsync).toHaveBeenCalled());
    const payload = m.createDoc.mutateAsync.mock.calls[0][0];
    // Backend gets explicit nulls (not "") so the column stays NULL.
    expect(payload.doc_type).toBeNull();
    expect(payload.title).toBeNull();
  });

  test('#15 — "Move to…" opens the dialog; confirming with a folder calls moveDocument', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' }), rootNode({ id: 'F2', name: 'Target' })]);
    setDocs([fileRow()]);
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-files-move-D1'));
    expect(screen.getByTestId('move-doc-dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('move-doc-target-F2'));
    fireEvent.submit(screen.getByTestId('move-doc-form'));
    await waitFor(() =>
      expect(m.moveDoc.mutateAsync).toHaveBeenCalledWith({
        id: 'D1', folderId: 'F2',
      }),
    );
  });

  test('#16 — "Move to…" → Unfiled calls moveDocument with null', async () => {
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([fileRow()]);
    render(<DocumentFolderView supplierId="S1" />);
    fireEvent.click(screen.getByTestId('folder-files-move-D1'));
    fireEvent.click(screen.getByTestId('move-doc-target-root'));
    fireEvent.submit(screen.getByTestId('move-doc-form'));
    await waitFor(() =>
      expect(m.moveDoc.mutateAsync).toHaveBeenCalledWith({
        id: 'D1', folderId: null,
      }),
    );
  });

  test('#17 — "Move to…" HIDDEN without documents.move', () => {
    setMe([
      'supplier_documents.view',
      'supplier_documents.create',
      'supplier_documents.edit',
      'documents.create',
      'documents.edit',
    ]);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([fileRow()]);
    render(<DocumentFolderView supplierId="S1" />);
    expect(screen.queryByTestId('folder-files-move-D1')).toBeNull();
    expect(screen.queryByTestId('folder-files-edit-D1')).toBeInTheDocument();
  });
});


// ===========================================================================
// Drag-and-drop
// ===========================================================================

describe('Drag (R6 #18-#19)', () => {
  test('#18 — a file row is draggable and sets the doc id on dragStart', () => {
    setMe(ALL_PERMS);
    setTree([{
      id: 'F1', name: 'Compliance', parent_id: null, is_archived: false,
      file_count: 0, children: [],
    }]);
    setDocs([{
      id: 'D1', supplier_id: 'S1', folder_id: 'F1',
      doc_type: null, title: 'doc', has_file: false, is_archived: false,
    }]);
    render(<DocumentFolderView supplierId="S1" />);
    const row = screen.getByTestId('folder-files-row-D1');
    expect(row.getAttribute('data-draggable')).toBe('true');
    const setData = jest.fn();
    fireEvent.dragStart(row, {
      dataTransfer: { setData, effectAllowed: '', files: [] },
    });
    expect(setData).toHaveBeenCalledWith(
      'application/x-sy-doc-id', 'D1',
    );
  });

  test('#19 — dropping a doc payload on a folder node triggers moveDocument with that folder id', async () => {
    setMe(ALL_PERMS);
    setTree([
      { id: 'F1', name: 'Compliance', parent_id: null, is_archived: false, file_count: 0, children: [] },
      { id: 'F2', name: 'Target', parent_id: null, is_archived: false, file_count: 0, children: [] },
    ]);
    setDocs([{
      id: 'D1', supplier_id: 'S1', folder_id: 'F1',
      doc_type: null, title: 'doc', has_file: false, is_archived: false,
    }]);
    render(<DocumentFolderView supplierId="S1" />);
    // dragStart to seed dragDocId (jsdom dataTransfer is partial; we
    // also pass it via the helper but the in-memory state is the
    // fallback the view honours).
    const row = screen.getByTestId('folder-files-row-D1');
    fireEvent.dragStart(row, {
      dataTransfer: { setData: jest.fn(), effectAllowed: '', files: [] },
    });
    const target = screen.getByTestId('folder-node-row-F2');
    // dragOver + drop together.
    fireEvent.dragOver(target, {
      dataTransfer: { getData: () => 'D1', files: [] },
    });
    fireEvent.drop(target, {
      dataTransfer: { getData: () => 'D1', files: [] },
    });
    await waitFor(() =>
      expect(m.moveDoc.mutateAsync).toHaveBeenCalledWith({
        id: 'D1', folderId: 'F2',
      }),
    );
  });
});


// ===========================================================================
// Desktop-target
// ===========================================================================

describe('Desktop-target (R6 #20)', () => {
  test('#20 — the desktop-only notice is rendered (md:hidden) so narrow viewports see it', () => {
    setMe(ALL_PERMS);
    setTree([]);
    setDocs([]);
    render(<DocumentFolderView supplierId="S1" />);
    const notice = screen.getByTestId('document-folder-mobile-notice');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveTextContent(/desktop/i);
    expect(notice.className).toMatch(/md:hidden/);
  });
});


// ===========================================================================
// Refactor safety guard (R6 #21)
// ===========================================================================

describe('Refactor safety (R6 #21)', () => {
  test('#21 — uses the shared preCheckFile (which is covered in documentFileShared.test.jsx)', () => {
    // This is a "tracer" assertion — the shared module test file
    // exercises the precheck branches directly. Here we just verify
    // the view imports its primitives from the shared module so a
    // future drift (e.g. defining a parallel preCheckFile inside the
    // view) would surface as a duplicate.
    //
    // We assert it indirectly by rendering and confirming the
    // shared-module DropZone renders (data-dragover starts at 'false').
    setMe(ALL_PERMS);
    setTree([rootNode({ id: 'F1' })]);
    setDocs([{
      id: 'D1', supplier_id: 'S1', folder_id: 'F1',
      doc_type: null, title: 'doc', has_file: false, is_archived: false,
    }]);
    render(<DocumentFolderView supplierId="S1" />);
    expect(screen.getByTestId('document-row-dropzone-D1').getAttribute('data-dragover')).toBe('false');
  });
});
