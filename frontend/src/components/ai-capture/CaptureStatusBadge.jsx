// frontend/src/components/ai-capture/CaptureStatusBadge.jsx — Chat 19C §R2.4
//
// 6-status badge for AI capture jobs. Mirrors the ActualStatusBadge pattern
// from 19B (lookup map keyed on backend status string; safe fallback).

const STATUS_STYLES = {
  Queued:           { label: 'Queued',           cls: 'bg-slate-100 text-slate-700' },
  Extracting:       { label: 'Extracting',       cls: 'bg-blue-100 text-blue-700' },
  Awaiting_Review:  { label: 'Awaiting Review',  cls: 'bg-amber-100 text-amber-800' },
  Completed:        { label: 'Completed',        cls: 'bg-green-100 text-green-700' },
  Failed:           { label: 'Failed',           cls: 'bg-rose-100 text-rose-700' },
  Discarded:        { label: 'Discarded',        cls: 'bg-slate-100 text-slate-500 line-through' },
};

export function CaptureStatusBadge({ status }) {
  const s = STATUS_STYLES[status] || {
    label: status,
    cls: 'bg-slate-100 text-slate-700',
  };
  return (
    <span
      data-testid={`capture-status-${status}`}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}
    >
      {s.label}
    </span>
  );
}
