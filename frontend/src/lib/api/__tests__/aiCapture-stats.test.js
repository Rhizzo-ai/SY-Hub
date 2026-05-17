// frontend/src/lib/api/__tests__/aiCapture-stats.test.js — Chat 20 §R5.3
import { getCaptureCostStats } from '@/lib/api/aiCapture';

jest.mock('@/lib/api', () => ({
  api: { get: jest.fn() },
}));
const { api } = jest.requireMock('@/lib/api');

const sample = {
  period: { from_date: '2026-05-01', to_date: '2026-05-30', days: 30 },
  totals: {
    total_jobs: 1, total_cost_pence: 100, avg_cost_pence: 100,
    total_prompt_tokens: 5, total_completion_tokens: 2,
  },
  daily_series: [{ date: '2026-05-01', cost_pence: 100, job_count: 1 }],
  by_status: [
    { status: 'Completed', cost_pence: 100, job_count: 1 },
    { status: 'Failed', cost_pence: 0, job_count: 0 },
    { status: 'Discarded', cost_pence: 0, job_count: 0 },
  ],
};

beforeEach(() => { api.get.mockReset(); });

describe('getCaptureCostStats', () => {
  test('GETs /v1/ai-capture-jobs/stats with date params', async () => {
    api.get.mockResolvedValue({ data: sample });
    await getCaptureCostStats({ fromDate: '2026-05-01', toDate: '2026-05-30' });
    expect(api.get).toHaveBeenCalledWith('/v1/ai-capture-jobs/stats', {
      params: { from_date: '2026-05-01', to_date: '2026-05-30' },
      signal: undefined,
    });
  });

  test('omits params when no dates provided', async () => {
    api.get.mockResolvedValue({ data: sample });
    await getCaptureCostStats();
    expect(api.get).toHaveBeenCalledWith('/v1/ai-capture-jobs/stats', {
      params: {}, signal: undefined,
    });
  });

  test('parses + returns response body', async () => {
    api.get.mockResolvedValue({ data: sample });
    const result = await getCaptureCostStats({ fromDate: '2026-05-01' });
    expect(result.totals.total_jobs).toBe(1);
    expect(result.daily_series).toHaveLength(1);
  });

  test('throws when response body fails schema', async () => {
    api.get.mockResolvedValue({ data: { totals: { total_jobs: 'bad' } } });
    await expect(
      getCaptureCostStats({ fromDate: '2026-05-01' })
    ).rejects.toThrow();
  });
});
