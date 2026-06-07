/**
 * <DocumentFolderView/> — Build Pack 2.7-DOCS-FE §R4 (Chat 46, B79-FE).
 *
 * Two-pane folder browser that replaces `<DocumentsTab/>` (the flat
 * supplier-documents table). Tree on the left, file list on the right.
 *
 *   - DESKTOP-TARGET (operator decision §R0.2): build for desktop;
 *     render a graceful single-column fallback + "best on desktop"
 *     notice on narrow viewports. NO real mobile UX in this pack.
 *   - MOVE PATHS (§R0.3 F2): drag-and-drop is primary polish; the
 *     "Move to…" button is the canonical headlessly-testable path.
 *   - FILE PRIMITIVES (§R0.3 F3): upload / replace / download re-use
 *     `documentFileShared` verbatim — zero reimplementation.
 *   - DIRECT CONTENTS (§R4.3): the right pane shows docs WHERE
 *     `folder_id === selectedFolderId`. Not recursive. This matches
 *     the backend's `file_count` (DIRECT count per folder).
 *   - "All documents" (§R4.4): `selectedFolderId = null` shows every
 *     doc for the supplier including unfiled (folder_id === null).
 *   - OPTIONAL FIELDS (§R0.3 F4 / Chat 45 D4/D5): doc_type + title are
 *     OPTIONAL on the backend. The dialog keeps the dropdown + title
 *     input; both default-empty; placeholder explains the title
 *     auto-fills from filename if left blank.
 *
 * State lives at the view level — child components are dumb. The state
 * is intentionally minimal to keep React re-renders cheap.
 */
