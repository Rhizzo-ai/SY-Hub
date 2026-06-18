/**
 * POSubmitErrorPanel tests — B107 §8.3.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { POSubmitErrorPanel } from '@/components/po/POSubmitErrorPanel';

function renderPanel(props) {
  return render(
    <MemoryRouter>
      <POSubmitErrorPanel {...props} />
    </MemoryRouter>,
  );
}

describe('POSubmitErrorPanel (B107 §6)', () => {
  test('unbudgeted_ack_required names the blocking cost code + amount', () => {
    renderPanel({
      error: { detail: {
        type: 'unbudgeted_ack_required',
        lines: [{ budget_line_id: 'b1', cost_code: '1500', committed_not_invoiced: '1200.00', floor: '1000' }],
      } },
      canClear: true,
      budgetHref: '/projects/p1/budgets',
    });
    const panel = screen.getByTestId('po-error-ack-required');
    expect(panel).toHaveTextContent('1500');
    expect(panel).toHaveTextContent('director sign-off');
    // canClear + budgetHref → the budget link renders.
    expect(screen.getByTestId('po-error-ack-budget-link')).toBeInTheDocument();
  });

  test('po_line_incomplete renders the 1-based line numbers', () => {
    renderPanel({ error: { detail: { type: 'po_line_incomplete', incomplete_line_numbers: [2, 4] } } });
    expect(screen.getByTestId('po-error-line-incomplete')).toHaveTextContent('2, 4');
  });

  test('budget_line_race shows Retry and clicking fires onRetry exactly once', () => {
    const onRetry = jest.fn();
    renderPanel({ error: { detail: { type: 'budget_line_race', cost_code_id: 'cc' } }, onRetry });
    fireEvent.click(screen.getByTestId('po-error-race-retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  test('renders nothing when there is no structured detail', () => {
    const { container } = renderPanel({ error: null });
    expect(container).toBeEmptyDOMElement();
  });
});
