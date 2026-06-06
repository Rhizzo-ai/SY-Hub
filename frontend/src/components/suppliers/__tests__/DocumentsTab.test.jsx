/**
 * <DocumentsTab/> tests — Chat 40 §R5 #5 + Build Pack 2.7-FE-docupload §R5.
 *
 * Covers all 13 Gate 2 acceptance cases (the file_ref cleanup +
 * upload/download contract + sensitive/edit gating + no-URL-leak),
 * alongside the original list/add/edit/archive/restore tests.
 *
 * Mocks are surgical:
 *   - `@/hooks/supplierDocuments` for every mutation/query hook
 *   - `@/lib/api/supplierDocuments` for the imperative downloader
 *   - `@/context/AuthContext` for perms
 *   - `sonner` for toast assertions
 * NO real network — every call goes through the mocks.
 */
jest.mock('@/hooks/supplierDocuments', () => ({
  useSupplierDocuments: jest.fn(),
  useCreateDocument: jest.fn(),
  usePatchDocument: jest.fn(),
  useArchiveDocument: jest.fn(),
  useUnarchiveDocument: jest.fn(),
  useUploadDocumentFile: jest.fn(),
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
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import DocumentsTab from '@/components/suppliers/DocumentsTab';

const hooks = jest.requireMock('@/hooks/supplierDocuments');
const docsApi = jest.requireMock('@/lib/api/supplierDocuments');
const { useAuth } = jest.requireMock('@/context/AuthContext');
const { toast } = jest.requireMock('sonner');

const ALL_PERMS = [
  'supplier_documents.view',
  'supplier_documents.view_sensitive',
  'supplier_documents.create',
  'supplier_documents.edit',
  'supplier_documents.archive',
];

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

function isoDelta(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function makeFile({
  name = 'cert.pdf',
  type = 'application/pdf',
  size = 1024,
  content = null,
} = {}) {
  // Build a File whose .size reflects the requested byte count without
  // actually allocating big buffers (jest-jsdom's File honours the byte
  // length we pass in for small sizes; for huge sizes we override via
  // Object.defineProperty in the §R5 #5 case).
  if (content !== null) {
    return new File([content], name, { type });
  }
  const buf = new Uint8Array(size);
  return new File([buf], name, { type });
}

let createMutate;
let patchMutate;
let archiveMutate;
let unarchiveMutate;
let uploadMutate;

beforeEach(() => {
  jest.clearAllMocks();
  createMutate = jest.fn().mockResolvedValue({});
  patchMutate = jest.fn().mockResolvedValue({});
  archiveMutate = jest.fn().mockResolvedValue({});
  unarchiveMutate = jest.fn().mockResolvedValue({});
  uploadMutate = jest.fn().mockResolvedValue({});
  hooks.useSupplierDocuments.mockReturnValue({
    data: { items: [] }, isLoading: false, isError: false,
  });
  hooks.useCreateDocument.mockReturnValue({ mutateAsync: createMutate });
  hooks.usePatchDocument.mockReturnValue({ mutateAsync: patchMutate });
  hooks.useArchiveDocument.mockReturnValue({ mutateAsync: archiveMutate });
  hooks.useUnarchiveDocument.mockReturnValue({ mutateAsync: unarchiveMutate });
  hooks.useUploadDocumentFile.mockReturnValue({ mutateAsync: uploadMutate });
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

// =========================================================================
// Original list / dialog / archive / restore coverage (kept green, file_ref
// cell + free-text input now removed per §R1).
// =========================================================================

describe('<DocumentsTab/> — list + actions', () => {
  test('list renders rows', () => {
    setMe(['supplier_documents.view']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [
        { id: 'D1', doc_type: 'Public_Liability', title: 'PL2026',
          issued_on: '2025-01-01', expires_on: isoDelta(60),
          is_archived: false, notes: null, has_file: false },
      ]},
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
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
        issued_on: null, expires_on: null,
        is_archived: false, notes: null, has_file: false }]},
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
        is_archived: false, has_file: false }] },
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
        is_archived: true, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
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

  test('expiry badge variants — expired shows; valid does not', () => {
    setMe(['supplier_documents.view']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [
        { id: 'D1', doc_type: 'Other', title: 'A', expires_on: isoDelta(-1),
          is_archived: false, has_file: false },
        { id: 'D2', doc_type: 'Other', title: 'B', expires_on: isoDelta(100),
          is_archived: false, has_file: false },
      ]},
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.getByTestId('document-row-expiry-D1')).toHaveTextContent('Expired');
    expect(screen.queryByTestId('document-row-expiry-D2')).toBeNull();
  });

  test('create flow: open dialog, fill, submit → create mutation called (no file_ref in payload)', async () => {
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
    // §R1.2 — file_ref is gone from the payload builder.
    expect(body).not.toHaveProperty('file_ref');
  });
});

// =========================================================================
// §R5 cases #1–#13 — Build Pack 2.7-FE-docupload acceptance suite
// =========================================================================

describe('§R5 #1 — cleanup: file_ref text input is GONE', () => {
  test('document-form-file-ref testid is ABSENT from the add dialog', () => {
    setMe(['supplier_documents.view', 'supplier_documents.create']);
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('documents-tab-add-btn'));
    expect(screen.getByTestId('document-form')).toBeInTheDocument();
    // Hard acceptance — the testid MUST NOT exist anywhere.
    expect(screen.queryByTestId('document-form-file-ref')).toBeNull();
    // Defence in depth — no "File ref" label text either.
    expect(screen.queryByText(/file ref/i)).toBeNull();
  });

  test('document-form-file-ref testid is ABSENT from the edit dialog', () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('document-row-edit-D1'));
    expect(screen.queryByTestId('document-form-file-ref')).toBeNull();
  });
});

