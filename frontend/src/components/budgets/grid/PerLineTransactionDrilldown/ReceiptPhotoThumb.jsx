/**
 * ReceiptPhotoThumb — R6 v2.
 *
 * Renders the first photo on a receipt as a 40×40 thumbnail.
 *
 * Contract:
 *   - `loading="lazy"` so off-screen receipts never block the grid.
 *   - `alt` is always populated: caption first, then filename, then a
 *     deterministic "Receipt photo" fallback. Never empty.
 *   - `onError` swaps in a glyph + the visible filename so a broken
 *     thumbnail can't blank-pixel the row.
 *
 * The photo serving endpoint is intentionally future-shaped:
 *   GET /api/v1/receipts/photos/{id}
 * — this lands when the photo router ships; until then the `onError`
 * branch handles the 404 cleanly. We never inline the file_path
 * (a server-side filesystem path that the browser cannot resolve).
 */
import { useState } from 'react';
import { ImageOff } from 'lucide-react';

export function ReceiptPhotoThumb({ photo, receiptId }) {
  const [broken, setBroken] = useState(false);
  if (!photo) {
    return (
      <div
        className="flex h-8 w-8 items-center justify-center rounded border border-slate-200 bg-slate-50 text-[10px] text-slate-400"
        data-testid={`bg2-receipt-photo-none-${receiptId}`}
        aria-hidden="true"
      >
        —
      </div>
    );
  }
  const altText = photo.caption?.trim()
    || photo.original_filename?.trim()
    || 'Receipt photo';
  if (broken) {
    return (
      <div
        className="flex h-8 w-8 items-center justify-center rounded border border-slate-200 bg-slate-100 text-slate-500"
        title={altText}
        data-testid={`bg2-receipt-photo-fallback-${receiptId}`}
        role="img"
        aria-label={`${altText} (image unavailable)`}
      >
        <ImageOff size={14} aria-hidden="true" />
      </div>
    );
  }
  const src = `/api/v1/receipts/photos/${photo.id}`;
  return (
    <img
      src={src}
      alt={altText}
      loading="lazy"
      width={32}
      height={32}
      className="h-8 w-8 rounded border border-slate-200 object-cover"
      onError={() => setBroken(true)}
      data-testid={`bg2-receipt-photo-${receiptId}`}
    />
  );
}

export default ReceiptPhotoThumb;
