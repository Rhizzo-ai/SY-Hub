// frontend/src/components/ai-capture/CostByStatusChart.jsx — Chat 20 §R3.5
//
// Stacked / grouped bar by status. Shows where the spend is going —
// useful for surfacing waste (lots of £ on Failed/Discarded = AI is
// missing).
import {
  ResponsiveContainer, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts';
import { fmtGBP } from '@/lib/format';

const STATUS_COLOURS = {
  Completed: '#0F6A7A',  // sy-teal
  Failed: '#f59e0b',     // amber-500
  Discarded: '#94a3b8',  // slate-400
};

export function CostByStatusChart({ data, isLoading }) {
  if (isLoading) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 animate-pulse"
        data-testid="cost-by-status-chart-loading"
      />
    );
  }
  const rows = (data?.by_status ?? []).map((r) => ({
    status: r.status,
    cost: r.cost_pence / 100,
    job_count: r.job_count,
  }));
  if (rows.length === 0 || rows.every((r) => r.cost === 0 && r.job_count === 0)) {
    return (
      <div
        className="h-72 rounded-lg border border-slate-200 bg-white p-4 flex items-center justify-center text-sm text-slate-500"
        data-testid="cost-by-status-chart-empty"
      >
        No completed, failed, or discarded jobs in this period.
      </div>
    );
  }
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid="cost-by-status-chart"
    >
      <div className="mb-3 text-sm font-medium text-slate-700">Cost by outcome</div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="status" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmtGBP(v)} />
            <Tooltip
              formatter={(value, _name, props) => [
                `${fmtGBP(value)} (${props.payload.job_count} jobs)`,
                'Cost',
              ]}
            />
            <Bar dataKey="cost">
              {rows.map((r) => (
                <Cell key={r.status} fill={STATUS_COLOURS[r.status]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