describe('§R5 #2 — upload happy path', () => {
  test('PDF pick → upload mutation called → row would flip to file-present', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'PL',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    const { rerender } = render(<DocumentsTab supplierId="S1" />);
    const file = makeFile({ name: 'cert.pdf', type: 'application/pdf', size: 100 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [file] },
      });
    });

    await waitFor(() => expect(uploadMutate).toHaveBeenCalledWith({ id: 'D1', file }));
    expect(toast.success).toHaveBeenCalledWith('File uploaded');

    // Simulate the cache invalidation flipping the row to file-present
    // (the upload hook does this; here we re-render with the new shape).
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'PL',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    rerender(<DocumentsTab supplierId="S1" />);

    expect(screen.getByTestId('document-row-file-name-D1')).toHaveTextContent('cert.pdf');
    expect(screen.getByTestId('document-row-file-size-D1')).toHaveTextContent('100 B');
    expect(screen.getByTestId('document-row-download-D1')).toBeInTheDocument();
  });
});

describe('§R5 #3 — pre-check blocks empty file, no request fires', () => {
  test('0-byte file → inline error, uploadMutate NOT called', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    const file = makeFile({ name: 'empty.pdf', type: 'application/pdf', content: '' });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [file] },
      });
    });

    expect(uploadMutate).not.toHaveBeenCalled();
    expect(screen.getByTestId('document-row-upload-error-D1')).toHaveTextContent(/empty/i);
  });
});

describe('§R5 #4 — pre-check blocks disallowed type', () => {
  test('.exe / application/octet-stream blocked, no request', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    const bad = makeFile({ name: 'virus.exe', type: 'application/octet-stream', size: 32 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [bad] },
      });
    });

    expect(uploadMutate).not.toHaveBeenCalled();
    expect(screen.getByTestId('document-row-upload-error-D1'))
      .toHaveTextContent(/unsupported file type/i);
  });
});

describe('§R5 #5 — pre-check blocks oversize', () => {
  test('> 25 MB blocked, message states the cap, no request', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    // Override `.size` so we exceed the cap without allocating 25 MB.
    const huge = makeFile({ name: 'huge.pdf', type: 'application/pdf', size: 1 });
    Object.defineProperty(huge, 'size', { value: 25 * 1024 * 1024 + 1 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [huge] },
      });
    });

    expect(uploadMutate).not.toHaveBeenCalled();
    expect(screen.getByTestId('document-row-upload-error-D1'))
      .toHaveTextContent(/25 MB/);
  });
});

describe('§R5 #6 — server 413 (pre-check bypassed) → size toast', () => {
  test('413 → "File is too large" toast with the 25 MB cap', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    uploadMutate.mockRejectedValueOnce(
      Object.assign(new Error('Boom'), {
        response: { status: 413, data: { detail: 'file too large' } },
      }),
    );
    render(<DocumentsTab supplierId="S1" />);
    const file = makeFile({ name: 'cert.pdf', type: 'application/pdf', size: 64 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [file] },
      });
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const msg = toast.error.mock.calls[0][0];
    expect(msg).toMatch(/too large/i);
    expect(msg).toMatch(/25 MB/);
  });
});

