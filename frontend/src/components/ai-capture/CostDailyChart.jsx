// frontend/src/components/ai-capture/CostDailyChart.jsx — Chat 20 §R3.4
//
// Daily cost line. Imports recharts directly — this is the file that
// pulls recharts into the lazy chunk. D12 individual imports for
// tree-shaking.
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { fmtGBP } from '@/lib/format';

export function CostDailyChart({ data, isLoading }) {
  if (isLoading) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 animate-pulse"
        data-testid="cost-daily-chart-loading"
      />
    );
  }
  const series = (data?.daily_series ?? []).map((d) => ({
    date: d.date.slice(5),  // MM-DD
    cost: d.cost_pence / 100,
  }));
  if (series.length === 0 || series.every((p) => p.cost === 0)) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 flex items-center justify-center text-sm text-slate-500"
        data-testid="cost-daily-chart-empty"
      >
        No AI capture spend in this period.
      </div>
    );
  }
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid="cost-daily-chart"
    >
      <div className="mb-3 text-sm font-medium text-slate-700">Daily cost</div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmtGBP(v)} />
            <Tooltip
              formatter={(value) => [fmtGBP(value), 'Cost']}
              labelFormatter={(label) => `Date: ${label}`}
            />
            <Line
              type="monotone"
              dataKey="cost"
              stroke="#0F6A7A"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
