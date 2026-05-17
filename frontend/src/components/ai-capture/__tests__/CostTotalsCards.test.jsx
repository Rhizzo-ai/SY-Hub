// frontend/src/components/ai-capture/__tests__/CostTotalsCards.test.jsx — Chat 20 §R5.5
import { render, screen } from '@testing-library/react';
import { CostTotalsCards } from '@/components/ai-capture/CostTotalsCards';

const sample = {
  period: { from_date: '2026-05-01', to_date: '2026-05-30', days: 30 },
  totals: {
    total_jobs: 12,
    total_cost_pence: 12345,  // £123.45
    avg_cost_pence: 1029,     // £10.29
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
  },
};

describe('CostTotalsCards', () => {
  test('renders skeletons when isLoading', () => {
    render(<CostTotalsCards data={undefined} isLoading={true} />);
    expect(screen.getByTestId('cost-total-spent-skeleton')).toBeInTheDocument();
    expect(screen.getByTestId('cost-total-jobs-skeleton')).toBeInTheDocument();
  });

  test('renders fmtGBP-formatted total_cost_pence ÷ 100', () => {
    render(<CostTotalsCards data={sample} isLoading={false} quickPick="30d" />);
    expect(screen.getByTestId('cost-total-spent')).toHaveTextContent(/\u00a3123\.45/);
  });

  test('renders job count as plain integer', () => {
    render(<CostTotalsCards data={sample} isLoading={false} quickPick="30d" />);
    expect(screen.getByTestId('cost-total-jobs')).toHaveTextContent('12');
  });

  test('renders average per job', () => {
    render(<CostTotalsCards data={sample} isLoading={false} quickPick="30d" />);
    expect(screen.getByTestId('cost-avg-per-job')).toHaveTextContent(/\u00a310\.29/);
  });

  test('renders "Last 30 days" when quickPick is 30d', () => {
    render(<CostTotalsCards data={sample} isLoading={false} quickPick="30d" />);
    expect(screen.getByTestId('cost-period')).toHaveTextContent('Last 30 days');
  });

  test('renders "All time" when quickPick is all (not day count)', () => {
    render(<CostTotalsCards data={sample} isLoading={false} quickPick="all" />);
    expect(screen.getByTestId('cost-period')).toHaveTextContent('All time');
  });

  test('shows zeros when totals are zero', () => {
    const empty = {
      ...sample,
      totals: {
        total_jobs: 0, total_cost_pence: 0, avg_cost_pence: 0,
        total_prompt_tokens: 0, total_completion_tokens: 0,
      },
    };
    render(<CostTotalsCards data={empty} isLoading={false} quickPick="7d" />);
    expect(screen.getByTestId('cost-total-jobs')).toHaveTextContent('0');
    expect(screen.getByTestId('cost-total-spent')).toHaveTextContent(/\u00a30\.00/);
  });
});
