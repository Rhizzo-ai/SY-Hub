// frontend/src/components/ai-capture/__tests__/CostDailyChart.test.jsx — Chat 20 §R5.6
//
// E12 cross-domain test stubbing: recharts is replaced with a minimal
// stub via React.createElement inside the hoisted jest.mock factory.
// This is REQUIRED — recharts uses ResizeObserver / SVG which jsdom
// doesn't provide, and bypassing it keeps the test fast + deterministic.
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

import { render, screen } from '@testing-library/react';
import { CostDailyChart } from '@/components/ai-capture/CostDailyChart';

describe('CostDailyChart', () => {
  test('renders loading skeleton when isLoading', () => {
    render(<CostDailyChart data={undefined} isLoading={true} />);
    expect(screen.getByTestId('cost-daily-chart-loading')).toBeInTheDocument();
  });

  test('renders empty state when daily_series is empty', () => {
    render(<CostDailyChart data={{ daily_series: [] }} isLoading={false} />);
    expect(screen.getByTestId('cost-daily-chart-empty')).toBeInTheDocument();
  });

  test('renders empty state when daily_series is all zeros', () => {
    const data = {
      daily_series: [
        { date: '2026-05-01', cost_pence: 0, job_count: 0 },
        { date: '2026-05-02', cost_pence: 0, job_count: 0 },
      ],
    };
    render(<CostDailyChart data={data} isLoading={false} />);
    expect(screen.getByTestId('cost-daily-chart-empty')).toBeInTheDocument();
  });

  test('renders chart container with non-zero data', () => {
    const data = {
      daily_series: [
        { date: '2026-05-01', cost_pence: 100, job_count: 1 },
        { date: '2026-05-02', cost_pence: 200, job_count: 2 },
      ],
    };
    const { container } = render(
      <CostDailyChart data={data} isLoading={false} />
    );
    expect(screen.getByTestId('cost-daily-chart')).toBeInTheDocument();
    expect(
      container.querySelector('[data-recharts-stub="LineChart"]')
    ).toBeInTheDocument();
  });
});
