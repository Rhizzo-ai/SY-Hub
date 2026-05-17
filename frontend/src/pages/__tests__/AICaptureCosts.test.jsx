// frontend/src/pages/__tests__/AICaptureCosts.test.jsx — Chat 20 §R5.8
//
// I13 hooks-above-perm-gate verification + perm gate + happy path.

// Recharts stub (E12).
jest.mock('recharts', () => {
  const React = require('react');
  const Stub = (name) => ({ children, ...props }) =>
    React.createElement(
      'div',
      { 'data-recharts-stub': name, ...props },
      children
    );
  return {
    ResponsiveContainer: Stub('ResponsiveContainer'),
    LineChart: Stub('LineChart'),
    Line: Stub('Line'),
    BarChart: Stub('BarChart'),
    Bar: Stub('Bar'),
    Cell: Stub('Cell'),
    XAxis: Stub('XAxis'),
    YAxis: Stub('YAxis'),
    Tooltip: Stub('Tooltip'),
    CartesianGrid: Stub('CartesianGrid'),
  };
});

jest.mock('@/lib/api', () => ({
  api: { get: jest.fn() },
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AICaptureCosts from '@/pages/AICaptureCosts';

const { api } = jest.requireMock('@/lib/api');
const { useAuth } = jest.requireMock('@/context/AuthContext');

const STATS = {
  period: { from_date: '2026-04-30', to_date: '2026-05-29', days: 30 },
  totals: {
    total_jobs: 5,
    total_cost_pence: 500,
    avg_cost_pence: 100,
    total_prompt_tokens: 200,
    total_completion_tokens: 80,
  },
  daily_series: [
    { date: '2026-05-29', cost_pence: 500, job_count: 5 },
  ],
  by_status: [
    { status: 'Completed', cost_pence: 500, job_count: 5 },
    { status: 'Failed', cost_pence: 0, job_count: 0 },
    { status: 'Discarded', cost_pence: 0, job_count: 0 },
  ],
};

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  api.get.mockReset();
  useAuth.mockReset();
});

describe('AICaptureCosts page', () => {
  test('renders no-perm message when user lacks ai_capture.view_costs', () => {
    useAuth.mockReturnValue({ me: { permissions: ['actuals.admin'] } });
    wrap(<AICaptureCosts />);
    expect(screen.getByTestId('cost-no-perm')).toBeInTheDocument();
    // Query must NOT be made when perm-gated out (hooks-above-gate
    // pattern uses `enabled` to short-circuit network).
    expect(api.get).not.toHaveBeenCalled();
  });

  test('renders dashboard skeleton then totals when api resolves', async () => {
    useAuth.mockReturnValue({
      me: { permissions: ['ai_capture.view_costs'] },
    });
    api.get.mockResolvedValue({ data: STATS });
    wrap(<AICaptureCosts />);
    expect(screen.getByTestId('ai-capture-costs-page')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('cost-total-spent')).toHaveTextContent(
        /\u00a35\.00/
      );
    });
    expect(screen.getByTestId('cost-total-jobs')).toHaveTextContent('5');
  });

  test('renders error message when API fails', async () => {
    useAuth.mockReturnValue({
      me: { permissions: ['ai_capture.view_costs'] },
    });
    api.get.mockRejectedValue({
      response: { data: { detail: { message: 'Boom' } } },
    });
    wrap(<AICaptureCosts />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-error')).toHaveTextContent('Boom');
    });
  });
});
