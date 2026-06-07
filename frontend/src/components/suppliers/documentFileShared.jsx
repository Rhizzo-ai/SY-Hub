/**
 * documentFileShared — Build Pack 2.7-DOCS-FE §R1 (Chat 46, B79-FE).
 *
 * Reusable file primitives extracted from `DocumentsTab.jsx` so the
 * retiring flat-table view and the new `<DocumentFolderView/>` import
 * the SAME implementation. Single source of truth for:
 *   - the §R0.3 MIME / extension allowlist + 25 MB cap,
 *   - the §R1.3 four-step preCheckFile (no-file → empty → type → size),
 *   - the §R0.2 error-mapping helpers (upload / download),
 *   - `<FilePicker/>` (mobile-baseline tap-to-pick),
 *   - `<DropZone/>` (desktop drag enhancement),
 *   - `<DocumentFileCell/>` (the row's file column, gated on perms).
 *
 * Hard contracts preserved verbatim from B76/B78:
 *   - `file.type` may be '' or a variant; the type gate ACCEPTS when
 *     MIME OR extension matches (server stays authoritative).
 *   - `key={nonce}` on the file input so the same file can be re-picked
 *     after a failed/cancelled upload (browsers suppress repeat onChange).
 *   - DropZone is a PASSIVE enhancement — the underlying `<input>`
 *     remains interactive so tap-to-pick survives intact.
 *
 * The module imports neither the flat table nor the folder view —
 * zero risk of circular dependency.
 */
import React, { useState } from 'react';


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

// ─── §R1.1 extension fallback — mirrors §R0.3, lower-case, dot-prefixed ─
// Used by preCheckFile when browsers report file.type as '' or a variant
// that is not in ALLOWED_MIME_TYPES (e.g. some PDFs report '', some CSVs
// report application/vnd.ms-excel, .doc/.xls often report
// application/octet-stream). Server stays the real validator — the
// client must not be stricter than the server.
export const ALLOWED_EXTENSIONS = Object.freeze([
  '.pdf',
  '.jpg', '.jpeg', '.png', '.gif', '.webp',
  '.doc', '.docx',
  '.xls', '.xlsx',
  '.csv', '.txt',
]);

// Include extensions in the OS picker so it's friendlier on platforms
// where MIME-only `accept` filters too aggressively (notably Windows +
// some mobile keyboards). The pre-check + server remain the real gate
// — `accept` is just a hint.
export const ACCEPT_ATTR = [...ALLOWED_MIME_TYPES, ...ALLOWED_EXTENSIONS].join(',');


/** Returns the lower-case dotted extension of `name`, or '' when none. */
export function fileExtension(name) {
  if (typeof name !== 'string') return '';
  const dot = name.lastIndexOf('.');
  if (dot < 0 || dot === name.length - 1) return '';
  return name.slice(dot).toLowerCase();
}


export function formatFileSize(bytes) {
  if (bytes == null || Number.isNaN(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}


/**
 * Returns an inline error string when the file fails pre-check, else
 * null. Order matters (§R1.3):
 *   1. no file       → "No file selected."
 *   2. empty (0 B)   → "File is empty — …"   (wins over type)
 *   3. type gate     → MIME ∈ allowlist OR extension ∈ allowlist.
 *                       Only when BOTH fail → "Unsupported file type…".
 *   4. size > MAX    → "File is too large — 25 MB cap."
 */
export function preCheckFile(file) {
  if (!file) return 'No file selected.';
  if (file.size === 0) return 'File is empty — please pick a non-empty file.';
  const mimeOk = ALLOWED_MIME_TYPES.includes(file.type);
  const extOk = ALLOWED_EXTENSIONS.includes(fileExtension(file.name));
  if (!mimeOk && !extOk) {
    return `Unsupported file type${file.type ? ` (${file.type})` : ''}.`;
  }
  if (file.size > MAX_FILE_BYTES) {
    return 'File is too large — 25 MB cap.';
  }
  return null;
}


/**
 * Maps an upload error to a §R0.2 toast string. Never echoes a raw
 * server detail back as if it were user-driven for 502 (storage down).
 */
export function uploadErrorMessage(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 413) return 'File is too large — 25 MB cap.';
  if (status === 422) return typeof detail === 'string' ? detail : 'Upload rejected.';
  if (status === 502) {
    return 'Document storage is temporarily unavailable, try again shortly.';
  }
  return (typeof detail === 'string' && detail) || err?.message || 'Upload failed.';
}


export function downloadErrorMessage(err) {
  if (err?.status === 404) return 'File not found.';
  if (err?.status === 502) {
    return 'Document storage is temporarily unavailable, try again shortly.';
  }
  return err?.detail || err?.message || 'Download failed.';
}


/**
 * Mobile-first tap-to-pick (§R2.5).
 *
 * The visible button is a <label> wrapping a screen-reader-only file
 * input — taps on iOS/Android open the system file picker directly.
 * NO drag-and-drop-only path. `key` is reset after each pick so the
 * same file can be re-selected (browsers suppress onChange when the
 * value is unchanged).
 */
export function FilePicker({ rowId, accept, isUploading, onPickFile, label, testid }) {
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
        data-row-id={rowId}
        onChange={(e) => {
          const f = e.target.files?.[0];
          setNonce((n) => n + 1);
          if (f) onPickFile(f);
        }}
      />
    </label>
  );
}


/**
 * DropZone — §R3 desktop drag-and-drop, layered on top of FilePicker.
 *
 * The children (a `<FilePicker/>` with its `<input type="file">`) MUST
 * remain interactive — tap-to-pick is the mobile baseline and is the
 * only required path. The drop-zone is a passive enhancement: it adds
 * onDragOver/onDragLeave/onDrop handlers that route the dropped file
 * through the same `onDropFile(file)` callback as the input's onChange.
 * Multi-file drops take only the first file.
 *
 * `onDropFile` is expected to perform the same pre-check the input path
 * does (parent owns the gate). DropZone itself is dumb.
 */
export function DropZone({ testid, onDropFile, children, className = '' }) {
  const [isOver, setIsOver] = useState(false);
  const base =
    'flex flex-col items-start gap-1 rounded-md border border-dashed px-3 py-2 transition-colors';
  const tone = isOver
    ? 'border-sy-teal-600 bg-sy-teal-50/60'
    : 'border-slate-300 bg-transparent';
  return (
    <div
      data-testid={testid}
      data-dragover={isOver ? 'true' : 'false'}
      className={`${base} ${tone} ${className}`}
      onDragOver={(e) => {
        // Must preventDefault — without it the browser opens the file
        // in a new tab instead of letting us handle the drop.
        e.preventDefault();
        if (!isOver) setIsOver(true);
      }}
      onDragEnter={(e) => {
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setIsOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        const file = e.dataTransfer?.files?.[0];
        if (file) onDropFile(file);
      }}
    >
      {children}
    </div>
  );
}


/**
 * Document row "file" cell (§R2.1–§R2.4).
 *
 * Pulled out as a sub-component so each row's conditional branches stay
 * legible. No external state — the parent owns the row-error/uploading
 * maps and just hands this component what to show.
 */
export function DocumentFileCell({
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
        <DropZone
          testid={`document-row-dropzone-${row.id}`}
          onDropFile={onPickFile}
        >
          <FilePicker
            rowId={row.id}
            accept={accept}
            isUploading={isUploading}
            onPickFile={onPickFile}
            label="Upload"
            testid={`document-row-upload-${row.id}`}
          />
          <span className="text-[11px] text-slate-500 mt-1">
            or drag a file here · PDF, image, Office docs · 25 MB max
          </span>
        </DropZone>
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
