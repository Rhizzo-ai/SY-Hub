/**
 * SupplierList tests — Chat 40 §R5 #1.
 *
 * Covers:
 *  - Rows render
 *  - Type filter sends `supplier_type`
 *  - Archived toggle sends `include_archived`
 *  - Search sends `q`
 *  - CIS badge only on subcontractor rows
 *  - Unverified cue + header summary for null/Unverified/Unmatched
 *  - Forbidden state without `suppliers.view`
 */
let mockCurrentSearch = '';

jest.mock('@/hooks/purchaseOrders', () => ({
  useSuppliers: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useSearchParams: () => {
      const params = new URLSearchParams(mockCurrentSearch);
      return [params, (next) => { mockCurrentSearch = next.toString(); }];
    },
  };
});

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SupplierList from '@/pages/SupplierList';

const { useSuppliers } = jest.requireMock('@/hooks/purchaseOrders');
const { useAuth } = jest.requireMock('@/context/AuthContext');

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

function setData(items) {
  useSuppliers.mockReturnValue({
    data: { items, total: items.length, limit: 50, offset: 0 },
    isLoading: false,
    isError: false,
  });
}

function renderAt(search = '') {
  mockCurrentSearch = search.startsWith('?') ? search.slice(1) : search;
  return render(
    <MemoryRouter>
      <SupplierList />
    </MemoryRouter>
  );
}

beforeEach(() => {
  useSuppliers.mockReset();
  useAuth.mockReset();
  setMe(['suppliers.view', 'suppliers.create']);
  mockCurrentSearch = '';
});

// Reads the params from the most recent useSuppliers call.
function lastParams() {
  return useSuppliers.mock.calls.at(-1)[0].params;
}

describe('SupplierList', () => {
  test('forbidden without suppliers.view', () => {
    setMe([]);
    setData([]);
    renderAt();
    expect(screen.getByTestId('supplier-list-forbidden')).toBeInTheDocument();
  });

  test('renders rows + New btn when permitted', () => {
    setData([
      { id: 'S1', name: 'ACME', supplier_type: 'Supplier', cis_status: 'gross',
        current_cis_status: null, is_archived: false, default_vat_rate: '20.0' },
    ]);
    renderAt();
    expect(screen.getByTestId('supplier-row-S1')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-new-btn')).toBeInTheDocument();
  });

  test('type filter sends supplier_type param', () => {
    setData([]);
    renderAt();
    fireEvent.change(screen.getByTestId('supplier-list-type-filter'), {
      target: { value: 'Subcontractor' },
    });
    expect(lastParams().supplier_type).toBe('Subcontractor');
  });

  test('type=All omits supplier_type', () => {
    setData([]);
    renderAt();
    // Initial render with no ?type= → default 'All' → supplier_type undefined.
    expect(useSuppliers.mock.calls[0][0].params.supplier_type).toBeUndefined();
  });

  test('archived toggle sends include_archived', () => {
    setData([]);
    renderAt();
    fireEvent.click(screen.getByTestId('supplier-list-archived-toggle'));
    expect(lastParams().include_archived).toBe(true);
  });

  test('search sends q', () => {
    setData([]);
    renderAt();
    fireEvent.change(screen.getByTestId('supplier-list-search'), {
      target: { value: 'acme' },
    });
    expect(lastParams().q).toBe('acme');
  });

  test('CIS badge shown for subcontractor rows only', () => {
    setData([
      { id: 'S1', name: 'Acme', supplier_type: 'Supplier',
        current_cis_status: null, is_archived: false },
      { id: 'S2', name: 'Subby', supplier_type: 'Subcontractor',
        current_cis_status: 'Gross', is_archived: false },
    ]);
    renderAt();
    expect(screen.queryByTestId('supplier-row-cis-S1')).toBeNull();
    expect(screen.getByTestId('supplier-row-cis-S2')).toBeInTheDocument();
  });

  test('unverified cue + header summary for Subcontractor with null/Unverified/Unmatched', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Subcontractor', current_cis_status: null, is_archived: false },
      { id: 'S2', name: 'B', supplier_type: 'Subcontractor', current_cis_status: 'Unverified', is_archived: false },
      { id: 'S3', name: 'C', supplier_type: 'Subcontractor', current_cis_status: 'Unmatched', is_archived: false },
      { id: 'S4', name: 'D', supplier_type: 'Subcontractor', current_cis_status: 'Gross', is_archived: false },
    ]);
    renderAt('?type=Subcontractor');
    expect(screen.getByTestId('supplier-row-unverified-S1')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-row-unverified-S2')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-row-unverified-S3')).toBeInTheDocument();
    expect(screen.queryByTestId('supplier-row-unverified-S4')).toBeNull();
    expect(screen.getByTestId('supplier-list-unverified-summary'))
      .toHaveTextContent('3 subcontractors need CIS verification');
  });

  test('no unverified cue when Type filter is not Subcontractor', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Subcontractor', current_cis_status: null, is_archived: false },
    ]);
    renderAt(); // defaults to All
    expect(screen.queryByTestId('supplier-list-unverified-summary')).toBeNull();
    expect(screen.queryByTestId('supplier-row-unverified-S1')).toBeNull();
  });

  test('seeds Type filter from ?type=Subcontractor query string', () => {
    setData([]);
    renderAt('?type=Subcontractor');
    expect(useSuppliers.mock.calls[0][0].params.supplier_type).toBe('Subcontractor');
    const sel = screen.getByTestId('supplier-list-type-filter');
    expect(sel.value).toBe('Subcontractor');
  });

  test('archived rows show "Archived" chip', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Supplier', is_archived: true },
    ]);
    renderAt();
    expect(screen.getByTestId('supplier-row-archived-S1')).toHaveTextContent('Archived');
  });

  test('empty state renders when no rows', () => {
    setData([]);
    renderAt();
    expect(screen.getByTestId('supplier-list-empty')).toBeInTheDocument();
  });
});
