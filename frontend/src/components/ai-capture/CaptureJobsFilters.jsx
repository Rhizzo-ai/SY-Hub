// frontend/src/components/ai-capture/CaptureJobsFilters.jsx — Chat 19C §R2.5
//
// Status filter for the inbox. `__ALL__` sentinel (D40) collapses to
// undefined in the listCaptureJobs filter so the backend returns every
// status without server-side validation rejecting an empty enum value.
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const STATUS_OPTIONS = [
  { value: 'Awaiting_Review', label: 'Awaiting Review (default)' },
  { value: 'Queued',          label: 'Queued' },
  { value: 'Extracting',      label: 'Extracting' },
  { value: 'Failed',          label: 'Failed' },
  { value: 'Discarded',       label: 'Discarded' },
  { value: 'Completed',       label: 'Completed' },
  { value: '__ALL__',         label: 'All statuses' },
];

export function CaptureJobsFilters({ status, onStatusChange }) {
  return (
    <div className="flex items-center gap-3" data-testid="capture-jobs-filters">
      <label className="text-sm text-slate-600">Status</label>
      <Select value={status} onValueChange={onStatusChange}>
        <SelectTrigger className="w-64" data-testid="capture-status-trigger">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {STATUS_OPTIONS.map((o) => (
            <SelectItem
              key={o.value}
              value={o.value}
              data-testid={`capture-status-option-${o.value}`}
            >
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