import React, { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Folder, FolderPlus, FilePlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';

import { useAuth } from '@/context/AuthContext';
import {
  useSupplierDocuments, useCreateDocument, usePatchDocument,
  useArchiveDocument, useUnarchiveDocument, useUploadDocumentFile,
  useMoveDocument,
} from '@/hooks/supplierDocuments';
import {
  useFolderTree, useCreateFolder, useRenameFolder, useMoveFolder,
  useArchiveFolder, useUnarchiveFolder,
} from '@/hooks/documentFolders';
import { downloadDocumentFile } from '@/lib/api/supplierDocuments';
import {
  canCreateDocs, canEditDocs, canArchiveDocs, canViewSensitiveDocs,
  canCreateFolder, canEditFolder, canMoveDocs,
} from '@/lib/poCapability';
import DocExpiryBadge from '@/components/suppliers/DocExpiryBadge';
import {
  DOC_TYPE_OPTIONS, formatDate, labelDocType,
} from '@/lib/cisFormat';
import {
  ACCEPT_ATTR,
  preCheckFile,
  uploadErrorMessage,
  downloadErrorMessage,
  formatFileSize,
  FilePicker,
  DropZone,
  DocumentFileCell,
} from '@/components/suppliers/documentFileShared';
import FolderNode, { DRAG_DOC_MIME } from '@/components/suppliers/FolderNode';
import FolderPicker from '@/components/suppliers/FolderPicker';


const OWNER_TYPE = 'supplier';


function emptyDocForm() {
  return {
    doc_type: '',
    title: '',
    issued_on: '',
    expires_on: '',
    notes: '',
  };
}

function docRowToForm(row) {
  return {
    doc_type: row.doc_type ?? '',
    title: row.title ?? '',
    issued_on: row.issued_on ?? '',
    expires_on: row.expires_on ?? '',
    notes: row.notes ?? '',
  };
}


function flattenTree(nodes) {
  const out = [];
  const walk = (list) => {
    for (const n of list) {
      out.push(n);
      if (n.children?.length) walk(n.children);
    }
  };
  walk(nodes || []);
  return out;
}

function folderPathById(nodes, id) {
  const path = [];
  const walk = (list, trail) => {
    for (const n of list) {
      const next = [...trail, n];
      if (n.id === id) {
        next.forEach((step) => path.push(step));
        return true;
      }
      if (n.children?.length && walk(n.children, next)) return true;
    }
    return false;
  };
  walk(nodes || [], []);
  return path;
}


export default function DocumentFolderView({ supplierId }) {
  const { me } = useAuth();
  const canCreate = canCreateDocs(me);
  const canEdit = canEditDocs(me);
  const canArchive = canArchiveDocs(me);
  const canSensitive = canViewSensitiveDocs(me);
  const canCreateFold = canCreateFolder(me);
  const canEditFold = canEditFolder(me);
  const canMove = canMoveDocs(me);

  const [selectedFolderId, setSelectedFolderId] = useState(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  // Default = every root expanded; overrides[id] explicitly opens/closes.
  // Pure-derived `expanded` Set is computed below — no useEffect, no
  // react-hooks/set-state-in-effect.
  const [overrides, setOverrides] = useState(() => new Map());
  const [dragDocId, setDragDocId] = useState(null);

  const treeQ = useFolderTree(OWNER_TYPE, supplierId, { includeArchived });
  const docsQ = useSupplierDocuments(supplierId, { includeArchived });

  const expanded = useMemo(() => {
    const eff = new Set();
    (treeQ.data || []).forEach((r) => {
      if (overrides.has(r.id)) {
        if (overrides.get(r.id)) eff.add(r.id);
      } else {
        eff.add(r.id);
      }
    });
    for (const [id, val] of overrides) {
      if (val) eff.add(id);
    }
    return eff;
  }, [treeQ.data, overrides]);

  const toggleExpand = (id) =>
    setOverrides((prev) => {
      const isOpen = expanded.has(id);
      const next = new Map(prev);
      next.set(id, !isOpen);
      return next;
    });

  const createDoc = useCreateDocument(supplierId);
  const patchDoc = usePatchDocument(supplierId);
  const archiveDoc = useArchiveDocument(supplierId);
  const unarchiveDoc = useUnarchiveDocument(supplierId);
  const uploadDoc = useUploadDocumentFile(supplierId);
  const moveDoc = useMoveDocument(supplierId);

  const createFold = useCreateFolder(OWNER_TYPE, supplierId);
  const renameFold = useRenameFolder(OWNER_TYPE, supplierId);
  const moveFold = useMoveFolder(OWNER_TYPE, supplierId);
  const archiveFold = useArchiveFolder(OWNER_TYPE, supplierId);
  const unarchiveFold = useUnarchiveFolder(OWNER_TYPE, supplierId);

  const [docDialog, setDocDialog] = useState(null);
  const [folderDialog, setFolderDialog] = useState(null);
  const [moveDocDialog, setMoveDocDialog] = useState(null);
  const [rowErrors, setRowErrors] = useState({});
  const [uploadingId, setUploadingId] = useState(null);

  const tree = treeQ.data || [];
  const flatFolders = useMemo(() => flattenTree(tree), [tree]);
  const folderById = useMemo(() => {
    const m = new Map();
    flatFolders.forEach((f) => m.set(f.id, f));
    return m;
  }, [flatFolders]);

  const allDocs = docsQ.data?.items ?? [];
  const docsInPane = useMemo(() => {
    if (selectedFolderId === null) return allDocs;
    return allDocs.filter((d) => d.folder_id === selectedFolderId);
  }, [allDocs, selectedFolderId]);

  const breadcrumb = useMemo(
    () => (selectedFolderId ? folderPathById(tree, selectedFolderId) : []),
    [tree, selectedFolderId],
  );

  const selectedFolder =
    selectedFolderId ? folderById.get(selectedFolderId) ?? null : null;

  // ─── Doc dialog ──────────────────────────────────────────────────────
  const openCreateDoc = () => setDocDialog({
    mode: 'create',
    form: emptyDocForm(),
    editingId: null,
    pendingFile: null,
    pendingFileError: null,
  });
  const openEditDoc = (row) => setDocDialog({
    mode: 'edit',
    form: docRowToForm(row),
    editingId: row.id,
    pendingFile: null,
    pendingFileError: null,
  });
  const closeDocDialog = () => setDocDialog(null);

  const onDocDialogPick = (file) => {
    setDocDialog((d) => {
      if (!d) return d;
      const inline = preCheckFile(file);
      if (inline) return { ...d, pendingFile: null, pendingFileError: inline };
      return { ...d, pendingFile: file, pendingFileError: null };
    });
  };

  const onSubmitDoc = async (e) => {
    e.preventDefault();
    if (!docDialog) return;
    const { form, editingId, pendingFile } = docDialog;
    const payload = {
      doc_type: form.doc_type?.trim() ? form.doc_type.trim() : null,
      title: form.title?.trim() ? form.title.trim() : null,
    };
    if (form.issued_on) payload.issued_on = form.issued_on;
    if (form.expires_on) payload.expires_on = form.expires_on;
    if (form.notes) payload.notes = form.notes;
    if (!editingId) payload.folder_id = selectedFolderId;

    let savedId = null;
    try {
      if (editingId) {
        await patchDoc.mutateAsync({ id: editingId, body: payload });
        savedId = editingId;
        toast.success('Document updated');
      } else {
        const created = await createDoc.mutateAsync(payload);
        savedId = created?.id ?? null;
        toast.success('Document added');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Save failed';
      toast.error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      return;
    }

    if (pendingFile && savedId) {
      try {
        await uploadDoc.mutateAsync({ id: savedId, file: pendingFile });
      } catch (err) {
        closeDocDialog();
        toast.error(uploadErrorMessage(err));
        return;
      }
    }
    closeDocDialog();
  };

  // ─── Row actions ─────────────────────────────────────────────────────
  const onPickRowFile = async (rowId, file) => {
    setRowErrors((s) => ({ ...s, [rowId]: null }));
    const inline = preCheckFile(file);
    if (inline) {
      setRowErrors((s) => ({ ...s, [rowId]: inline }));
      return;
    }
    setUploadingId(rowId);
    try {
      await uploadDoc.mutateAsync({ id: rowId, file });
      toast.success('File uploaded');
    } catch (err) {
      toast.error(uploadErrorMessage(err));
    } finally {
      setUploadingId(null);
    }
  };

  const onDownload = async (row) => {
    try {
      const { blob, filename } = await downloadDocumentFile(row.id);
      const objectUrl = URL.createObjectURL(blob);
      try {
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = filename || row.file_name || 'document';
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    } catch (err) {
      toast.error(downloadErrorMessage(err));
    }
  };

  const onArchiveRow = async (row) => {
    try {
      await archiveDoc.mutateAsync(row.id);
      toast.success('Document archived');
    } catch (err) {
      toast.error(err?.response?.data?.detail ?? 'Archive failed');
    }
  };
  const onRestoreRow = async (row) => {
    try {
      await unarchiveDoc.mutateAsync(row.id);
      toast.success('Document restored');
    } catch (err) {
      toast.error(err?.response?.data?.detail ?? 'Restore failed');
    }
  };

  // ─── Drag / move ─────────────────────────────────────────────────────
  const handleDropDocOnFolder = async (folderId, docId) => {
    if (!docId) return;
    if (!canMove) {
      toast.error("You don't have permission to do that.");
      return;
    }
    try {
      await moveDoc.mutateAsync({ id: docId, folderId });
      toast.success('Document moved');
    } catch (err) {
      mapMoveError(err);
    } finally {
      setDragDocId(null);
    }
  };

  // ─── Folder dialog submits ───────────────────────────────────────────
  const onSubmitFolderDialog = async (e) => {
    e.preventDefault();
    if (!folderDialog) return;
    const { mode } = folderDialog;
    try {
      if (mode === 'create') {
        await createFold.mutateAsync({
          name: folderDialog.name?.trim(),
          parent_id: folderDialog.parentId ?? null,
        });
        toast.success('Folder created');
      } else if (mode === 'rename') {
        await renameFold.mutateAsync({
          id: folderDialog.folderId,
          name: folderDialog.name?.trim(),
        });
        toast.success('Folder renamed');
      } else if (mode === 'move') {
        await moveFold.mutateAsync({
          id: folderDialog.folderId,
          newParentId: folderDialog.newParentId ?? null,
        });
        toast.success('Folder moved');
      }
      setFolderDialog(null);
    } catch (err) {
      mapMoveError(err);
    }
  };

  const onArchiveFolderClick = async (folder) => {
    try {
      await archiveFold.mutateAsync(folder.id);
      toast.success('Folder archived');
    } catch (err) {
      mapMoveError(err);
    }
  };
  const onUnarchiveFolderClick = async (folder) => {
    try {
      await unarchiveFold.mutateAsync(folder.id);
      toast.success('Folder restored');
    } catch (err) {
      mapMoveError(err);
    }
  };
  const onSubmitMoveDoc = async (e) => {
    e.preventDefault();
    if (!moveDocDialog) return;
    const { docId } = moveDocDialog;
    const targetId = moveDocDialog.targetFolderId ?? null;
    try {
      await moveDoc.mutateAsync({ id: docId, folderId: targetId });
      toast.success('Document moved');
      setMoveDocDialog(null);
    } catch (err) {
      mapMoveError(err);
    }
  };

  return (
    <div className="space-y-4" data-testid="document-folder-view">
      <NarrowNotice />
      <Header
        canCreate={canCreate}
        canCreateFold={canCreateFold}
        includeArchived={includeArchived}
        onToggleArchived={(v) => setIncludeArchived(v)}
        onNewFolder={() => setFolderDialog({
          mode: 'create', parentId: selectedFolderId, name: '',
        })}
        onAddDoc={openCreateDoc}
      />

      {treeQ.isLoading && (
        <div className="text-sm" data-testid="document-folder-loading">Loading…</div>
      )}
      {treeQ.isError && (
        <div className="text-sm text-red-600">Failed to load folders.</div>
      )}

      {!treeQ.isLoading && !treeQ.isError && (
        <div
          className="flex flex-col md:flex-row gap-4"
          data-testid="document-folder-panes"
        >
          <TreePane
            tree={tree}
            allDocsCount={allDocs.length}
            selectedFolderId={selectedFolderId}
            expanded={expanded}
            dragDocId={dragDocId}
            canCreateFold={canCreateFold}
            canEditFold={canEditFold}
            canMove={canMove}
            onSelectFolder={setSelectedFolderId}
            onToggleExpand={toggleExpand}
            onDropDoc={handleDropDocOnFolder}
            onNewSub={(parent) => setFolderDialog({
              mode: 'create', parentId: parent.id, name: '',
            })}
            onRename={(folder) => setFolderDialog({
              mode: 'rename', folderId: folder.id, name: folder.name,
            })}
            onMove={(folder) => setFolderDialog({
              mode: 'move',
              folderId: folder.id,
              newParentId: folder.parent_id,
            })}
            onArchive={onArchiveFolderClick}
            onUnarchive={onUnarchiveFolderClick}
          />
          <FilesPane
            breadcrumb={breadcrumb}
            selectedFolder={selectedFolder}
            docs={docsInPane}
            isLoading={docsQ.isLoading}
            isError={docsQ.isError}
            canEdit={canEdit}
            canSensitive={canSensitive}
            canArchive={canArchive}
            canMove={canMove}
            canEditFold={canEditFold}
            folderById={folderById}
            rowErrors={rowErrors}
            uploadingId={uploadingId}
            showFolderColumn={selectedFolderId === null}
            onPickRowFile={onPickRowFile}
            onDownload={onDownload}
            onArchiveRow={onArchiveRow}
            onRestoreRow={onRestoreRow}
            onOpenEdit={openEditDoc}
            onOpenMove={(d) => setMoveDocDialog({
              docId: d.id,
              currentFolderId: d.folder_id ?? null,
              targetFolderId: d.folder_id ?? null,
            })}
            onDragStart={(id) => setDragDocId(id)}
            onDragEnd={() => setDragDocId(null)}
            onRenameSelected={(folder) => setFolderDialog({
              mode: 'rename', folderId: folder.id, name: folder.name,
            })}
            onMoveSelected={(folder) => setFolderDialog({
              mode: 'move', folderId: folder.id, newParentId: folder.parent_id,
            })}
            onArchiveSelected={onArchiveFolderClick}
            onUnarchiveSelected={onUnarchiveFolderClick}
          />
        </div>
      )}

      <DocDialog
        me={me}
        docDialog={docDialog}
        onClose={closeDocDialog}
        onSubmit={onSubmitDoc}
        onUpdate={setDocDialog}
        onPickFile={onDocDialogPick}
      />
      <FolderDialog
        folderDialog={folderDialog}
        onClose={() => setFolderDialog(null)}
        onSubmit={onSubmitFolderDialog}
        onUpdate={setFolderDialog}
        tree={tree}
      />
      <MoveDocDialog
        moveDocDialog={moveDocDialog}
        onClose={() => setMoveDocDialog(null)}
        onSubmit={onSubmitMoveDoc}
        onUpdate={setMoveDocDialog}
        tree={tree}
      />
    </div>
  );
}


// ─── Toast mapping helper (top-level so all callbacks share it) ────────
function mapMoveError(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 422 && typeof detail === 'string') {
    toast.error(detail);
    return;
  }
  if (status === 403) {
    toast.error("You don't have permission to do that.");
    return;
  }
  if (status === 404) {
    toast.error('That item no longer exists.');
    return;
  }
  toast.error(
    (typeof detail === 'string' && detail) || err?.message || 'Action failed.',
  );
}


function NarrowNotice() {
  return (
    <div
      className="md:hidden text-xs text-sy-grey-700 border border-sy-grey-300 bg-sy-grey-50 rounded px-3 py-2"
      data-testid="document-folder-mobile-notice"
    >
      Best viewed on desktop — a mobile-optimised document view is coming.
    </div>
  );
}


function Header({
  canCreate, canCreateFold, includeArchived, onToggleArchived, onNewFolder, onAddDoc,
}) {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <label className="text-sm flex items-center gap-2">
        <input
          type="checkbox"
          checked={includeArchived}
          onChange={(e) => onToggleArchived(e.target.checked)}
          data-testid="document-folder-archived-toggle"
        />
        <span>Show archived</span>
      </label>
      <div className="flex items-center gap-2">
        {canCreateFold && (
          <Button
            type="button"
            variant="outline"
            onClick={onNewFolder}
            data-testid="document-folder-new-folder-btn"
          >
            <FolderPlus className="w-4 h-4 mr-1" />
            New folder
          </Button>
        )}
        {canCreate && (
          <Button
            type="button"
            onClick={onAddDoc}
            data-testid="document-folder-add-doc-btn"
          >
            <FilePlus className="w-4 h-4 mr-1" />
            Add document
          </Button>
        )}
      </div>
    </div>
  );
}


function TreePane({
  tree, allDocsCount, selectedFolderId, expanded, dragDocId,
  canCreateFold, canEditFold, canMove,
  onSelectFolder, onToggleExpand, onDropDoc,
  onNewSub, onRename, onMove, onArchive, onUnarchive,
}) {
  return (
    <aside
      className="w-full md:w-72 md:shrink-0 border border-sy-grey-300 rounded p-2 bg-white"
      data-testid="folder-tree-pane"
    >
      <button
        type="button"
        onClick={() => onSelectFolder(null)}
        className={[
          'w-full flex items-center gap-2 px-2 py-1 rounded text-sm hover:bg-sy-grey-50',
          selectedFolderId === null ? 'bg-sy-teal-50 text-sy-teal-800 font-medium' : '',
        ].filter(Boolean).join(' ')}
        data-testid="folder-tree-all"
      >
        <Folder className="w-4 h-4" />
        <span className="flex-1 text-left">All documents</span>
        <span className="text-xs text-slate-500">{allDocsCount}</span>
      </button>

      <div className="mt-1 space-y-0.5">
        {tree.length === 0 && (
          <div
            className="text-xs text-sy-grey-600 px-2 py-2"
            data-testid="folder-tree-empty"
          >
            No folders yet.
          </div>
        )}
        {tree.map((node) => (
          <FolderNode
            key={node.id}
            node={node}
            depth={0}
            expanded={expanded}
            selectedId={selectedFolderId}
            dragDocId={dragDocId}
            onToggle={onToggleExpand}
            onSelect={onSelectFolder}
            onDropDoc={onDropDoc}
            canCreateFold={canCreateFold}
            canEditFold={canEditFold}
            canMove={canMove}
            onNewSubfolder={onNewSub}
            onRename={onRename}
            onMove={onMove}
            onArchive={onArchive}
            onUnarchive={onUnarchive}
          />
        ))}
      </div>
    </aside>
  );
}


function FilesPane({
  breadcrumb, selectedFolder,
  docs, isLoading, isError,
  canEdit, canSensitive, canArchive, canMove, canEditFold,
  folderById, rowErrors, uploadingId, showFolderColumn,
  onPickRowFile, onDownload, onArchiveRow, onRestoreRow,
  onOpenEdit, onOpenMove, onDragStart, onDragEnd,
  onRenameSelected, onMoveSelected, onArchiveSelected, onUnarchiveSelected,
}) {
  return (
    <section
      className="flex-1 border border-sy-grey-300 rounded p-3 bg-white min-w-0"
      data-testid="folder-files-pane"
    >
      <FilesPaneHeader
        breadcrumb={breadcrumb}
        selectedFolder={selectedFolder}
        canEditFold={canEditFold}
        canMove={canMove}
        onRename={onRenameSelected}
        onMove={onMoveSelected}
        onArchive={onArchiveSelected}
        onUnarchive={onUnarchiveSelected}
      />
      <FilesTable
        docs={docs}
        isLoading={isLoading}
        isError={isError}
        canEdit={canEdit}
        canSensitive={canSensitive}
        canArchive={canArchive}
        canMove={canMove}
        folderById={folderById}
        rowErrors={rowErrors}
        uploadingId={uploadingId}
        showFolderColumn={showFolderColumn}
        onPickRowFile={onPickRowFile}
        onDownload={onDownload}
        onArchiveRow={onArchiveRow}
        onRestoreRow={onRestoreRow}
        onOpenEdit={onOpenEdit}
        onOpenMove={onOpenMove}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      />
    </section>
  );
}


function FilesPaneHeader({
  breadcrumb, selectedFolder, canEditFold, canMove,
  onRename, onMove, onArchive, onUnarchive,
}) {
  return (
    <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
      <div
        className="text-sm text-sy-grey-700 break-words"
        data-testid="folder-files-breadcrumb"
      >
        {selectedFolder === null && <span>All documents</span>}
        {selectedFolder && (
          <BreadcrumbTrail
            steps={breadcrumb}
            archived={selectedFolder.is_archived}
          />
        )}
      </div>
      {selectedFolder && canEditFold && !selectedFolder.is_archived && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onRename(selectedFolder)}
            className="text-xs underline text-sy-teal-700"
            data-testid="folder-files-rename-btn"
          >
            Rename
          </button>
          {canMove && (
            <button
              type="button"
              onClick={() => onMove(selectedFolder)}
              className="text-xs underline text-sy-teal-700 ml-2"
              data-testid="folder-files-move-btn"
            >
              Move
            </button>
          )}
          <button
            type="button"
            onClick={() => onArchive(selectedFolder)}
            className="text-xs underline text-red-700 ml-2"
            data-testid="folder-files-archive-btn"
          >
            Archive
          </button>
        </div>
      )}
      {selectedFolder && canEditFold && selectedFolder.is_archived && (
        <button
          type="button"
          onClick={() => onUnarchive(selectedFolder)}
          className="text-xs underline text-sy-teal-700"
          data-testid="folder-files-unarchive-btn"
        >
          Restore folder
        </button>
      )}
    </div>
  );
}


