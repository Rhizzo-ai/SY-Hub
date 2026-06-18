/**
 * ClearUnbudgetedDialog tests — B107 §8.4 (confirm fires the POST; the
 * hook — which invalidates the budget query — is mocked).
 */
jest.mock('@/hooks/budgets', () => ({ useClearUnbudgeted: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ClearUnbudgetedDialog } from '@/components/budgets/grid/ClearUnbudgetedDialog';

const { useClearUnbudgeted } = jest.requireMock('@/hooks/budgets');

describe('ClearUnbudgetedDialog (B107 §4.2)', () => {
  let mutateAsync;
  beforeEach(() => {
    mutateAsync = jest.fn().mockResolvedValue({});
    useClearUnbudgeted.mockReset().mockReturnValue({ mutateAsync, isPending: false });
  });

  test('confirm fires the clear POST with the line id', async () => {
    render(<ClearUnbudgetedDialog
      open
      onOpenChange={() => {}}
      line={{ id: 'line-1', committed_not_invoiced: '1500' }}
      budgetId="bud-1"
      codeLabel="1500"
    />);
    fireEvent.click(screen.getByTestId('clear-unbudgeted-confirm'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith('line-1'));
  });

  test('shows the cost code + committed amount', () => {
    render(<ClearUnbudgetedDialog
      open
      onOpenChange={() => {}}
      line={{ id: 'line-1', committed_not_invoiced: '1500' }}
      budgetId="bud-1"
      codeLabel="1500"
    />);
    expect(screen.getByTestId('clear-unbudgeted-code')).toHaveTextContent('1500');
    expect(screen.getByTestId('clear-unbudgeted-committed')).toHaveTextContent('1,500');
  });
});
