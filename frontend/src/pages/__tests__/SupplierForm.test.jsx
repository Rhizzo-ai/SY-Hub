/**
 * SupplierForm tests — Chat 40 §R5 #2.
 *
 * Covers:
 *  - create sends lowercase cis_status; '' → null
 *  - bank fields use bank_account_no
 *  - sensitive block hidden without perm
 *  - subcontractor block toggles on type
 *  - UTR validation (10 digits)
 *  - Supplier → omits subcontractor fields
 *  - edit Subcontractor → Supplier sends cis_subtype: null
 */
let mockCurrentParams = {};

jest.mock('@/hooks/purchaseOrders', () => ({
  useSupplier: jest.fn(),
  useCreateSupplier: jest.fn(),
  usePatchSupplier: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useParams: () => mockCurrentParams,
    useNavigate: () => () => {},
  };
});

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SupplierForm from '@/pages/SupplierForm';

const hooks = jest.requireMock('@/hooks/purchaseOrders');
const { useAuth } = jest.requireMock('@/context/AuthContext');

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

let createMutateAsync;
let patchMutateAsync;

beforeEach(() => {
  createMutateAsync = jest.fn().mockResolvedValue({ id: 'NEW' });
  patchMutateAsync = jest.fn().mockResolvedValue({ id: 'EDIT' });
  hooks.useSupplier.mockReset().mockReturnValue({ data: null });
  hooks.useCreateSupplier.mockReset()
    .mockReturnValue({ mutateAsync: createMutateAsync, isPending: false });
  hooks.usePatchSupplier.mockReset()
    .mockReturnValue({ mutateAsync: patchMutateAsync, isPending: false });
  useAuth.mockReset();
  mockCurrentParams = {};
});

function renderCreate(perms = ['suppliers.create', 'suppliers.view_sensitive']) {
  setMe(perms);
  mockCurrentParams = {};
  return render(
    <MemoryRouter initialEntries={['/suppliers/new']}>
      <SupplierForm />
    </MemoryRouter>
  );
}

function renderEdit(existing, perms = ['suppliers.edit', 'suppliers.view_sensitive']) {
  setMe(perms);
  mockCurrentParams = { id: existing.id };
  hooks.useSupplier.mockReturnValue({ data: existing });
  return render(
    <MemoryRouter initialEntries={[`/suppliers/${existing.id}/edit`]}>
      <SupplierForm />
    </MemoryRouter>
  );
}

describe('SupplierForm — create (D1/D2)', () => {
  test('cis_status="" submits as null (D1)', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].cis_status).toBeNull();
  });

  test('cis_status options are lowercase backend enum (D1)', () => {
    renderCreate();
    const select = screen.getByTestId('supplier-form-cis');
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values).toEqual(['', 'gross', 'net_20', 'net_30', 'not_registered']);
  });

  test('selecting Gross sends lowercase "gross"', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.change(screen.getByTestId('supplier-form-cis'), { target: { value: 'gross' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].cis_status).toBe('gross');
  });

  test('bank field uses bank_account_no (D2), bank_name + company_number present', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.change(screen.getByTestId('supplier-form-account-number'),
                     { target: { value: '12345678' } });
    fireEvent.change(screen.getByTestId('supplier-form-bank-name'),
                     { target: { value: 'Barclays' } });
    fireEvent.change(screen.getByTestId('supplier-form-company-number'),
                     { target: { value: '01234567' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.bank_account_no).toBe('12345678');
    expect(body.bank_name).toBe('Barclays');
    expect(body.company_number).toBe('01234567');
    expect(body.bank_account_number).toBeUndefined();
  });

  test('sensitive block hidden without suppliers.view_sensitive', () => {
    renderCreate(['suppliers.create']);
    expect(screen.queryByTestId('supplier-form-sensitive-block')).toBeNull();
    expect(screen.queryByTestId('supplier-form-account-number')).toBeNull();
    // Form itself still renders (canSubmit is true via suppliers.create).
    expect(screen.getByTestId('supplier-form')).toBeInTheDocument();
  });
});

describe('SupplierForm — subcontractor block (ADD half §R4.2)', () => {
  test('Subcontractor block hidden when type=Supplier', () => {
    renderCreate();
    expect(screen.queryByTestId('supplier-form-subcontractor-block')).toBeNull();
  });

  test('Subcontractor block appears when type=Subcontractor', () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Subcontractor' } });
    expect(screen.getByTestId('supplier-form-subcontractor-block')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-form-cis-subtype')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-form-cis-registered')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-form-utr')).toBeInTheDocument();
  });

  test('UTR must be exactly 10 digits — invalid blocks submit', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Subcontractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Sub' } });
    fireEvent.change(screen.getByTestId('supplier-form-utr'),
                     { target: { value: '123' } });
    expect(screen.getByTestId('supplier-form-utr-error')).toHaveTextContent('10 digits');
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    expect(createMutateAsync).not.toHaveBeenCalled();
  });

  test('UTR exactly 10 digits — submits utr', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Subcontractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Sub' } });
    fireEvent.change(screen.getByTestId('supplier-form-utr'),
                     { target: { value: '0123456789' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].utr).toBe('0123456789');
  });

  test('Supplier omits cis_subtype / cis_registered / utr', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.cis_subtype).toBeUndefined();
    expect(body.cis_registered).toBeUndefined();
    expect(body.utr).toBeUndefined();
    expect(body.supplier_type).toBe('Supplier');
  });

  test('Subcontractor submit includes cis_subtype + cis_registered', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Subcontractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Sub' } });
    fireEvent.change(screen.getByTestId('supplier-form-cis-subtype'),
                     { target: { value: 'Labour_Only' } });
    fireEvent.click(screen.getByTestId('supplier-form-cis-registered'));
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.supplier_type).toBe('Subcontractor');
    expect(body.cis_subtype).toBe('Labour_Only');
    expect(body.cis_registered).toBe(true);
  });

  test('edit Subcontractor→Supplier sends cis_subtype: null', async () => {
    renderEdit({
      id: 'S1', name: 'Was a sub', supplier_type: 'Subcontractor',
      cis_subtype: 'Labour_Only', cis_registered: true,
      cis_status: 'net_20', default_vat_rate: '20.0', payment_terms_days: 30,
    });
    await waitFor(() => {
      expect(screen.getByTestId('supplier-form-type').value).toBe('Subcontractor');
    });
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Supplier' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(patchMutateAsync).toHaveBeenCalled());
    const body = patchMutateAsync.mock.calls[0][0];
    expect(body.supplier_type).toBe('Supplier');
    expect(body.cis_subtype).toBeNull();
  });
});
