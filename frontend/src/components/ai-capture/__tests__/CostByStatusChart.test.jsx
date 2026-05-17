// frontend/src/components/ai-capture/__tests__/CostByStatusChart.test.jsx — Chat 20 §R5.7
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
import { CostByStatusChart } from '@/components/ai-capture/CostByStatusChart';

describe('CostByStatusChart', () => {
  test('renders loading skeleton when isLoading', () => {
    render(<CostByStatusChart data={undefined} isLoading={true} />);
    expect(
      screen.getByTestId('cost-by-status-chart-loading')
    ).toBeInTheDocument();
  });

  test('renders empty state when all buckets are zero', () => {
    const data = {
      by_status: [
        { status: 'Completed', cost_pence: 0, job_count: 0 },
        { status: 'Failed', cost_pence: 0, job_count: 0 },
        { status: 'Discarded', cost_pence: 0, job_count: 0 },
      ],
    };
    render(<CostByStatusChart data={data} isLoading={false} />);
    expect(
      screen.getByTestId('cost-by-status-chart-empty')
    ).toBeInTheDocument();
  });

  test('renders chart container when any bucket non-zero', () => {
    const data = {
      by_status: [
        { status: 'Completed', cost_pence: 500, job_count: 5 },
        { status: 'Failed', cost_pence: 100, job_count: 1 },
        { status: 'Discarded', cost_pence: 0, job_count: 0 },
      ],
    };
    const { container } = render(
      <CostByStatusChart data={data} isLoading={false} />
    );
    expect(screen.getByTestId('cost-by-status-chart')).toBeInTheDocument();
    expect(
      container.querySelector('[data-recharts-stub="BarChart"]')
    ).toBeInTheDocument();
  });
});
