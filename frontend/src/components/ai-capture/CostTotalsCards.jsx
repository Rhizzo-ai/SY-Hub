// frontend/src/components/ai-capture/CostTotalsCards.jsx — Chat 20 §R3.3
//
// Four-card row of headline totals. Pence → GBP at render via fmtGBP(/100).
import { fmtGBP } from '@/lib/format';

function Card({ label, value, testid, isLoading }) {
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid={testid}
    >
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 h-8 flex items-center">
        {isLoading ? (
          <div
            className="h-6 w-24 rounded animate-pulse bg-slate-200"
            data-testid={`${testid}-skeleton`}
          />
        ) : (
          <span className="font-mono text-2xl text-slate-900">{value}</span>
        )}
      </div>
    </div>
  );
}

export function CostTotalsCards({ data, isLoading, quickPick }) {
  const t = data?.totals;
  const p = data?.period;
  // Friendly preset label (PASS 2 H10) — "All time" rather than "800 days".
  const periodLabel = (() => {
    if (!p) return '—';
    if (quickPick === 'all') return 'All time';
    if (quickPick === '7d') return 'Last 7 days';
    if (quickPick === '30d') return 'Last 30 days';
    if (quickPick === '90d') return 'Last 90 days';
    return `${p.days} day${p.days === 1 ? '' : 's'}`;
  })();
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        label="Total spent"
        value={fmtGBP((t?.total_cost_pence ?? 0) / 100)}
        testid="cost-total-spent"
        isLoading={isLoading}
      />
      <Card
        label="Total jobs"
        value={String(t?.total_jobs ?? 0)}
        testid="cost-total-jobs"
        isLoading={isLoading}
      />
      <Card
        label="Average per job"
        value={fmtGBP((t?.avg_cost_pence ?? 0) / 100)}
        testid="cost-avg-per-job"
        isLoading={isLoading}
      />
      <Card
        label="Period"
        value={periodLabel}
        testid="cost-period"
        isLoading={isLoading}
      />
    </div>
  );
}
