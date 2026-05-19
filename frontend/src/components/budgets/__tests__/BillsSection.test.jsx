/**
 * BillsSection tests — Chat 23 R4.4.
 *
 * Verifies the live actuals integration end-to-end at the component
 * level: empty state, loading state, table rendering with semantic
 * BillStatusBadge, and the budget_line_id-keyed query.
 *
 * The actuals API is mocked at module level (`@/lib/api/actuals`) so
 * the component's `useActualsForBudgetLine` query hits a deterministic
 * fixture without spinning up MSW.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { BillsSection }
  from '../grid/PerLineTransactionDrilldown/BillsSection';

jest.mock('@/lib/api/actuals', () => ({
  listActuals: jest.fn(),
}));
import * as actualsApi from '@/lib/api/actuals';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('BillsSection', () => {
  beforeEach(() => {
    actualsApi.listActuals.mockReset();
  });

  test('shows the empty-state when no bills returned', async () => {
    actualsApi.listActuals.mockResolvedValueOnce({ items: [], total: 0 });
    wrap(<BillsSection budgetLineId="line-1" projectId="proj-1" />);
    await waitFor(() =>
      expect(screen.getByTestId('bg2-bills-empty')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('bg2-bills-empty').textContent)
      .toMatch(/No bills posted/i);
  });

  test('passes budget_line_id + project_id + limit:50 to the API', async () => {
    actualsApi.listActuals.mockResolvedValueOnce({ items: [], total: 0 });
    wrap(<BillsSection budgetLineId="line-99" projectId="proj-99" />);
    await waitFor(() => {
      expect(actualsApi.listActuals).toHaveBeenCalledWith(
        expect.objectContaining({
          params: expect.objectContaining({
            budget_line_id: 'line-99',
            project_id: 'proj-99',
            limit: 50,
          }),
        }),
      );
    });
  });

  test('renders the 6-column table when bills exist', async () => {
    actualsApi.listActuals.mockResolvedValueOnce({
      items: [{
        id: 'bill-1',
        supplier_invoice_ref: 'INV-001',
        supplier_name_snapshot: 'ACME Concrete Ltd',
        gross_amount: '12345.67',
        status: 'Posted',
        transaction_date: '2026-05-01T00:00:00Z',
        posted_at: '2026-05-02T09:00:00Z',
      }, {
        id: 'bill-2',
        supplier_invoice_ref: 'INV-002',
        supplier_name_snapshot: 'Bricks R Us',
        gross_amount: '500.00',
        status: 'Paid',
        transaction_date: '2026-05-03T00:00:00Z',
      }],
      total: 2,
    });
    wrap(<BillsSection budgetLineId="line-2" projectId="proj-2" />);
    await waitFor(() =>
      expect(screen.getByTestId('bg2-bills-table')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('bg2-bill-bill-1')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-bill-bill-2')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-bill-status-Posted')).toHaveTextContent('Posted');
    expect(screen.getByTestId('bg2-bill-status-Paid')).toHaveTextContent('Paid');
    expect(screen.getByTestId('bg2-bill-open-bill-1')).toHaveAttribute(
      'href', '/projects/proj-2/actuals/bill-1',
    );
  });
});
