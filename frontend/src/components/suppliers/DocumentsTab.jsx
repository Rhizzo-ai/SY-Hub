/**
 * <DocumentsTab/> — Chat 40 §R3 #13 / Build Pack 2.7-FE-docupload §R1+§R2.
 *
 * Toolbar (Add + show-archived toggle) → table → add/edit dialog.
 * Archived rows are visually de-emphasised. Notes are sensitive
 * (gated on supplier_documents.view_sensitive); the attached file's
 * metadata + bytes are sensitive too.
 *
 * File column (§R2):
 *   has_file && canViewSensitiveDocs  →  file_name + size + Download
 *   has_file && !canViewSensitiveDocs →  neutral "File attached"
 *   !has_file && canEditDocs          →  Upload control (mobile tap-to-pick)
 *   !has_file && !canEditDocs         →  "—"
 *   has_file && canEditDocs (not archived) → Replace control
 *
 * Upload (§R2.5): tap-to-pick <input type="file"> baseline; client-side
 * pre-check rejects empty/disallowed-type/>25 MB BEFORE the request fires.
 * Server errors map per §R0.2 (413/422/404/502).
 *
 * Download (§R2.6): authedFetch via downloadDocumentFile → blob → object
 * URL → click → revoke. The SharePoint URL NEVER reaches the DOM.
 *
 * Edit pre-fills from the cached row (§R0: single-doc GET is
 * intentionally not surfaced).
 */
import React, { useState } from 'react';
import { toast } from 'sonner';

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
} from '@/hooks/supplierDocuments';
import { downloadDocumentFile } from '@/lib/api/supplierDocuments';
import {
  canCreateDocs, canEditDocs, canArchiveDocs, canViewSensitiveDocs,
} from '@/lib/poCapability';
import DocExpiryBadge from '@/components/suppliers/DocExpiryBadge';
import {
  DOC_TYPE_OPTIONS, formatDate, labelDocType,
} from '@/lib/cisFormat';

// ─── §R0.3 backend allowlist — MUST mirror exactly ──────────────────────
export const ALLOWED_MIME_TYPES = Object.freeze([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/csv',
  'text/plain',
]);
// SHAREPOINT_MAX_BYTES default — server is source of truth, this just
// fails fast on the client.
export const MAX_FILE_BYTES = 25 * 1024 * 1024;
const ACCEPT_ATTR = ALLOWED_MIME_TYPES.join(',');

