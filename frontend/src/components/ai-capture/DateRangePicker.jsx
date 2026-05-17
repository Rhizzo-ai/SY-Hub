// frontend/src/components/ai-capture/DateRangePicker.jsx — Chat 20 §R3.2
//
// Simple radio-style toggle group. NO Radix Select — static options,
// no need for F9 sentinel pattern (D8).
const OPTIONS = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: 'all', label: 'All time' },
];

export function DateRangePicker({ value, onChange }) {
  return (
    <div
      className="inline-flex rounded-md border border-slate-200 bg-white p-0.5"
      role="radiogroup"
      data-testid="date-range-picker"
    >
      {OPTIONS.map((opt) => {
        const isActive = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(opt.value)}
            data-testid={`date-range-${opt.value}`}
            className={[
              'px-3 py-1.5 text-sm rounded',
              isActive
                ? 'bg-sy-teal text-white'
                : 'text-slate-600 hover:text-slate-900',
            ].join(' ')}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
