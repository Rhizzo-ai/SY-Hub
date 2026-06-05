/**
 * SupplierForm tests — Chat 40 §R5 #2 + Chat 41 §R8 (Build Pack
 *   2.7-FE-revision).
 *
 * Covers:
 *  - cis_status lowercase enum; '' → null
 *  - bank fields use bank_account_no
 *  - sensitive block hidden without perm
 *  - 4-way type select (Contractor / Supplier / Consultant / Other);
 *    "Subcontractor" is NOT an option
 *  - Contractor sub-block (CIS registered + UTR) toggles on type
 *  - UTR validation (10 digits, Contractor only)
 *  - Non-Contractor → omits cis_registered / utr
 *  - Payload omits the dropped fields (default-VAT + sub-type)
 *  - vat_registered boolean submits (independent of vat_number)
 *  - trade name + address/contact fields submit through
 */
let mockCurrentParams = {};

jest.mock('@/hooks/purchaseOrders', () => ({
  useSupplier: jest.fn(),
  useCreateSupplier: jest.fn(),
  usePatchSupplier: jest.fn(),
}));
// Chat 41 §R8 — the form pulls in <TradePicker/>, which fetches via
// useTrades + useCreateTrade. Without these mocks the picker hits the
// network and the suite breaks. Mirrors the @/hooks/cis pattern in
// CISTab.test.jsx.
jest.mock('@/hooks/trades', () => ({
  useTrades: jest.fn(),
  useCreateTrade: jest.fn(),
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
const tradesHooks = jest.requireMock('@/hooks/trades');
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
  tradesHooks.useTrades.mockReset()
    .mockReturnValue({ data: { items: [] } });
  tradesHooks.useCreateTrade.mockReset()
    .mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
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

describe('SupplierForm — CIS field is Contractor-gated (post-Gate-1 fix, render-presence)', () => {
  // These two tests pair on the SAME mount, querying the DOM by
  // data-testid before and after flipping the type — defending the
  // case where a payload-only assertion lets stale JSX slip through.
  test('CIS select is NOT in the document for default type (Supplier)', () => {
    renderCreate();
    expect(screen.queryByTestId('supplier-form-cis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('supplier-form-contractor-block')).not.toBeInTheDocument();
  });

  test('CIS select appears the instant type switches to Contractor and disappears on switch-back', () => {
    renderCreate();
    expect(screen.queryByTestId('supplier-form-cis')).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    expect(screen.getByTestId('supplier-form-cis')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-form-contractor-block'))
      .toContainElement(screen.getByTestId('supplier-form-cis'));

    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Supplier' } });
    expect(screen.queryByTestId('supplier-form-cis')).not.toBeInTheDocument();
  });

  test.each(['Consultant', 'Other'])(
    'CIS select stays hidden when type=%s',
    (t) => {
      renderCreate();
      fireEvent.change(screen.getByTestId('supplier-form-type'),
                       { target: { value: t } });
      expect(screen.queryByTestId('supplier-form-cis')).not.toBeInTheDocument();
    },
  );
});

describe('SupplierForm — create (D1/D2)', () => {
  test('cis_status select is hidden on the default (Supplier) type — post-Gate-1 fix', () => {
    renderCreate();
    expect(screen.queryByTestId('supplier-form-cis')).toBeNull();
  });

  test('non-Contractor submit OMITS cis_status entirely', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect('cis_status' in createMutateAsync.mock.calls[0][0]).toBe(false);
  });

  test('Contractor: cis_status="" submits as null (D1)', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Subby' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].cis_status).toBeNull();
  });

  test('Contractor cis_status options are lowercase backend enum (D1)', () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    const select = screen.getByTestId('supplier-form-cis');
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values).toEqual(['', 'gross', 'net_20', 'net_30', 'not_registered']);
  });

  test('Contractor: selecting Gross sends lowercase "gross"', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Subby' } });
    fireEvent.change(screen.getByTestId('supplier-form-cis'), { target: { value: 'gross' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].cis_status).toBe('gross');
  });

  test('edit Contractor→Supplier drops cis_status from the payload (post-Gate-1 fix)', async () => {
    renderEdit({
      id: 'S2', name: 'Was contractor', supplier_type: 'Contractor',
      cis_status: 'net_20', cis_registered: true, utr: '0123456789',
      payment_terms_days: 30,
    });
    await waitFor(() => {
      expect(screen.getByTestId('supplier-form-type').value).toBe('Contractor');
    });
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Supplier' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(patchMutateAsync).toHaveBeenCalled());
    expect('cis_status' in patchMutateAsync.mock.calls[0][0]).toBe(false);
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
    expect(screen.getByTestId('supplier-form')).toBeInTheDocument();
  });
});

describe('SupplierForm — type picker (Chat 41 §R3.1)', () => {
  test('type select exposes exactly the 4 contact-book values', () => {
    renderCreate();
    const select = screen.getByTestId('supplier-form-type');
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values).toEqual(['Contractor', 'Supplier', 'Consultant', 'Other']);
  });

  test('Subcontractor is not a selectable option', () => {
    renderCreate();
    const select = screen.getByTestId('supplier-form-type');
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values).not.toContain('Subcontractor');
  });

  test('default supplier_type on a fresh create is "Supplier"', () => {
    renderCreate();
    expect(screen.getByTestId('supplier-form-type').value).toBe('Supplier');
  });
});

