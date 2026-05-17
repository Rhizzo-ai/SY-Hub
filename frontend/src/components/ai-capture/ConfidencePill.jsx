// frontend/src/components/ai-capture/ConfidencePill.jsx — Chat 19C §R2.7
//
// Single source of truth for the 0.80 confidence threshold + warning icon
// (D36). Used inline in tables and per-field in ExtractedFieldsPanel so
// future threshold tweaks only need editing aiCaptureCapability.js.
import { AlertTriangle } from 'lucide-react';
import { isLowConfidence } from '@/lib/aiCaptureCapability';
import { fmtConfidence } from '@/lib/format';

export function ConfidencePill({ value }) {
  if (value == null) {
    return (
      <span
        className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500"
        data-testid="confidence-pill-null"
      >
        —
      </span>
    );
  }
  const low = isLowConfidence(value);
  const cls = low
    ? 'bg-amber-50 text-amber-700'
    : 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${cls}`}
      data-testid={low ? 'confidence-pill-low' : 'confidence-pill-ok'}
      title={low ? 'Low confidence — review carefully' : undefined}
    >
      {low && <AlertTriangle size={11} strokeWidth={2.25} />}
      {fmtConfidence(value)}
    </span>
  );
}