function BreadcrumbTrail({ steps, archived }) {
  return (
    <span>
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        return (
          <React.Fragment key={step.id}>
            {i > 0 && <span className="text-sy-grey-400 mx-1">›</span>}
            <span className={isLast ? 'font-medium' : ''}>{step.name}</span>
          </React.Fragment>
        );
      })}
      {archived && (
        <span className="ml-2 text-[10px] uppercase tracking-widest text-slate-400">
          Archived
        </span>
      )}
    </span>
  );
}


function FilesTable({
  docs, isLoading, isError,
  canEdit, canSensitive, canArchive, canMove,
  folderById, rowErrors, uploadingId, showFolderColumn,
  onPickRowFile, onDownload, onArchiveRow, onRestoreRow,
  onOpenEdit, onOpenMove, onDragStart, onDragEnd,
}) {
  if (isLoading) {
    return (
      <div className="text-sm" data-testid="folder-files-loading">Loading…</div>
    );
  }
  if (isError) {
    return <div className="text-sm text-red-600">Failed to load documents.</div>;
  }

  return (
    <Table data-testid="folder-files-table">
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead>Title</TableHead>
          {showFolderColumn && <TableHead>Folder</TableHead>}
          <TableHead>Issued</TableHead>
          <TableHead>Expires</TableHead>
          <TableHead>File</TableHead>
          <TableHead className="w-40">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {docs.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={showFolderColumn ? 7 : 6}
              className="text-sy-grey-500"
              data-testid="folder-files-empty"
            >
              No documents in this folder.
            </TableCell>
          </TableRow>
        )}
        {docs.map((d) => (
          <FileRow
            key={d.id}
            d={d}
            canEdit={canEdit}
            canSensitive={canSensitive}
            canArchive={canArchive}
            canMove={canMove}
            folderById={folderById}
            rowError={rowErrors[d.id]}
            uploading={uploadingId === d.id}
            showFolderColumn={showFolderColumn}
            onPickRowFile={onPickRowFile}
            onDownload={onDownload}
            onArchiveRow={onArchiveRow}
            onRestoreRow={onRestoreRow}
            onOpenEdit={onOpenEdit}
            onOpenMove={onOpenMove}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
          />
        ))}
      </TableBody>
    </Table>
  );
}


