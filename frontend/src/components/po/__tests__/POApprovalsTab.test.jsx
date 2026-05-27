/**
 * <POApprovalsTab/> tests — R7 Batch 2 §R7.5.
 *
 * Per-project approvals dashboard. Data source is
 * `useProjectPOs(projectId, { params: { status: 'pending_approval' } })`,
 * mocked here to drive matrix behaviour. Includes the client-side
 * filter fallback assertion (rows with non-pending status are
 * dropped — defensive against backends that ignore the param).
 */
import { screen } from '@testing-library/react';
import POApprovalsTab from '../POApprovalsTab';
import { renderWithProviders } from '../../../test/renderWithProviders';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/purchaseOrders', () => ({
  useProjectPOs: jest.fn(),
}));
jest.mock('react-router-dom', () => {
  const real = jest.requireActual('react-router-dom');
  return { ...real, useParams: () => ({ id: 'project-1' }) };
});

const { useAuth } = require('../../../context/AuthContext');
const { useProjectPOs } = require('../../../hooks/purchaseOrders');

const ME_APPROVER = {
  permissions: ['pos.view', 'pos.approve', 'pos.view_sensitive'],
};
const ME_READONLY = { permissions: ['pos.view'] };
const ME_NO_VIEW  = { permissions: [] };

function makeRow({ id, status = 'pending_approval', po_number = `PO-${id}` }) {
  return {
    id, status, po_number, supplier_name: `Supplier ${id}`,
    gross_total: '1000.00',
  };
}


describe('<POApprovalsTab/> — R7.5 per-project approvals dashboard', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test('forbidden persona sees the perm-gated copy', () => {
    useAuth.mockReturnValue({ user: ME_NO_VIEW });
    useProjectPOs.mockReturnValue({ data: { items: [] }, isLoading: false });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-forbidden')).toBeInTheDocument();
  });

  test('renders only pending_approval rows (client-side filter fallback)', () => {
    useAuth.mockReturnValue({ user: ME_APPROVER });
    useProjectPOs.mockReturnValue({
      data: {
        items: [
          makeRow({ id: 'a' }),
          makeRow({ id: 'b', status: 'issued' }),       // dropped
          makeRow({ id: 'c' }),
          makeRow({ id: 'd', status: 'draft' }),        // dropped
        ],
      },
      isLoading: false,
    });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-tab')).toBeInTheDocument();
    expect(screen.getByTestId('po-approvals-row-a')).toBeInTheDocument();
    expect(screen.getByTestId('po-approvals-row-c')).toBeInTheDocument();
    expect(screen.queryByTestId('po-approvals-row-b')).not.toBeInTheDocument();
    expect(screen.queryByTestId('po-approvals-row-d')).not.toBeInTheDocument();
  });

  test('empty list renders the "no POs awaiting approval" state', () => {
    useAuth.mockReturnValue({ user: ME_APPROVER });
    useProjectPOs.mockReturnValue({ data: { items: [] }, isLoading: false });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-empty')).toBeInTheDocument();
  });

  test('approver persona — Review affordance on each row', () => {
    useAuth.mockReturnValue({ user: ME_APPROVER });
    useProjectPOs.mockReturnValue({
      data: { items: [makeRow({ id: 'a' })] },
      isLoading: false,
    });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-row-a-action')).toBeInTheDocument();
    expect(screen.queryByTestId('po-approvals-row-a-readonly')).not.toBeInTheDocument();
  });

  test('read-only persona — sees list but no Review affordance', () => {
    useAuth.mockReturnValue({ user: ME_READONLY });
    useProjectPOs.mockReturnValue({
      data: { items: [makeRow({ id: 'a' })] },
      isLoading: false,
    });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-row-a')).toBeInTheDocument();
    expect(screen.queryByTestId('po-approvals-row-a-action')).not.toBeInTheDocument();
    expect(screen.getByTestId('po-approvals-row-a-readonly')).toBeInTheDocument();
  });

  test('loading state renders po-approvals-loading', () => {
    useAuth.mockReturnValue({ user: ME_APPROVER });
    useProjectPOs.mockReturnValue({ isLoading: true });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-loading')).toBeInTheDocument();
  });

  test('error state renders po-approvals-error', () => {
    useAuth.mockReturnValue({ user: ME_APPROVER });
    useProjectPOs.mockReturnValue({ isError: true });
    renderWithProviders(<POApprovalsTab />);
    expect(screen.getByTestId('po-approvals-error')).toBeInTheDocument();
  });
});
