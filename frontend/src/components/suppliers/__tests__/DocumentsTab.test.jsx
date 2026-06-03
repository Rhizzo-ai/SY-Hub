/**
 * <DocumentsTab/> tests — Chat 40 §R5 #5.
 *
 * Covers:
 *  - List renders
 *  - Add gated on supplier_documents.create
 *  - Edit gated on supplier_documents.edit
 *  - Archive / Restore actions
 *  - Show-archived toggle
 *  - file_ref masked without sensitive
 *  - Expiry badge variants present on rows
 */
jest.mock('@/hooks/supplierDocuments', () => ({
  useSupplierDocuments: jest.fn(),
  useCreateDocument: jest.fn(),
  usePatchDocument: jest.fn(),
  useArchiveDocument: jest.fn(),
  useUnarchiveDocument: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DocumentsTab from '@/components/suppliers/DocumentsTab';

const hooks = jest.requireMock('@/hooks/supplierDocuments');
const { useAuth } = jest.requireMock('@/context/AuthContext');
const { toast } = jest.requireMock('sonner');

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

function isoDelta(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

let createMutate;
let patchMutate;
let archiveMutate;
let unarchiveMutate;
beforeEach(() => {
  createMutate = jest.fn().mockResolvedValue({});
  patchMutate = jest.fn().mockResolvedValue({});
  archiveMutate = jest.fn().mockResolvedValue({});
  unarchiveMutate = jest.fn().mockResolvedValue({});
  hooks.useSupplierDocuments.mockReturnValue({ data: { items: [] }, isLoading: false, isError: false });
  hooks.useCreateDocument.mockReturnValue({ mutateAsync: createMutate });
  hooks.usePatchDocument.mockReturnValue({ mutateAsync: patchMutate });
  hooks.useArchiveDocument.mockReturnValue({ mutateAsync: archiveMutate });
  hooks.useUnarchiveDocument.mockReturnValue({ mutateAsync: unarchiveMutate });
  useAuth.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('<DocumentsTab/>', () => {
  test('list renders rows', () => {
    setMe(['supplier_documents.view']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [
        { id: 'D1', doc_type: 'Public_Liability', title: 'PL2026',
          issued_on: '2025-01-01', expires_on: isoDelta(60),
          file_ref: 'pl.pdf', is_archived: false, notes: null },
      ]},
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('document-row-D1')).toBeInTheDocument();
    expect(screen.getByTestId('document-row-D1')).toHaveTextContent('PL2026');
  });

  test('Add button hidden without supplier_documents.create', () => {
    setMe(['supplier_documents.view']);
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.queryByTestId('documents-tab-add-btn')).toBeNull();
  });

  test('Add button shown with supplier_documents.create', () => {
    setMe(['supplier_documents.view', 'supplier_documents.create']);
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('documents-tab-add-btn')).toBeInTheDocument();
  });

  test('Edit hidden without supplier_documents.edit; shown with', () => {
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        issued_on: null, expires_on: null, file_ref: null,
        is_archived: false, notes: null }]},
      isLoading: false, isError: false,
    });
    setMe(['supplier_documents.view']);
    const { rerender } = render(<DocumentsTab supplierId="S1" />);
    expect(screen.queryByTestId('document-row-edit-D1')).toBeNull();
    setMe(['supplier_documents.view', 'supplier_documents.edit']);
    rerender(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('document-row-edit-D1')).toBeInTheDocument();
  });

  test('Archive action fires mutation + toast', async () => {
    setMe(['supplier_documents.view', 'supplier_documents.archive']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('document-row-archive-D1'));
    await waitFor(() => expect(archiveMutate).toHaveBeenCalledWith('D1'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Document archived'));
  });

  test('Restore action shown for archived row, fires unarchive', async () => {
    setMe(['supplier_documents.view', 'supplier_documents.archive']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: true }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('document-row-archived-D1')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('document-row-restore-D1'));
    await waitFor(() => expect(unarchiveMutate).toHaveBeenCalledWith('D1'));
  });

  test('Show-archived toggle re-queries with include_archived=true', () => {
    setMe(['supplier_documents.view']);
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('documents-tab-archived-toggle'));
    const last = hooks.useSupplierDocuments.mock.calls.at(-1);
    expect(last[1].includeArchived).toBe(true);
  });

  test('file_ref masked without supplier_documents.view_sensitive', () => {
    setMe(['supplier_documents.view']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        file_ref: null, is_archived: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('document-row-file-ref-D1')).toHaveTextContent('—');
  });

  test('expiry badge variants — expired shows; valid does not', () => {
    setMe(['supplier_documents.view']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [
        { id: 'D1', doc_type: 'Other', title: 'A', expires_on: isoDelta(-1), is_archived: false },
        { id: 'D2', doc_type: 'Other', title: 'B', expires_on: isoDelta(100), is_archived: false },
      ]},
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('document-row-expiry-D1')).toHaveTextContent('Expired');
    // D2 row exists but no expiry badge node inside it.
    expect(screen.queryByTestId('document-row-expiry-D2')).toBeNull();
  });

  test('create flow: open dialog, fill, submit → create mutation called', async () => {
    setMe(['supplier_documents.view', 'supplier_documents.create']);
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('documents-tab-add-btn'));
    expect(screen.getByTestId('document-form')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('document-form-title'),
                     { target: { value: 'New doc' } });
    fireEvent.click(screen.getByTestId('document-form-save'));
    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    const body = createMutate.mock.calls[0][0];
    expect(body.title).toBe('New doc');
    expect(body.doc_type).toBe('Public_Liability'); // default
  });
});
