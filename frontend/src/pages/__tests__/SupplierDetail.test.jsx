/**
 * SupplierDetail tests — Chat 40 §R5 #3.
 */
let mockCurrentParams = { id: 'S1' };
let mockCurrentSearch = '';

jest.mock('@/hooks/purchaseOrders', () => ({
  useSupplier: jest.fn(),
  useArchiveSupplier: jest.fn(),
  useUnarchiveSupplier: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('@/components/suppliers/CISTab', () => () => (
  <div data-testid="cis-tab-stub" />
));
jest.mock('@/components/suppliers/DocumentsTab', () => () => (
  <div data-testid="documents-tab-stub" />
));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useParams: () => mockCurrentParams,
    useNavigate: () => () => {},
    useSearchParams: () => {
      const params = new URLSearchParams(mockCurrentSearch);
      return [params, (next) => { mockCurrentSearch = next.toString(); }];
    },
  };
});

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SupplierDetail from '@/pages/SupplierDetail';

const hooks = jest.requireMock('@/hooks/purchaseOrders');
const { useAuth } = jest.requireMock('@/context/AuthContext');

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

let archiveMutate;
let unarchiveMutate;
beforeEach(() => {
  archiveMutate = jest.fn().mockResolvedValue({});
  unarchiveMutate = jest.fn().mockResolvedValue({});
  hooks.useArchiveSupplier.mockReset().mockReturnValue({ mutateAsync: archiveMutate });
  hooks.useUnarchiveSupplier.mockReset().mockReturnValue({ mutateAsync: unarchiveMutate });
  hooks.useSupplier.mockReset();
  useAuth.mockReset();
  mockCurrentParams = { id: 'S1' };
  mockCurrentSearch = '';
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

function renderDetail(supplier, perms) {
  setMe(perms);
  hooks.useSupplier.mockReturnValue({ data: supplier, isLoading: false, isError: false });
  return render(
    <MemoryRouter initialEntries={['/suppliers/S1']}>
      <SupplierDetail />
    </MemoryRouter>
  );
}

const BASE_SUPPLIER = {
  id: 'S1', name: 'ACME', supplier_type: 'Supplier',
  cis_status: 'gross', current_cis_status: null,
  default_vat_rate: '20.0', payment_terms_days: 30,
  contact_email: 'a@b.test', contact_phone: '012345',
  vat_number: 'GB123', company_number: '01234567',
  bank_name: 'Barclays', bank_account_no: '12345678', bank_sort_code: '11-22-33',
  is_archived: false, notes: null,
};

describe('SupplierDetail — tabs visibility', () => {
  test('only Overview + Documents tabs for Supplier (no CIS, no Contracts)', () => {
    renderDetail(BASE_SUPPLIER,
      ['suppliers.view', 'supplier_documents.view']);
    expect(screen.getByTestId('supplier-tab-overview')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-tab-documents')).toBeInTheDocument();
    expect(screen.queryByTestId('supplier-tab-cis')).toBeNull();
    expect(screen.queryByTestId('supplier-tab-contracts')).toBeNull();
  });

  test('Documents tab hidden without supplier_documents.view', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view']);
    expect(screen.queryByTestId('supplier-tab-documents')).toBeNull();
  });

  test('Subcontractor shows CIS + Documents + Contracts (with perms)', () => {
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Subcontractor', cis_subtype: 'Labour_Only',
        cis_registered: true, utr: '0123456789' },
      ['suppliers.view', 'cis.view', 'supplier_documents.view']
    );
    expect(screen.getByTestId('supplier-tab-cis')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-tab-documents')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-tab-contracts')).toBeInTheDocument();
  });

  test('CIS tab hidden when cis.view not granted', () => {
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Subcontractor' },
      ['suppliers.view', 'supplier_documents.view']
    );
    expect(screen.queryByTestId('supplier-tab-cis')).toBeNull();
  });

  test('Contracts tab shows placeholder content for Subcontractor', () => {
    mockCurrentSearch = 'tab=contracts';
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Subcontractor' },
      ['suppliers.view']
    );
    expect(screen.getByTestId('supplier-contracts-placeholder')).toHaveTextContent('2.8-FE');
  });
});

describe('SupplierDetail — sensitive rendering (D6)', () => {
  test('bank_account_no / bank_name / company_number rendered with perm', () => {
    renderDetail(BASE_SUPPLIER,
      ['suppliers.view', 'suppliers.view_sensitive', 'supplier_documents.view']);
    expect(screen.getByTestId('supplier-detail-bank-name-val')).toHaveTextContent('Barclays');
    expect(screen.getByTestId('supplier-detail-account-number-val')).toHaveTextContent('12345678');
    expect(screen.getByTestId('supplier-detail-company-number-val')).toHaveTextContent('01234567');
  });

  test('sensitive rows masked to "—" without view_sensitive', () => {
    const masked = { ...BASE_SUPPLIER,
      bank_name: null, bank_account_no: null, company_number: null,
      bank_sort_code: null, vat_number: null };
    renderDetail(masked, ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-bank-name-val')).toHaveTextContent('—');
    expect(screen.getByTestId('supplier-detail-account-number-val')).toHaveTextContent('—');
    expect(screen.getByTestId('supplier-detail-company-number-val')).toHaveTextContent('—');
  });
});

describe('SupplierDetail — archive / restore (D3)', () => {
  test('Active supplier: Archive button shown, no Restore', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view', 'suppliers.archive']);
    expect(screen.getByTestId('supplier-detail-archive-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('supplier-detail-restore-btn')).toBeNull();
  });

  test('Archived supplier: Restore button shown, no Archive', () => {
    renderDetail({ ...BASE_SUPPLIER, is_archived: true },
      ['suppliers.view', 'suppliers.archive']);
    expect(screen.getByTestId('supplier-detail-restore-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('supplier-detail-archive-btn')).toBeNull();
  });

  test('Header subtitle uses is_archived bool (not phantom status)', () => {
    renderDetail({ ...BASE_SUPPLIER, is_archived: true },
      ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail')).toHaveTextContent('Archived');
  });
});
