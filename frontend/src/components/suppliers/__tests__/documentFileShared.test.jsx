/**
 * documentFileShared tests — Build Pack 2.7-DOCS-FE §R6 / Gate 1.
 *
 * Ports the coverage from `DocumentsTab.test.jsx` that targets the
 * extracted primitives, NOT the flat-table view. Deleting
 * `DocumentsTab.jsx` (Gate 4) silently drops those tests; running them
 * here proves the behaviour survives the retirement.
 *
 * Sourced from the following blocks of `DocumentsTab.test.jsx`:
 *   - §R5 #2-#13 upload/download paths' helper-level invariants
 *     (precheck, formatFileSize, error mapping).
 *   - §R2.4 archived-row → no controls (DocumentFileCell branch).
 *   - §R9 uploading-state disables the picker (FilePicker prop).
 *   - §R2.5 accept allowlist on the actual <input type="file">.
 *   - docfix §R1 #1-#5 + helper unit tests for the extension fallback.
 *   - docfix §R6 #11/#12/#13 drag-drop primitives (DropZone wired
 *     through to onDropFile; jsdom drag pinned via dataTransfer).
 *   - the no-URL-leak invariant on file_ref (kept as a guard at the
 *     cell-level: a non-sensitive viewer with `has_file=true` MUST get
 *     the neutral "File attached" branch — no name, no download).
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

import {
  ALLOWED_MIME_TYPES,
  MAX_FILE_BYTES,
  ALLOWED_EXTENSIONS,
  ACCEPT_ATTR,
  fileExtension,
  formatFileSize,
  preCheckFile,
  uploadErrorMessage,
  downloadErrorMessage,
  FilePicker,
  DropZone,
  DocumentFileCell,
} from '@/components/suppliers/documentFileShared';


// ---------------------------------------------------------------------------
// preCheckFile — four-step gate (no-file → empty → type → size)
// ---------------------------------------------------------------------------

function pcFile({ name, type, size }) {
  // defineProperty avoids allocating big buffers for oversize cases.
  const f = new File([new Uint8Array(Math.min(size, 8))], name, { type });
  Object.defineProperty(f, 'size', { value: size, configurable: true });
  return f;
}

describe('preCheckFile — type gate + extension fallback', () => {
  test('null/undefined → "No file selected."', () => {
    expect(preCheckFile(null)).toMatch(/no file selected/i);
    expect(preCheckFile(undefined)).toMatch(/no file selected/i);
  });

  test('empty (0 B) wins over the type gate (empty.pdf still flagged empty)', () => {
    const f = pcFile({ name: 'empty.pdf', type: 'application/pdf', size: 0 });
    expect(preCheckFile(f)).toMatch(/empty/i);
  });

  test('valid MIME → null', () => {
    const f = pcFile({ name: 'plan.pdf', type: 'application/pdf', size: 1024 });
    expect(preCheckFile(f)).toBeNull();
  });

  test('empty MIME + valid extension is ACCEPTED (browsers report "")', () => {
    const f = pcFile({ name: 'plan.pdf', type: '', size: 1024 });
    expect(preCheckFile(f)).toBeNull();
  });

  test('variant MIME with valid extension is ACCEPTED via extension', () => {
    const f = pcFile({
      name: 'invoices.csv',
      type: 'application/vnd.ms-excel',
      size: 2048,
    });
    expect(preCheckFile(f)).toBeNull();
  });

  test('octet-stream + valid extension (.docx) is ACCEPTED via extension', () => {
    const f = pcFile({
      name: 'spec.docx',
      type: 'application/octet-stream',
      size: 1024,
    });
    expect(preCheckFile(f)).toBeNull();
  });

  test('genuinely bad file (.exe + octet-stream) is REJECTED with the offending MIME echoed', () => {
    const f = pcFile({ name: 'virus.exe', type: 'application/octet-stream', size: 1024 });
    const msg = preCheckFile(f);
    expect(msg).toMatch(/unsupported file type/i);
    expect(msg).toMatch(/application\/octet-stream/);
  });

  test('bad MIME + bad extension + no MIME echoed when type is ""', () => {
    const f = pcFile({ name: 'mystery.xyz', type: '', size: 64 });
    const msg = preCheckFile(f);
    expect(msg).toMatch(/unsupported file type/i);
    expect(msg).not.toMatch(/\(/);  // no parenthesised MIME tail
  });

  test('oversize (> 25 MB) is REJECTED even with valid type+extension', () => {
    const f = pcFile({
      name: 'huge.pdf',
      type: 'application/pdf',
      size: MAX_FILE_BYTES + 1,
    });
    expect(preCheckFile(f)).toMatch(/25 MB/);
  });
});


// ---------------------------------------------------------------------------
// fileExtension — case-insensitive, edge-tolerant
// ---------------------------------------------------------------------------

describe('fileExtension', () => {
  test('case-insensitive', () => {
    expect(fileExtension('report.PDF')).toBe('.pdf');
    expect(fileExtension('Spreadsheet.XLSX')).toBe('.xlsx');
  });
  test('takes only the trailing segment', () => {
    expect(fileExtension('archive.tar.gz')).toBe('.gz');
  });
  test('returns "" for edge inputs', () => {
    expect(fileExtension('no-extension')).toBe('');
    expect(fileExtension('trailing.')).toBe('');
    expect(fileExtension(null)).toBe('');
    expect(fileExtension(undefined)).toBe('');
    expect(fileExtension(42)).toBe('');
  });
});


// ---------------------------------------------------------------------------
// Allowlists are frozen and contain the §R0.3 entries
// ---------------------------------------------------------------------------

describe('Allowlists', () => {
  test('frozen', () => {
    expect(Object.isFrozen(ALLOWED_MIME_TYPES)).toBe(true);
    expect(Object.isFrozen(ALLOWED_EXTENSIONS)).toBe(true);
  });
  test('every §R0.3 MIME is in the accept attr', () => {
    [
      'application/pdf',
      'image/jpeg', 'image/png', 'image/gif', 'image/webp',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'text/csv', 'text/plain',
    ].forEach((m) => {
      expect(ACCEPT_ATTR).toContain(m);
      expect(ALLOWED_MIME_TYPES).toContain(m);
    });
  });
});


// ---------------------------------------------------------------------------
// formatFileSize — unit boundaries
// ---------------------------------------------------------------------------

describe('formatFileSize', () => {
  test('returns "" for nullish / NaN', () => {
    expect(formatFileSize(null)).toBe('');
    expect(formatFileSize(undefined)).toBe('');
    expect(formatFileSize(Number.NaN)).toBe('');
  });
  test('bytes/KB/MB/GB rollover', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(2048)).toMatch(/KB$/);
    expect(formatFileSize(5 * 1024 * 1024)).toMatch(/MB$/);
    expect(formatFileSize(2 * 1024 * 1024 * 1024)).toMatch(/GB$/);
  });
});


// ---------------------------------------------------------------------------
// uploadErrorMessage / downloadErrorMessage — §R0.2 mapping
// ---------------------------------------------------------------------------

describe('uploadErrorMessage', () => {
  test('413 → fixed cap copy', () => {
    expect(uploadErrorMessage({ response: { status: 413 } })).toMatch(/25 MB cap/);
  });
  test('422 with string detail → echoes detail', () => {
    expect(uploadErrorMessage({
      response: { status: 422, data: { detail: 'reason X' } },
    })).toBe('reason X');
  });
  test('422 with non-string detail → "Upload rejected." (no JSON dump)', () => {
    expect(uploadErrorMessage({
      response: { status: 422, data: { detail: { loc: ['body'] } } },
    })).toBe('Upload rejected.');
  });
  test('502 NEVER echoes server detail (storage down is not the user\'s fault)', () => {
    expect(uploadErrorMessage({
      response: { status: 502, data: { detail: 'sharepoint exploded' } },
    })).toMatch(/temporarily unavailable/);
  });
  test('fallback to detail, then err.message, then generic', () => {
    expect(uploadErrorMessage({ message: 'boom' })).toBe('boom');
    expect(uploadErrorMessage({})).toBe('Upload failed.');
  });
});

describe('downloadErrorMessage', () => {
  test('404 → "File not found."', () => {
    expect(downloadErrorMessage({ status: 404 })).toBe('File not found.');
  });
  test('502 → friendly storage copy', () => {
    expect(downloadErrorMessage({ status: 502 })).toMatch(/temporarily unavailable/);
  });
  test('falls through to detail/message/generic', () => {
    expect(downloadErrorMessage({ detail: 'd' })).toBe('d');
    expect(downloadErrorMessage({ message: 'm' })).toBe('m');
    expect(downloadErrorMessage({})).toBe('Download failed.');
  });
});


// ---------------------------------------------------------------------------
// FilePicker — tap-to-pick is a real <input type="file">; uploading
// state disables it; key=nonce resets after each pick so the same file
// can be re-selected.
// ---------------------------------------------------------------------------

describe('<FilePicker/>', () => {
  test('renders a real <input type="file"> with the accept attr', () => {
    render(
      <FilePicker
        rowId="r1"
        accept={ACCEPT_ATTR}
        isUploading={false}
        onPickFile={() => {}}
        label="Upload"
        testid="fp"
      />,
    );
    const input = screen.getByTestId('fp');
    expect(input.tagName).toBe('INPUT');
    expect(input.getAttribute('type')).toBe('file');
    expect(input.getAttribute('accept')).toBe(ACCEPT_ATTR);
  });

  test('isUploading=true disables the input and switches the label copy', () => {
    render(
      <FilePicker
        rowId="r1" accept="*" isUploading={true}
        onPickFile={() => {}} label="Upload" testid="fp"
      />,
    );
    expect(screen.getByTestId('fp')).toBeDisabled();
    expect(screen.getByText(/Uploading…/)).toBeInTheDocument();
  });

  test('onPickFile fires with the picked file', () => {
    const cb = jest.fn();
    render(
      <FilePicker
        rowId="r1" accept="*" isUploading={false}
        onPickFile={cb} label="Upload" testid="fp"
      />,
    );
    const f = pcFile({ name: 'a.pdf', type: 'application/pdf', size: 16 });
    fireEvent.change(screen.getByTestId('fp'), { target: { files: [f] } });
    expect(cb).toHaveBeenCalledWith(f);
  });
});


// ---------------------------------------------------------------------------
// DropZone — drag handlers route to onDropFile
// ---------------------------------------------------------------------------

describe('<DropZone/>', () => {
  test('dropping a file routes it through onDropFile', () => {
    const cb = jest.fn();
    render(
      <DropZone testid="dz" onDropFile={cb}>
        <span>kid</span>
      </DropZone>,
    );
    const dz = screen.getByTestId('dz');
    const f = pcFile({ name: 'a.pdf', type: 'application/pdf', size: 16 });
    fireEvent.drop(dz, { dataTransfer: { files: [f] } });
    expect(cb).toHaveBeenCalledWith(f);
  });

  test('dragOver flips the data-dragover attribute', () => {
    render(
      <DropZone testid="dz" onDropFile={() => {}}>
        <span>kid</span>
      </DropZone>,
    );
    const dz = screen.getByTestId('dz');
    expect(dz.getAttribute('data-dragover')).toBe('false');
    fireEvent.dragEnter(dz);
    expect(dz.getAttribute('data-dragover')).toBe('true');
    fireEvent.dragLeave(dz);
    expect(dz.getAttribute('data-dragover')).toBe('false');
  });
});


// ---------------------------------------------------------------------------
// DocumentFileCell — the §R2 branches (sensitive / non-sensitive / no-file
// / archived). The no-URL-leak invariant lives here.
// ---------------------------------------------------------------------------

const baseRow = {
  id: 'D1', has_file: false, is_archived: false,
  file_name: null, file_size: null,
};

describe('<DocumentFileCell/>', () => {
  test('has_file && sensitive → renders filename + size + Download', () => {
    render(
      <DocumentFileCell
        row={{ ...baseRow, has_file: true, file_name: 'cert.pdf', file_size: 1024 }}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByTestId('document-row-file-name-D1')).toHaveTextContent('cert.pdf');
    expect(screen.getByTestId('document-row-download-D1')).toBeInTheDocument();
    expect(screen.getByTestId('document-row-file-size-D1')).toBeInTheDocument();
  });

  test('has_file && !sensitive → neutral "File attached" only (no filename, no Download)', () => {
    render(
      <DocumentFileCell
        row={{ ...baseRow, has_file: true, file_name: 'cert.pdf', file_size: 1024 }}
        canEdit={false} canSensitive={false}
        accept={ACCEPT_ATTR}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByTestId('document-row-file-attached-D1')).toBeInTheDocument();
    expect(screen.queryByTestId('document-row-file-name-D1')).toBeNull();
    expect(screen.queryByTestId('document-row-download-D1')).toBeNull();
  });

  test('!has_file && canEdit && !archived → Upload + DropZone', () => {
    render(
      <DocumentFileCell
        row={baseRow}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByTestId('document-row-dropzone-D1')).toBeInTheDocument();
    expect(screen.getByTestId('document-row-upload-D1')).toBeInTheDocument();
  });

  test('archived row → NO upload, NO download, just "—" placeholder', () => {
    // archived + has_file=false + can edit → still '—' (no upload while archived).
    render(
      <DocumentFileCell
        row={{ ...baseRow, is_archived: true }}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByTestId('document-row-no-file-D1')).toBeInTheDocument();
    expect(screen.queryByTestId('document-row-upload-D1')).toBeNull();
  });

  test('archived row with file + sensitive → renders filename + download BUT NOT Replace', () => {
    render(
      <DocumentFileCell
        row={{
          ...baseRow, has_file: true, is_archived: true,
          file_name: 'cert.pdf', file_size: 1024,
        }}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByTestId('document-row-download-D1')).toBeInTheDocument();
    expect(screen.queryByTestId('document-row-replace-D1')).toBeNull();
  });

  test('inlineError surfaces on the upload branch', () => {
    render(
      <DocumentFileCell
        row={baseRow}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        inlineError="File is empty — please pick a non-empty file."
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByTestId('document-row-upload-error-D1')).toHaveTextContent(/empty/);
  });

  test('isUploading → label flips to "Uploading…" (FilePicker prop wired)', () => {
    render(
      <DocumentFileCell
        row={baseRow}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        isUploading={true}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(screen.getByText(/Uploading…/)).toBeInTheDocument();
  });

  test('no-URL-leak: when row.file_ref is somehow present, the cell never reads it', () => {
    // Regression guard. file_ref is system-owned; the cell only knows
    // about has_file / file_name / file_size. We render with a
    // file_ref-shaped attribute and assert it never reaches the DOM.
    render(
      <DocumentFileCell
        row={{ ...baseRow, has_file: true, file_name: 'cert.pdf',
          file_ref: '{"sharepoint_id":"X"}', file_size: 1024 }}
        canEdit={true} canSensitive={true}
        accept={ACCEPT_ATTR}
        onPickFile={() => {}}
        onDownload={() => {}}
      />,
    );
    expect(document.body.innerHTML).not.toContain('sharepoint_id');
    expect(document.body.innerHTML).not.toContain('file_ref');
  });
});
