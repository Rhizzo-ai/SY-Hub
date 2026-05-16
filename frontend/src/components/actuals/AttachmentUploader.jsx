/**
 * AttachmentUploader (Chat 19B §R3.4).
 *
 * Drag-drop multi-file + paste-from-clipboard. Per actual, gated on
 * `canAttach(actual, me, isDesktop)`. Uploads SEQUENTIALLY (no batch
 * endpoint; predictable toast order).
 *
 * Paste handler: React synthetic `onPaste` is attached to the dropzone
 * div AFTER spreading `getRootProps()`. react-dropzone v14's `getRootProps`
 * hardcodes its own `rootRef` and silently overrides user-supplied refs,
 * so the listener-on-ref pattern is broken. `onPaste` is not returned by
 * `getRootProps()` so it composes cleanly.
 */
import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { toast } from 'sonner';
import { useUploadAttachment } from '@/hooks/actuals';

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/heic': ['.heic'],
  'image/heif': ['.heif'],
  'image/tiff': ['.tif', '.tiff'],
};

// 25 MB — matches backend ACTUALS_ATTACHMENT_MAX_BYTES.
const MAX_SIZE = 25 * 1024 * 1024;

export function AttachmentUploader({ actualId, disabled }) {
  const uploadMut = useUploadAttachment(actualId);

  const uploadOne = useCallback(
    async (file) => {
      if (file.size > MAX_SIZE) {
        toast.error(`${file.name}: file is too large (max 25 MB)`);
        return;
      }
      try {
        await uploadMut.mutateAsync(file);
        toast.success(`Uploaded ${file.name}`);
      } catch (err) {
        const detail = err?.response?.data?.detail;
        const msg =
          typeof detail === 'string'
            ? detail
            : detail?.message ?? err?.message;
        toast.error(`${file.name}: ${msg ?? 'upload failed'}`);
      }
    },
    [uploadMut],
  );

  const onDrop = useCallback(
    async (acceptedFiles, rejectedFiles) => {
      for (const r of rejectedFiles) {
        const reason = r.errors?.[0]?.message ?? 'invalid file';
        toast.error(`${r.file.name}: ${reason}`);
      }
      for (const f of acceptedFiles) {
        // eslint-disable-next-line no-await-in-loop
        await uploadOne(f);
      }
    },
    [uploadOne],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: MAX_SIZE,
    multiple: true,
    disabled,
  });

  const handlePaste = useCallback(
    (e) => {
      if (disabled) return;
      const items = e.clipboardData?.items;
      if (!items) return;
      const files = [];
      for (const item of items) {
        if (item.kind === 'file') {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length) {
        e.preventDefault();
        onDrop(files, []);
      }
    },
    [disabled, onDrop],
  );

  return (
    <div
      {...getRootProps()}
      onPaste={handlePaste}
      data-testid="attachment-uploader"
      className={`rounded-lg border-2 border-dashed p-6 text-center cursor-pointer focus:outline-none focus:ring-2 focus:ring-sy-teal ${
        disabled ? 'opacity-50 cursor-not-allowed' : ''
      } ${isDragActive ? 'border-sy-teal bg-sy-teal/5' : 'border-slate-300'}`}
    >
      <input {...getInputProps()} />
      <p className="text-sm text-slate-600">
        {disabled
          ? 'Attachments disabled for this status.'
          : isDragActive
          ? 'Drop files to upload…'
          : 'Drag PDFs or images here, click to browse, or paste from clipboard.'}
      </p>
      <p className="mt-1 text-xs text-slate-400">
        Max 25 MB · PDF, JPG, PNG, HEIC, TIFF
      </p>
      {uploadMut.isPending && (
        <p
          className="mt-2 text-xs text-sy-teal"
          data-testid="uploader-progress"
        >
          Uploading…
        </p>
      )}
    </div>
  );
}
