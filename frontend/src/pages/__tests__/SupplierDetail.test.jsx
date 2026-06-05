/**
 * SupplierDetail tests — Chat 40 §R5 #3 + Chat 41 §R8 (Build Pack
 *   2.7-FE-revision).
 *
 * Covers:
 *  - Tab gates: Contractor (was Subcontractor) drives CIS + Contracts.
 *  - Default-VAT row + sub-type row are GONE.
 *  - New rows: Trade, VAT registered, Trading name, Contact name.
 *  - Address block hides when every address field is null; shows when
 *    any field is present.
 *  - Sensitive rendering (D6) unchanged.
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
import { render, screen } from '@testing-library/react';
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
  payment_terms_days: 30,
  contact_email: 'a@b.test', contact_phone: '012345',
  vat_number: 'GB123', vat_registered: true, company_number: '01234567',
  bank_name: 'Barclays', bank_account_no: '12345678', bank_sort_code: '11-22-33',
  trade: 'Groundworks', trading_name: 'ACME Trading', contact_name: 'Jane',
  address_line1: '1 High St', address_line2: null,
  city: 'London', postcode: 'SW1A 1AA', country: 'UK',
  is_archived: false, notes: null,
};

describe('SupplierDetail — tabs visibility (Chat 41 §R4.2)', () => {
  test('header subtitle omits "· CIS …" for non-Contractor (post-Gate-1 fix)', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view']);
    const subtitle = screen.getByTestId('supplier-detail-subtitle');
    expect(subtitle).toHaveTextContent('Active · Supplier');
    expect(subtitle.textContent).not.toMatch(/CIS/);
    expect(screen.queryByTestId('supplier-detail-subtitle-cis')).toBeNull();
  });

  test('header subtitle shows "· CIS …" for Contractor', () => {
    renderDetail({ ...BASE_SUPPLIER, supplier_type: 'Contractor', cis_status: 'gross' },
      ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-subtitle-cis')).toHaveTextContent(/CIS\s*Gross/);
  });

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

  test('Contractor shows CIS + Documents + Contracts (with perms)', () => {
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Contractor',
        cis_registered: true, utr: '0123456789' },
      ['suppliers.view', 'cis.view', 'supplier_documents.view']
    );
    expect(screen.getByTestId('supplier-tab-cis')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-tab-documents')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-tab-contracts')).toBeInTheDocument();
  });

  test('CIS tab hidden when cis.view not granted', () => {
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Contractor' },
      ['suppliers.view', 'supplier_documents.view']
    );
    expect(screen.queryByTestId('supplier-tab-cis')).toBeNull();
  });

  test('Contracts tab shows placeholder content for Contractor', () => {
    mockCurrentSearch = 'tab=contracts';
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Contractor' },
      ['suppliers.view']
    );
    expect(screen.getByTestId('supplier-contracts-placeholder')).toHaveTextContent('2.8-FE');
  });

  test.each(['Supplier', 'Consultant', 'Other'])(
    'non-Contractor type "%s" hides CIS + Contracts tabs',
    (t) => {
      renderDetail({ ...BASE_SUPPLIER, supplier_type: t },
        ['suppliers.view', 'cis.view', 'supplier_documents.view']);
      expect(screen.queryByTestId('supplier-tab-cis')).toBeNull();
      expect(screen.queryByTestId('supplier-tab-contracts')).toBeNull();
    },
  );
});

describe('SupplierDetail — contact-book fields (Chat 41 §R4.3)', () => {
  test('Trade row renders the serialised trade name', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-trade')).toHaveTextContent('Groundworks');
  });

  test('Trade row falls back to em-dash when null', () => {
    renderDetail({ ...BASE_SUPPLIER, trade: null }, ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-trade')).toHaveTextContent('—');
  });

  test('VAT registered row renders Yes / No', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-vat-registered')).toHaveTextContent('Yes');
  });

  test('Trading + Contact name rows render', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-trading-name')).toHaveTextContent('ACME Trading');
    expect(screen.getByTestId('supplier-detail-contact-name')).toHaveTextContent('Jane');
  });

  test('Address block renders when any address field is present', () => {
    renderDetail(BASE_SUPPLIER, ['suppliers.view']);
    expect(screen.getByTestId('supplier-detail-address-block')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-detail-address-line1')).toHaveTextContent('1 High St');
    expect(screen.getByTestId('supplier-detail-city')).toHaveTextContent('London');
  });

  test('Address block hides when every address field is null', () => {
    renderDetail(
      { ...BASE_SUPPLIER,
        address_line1: null, address_line2: null,
        city: null, postcode: null, country: null },
      ['suppliers.view'],
    );
    expect(screen.queryByTestId('supplier-detail-address-block')).toBeNull();
  });

  test('Default-VAT row is gone (rev-A dropped the field)', () => {
    renderDetail(BASE_SUPPLIER,
      ['suppliers.view', 'suppliers.view_sensitive', 'supplier_documents.view']);
    expect(screen.queryByTestId('supplier-detail-vat-rate')).toBeNull();
  });

  test('CIS sub-type row is gone (rev-A dropped the field)', () => {
    renderDetail(
      { ...BASE_SUPPLIER, supplier_type: 'Contractor' },
      ['suppliers.view', 'cis.view'],
    );
    expect(screen.queryByTestId('supplier-detail-cis-subtype')).toBeNull();
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