describe('§R5 #7 — server 422 → surface server detail', () => {
  test('422 with detail string is shown in the toast verbatim', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    uploadMutate.mockRejectedValueOnce(
      Object.assign(new Error('Boom'), {
        response: { status: 422, data: { detail: 'Disallowed content type' } },
      }),
    );
    render(<DocumentsTab supplierId="S1" />);
    const file = makeFile({ name: 'cert.pdf', type: 'application/pdf', size: 64 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [file] },
      });
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Disallowed content type'));
  });
});

describe('§R5 #8 — download 404 → not-found toast', () => {
  test('404 from downloadDocumentFile maps to "File not found"', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    docsApi.downloadDocumentFile.mockRejectedValueOnce(
      Object.assign(new Error('not found'), { status: 404 }),
    );
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('document-row-download-D1'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('File not found.'));
  });
});

describe('§R5 #9 — 502 maps to friendly storage-unavailable, NEVER as user error', () => {
  test('upload 502 → friendly toast; raw detail NOT echoed', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    uploadMutate.mockRejectedValueOnce(
      Object.assign(new Error('Boom'), {
        response: { status: 502, data: { detail: 'document storage unavailable' } },
      }),
    );
    render(<DocumentsTab supplierId="S1" />);
    const file = makeFile({ name: 'cert.pdf', type: 'application/pdf', size: 64 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [file] },
      });
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const msg = toast.error.mock.calls[0][0];
    expect(msg).toMatch(/temporarily unavailable/i);
    expect(msg).toMatch(/try again shortly/i);
    // Hard negative — raw backend detail MUST NOT be the user-facing toast.
    expect(msg).not.toBe('document storage unavailable');
  });

  test('download 502 → same friendly toast', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    docsApi.downloadDocumentFile.mockRejectedValueOnce(
      Object.assign(new Error('storage unavailable'), {
        status: 502, detail: 'document storage unavailable',
      }),
    );
    render(<DocumentsTab supplierId="S1" />);
    fireEvent.click(screen.getByTestId('document-row-download-D1'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const msg = toast.error.mock.calls[0][0];
    expect(msg).toMatch(/temporarily unavailable/i);
    expect(msg).not.toBe('document storage unavailable');
  });
});

describe('§R5 #10 — download triggers blob save (URL created + revoked)', () => {
  test('downloadDocumentFile called for the row; objectURL created + revoked; <a download> fires', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    const blob = new Blob(['hello'], { type: 'application/pdf' });
    docsApi.downloadDocumentFile.mockResolvedValueOnce({
      blob, filename: 'cert-from-cd.pdf',
    });

    const createURL = jest.fn().mockReturnValue('blob:mock://1');
    const revokeURL = jest.fn();
    URL.createObjectURL = createURL;
    URL.revokeObjectURL = revokeURL;
    const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});

    render(<DocumentsTab supplierId="S1" />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('document-row-download-D1'));
    });

    await waitFor(() => expect(docsApi.downloadDocumentFile).toHaveBeenCalledWith('D1'));
    expect(createURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeURL).toHaveBeenCalledWith('blob:mock://1');

    clickSpy.mockRestore();
  });

  test('falls back to row.file_name when Content-Disposition is absent', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'fallback.pdf', file_size: 12,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    docsApi.downloadDocumentFile.mockResolvedValueOnce({
      blob: new Blob(['x']), filename: null,
    });
    URL.createObjectURL = jest.fn().mockReturnValue('blob:1');
    URL.revokeObjectURL = jest.fn();
    let capturedDownload = null;
    const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function clickImpl() {
        capturedDownload = this.getAttribute('download');
      });

    render(<DocumentsTab supplierId="S1" />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('document-row-download-D1'));
    });

    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(capturedDownload).toBe('fallback.pdf');

    clickSpy.mockRestore();
  });
});

describe('§R5 #11 — sensitive gating: no name/size/Download without view_sensitive', () => {
  test('non-sensitive viewer sees only the neutral "File attached" indicator', () => {
    setMe([
      'supplier_documents.view',
      'supplier_documents.edit',
      // NOTE: NO view_sensitive.
    ]);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 12345,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);

    expect(screen.getByTestId('document-row-file-attached-D1'))
      .toHaveTextContent(/file attached/i);
    expect(screen.queryByTestId('document-row-file-name-D1')).toBeNull();
    expect(screen.queryByTestId('document-row-file-size-D1')).toBeNull();
    expect(screen.queryByTestId('document-row-download-D1')).toBeNull();
    // And the cell does NOT leak the filename.
    const cell = screen.getByTestId('document-row-file-D1');
    expect(cell.textContent).not.toMatch(/cert\.pdf/);
  });
});

