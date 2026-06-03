/**
 * <DocumentsTab/> — Chat 40 §R3 #13 / §R4.5.
 *
 * Toolbar (Add + show-archived toggle) → table → add/edit dialog.
 * Archived rows are visually de-emphasised. File ref + notes are
 * sensitive (gated on supplier_documents.view_sensitive).
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
  useArchiveDocument, useUnarchiveDocument,
} from '@/hooks/supplierDocuments';
import {
  canCreateDocs, canEditDocs, canArchiveDocs, canViewSensitiveDocs,
} from '@/lib/poCapability';
import SensitiveValue from '@/components/po/SensitiveValue';
import DocExpiryBadge from '@/components/suppliers/DocExpiryBadge';
import {
  DOC_TYPE_OPTIONS, formatDate, labelDocType,
} from '@/lib/cisFormat';

function emptyForm() {
  return {
    doc_type: 'Public_Liability',
    title: '',
    file_ref: '',
    issued_on: '',
    expires_on: '',
    notes: '',
  };
}

function rowToForm(row) {
  return {
    doc_type: row.doc_type,
    title: row.title ?? '',
    file_ref: row.file_ref ?? '',
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

  const list = useSupplierDocuments(supplierId, { includeArchived });
  const create = useCreateDocument(supplierId);
  const patch = usePatchDocument(supplierId);
  const archive = useArchiveDocument(supplierId);
  const unarchive = useUnarchiveDocument(supplierId);

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
      if (form.file_ref) payload.file_ref = form.file_ref;
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
              <TableHead>File ref</TableHead>
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
                <TableCell>
                  <SensitiveValue
                    value={d.file_ref} hidden={!canSensitive}
                    testid={`document-row-file-ref-${d.id}`}
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
            <div>
              <Label htmlFor="doc-form-fileref">File ref</Label>
              <Input
                id="doc-form-fileref" type="text"
                value={form.file_ref} onChange={onChange('file_ref')}
                data-testid="document-form-file-ref"
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