describe('SupplierForm — Contractor sub-block (Chat 41 §R3.4)', () => {
  test('Contractor block hidden when type=Supplier', () => {
    renderCreate();
    expect(screen.queryByTestId('supplier-form-contractor-block')).toBeNull();
  });

  test.each(['Consultant', 'Other'])(
    'Contractor block hidden for type=%s',
    (v) => {
      renderCreate();
      fireEvent.change(screen.getByTestId('supplier-form-type'),
                       { target: { value: v } });
      expect(screen.queryByTestId('supplier-form-contractor-block')).toBeNull();
    },
  );

  test('Contractor block appears when type=Contractor (CIS registered + UTR)', () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    expect(screen.getByTestId('supplier-form-contractor-block')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-form-cis-registered')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-form-utr')).toBeInTheDocument();
  });

  test('UTR must be exactly 10 digits — invalid blocks submit', () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Subby' } });
    fireEvent.change(screen.getByTestId('supplier-form-utr'),
                     { target: { value: '123' } });
    expect(screen.getByTestId('supplier-form-utr-error')).toHaveTextContent('10 digits');
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    expect(createMutateAsync).not.toHaveBeenCalled();
  });

  test('UTR exactly 10 digits — submits utr', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Subby' } });
    fireEvent.change(screen.getByTestId('supplier-form-utr'),
                     { target: { value: '0123456789' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].utr).toBe('0123456789');
  });

  test('Supplier omits the dropped sub-type / default-VAT and the contractor-only keys', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.cis_subtype).toBeUndefined();
    expect(body.default_vat_rate).toBeUndefined();
    expect(body.cis_registered).toBeUndefined();
    expect(body.utr).toBeUndefined();
    expect(body.supplier_type).toBe('Supplier');
  });

  test('Contractor submit includes cis_registered + omits cis_subtype', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Contractor' } });
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'Subby' } });
    fireEvent.click(screen.getByTestId('supplier-form-cis-registered'));
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.supplier_type).toBe('Contractor');
    expect(body.cis_registered).toBe(true);
    expect(body.cis_subtype).toBeUndefined();
    expect(body.default_vat_rate).toBeUndefined();
  });

  test('edit Contractor→Supplier drops contractor keys without sending a null cleanup', async () => {
    renderEdit({
      id: 'S1', name: 'Was a contractor', supplier_type: 'Contractor',
      cis_registered: true, utr: '0123456789',
      cis_status: 'net_20', payment_terms_days: 30,
    });
    await waitFor(() => {
      expect(screen.getByTestId('supplier-form-type').value).toBe('Contractor');
    });
    fireEvent.change(screen.getByTestId('supplier-form-type'),
                     { target: { value: 'Supplier' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(patchMutateAsync).toHaveBeenCalled());
    const body = patchMutateAsync.mock.calls[0][0];
    expect(body.supplier_type).toBe('Supplier');
    expect(body.cis_subtype).toBeUndefined();
    expect(body.default_vat_rate).toBeUndefined();
    expect(body.cis_registered).toBeUndefined();
  });
});

describe('SupplierForm — new fields (Chat 41 §R3.5/§R3.6)', () => {
  test('vat_registered submits as boolean (independent of vat_number)', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-vat-registered'));
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.vat_registered).toBe(true);
    // vat_number is sensitive + unchanged → either null or its current
    // value, but NEVER inferred from vat_registered.
    expect(body.vat_number).toBeNull();
  });

  test('vat_registered defaults to false on a fresh create', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].vat_registered).toBe(false);
  });

  test('address + trading/contact name fields submit through', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.change(screen.getByTestId('supplier-form-trading-name'),
                     { target: { value: 'ACME Trading' } });
    fireEvent.change(screen.getByTestId('supplier-form-contact-name'),
                     { target: { value: 'Jane Roe' } });
    fireEvent.change(screen.getByTestId('supplier-form-address-line1'),
                     { target: { value: '1 High St' } });
    fireEvent.change(screen.getByTestId('supplier-form-address-line2'),
                     { target: { value: 'Unit 2' } });
    fireEvent.change(screen.getByTestId('supplier-form-city'),
                     { target: { value: 'London' } });
    fireEvent.change(screen.getByTestId('supplier-form-postcode'),
                     { target: { value: 'SW1A 1AA' } });
    fireEvent.change(screen.getByTestId('supplier-form-country'),
                     { target: { value: 'UK' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const body = createMutateAsync.mock.calls[0][0];
    expect(body.trading_name).toBe('ACME Trading');
    expect(body.contact_name).toBe('Jane Roe');
    expect(body.address_line1).toBe('1 High St');
    expect(body.address_line2).toBe('Unit 2');
    expect(body.city).toBe('London');
    expect(body.postcode).toBe('SW1A 1AA');
    expect(body.country).toBe('UK');
  });

  test('trade is sent as a name string (null on empty)', async () => {
    renderCreate();
    fireEvent.change(screen.getByTestId('supplier-form-name'), { target: { value: 'ACME' } });
    fireEvent.click(screen.getByTestId('supplier-form-save'));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].trade).toBeNull();
  });

  test('TradePicker is rendered in the form', () => {
    renderCreate();
    expect(screen.getByTestId('supplier-form-trade-trigger')).toBeInTheDocument();
  });
});