describe('§R5 #12 — edit gating: no Upload/Replace without edit perm', () => {
  test('viewer without edit perm sees "No file" placeholder, not an upload control', () => {
    setMe([
      'supplier_documents.view',
      'supplier_documents.view_sensitive',
      // NOTE: NO edit.
    ]);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);

    expect(screen.queryByTestId('document-row-upload-D1')).toBeNull();
    expect(screen.queryByTestId('document-row-replace-D1')).toBeNull();
    expect(screen.getByTestId('document-row-no-file-D1')).toBeInTheDocument();
  });

  test('archived row with file: Download IS allowed for sensitive viewers; Replace is NOT', () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: true, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);

    // §R2.4 — download IS allowed on archived rows for sensitive viewers
    expect(screen.getByTestId('document-row-download-D1')).toBeInTheDocument();
    // But replace MUST NOT render on archived rows.
    expect(screen.queryByTestId('document-row-replace-D1')).toBeNull();
  });
});

describe('§R5 #13 — no SharePoint / Graph URL leaks into the DOM', () => {
  test('file column renders no sharepoint / graph.microsoft / http URL', () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);

    const cell = screen.getByTestId('document-row-file-D1');
    const html = cell.outerHTML.toLowerCase();
    expect(html).not.toMatch(/sharepoint/);
    expect(html).not.toMatch(/graph\.microsoft/);
    // No http(s)://… anywhere in the rendered file cell. The Download
    // button uses an in-memory click → no URL surfaces in the DOM.
    expect(html).not.toMatch(/https?:\/\//);
  });

  test('non-sensitive viewer also has no URL leakage', () => {
    setMe(['supplier_documents.view']);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: true,
        file_name: 'cert.pdf', file_size: 100,
        file_content_type: 'application/pdf' }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    const cell = screen.getByTestId('document-row-file-D1');
    const html = cell.outerHTML.toLowerCase();
    expect(html).not.toMatch(/sharepoint/);
    expect(html).not.toMatch(/graph\.microsoft/);
    expect(html).not.toMatch(/https?:\/\//);
  });
});

// =========================================================================
// §R2.4 — archived rows: no upload control either
// =========================================================================

describe('§R2.4 — archived row: no upload/replace controls', () => {
  test('archived row with NO file shows "No file" — no Upload', () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: true, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    expect(screen.queryByTestId('document-row-upload-D1')).toBeNull();
    expect(screen.getByTestId('document-row-no-file-D1')).toBeInTheDocument();
  });
});

// =========================================================================
// §R9 scope-creep — disabled "Uploading…" state prevents double-submit
// =========================================================================

describe('§R9 — uploading state disables the picker', () => {
  test('while a previous upload is in flight, the input is disabled', async () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    // Keep the promise pending so we can observe the in-flight state.
    let resolveUpload;
    uploadMutate.mockImplementationOnce(
      () => new Promise((r) => { resolveUpload = r; }),
    );
    render(<DocumentsTab supplierId="S1" />);
    const file = makeFile({ name: 'cert.pdf', type: 'application/pdf', size: 64 });

    await act(async () => {
      fireEvent.change(screen.getByTestId('document-row-upload-D1'), {
        target: { files: [file] },
      });
    });

    // Disabled state visible while mutation is in flight.
    const inputDuring = screen.getByTestId('document-row-upload-D1');
    expect(inputDuring).toBeDisabled();

    await act(async () => { resolveUpload({}); });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });
});

// =========================================================================
// §R2.5 mobile-first: the picker IS a real <input type="file"> with
// the correct accept allowlist (NOT a drag-drop-only zone).
// =========================================================================

describe('§R2.5 — mobile-first <input type="file"> + accept allowlist', () => {
  test('upload control is an <input type="file"> with the §R0.3 MIME allowlist', () => {
    setMe(ALL_PERMS);
    hooks.useSupplierDocuments.mockReturnValue({
      data: { items: [{ id: 'D1', doc_type: 'Other', title: 'X',
        is_archived: false, has_file: false }] },
      isLoading: false, isError: false,
    });
    render(<DocumentsTab supplierId="S1" />);
    const input = screen.getByTestId('document-row-upload-D1');
    expect(input.tagName).toBe('INPUT');
    expect(input.getAttribute('type')).toBe('file');
    const accept = input.getAttribute('accept') || '';
    // Every entry in §R0.3 must be in the accept attr.
    [
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
    ].forEach((mime) => {
      expect(accept).toContain(mime);
    });
  });
});