function FileRow({
  d, canEdit, canSensitive, canArchive, canMove, folderById,
  rowError, uploading, showFolderColumn,
  onPickRowFile, onDownload, onArchiveRow, onRestoreRow,
  onOpenEdit, onOpenMove, onDragStart, onDragEnd,
}) {
  const folderName = d.folder_id
    ? (folderById.get(d.folder_id)?.name ?? '—')
    : 'Unfiled';

  return (
    <TableRow
      className={d.is_archived ? 'text-slate-400' : ''}
      draggable={canMove}
      onDragStart={(e) => {
        onDragStart(d.id);
        if (e.dataTransfer) {
          e.dataTransfer.setData(DRAG_DOC_MIME, d.id);
          e.dataTransfer.effectAllowed = 'move';
        }
      }}
      onDragEnd={onDragEnd}
      data-testid={`folder-files-row-${d.id}`}
      data-draggable={canMove ? 'true' : 'false'}
    >
      <TableCell>
        {d.doc_type ? labelDocType(d.doc_type) : <span className="text-slate-400">—</span>}
      </TableCell>
      <TableCell>
        <span data-testid={`folder-files-title-${d.id}`}>
          {d.title || (d.file_name ?? '—')}
        </span>
        {d.is_archived && (
          <span className="ml-2 text-[10px] uppercase tracking-widest text-slate-400">
            Archived
          </span>
        )}
      </TableCell>
      {showFolderColumn && (
        <TableCell>
          <span
            className={`text-xs ${d.folder_id ? 'text-sy-grey-700' : 'text-slate-400 italic'}`}
            data-testid={`folder-files-folder-${d.id}`}
          >
            {folderName}
          </span>
        </TableCell>
      )}
      <TableCell>{formatDate(d.issued_on)}</TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-2">
          {formatDate(d.expires_on)}
          <DocExpiryBadge
            expiresOn={d.expires_on}
            testid={`folder-files-expiry-${d.id}`}
          />
        </span>
      </TableCell>
      <TableCell data-testid={`folder-files-file-${d.id}`}>
        <DocumentFileCell
          row={d}
          canEdit={canEdit}
          canSensitive={canSensitive}
          accept={ACCEPT_ATTR}
          inlineError={rowError}
          isUploading={uploading}
          onPickFile={(file) => onPickRowFile(d.id, file)}
          onDownload={() => onDownload(d)}
        />
      </TableCell>
      <TableCell>
        <FileRowActions
          d={d}
          canEdit={canEdit}
          canArchive={canArchive}
          canMove={canMove}
          onOpenEdit={onOpenEdit}
          onOpenMove={onOpenMove}
          onArchiveRow={onArchiveRow}
          onRestoreRow={onRestoreRow}
        />
      </TableCell>
    </TableRow>
  );
}


