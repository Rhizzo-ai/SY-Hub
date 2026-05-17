// frontend/src/pages/AICaptureCosts.jsx — Chat 20 §R3.1 (B38)
//
// Cost dashboard. Lazy-loaded from App.js (§R4) so recharts is
// code-split into its own chunk.
//
// I13 hooks-above-perm-gate: useCaptureCostStats MUST be above the
// canViewCaptureCosts() early-return.
import { useState, useMemo } from 'react';
import { useAuth } from '@/context/AuthContext';
import { canViewCaptureCosts } from '@/lib/aiCaptureCapability';
import { useCaptureCostStats } from '@/hooks/aiCapture';
import { CostTotalsCards } from '@/components/ai-capture/CostTotalsCards';
import { CostDailyChart } from '@/components/ai-capture/CostDailyChart';
import { CostByStatusChart } from '@/components/ai-capture/CostByStatusChart';
import { DateRangePicker } from '@/components/ai-capture/DateRangePicker';

function computeRange(quickPick) {
  const today = new Date();
  const toYMD = (d) => d.toISOString().slice(0, 10);
  // "All time" sends an explicit pre-feature epoch start; backend's missing-
  // params default is last-30-days, which would silently truncate "all" to
  // 30 days. AI capture didn't exist before Feb 2026 so '2024-01-01' is
  // safe as a forever-floor. (PASS 2 H6.)
  if (quickPick === 'all') {
    return { fromDate: '2024-01-01', toDate: toYMD(today) };
  }
  const days = { '7d': 6, '30d': 29, '90d': 89 }[quickPick] ?? 29;
  const from = new Date(today);
  from.setDate(from.getDate() - days);
  return { fromDate: toYMD(from), toDate: toYMD(today) };
}

export default function AICaptureCosts() {
  const { me } = useAuth();
  const [quickPick, setQuickPick] = useState('30d');
  const range = useMemo(() => computeRange(quickPick), [quickPick]);

  const { data, isLoading, error } = useCaptureCostStats(range, {
    enabled: canViewCaptureCosts(me),
  });

  if (!canViewCaptureCosts(me)) {
    return (
      <div className="p-6 text-sm text-slate-500" data-testid="cost-no-perm">
        You don't have permission to view AI Capture costs.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6" data-testid="ai-capture-costs-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="font-heading text-2xl text-slate-900">AI Capture Costs</h1>
        <DateRangePicker value={quickPick} onChange={setQuickPick} />
      </div>

      {error && (
        <div className="text-sm text-rose-600" data-testid="cost-error">
          {error?.response?.data?.detail?.message
            || error?.message
            || 'Failed to load stats'}
        </div>
      )}

      <CostTotalsCards data={data} isLoading={isLoading} quickPick={quickPick} />

      <CostDailyChart data={data} isLoading={isLoading} />

      <CostByStatusChart data={data} isLoading={isLoading} />
    </div>
  );
}
