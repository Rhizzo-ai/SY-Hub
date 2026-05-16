/**
 * ActualsFilters (Chat 19B §R2.6).
 *
 * Three filter inputs:
 *   - Status select  (All | Draft | Posted | Paid | Disputed | Void)
 *   - Source select  (All sources | Manual | Xero bill | ...)
 *   - Search input   (debounced 250 ms; matches description + supplier)
 */
import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const STATUSES = ['All', 'Draft', 'Posted', 'Paid', 'Disputed', 'Void'];
const SOURCE_TYPES = [
  { value: '__ALL__', label: 'All sources' },
  { value: 'Manual_Entry', label: 'Manual' },
  { value: 'Xero_Bill', label: 'Xero bill' },
  { value: 'Xero_Credit_Note', label: 'Xero credit note' },
  { value: 'SC_Valuation', label: 'Subcontract valuation' },
  { value: 'Day_Rate_Timesheet', label: 'Day-rate timesheet' },
  { value: 'Expense_Claim', label: 'Expense claim' },
  { value: 'Journal', label: 'Journal' },
  { value: 'Internal_Recharge', label: 'Internal recharge' },
];

export function ActualsFilters({ value, onChange }) {
  const [searchDraft, setSearchDraft] = useState(value.search || '');

  // Debounce search input — 250 ms
  useEffect(() => {
    const t = setTimeout(() => {
      onChange({ ...value, search: searchDraft });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="actuals-filters">
      <Select
        value={value.status ?? 'All'}
        onValueChange={(v) =>
          onChange({ ...value, status: v === 'All' ? undefined : v })
        }
      >
        <SelectTrigger className="w-36" data-testid="actuals-filter-status">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {STATUSES.map((s) => (
            <SelectItem key={s} value={s}>{s}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={value.source_type ?? '__ALL__'}
        onValueChange={(v) =>
          onChange({ ...value, source_type: v === '__ALL__' ? undefined : v })
        }
      >
        <SelectTrigger className="w-48" data-testid="actuals-filter-source">
          <SelectValue placeholder="All sources" />
        </SelectTrigger>
        <SelectContent>
          {SOURCE_TYPES.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Input
        type="search"
        placeholder="Search supplier / description"
        value={searchDraft}
        onChange={(e) => setSearchDraft(e.target.value)}
        className="w-64"
        data-testid="actuals-filter-search"
      />
    </div>
  );
}