function FileRowActions({
  d, canEdit, canArchive, canMove, onOpenEdit, onOpenMove, onArchiveRow, onRestoreRow,
}) {
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1">
      {canEdit && !d.is_archived && (
        <button
          type="button"
          onClick={() => onOpenEdit(d)}
          className="text-xs underline text-sy-teal-700"
          data-testid={`folder-files-edit-${d.id}`}
        >
          Edit
        </button>
      )}
      {canMove && !d.is_archived && (
        <button
          type="button"
          onClick={() => onOpenMove(d)}
          className="text-xs underline text-sy-teal-700"
          data-testid={`folder-files-move-${d.id}`}
        >
          Move to…
        </button>
      )}
      {canArchive && !d.is_archived && (
        <button
          type="button"
          onClick={() => onArchiveRow(d)}
          className="text-xs underline text-red-700"
          data-testid={`folder-files-archive-${d.id}`}
        >
          Archive
        </button>
      )}
      {canArchive && d.is_archived && (
        <button
          type="button"
          onClick={() => onRestoreRow(d)}
          className="text-xs underline text-sy-teal-700"
          data-testid={`folder-files-restore-${d.id}`}
        >
          Restore
        </button>
      )}
    </div>
  );
}


// ─── Dialogs ───────────────────────────────────────────────────────────

