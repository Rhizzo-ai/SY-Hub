/**
 * SupplierList tests — Chat 40 §R5 #1 + Chat 41 §R8 (Build Pack
 *   2.7-FE-revision).
 *
 * Covers:
 *  - Rows render
 *  - 4-way type filter (Contractor / Supplier / Consultant / Other)
 *  - `?type=Contractor` seed; stale `?type=Subcontractor` → 'All'
 *  - Default-VAT column is gone
 *  - Trade column shown by default
 *  - Column-picker toggles a column on / off (header presence)
 *  - Empty-row colSpan matches CORE + visible-optional count
 *  - CIS badge + unverified cue gate on Contractor (was Subcontractor)
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

function lastParams() {
  return useSuppliers.mock.calls.at(-1)[0].params;
}

describe('SupplierList — base behaviour', () => {
  test('forbidden without suppliers.view', () => {
    setMe([]);
    setData([]);
    renderAt();
    expect(screen.getByTestId('supplier-list-forbidden')).toBeInTheDocument();
  });

  test('renders rows + New btn when permitted', () => {
    setData([
      { id: 'S1', name: 'ACME', supplier_type: 'Supplier', cis_status: 'gross',
        current_cis_status: null, is_archived: false, trade: 'Groundworks' },
    ]);
    renderAt();
    expect(screen.getByTestId('supplier-row-S1')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-new-btn')).toBeInTheDocument();
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

describe('SupplierList — 4-way type filter (Chat 41 §R5.1/§R5.2)', () => {
  test('Type select exposes the 4 contact-book values + All', () => {
    setData([]);
    renderAt();
    const sel = screen.getByTestId('supplier-list-type-filter');
    const values = Array.from(sel.querySelectorAll('option')).map((o) => o.value);
    expect(values).toEqual(['All', 'Contractor', 'Supplier', 'Consultant', 'Other']);
  });

  test('Subcontractor is not an option', () => {
    setData([]);
    renderAt();
    const sel = screen.getByTestId('supplier-list-type-filter');
    const values = Array.from(sel.querySelectorAll('option')).map((o) => o.value);
    expect(values).not.toContain('Subcontractor');
  });

  test('type=All omits supplier_type', () => {
    setData([]);
    renderAt();
    expect(useSuppliers.mock.calls[0][0].params.supplier_type).toBeUndefined();
  });

  test('Contractor filter sends supplier_type=Contractor', () => {
    setData([]);
    renderAt();
    fireEvent.change(screen.getByTestId('supplier-list-type-filter'), {
      target: { value: 'Contractor' },
    });
    expect(lastParams().supplier_type).toBe('Contractor');
  });

  test('?type=Contractor seeds the filter', () => {
    setData([]);
    renderAt('?type=Contractor');
    expect(useSuppliers.mock.calls[0][0].params.supplier_type).toBe('Contractor');
    expect(screen.getByTestId('supplier-list-type-filter').value).toBe('Contractor');
  });

  test('stale ?type=Subcontractor bookmark falls back to All', () => {
    setData([]);
    renderAt('?type=Subcontractor');
    expect(useSuppliers.mock.calls[0][0].params.supplier_type).toBeUndefined();
    expect(screen.getByTestId('supplier-list-type-filter').value).toBe('All');
  });

  test('heading uses the selected TYPE_OPTIONS label', () => {
    setData([]);
    renderAt('?type=Contractor');
    expect(screen.getByTestId('supplier-list')).toHaveTextContent('Contractors');
  });
});

describe('SupplierList — CIS gating on Contractor (Chat 41 §R5.3)', () => {
  test('CIS badge shown for Contractor rows only (visible cis column)', () => {
    setData([
      { id: 'S1', name: 'Acme', supplier_type: 'Supplier',
        current_cis_status: null, is_archived: false },
      { id: 'S2', name: 'Subby', supplier_type: 'Contractor',
        current_cis_status: 'Gross', is_archived: false },
    ]);
    renderAt();
    expect(screen.queryByTestId('supplier-row-cis-S1')).toBeNull();
    expect(screen.getByTestId('supplier-row-cis-S2')).toBeInTheDocument();
  });

  test('unverified cue + summary fires on Contractor view for null / Unverified / Unmatched', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Contractor', current_cis_status: null, is_archived: false },
      { id: 'S2', name: 'B', supplier_type: 'Contractor', current_cis_status: 'Unverified', is_archived: false },
      { id: 'S3', name: 'C', supplier_type: 'Contractor', current_cis_status: 'Unmatched', is_archived: false },
      { id: 'S4', name: 'D', supplier_type: 'Contractor', current_cis_status: 'Gross', is_archived: false },
    ]);
    renderAt('?type=Contractor');
    expect(screen.getByTestId('supplier-row-unverified-S1')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-row-unverified-S2')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-row-unverified-S3')).toBeInTheDocument();
    expect(screen.queryByTestId('supplier-row-unverified-S4')).toBeNull();
    expect(screen.getByTestId('supplier-list-unverified-summary'))
      .toHaveTextContent('3 contractors need CIS verification');
  });

  test('no unverified cue on the All / mixed view', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Contractor', current_cis_status: null, is_archived: false },
    ]);
    renderAt();
    expect(screen.queryByTestId('supplier-list-unverified-summary')).toBeNull();
    expect(screen.queryByTestId('supplier-row-unverified-S1')).toBeNull();
  });
});

describe('SupplierList — columns + column-picker (Chat 41 §R5.4 / §R6)', () => {
  test('default-VAT column is gone (rev-A dropped the field)', () => {
    setData([{ id: 'S1', name: 'A', supplier_type: 'Supplier', is_archived: false }]);
    renderAt();
    // No header with the old label, no per-row cell, no col-testid.
    expect(screen.queryByTestId('supplier-list-col-vat-rate')).toBeNull();
    expect(screen.queryByText(/Default VAT/i)).toBeNull();
  });

  test('Trade column shows by default (default-on)', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Supplier', trade: 'Groundworks', is_archived: false },
    ]);
    renderAt();
    expect(screen.getByTestId('supplier-list-col-trade')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-row-trade-S1')).toHaveTextContent('Groundworks');
  });

  test('Trade column hides when toggled off', () => {
    setData([{ id: 'S1', name: 'A', supplier_type: 'Supplier', is_archived: false }]);
    renderAt();
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    fireEvent.click(screen.getByTestId('column-toggle-trade'));
    expect(screen.queryByTestId('supplier-list-col-trade')).toBeNull();
  });

  test('Email column appears when toggled on (off by default)', () => {
    setData([
      { id: 'S1', name: 'A', supplier_type: 'Supplier',
        contact_email: 'a@b.test', is_archived: false },
    ]);
    renderAt();
    expect(screen.queryByTestId('supplier-list-col-email')).toBeNull();
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    fireEvent.click(screen.getByTestId('column-toggle-email'));
    expect(screen.getByTestId('supplier-list-col-email')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-row-email-S1')).toHaveTextContent('a@b.test');
  });

  test('empty-state colSpan matches CORE + visible-optional column count', () => {
    setData([]);
    renderAt();
    // Defaults: 3 core + 2 optional-on (trade, cis) = 5.
    const cell = screen.getByTestId('supplier-list-empty');
    expect(cell.getAttribute('colspan')).toBe('5');

    // Toggle Email on → 6.
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    fireEvent.click(screen.getByTestId('column-toggle-email'));
    expect(screen.getByTestId('supplier-list-empty').getAttribute('colspan')).toBe('6');
  });

  test('core columns Name / Type / Status always render', () => {
    setData([{ id: 'S1', name: 'A', supplier_type: 'Supplier', is_archived: false }]);
    renderAt();
    expect(screen.getByTestId('supplier-list-col-name')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-col-type')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-col-status')).toBeInTheDocument();
  });
});

describe('SupplierList — click-to-sort (Chat 41 §R-eyeball-Step2B Part 2)', () => {
  // Row order is what we read; the visible <Link> wraps the name so we
  // can read its text directly from the row testid.
  function nameOrder() {
    const tbody = screen.getByTestId('supplier-list-table').querySelector('tbody');
    return Array.from(tbody.querySelectorAll('tr'))
      .map((r) => (r.getAttribute('data-testid') ?? '').replace('supplier-row-', ''));
  }

  test('Name column: first click asc, second desc, indicator reflects state', () => {
    setData([
      { id: 'CHA', name: 'Charlie', supplier_type: 'Supplier' },
      { id: 'ALP', name: 'Alpha',   supplier_type: 'Supplier' },
      { id: 'BRA', name: 'Bravo',   supplier_type: 'Supplier' },
    ]);
    renderAt();

    // unsorted at mount.
    expect(screen.getByTestId('supplier-list-sort-name-none')).toBeInTheDocument();

    // First click → ascending.
    fireEvent.click(screen.getByTestId('supplier-list-sort-name'));
    expect(nameOrder()).toEqual(['ALP', 'BRA', 'CHA']);
    expect(screen.getByTestId('supplier-list-sort-name-asc')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-col-name'))
      .toHaveAttribute('aria-sort', 'ascending');

    // Second click → descending.
    fireEvent.click(screen.getByTestId('supplier-list-sort-name'));
    expect(nameOrder()).toEqual(['CHA', 'BRA', 'ALP']);
    expect(screen.getByTestId('supplier-list-sort-name-desc')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-col-name'))
      .toHaveAttribute('aria-sort', 'descending');

    // Third click → clear (back to insertion order).
    fireEvent.click(screen.getByTestId('supplier-list-sort-name'));
    expect(nameOrder()).toEqual(['CHA', 'ALP', 'BRA']);
    expect(screen.getByTestId('supplier-list-sort-name-none')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-list-col-name'))
      .toHaveAttribute('aria-sort', 'none');
  });

  test('Trade column sort (non-name): asc then desc; null trades sink in asc', () => {
    setData([
      { id: 'R',  name: 'R-row', supplier_type: 'Supplier', trade: 'Roofing'    },
      { id: 'E',  name: 'E-row', supplier_type: 'Supplier', trade: 'Electrical' },
      { id: 'N',  name: 'N-row', supplier_type: 'Supplier', trade: null         },
      { id: 'G',  name: 'G-row', supplier_type: 'Supplier', trade: 'Groundworks'},
    ]);
    renderAt();

    fireEvent.click(screen.getByTestId('supplier-list-sort-trade'));
    // asc: '' < Electrical < Groundworks < Roofing.
    expect(nameOrder()).toEqual(['N', 'E', 'G', 'R']);
    expect(screen.getByTestId('supplier-list-sort-trade-asc')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('supplier-list-sort-trade'));
    expect(nameOrder()).toEqual(['R', 'G', 'E', 'N']);
    expect(screen.getByTestId('supplier-list-sort-trade-desc')).toBeInTheDocument();
  });

  test('switching to a different sort column resets to asc', () => {
    setData([
      { id: 'A1', name: 'Acme',  supplier_type: 'Supplier' },
      { id: 'Z1', name: 'Zenix', supplier_type: 'Contractor' },
      { id: 'M1', name: 'Mango', supplier_type: 'Other' },
    ]);
    renderAt();

    fireEvent.click(screen.getByTestId('supplier-list-sort-name'));
    fireEvent.click(screen.getByTestId('supplier-list-sort-name'));
    expect(screen.getByTestId('supplier-list-sort-name-desc')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('supplier-list-sort-type'));
    expect(screen.getByTestId('supplier-list-sort-type-asc')).toBeInTheDocument();
    // Name is back to unsorted (only one indicator highlighted at a time).
    expect(screen.getByTestId('supplier-list-sort-name-none')).toBeInTheDocument();
    // Type asc: Contractor < Other < Supplier.
    expect(nameOrder()).toEqual(['Z1', 'M1', 'A1']);
  });
});