function formatFileSize(bytes) {
  if (bytes == null || Number.isNaN(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

// Returns an inline error string when the file fails pre-check, else null.
// Order matters: empty wins over type/size so we don't blame the file's
// type when it has no bytes at all.
function preCheckFile(file) {
  if (!file) return 'No file selected.';
  if (file.size === 0) return 'File is empty — please pick a non-empty file.';
  if (!ALLOWED_MIME_TYPES.includes(file.type)) {
    return `Unsupported file type${file.type ? ` (${file.type})` : ''}.`;
  }
  if (file.size > MAX_FILE_BYTES) {
    return 'File is too large — 25 MB cap.';
  }
  return null;
}

// Maps an upload error to a §R0.2 toast string. Never echoes a raw
// server detail back as if it were user-driven for 502 (storage down).
function uploadErrorMessage(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 413) return 'File is too large — 25 MB cap.';
  if (status === 422) return typeof detail === 'string' ? detail : 'Upload rejected.';
  if (status === 502) {
    return 'Document storage is temporarily unavailable, try again shortly.';
  }
  return (typeof detail === 'string' && detail) || err?.message || 'Upload failed.';
}

function downloadErrorMessage(err) {
  if (err?.status === 404) return 'File not found.';
  if (err?.status === 502) {
    return 'Document storage is temporarily unavailable, try again shortly.';
  }
  return err?.detail || err?.message || 'Download failed.';
}

function emptyForm() {
  return {
    doc_type: 'Public_Liability',
    title: '',
    issued_on: '',
    expires_on: '',
    notes: '',
  };
}

function rowToForm(row) {
  return {
    doc_type: row.doc_type,
    title: row.title ?? '',
    issued_on: row.issued_on ?? '',
    expires_on: row.expires_on ?? '',
    notes: row.notes ?? '',
  };
}

export default function DocumentsTab({ supplierId }) {
  const { me } = useAuth();
  const canCreate = canCreateDocs(me);
  const canEdit = canEditDocs(me);
  const canArchive = canArchiveDocs(me);
  const canSensitive = canViewSensitiveDocs(me);

  const [includeArchived, setIncludeArchived] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null); // doc id when editing, null on create
  const [form, setForm] = useState(emptyForm());
  // Per-row inline pre-check error (id → message). Cleared on successful
  // request fire or on a fresh file pick. Lives in component state so
  // there's no leakage between rows.
  const [rowErrors, setRowErrors] = useState({});
  // Per-row "uploading…" flag (§R9 scope-creep — prevents double-submit
  // and gives a clear in-flight indicator on slow/mobile connections).
  const [uploadingId, setUploadingId] = useState(null);

  const list = useSupplierDocuments(supplierId, { includeArchived });
  const create = useCreateDocument(supplierId);
  const patch = usePatchDocument(supplierId);
  const archive = useArchiveDocument(supplierId);
  const unarchive = useUnarchiveDocument(supplierId);
  const upload = useUploadDocumentFile(supplierId);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialogOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row.id);
    setForm(rowToForm(row));
    setDialogOpen(true);
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        doc_type: form.doc_type,
        title: form.title?.trim(),
      };
      // Optional fields — omit when blank so backend `notnull` defaults stand.
      if (form.issued_on) payload.issued_on = form.issued_on;
      if (form.expires_on) payload.expires_on = form.expires_on;
      if (form.notes) payload.notes = form.notes;
      if (editing) {
        await patch.mutateAsync({ id: editing, body: payload });
        toast.success('Document updated');
      } else {
        await create.mutateAsync(payload);
        toast.success('Document added');
      }
      setDialogOpen(false);
    } catch (err) {
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Save failed';
      toast.error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
  };

  const onArchive = async (row) => {
    if (!window.confirm(`Archive "${row.title}"?`)) return;
    try {
      await archive.mutateAsync(row.id);
      toast.success('Document archived');
    } catch (err) {
      toast.error(err?.response?.data?.detail ?? 'Archive failed');
    }
  };
  const onRestore = async (row) => {
    try {
      await unarchive.mutateAsync(row.id);
      toast.success('Document restored');
    } catch (err) {
      toast.error(err?.response?.data?.detail ?? 'Restore failed');
    }
  };

  // ─── §R2.5 Upload (and §R2.3 Replace — same endpoint, supersede). ────
  const onPickFile = async (rowId, file) => {
    setRowErrors((s) => ({ ...s, [rowId]: null }));
    const inline = preCheckFile(file);
    if (inline) {
      // §R2.5: BLOCK the request entirely; surface inline so the user
      // sees the problem without a noisy toast.
      setRowErrors((s) => ({ ...s, [rowId]: inline }));
      return;
    }
    setUploadingId(rowId);
    try {
      await upload.mutateAsync({ id: rowId, file });
      toast.success('File uploaded');
    } catch (err) {
      toast.error(uploadErrorMessage(err));
    } finally {
      setUploadingId(null);
    }
  };

  // ─── §R2.6 Download — bytes-only via authedFetch, never SharePoint URL.
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

  const rows = list.data?.items ?? [];

  return (
    <div className="space-y-4" data-testid="documents-tab">
      <div className="flex items-center justify-between">
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            data-testid="documents-tab-archived-toggle"
          />
          <span>Show archived</span>
        </label>
        {canCreate && (
          <Button onClick={openCreate} data-testid="documents-tab-add-btn">
            + Add document
          </Button>
        )}
      </div>

      {list.isLoading && <div className="text-sm" data-testid="documents-tab-loading">Loading…</div>}
      {list.isError && <div className="text-sm text-red-600">Failed to load documents.</div>}

      {!list.isLoading && !list.isError && (
        <Table data-testid="documents-tab-table">
          <TableHeader>
            <TableRow>
              <TableHead>Type</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Issued</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>File</TableHead>
              <TableHead className="w-32">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-sy-grey-500" data-testid="documents-tab-empty">
                  No documents.
                </TableCell>
              </TableRow>
            )}
            {rows.map((d) => (
              <TableRow
                key={d.id}
                className={d.is_archived ? 'text-slate-400' : ''}
                data-testid={`document-row-${d.id}`}
              >
                <TableCell>{labelDocType(d.doc_type)}</TableCell>
                <TableCell>
                  {d.title}
                  {d.is_archived && (
                    <span className="ml-2 text-[10px] uppercase tracking-widest text-slate-400"
                          data-testid={`document-row-archived-${d.id}`}>Archived</span>
                  )}
                </TableCell>
                <TableCell>{formatDate(d.issued_on)}</TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-2">
                    {formatDate(d.expires_on)}
                    <DocExpiryBadge
                      expiresOn={d.expires_on}
                      testid={`document-row-expiry-${d.id}`}
                    />
                  </span>
                </TableCell>
                <TableCell data-testid={`document-row-file-${d.id}`}>
                  <DocumentFileCell
                    row={d}
                    canEdit={canEdit}
                    canSensitive={canSensitive}
                    accept={ACCEPT_ATTR}
                    inlineError={rowErrors[d.id]}
                    isUploading={uploadingId === d.id}
                    onPickFile={(file) => onPickFile(d.id, file)}
                    onDownload={() => onDownload(d)}
                  />
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    {canEdit && !d.is_archived && (
                      <button
                        type="button"
                        onClick={() => openEdit(d)}
                        className="text-xs underline text-sy-teal-700"
                        data-testid={`document-row-edit-${d.id}`}
                      >Edit</button>
                    )}
                    {canArchive && !d.is_archived && (
                      <button
                        type="button"
                        onClick={() => onArchive(d)}
                        className="text-xs underline text-red-700 ml-2"
                        data-testid={`document-row-archive-${d.id}`}
                      >Archive</button>
                    )}
                    {canArchive && d.is_archived && (
                      <button
                        type="button"
                        onClick={() => onRestore(d)}
                        className="text-xs underline text-sy-teal-700"
                        data-testid={`document-row-restore-${d.id}`}
                      >Restore</button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent data-testid="document-form-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit document' : 'Add document'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={onSubmit} className="space-y-3" data-testid="document-form">
            <div>
              <Label htmlFor="doc-form-type">Type *</Label>
              <select
                id="doc-form-type"
                className="w-full px-2 py-1.5 border rounded text-sm"
                value={form.doc_type} onChange={onChange('doc_type')}
                data-testid="document-form-type"
                required
              >
                {DOC_TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>{labelDocType(t)}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="doc-form-title">Title *</Label>
              <Input
                id="doc-form-title" type="text" required
                value={form.title} onChange={onChange('title')}
                data-testid="document-form-title"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="doc-form-issued">Issued on</Label>
                <Input
                  id="doc-form-issued" type="date"
                  value={form.issued_on} onChange={onChange('issued_on')}
                  data-testid="document-form-issued"
                />
              </div>
              <div>
                <Label htmlFor="doc-form-expires">Expires on</Label>
                <Input
                  id="doc-form-expires" type="date"
                  value={form.expires_on} onChange={onChange('expires_on')}
                  data-testid="document-form-expires"
                />
              </div>
            </div>
            <div>
              <Label htmlFor="doc-form-notes">Notes</Label>
              <Textarea
                id="doc-form-notes" rows={2}
                value={form.notes} onChange={onChange('notes')}
                data-testid="document-form-notes"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}
                      data-testid="document-form-cancel">
                Cancel
              </Button>
              <Button type="submit" data-testid="document-form-save">
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}


/**
 * File-cell renderer (§R2.1–§R2.4).
 *
 * Pulled out as a sub-component so each row's conditional branches stay
 * legible. No external state — the parent owns the row-error/uploading
 * maps and just hands this component what to show.
 */
function DocumentFileCell({
  row, canEdit, canSensitive, accept,
  inlineError, isUploading, onPickFile, onDownload,
}) {
  const hasFile = !!row.has_file;
  const isArchived = !!row.is_archived;

  // ─── R2.1 — file present ───────────────────────────────────────────
  if (hasFile) {
    if (canSensitive) {
      // Sensitive viewer: name + size + Download.
      return (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-sm break-all"
              data-testid={`document-row-file-name-${row.id}`}
            >
              {row.file_name ?? 'Attached file'}
            </span>
            {row.file_size != null && (
              <span
                className="text-xs text-slate-500"
                data-testid={`document-row-file-size-${row.id}`}
              >
                {formatFileSize(row.file_size)}
              </span>
            )}
            <button
              type="button"
              onClick={onDownload}
              className="text-xs underline text-sy-teal-700"
              data-testid={`document-row-download-${row.id}`}
            >
              Download
            </button>
          </div>
          {canEdit && !isArchived && (
            <FilePicker
              rowId={row.id}
              accept={accept}
              isUploading={isUploading}
              onPickFile={onPickFile}
              label="Replace"
              testid={`document-row-replace-${row.id}`}
            />
          )}
          {inlineError && (
            <span
              className="text-xs text-red-600"
              data-testid={`document-row-upload-error-${row.id}`}
            >
              {inlineError}
            </span>
          )}
        </div>
      );
    }
    // Non-sensitive viewer: neutral indicator ONLY (no name, no size,
    // no Download). File metadata is sensitive.
    return (
      <span
        className="text-sm text-slate-500"
        data-testid={`document-row-file-attached-${row.id}`}
      >
        File attached
      </span>
    );
  }

  // ─── R2.2 — no file ────────────────────────────────────────────────
  if (canEdit && !isArchived) {
    return (
      <div className="flex flex-col gap-1">
        <FilePicker
          rowId={row.id}
          accept={accept}
          isUploading={isUploading}
          onPickFile={onPickFile}
          label="Upload"
          testid={`document-row-upload-${row.id}`}
        />
        <span className="text-[11px] text-slate-500">
          PDF, image, Office docs · 25 MB max
        </span>
        {inlineError && (
          <span
            className="text-xs text-red-600"
            data-testid={`document-row-upload-error-${row.id}`}
          >
            {inlineError}
          </span>
        )}
      </div>
    );
  }

  return (
    <span
      className="text-sm text-slate-400"
      data-testid={`document-row-no-file-${row.id}`}
    >
      —
    </span>
  );
}

/**
 * Mobile-first <input type="file"> baseline (§R2.5).
 *
 * Tap-to-pick is the only required interaction. The visible button is a
 * <label> wrapping a screen-reader-only file input — taps on iOS/Android
 * open the system file picker directly. NO drag-and-drop-only path.
 *
 * `key` is reset after each pick so the same file can be re-selected
 * (browsers suppress `onChange` if the value is unchanged).
 */
function FilePicker({ rowId, accept, isUploading, onPickFile, label, testid }) {
  const [nonce, setNonce] = useState(0);
  const labelClasses = isUploading
    ? 'inline-flex items-center text-xs underline text-slate-400 cursor-not-allowed'
    : 'inline-flex items-center text-xs underline text-sy-teal-700 cursor-pointer';
  return (
    <label className={labelClasses}>
      <span>{isUploading ? 'Uploading…' : label}</span>
      <input
        key={nonce}
        type="file"
        accept={accept}
        disabled={isUploading}
        className="sr-only"
        data-testid={testid}
        onChange={(e) => {
          const f = e.target.files?.[0];
          setNonce((n) => n + 1);
          if (f) onPickFile(f);
        }}
      />
    </label>
  );
}

DocumentsTab.preCheckFile = preCheckFile;
DocumentsTab.formatFileSize = formatFileSize;