function DocDialog({ me, docDialog, onClose, onSubmit, onUpdate, onPickFile }) {
  return (
    <Dialog open={!!docDialog} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="document-form-dialog">
        <DialogHeader>
          <DialogTitle>
            {docDialog?.mode === 'edit' ? 'Edit document' : 'Add document'}
          </DialogTitle>
        </DialogHeader>
        {docDialog && (
          <form
            onSubmit={onSubmit}
            className="space-y-3"
            data-testid="document-form"
          >
            <DocFormFields docDialog={docDialog} onUpdate={onUpdate} />
            {canEditDocs(me) && (
              <DocAttachField
                docDialog={docDialog}
                onUpdate={onUpdate}
                onPickFile={onPickFile}
              />
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                data-testid="document-form-cancel"
              >
                Cancel
              </Button>
              <Button type="submit" data-testid="document-form-save">
                Save
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}


function DocFormFields({ docDialog, onUpdate }) {
  const set = (k, v) => onUpdate((d) => ({ ...d, form: { ...d.form, [k]: v } }));
  return (
    <>
      <div>
        <Label htmlFor="docf-type">Category</Label>
        <select
          id="docf-type"
          className="w-full px-2 py-1.5 border rounded text-sm"
          value={docDialog.form.doc_type}
          onChange={(e) => set('doc_type', e.target.value)}
          data-testid="document-form-type"
        >
          <option value="">— No category —</option>
          {DOC_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>{labelDocType(t)}</option>
          ))}
        </select>
      </div>
      <div>
        <Label htmlFor="docf-title">Title</Label>
        <Input
          id="docf-title"
          type="text"
          value={docDialog.form.title}
          onChange={(e) => set('title', e.target.value)}
          placeholder="Leave blank to use the file name"
          data-testid="document-form-title"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="docf-issued">Issued on</Label>
          <Input
            id="docf-issued" type="date"
            value={docDialog.form.issued_on}
            onChange={(e) => set('issued_on', e.target.value)}
            data-testid="document-form-issued"
          />
        </div>
        <div>
          <Label htmlFor="docf-expires">Expires on</Label>
          <Input
            id="docf-expires" type="date"
            value={docDialog.form.expires_on}
            onChange={(e) => set('expires_on', e.target.value)}
            data-testid="document-form-expires"
          />
        </div>
      </div>
      <div>
        <Label htmlFor="docf-notes">Notes</Label>
        <Textarea
          id="docf-notes" rows={2}
          value={docDialog.form.notes}
          onChange={(e) => set('notes', e.target.value)}
          data-testid="document-form-notes"
        />
      </div>
    </>
  );
}


function DocAttachField({ docDialog, onUpdate, onPickFile }) {
  return (
    <div data-testid="document-form-attach">
      <Label>Attach file (optional)</Label>
      <DropZone testid="document-form-dropzone" onDropFile={onPickFile}>
        <FilePicker
          rowId="form"
          accept={ACCEPT_ATTR}
          isUploading={false}
          onPickFile={onPickFile}
          label={docDialog.pendingFile ? 'Choose different file' : 'Choose file'}
          testid="document-form-file"
        />
        <span className="text-[11px] text-slate-500 mt-1">
          or drag a file here · PDF, image, Office docs · 25 MB max
        </span>
      </DropZone>
      {docDialog.pendingFile && (
        <div
          className="mt-1 flex items-center gap-2 text-xs text-slate-700"
          data-testid="document-form-file-staged"
        >
          <span className="break-all" data-testid="document-form-file-name">
            {docDialog.pendingFile.name}
          </span>
          <span className="text-slate-500">
            ({formatFileSize(docDialog.pendingFile.size)})
          </span>
          <button
            type="button"
            onClick={() => onUpdate((d) => ({ ...d, pendingFile: null, pendingFileError: null }))}
            className="underline text-sy-teal-700"
            data-testid="document-form-file-clear"
          >
            Remove
          </button>
        </div>
      )}
      {docDialog.pendingFileError && (
        <span
          className="block text-xs text-red-600 mt-1"
          data-testid="document-form-file-error"
        >
          {docDialog.pendingFileError}
        </span>
      )}
    </div>
  );
}


function FolderDialog({ folderDialog, onClose, onSubmit, onUpdate, tree }) {
  return (
    <Dialog open={!!folderDialog} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="folder-form-dialog">
        <DialogHeader>
          <DialogTitle>
            {folderDialog?.mode === 'create' && 'New folder'}
            {folderDialog?.mode === 'rename' && 'Rename folder'}
            {folderDialog?.mode === 'move' && 'Move folder'}
          </DialogTitle>
        </DialogHeader>
        {folderDialog && (
          <form
            onSubmit={onSubmit}
            className="space-y-3"
            data-testid="folder-form"
          >
            {(folderDialog.mode === 'create' || folderDialog.mode === 'rename') && (
              <div>
                <Label htmlFor="folder-form-name">Name</Label>
                <Input
                  id="folder-form-name"
                  type="text"
                  value={folderDialog.name ?? ''}
                  onChange={(e) => onUpdate((d) => ({ ...d, name: e.target.value }))}
                  required
                  autoFocus
                  data-testid="folder-form-name"
                />
              </div>
            )}
            {folderDialog.mode === 'move' && (
              <FolderPicker
                tree={tree}
                excludeId={folderDialog.folderId}
                value={folderDialog.newParentId ?? null}
                onChange={(v) => onUpdate((d) => ({ ...d, newParentId: v }))}
                testid="folder-form-target"
                labelTop="Move to root (no parent)"
              />
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                data-testid="folder-form-cancel"
              >
                Cancel
              </Button>
              <Button type="submit" data-testid="folder-form-save">
                {folderDialog.mode === 'create' && 'Create'}
                {folderDialog.mode === 'rename' && 'Rename'}
                {folderDialog.mode === 'move' && 'Move'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}


function MoveDocDialog({ moveDocDialog, onClose, onSubmit, onUpdate, tree }) {
  return (
    <Dialog open={!!moveDocDialog} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="move-doc-dialog">
        <DialogHeader>
          <DialogTitle>Move document</DialogTitle>
        </DialogHeader>
        {moveDocDialog && (
          <form
            onSubmit={onSubmit}
            className="space-y-3"
            data-testid="move-doc-form"
          >
            <FolderPicker
              tree={tree}
              value={moveDocDialog.targetFolderId}
              onChange={(v) => onUpdate((d) => ({ ...d, targetFolderId: v }))}
              testid="move-doc-target"
              labelTop="Unfiled (no folder)"
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                data-testid="move-doc-cancel"
              >
                Cancel
              </Button>
              <Button type="submit" data-testid="move-doc-save">
                Move
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
