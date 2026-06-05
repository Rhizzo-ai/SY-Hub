/**
 * SupplierForm — Chat 24 §R5 · Chat 40 §R2 + §R4.2 · Chat 41 §R3
 *   (Build Pack 2.7-FE-revision).
 *
 * Single contact book. Type is a 4-way label
 * (Contractor / Supplier / Consultant / Other), default `Supplier`.
 * The CIS / contractor sub-block (cis_registered + UTR) only renders
 * for `Contractor`. CIS deduction status (cis_status) renders for ALL
 * types — backend accepts it on any row and the field is harmless on
 * non-contractors.
 *
 * Drops vs. prior shipped form (rev-A backend dropped both fields):
 *   - CIS sub-type (form field + label map usage)
 *   - default VAT (form field + payload)
 *
 * Adds (backend accepted these all along; the old form never exposed
 * them):
 *   - `trade` via <TradePicker/> (name-driven; backend `_resolve_trade`
 *     get-or-creates idempotently)
 *   - `trading_name`, `contact_name`
 *   - Address block: address_line1/2, city, postcode, country
 *
 * Chat 41 §R-eyeball-Step2A (Prompt 2.7-FE-revision) — `vat_registered`
 *   dropped (was added in 0040, removed in 0041 per operator decision).
 *   "Has a VAT number" is the de-facto registered signal; Xero owns
 *   VAT logic.
 *
 * UTR (10 digits) and bank fields stay in the sensitive block.
 * `current_cis_status` is NEVER in the form — read-only, CIS-owned.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import {
  useCreateSupplier, usePatchSupplier, useSupplier,
} from '@/hooks/purchaseOrders';
import {
  canCreateSupplier, canEditSupplier, canViewSensitiveSupplier,
} from '@/lib/poCapability';
import TradePicker from '@/components/suppliers/TradePicker';

const CIS_STATUS_OPTIONS = ['', 'gross', 'net_20', 'net_30', 'not_registered'];
const CIS_STATUS_LABEL = {
  '': '—',
  gross: 'Gross',
  net_20: 'Net 20%',
  net_30: 'Net 30%',
  not_registered: 'Not registered',
};

const SUPPLIER_TYPES = ['Contractor', 'Supplier', 'Consultant', 'Other'];

// UTR: HMRC self-assessment Unique Taxpayer Reference is exactly 10
// digits. Client-side: trim, allow empty, otherwise enforce.
const UTR_RE = /^\d{10}$/;

function emptyForm() {
  return {
    name: '',
    supplier_type: 'Supplier',
    cis_status: '',
    payment_terms_days: 30,
    vat_number: '',
    company_number: '',
    bank_name: '',
    bank_account_no: '',
    bank_sort_code: '',
    contact_email: '',
    contact_phone: '',
    notes: '',
    cis_registered: false,
    utr: '',
    trade: '',
    trading_name: '',
    contact_name: '',
    address_line1: '',
    address_line2: '',
    city: '',
    postcode: '',
    country: '',
  };
}

export default function SupplierForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isEdit = !!id;
  const { me } = useAuth();
  const canSensitive = canViewSensitiveSupplier(me);
  const canSubmit = isEdit ? canEditSupplier(me) : canCreateSupplier(me);

  const { data: existing } = useSupplier(id, { enabled: isEdit });
  const create = useCreateSupplier();
  const patch = usePatchSupplier(id);
  const [form, setForm] = useState(emptyForm());
  const [error, setError] = useState(null);

  useEffect(() => {
    if (existing) {
      const overlay = { ...existing };
      Object.keys(overlay).forEach((k) => {
        if (overlay[k] === null && typeof emptyForm()[k] === 'string') {
          overlay[k] = '';
        }
      });
      // cis_registered is a boolean; backend may serialize null on
      // legacy rows. Coerce to false.
      if (overlay.cis_registered === null || overlay.cis_registered === undefined) {
        overlay.cis_registered = false;
      }
      // The picker is name-driven; seed from the serialised `trade`
      // string (not trade_id).
      if (overlay.trade === null || overlay.trade === undefined) {
        overlay.trade = '';
      }
      setForm({ ...emptyForm(), ...overlay });
    }
  }, [existing]);

  if (!canSubmit) {
    return <div className="p-6 text-sm" data-testid="supplier-form-forbidden">
      You do not have permission to {isEdit ? 'edit' : 'create'} suppliers.
    </div>;
  }

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const onCheckChange = (k) => (e) => setForm({ ...form, [k]: e.target.checked });

  const isContractor = form.supplier_type === 'Contractor';

  // UTR validation — only enforced when shown (Contractor block).
  const utrError = (() => {
    if (!isContractor) return null;
    const utr = (form.utr ?? '').trim();
    if (utr === '') return null;
    if (!UTR_RE.test(utr)) return 'UTR must be exactly 10 digits.';
    return null;
  })();

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (utrError) {
      setError(utrError);
      return;
    }
    const payload = {
      name: form.name?.trim(),
      supplier_type: form.supplier_type,
      payment_terms_days: Number(form.payment_terms_days) || 0,
      contact_email: form.contact_email || null,
      contact_phone: form.contact_phone || null,
      notes: form.notes || null,
      // Chat 41 §R-eyeball-Step2A — vat_registered removed (Xero owns
      // VAT logic; "has a VAT number" is the de-facto signal).
      // §R3.5 — send `trade` (name). Backend `_resolve_trade`
      // get-or-creates idempotently. Sending the name keeps the
      // form's submit self-contained even if the picker's create
      // call and the form submit race.
      trade: form.trade?.trim() || null,
      trading_name: form.trading_name || null,
      contact_name: form.contact_name || null,
      address_line1: form.address_line1 || null,
      address_line2: form.address_line2 || null,
      city: form.city || null,
      postcode: form.postcode || null,
      country: form.country || null,
    };

    if (isContractor) {
      payload.cis_registered = !!form.cis_registered;
      // Operator eyeball (post-Gate-1): cis_status is CIS-only and
      // must not persist on non-Contractor types. Send it only when
      // the row is a Contractor; on edit-Contractor→Supplier the
      // backend rev-A nullifies cis_status server-side.
      payload.cis_status = form.cis_status === '' ? null : form.cis_status;
      if (canSensitive) {
        payload.utr = form.utr?.trim() || null;
      }
    }
    // Non-Contractor types omit cis_registered / utr — backend
    // accepts them anywhere but they're meaningless off-Contractor
    // and there's no cleanup signal to send (the sub-type column,
    // prior null-flip target, no longer exists server-side).

    if (canSensitive) {
      payload.vat_number = form.vat_number || null;
      payload.company_number = form.company_number || null;
      payload.bank_name = form.bank_name || null;
      payload.bank_account_no = form.bank_account_no || null;
      payload.bank_sort_code = form.bank_sort_code || null;
    }
    try {
      const result = isEdit
        ? await patch.mutateAsync(payload)
        : await create.mutateAsync(payload);
      navigate(`/suppliers/${result.id}`);
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Save failed');
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="p-6 max-w-2xl space-y-3"
      data-testid="supplier-form"
    >
      <h1 className="text-xl font-semibold">{isEdit ? 'Edit contact' : 'New contact'}</h1>

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">Type *</span>
        <select
          className="w-full px-2 py-1 border rounded text-sm"
          value={form.supplier_type} onChange={onChange('supplier_type')}
          data-testid="supplier-form-type"
        >
          {SUPPLIER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">Name *</span>
        <input
          type="text" required
          className="w-full px-2 py-1 border rounded text-sm"
          value={form.name} onChange={onChange('name')}
          data-testid="supplier-form-name"
        />
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Trading name</span>
          <input
            type="text"
            className="w-full px-2 py-1 border rounded text-sm"
            value={form.trading_name ?? ''} onChange={onChange('trading_name')}
            data-testid="supplier-form-trading-name"
          />
        </label>
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Contact name</span>
          <input
            type="text"
            className="w-full px-2 py-1 border rounded text-sm"
            value={form.contact_name ?? ''} onChange={onChange('contact_name')}
            data-testid="supplier-form-contact-name"
          />
        </label>
      </div>

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">Trade</span>
        <TradePicker
          value={form.trade}
          onChange={(name) => setForm({ ...form, trade: name })}
          testid="supplier-form-trade"
        />
      </label>

      {isContractor && (
        <div
          className="space-y-2 p-2 border border-dashed rounded bg-slate-50"
          data-testid="supplier-form-contractor-block"
        >
          <div className="text-xs text-sy-grey-700">CIS / contractor details</div>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">CIS status</span>
            <select
              className="w-full px-2 py-1 border rounded text-sm"
              value={form.cis_status ?? ''} onChange={onChange('cis_status')}
              data-testid="supplier-form-cis"
            >
              {CIS_STATUS_OPTIONS.map((c) => (
                <option key={c || 'blank'} value={c}>{CIS_STATUS_LABEL[c]}</option>
              ))}
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!form.cis_registered}
              onChange={onCheckChange('cis_registered')}
              data-testid="supplier-form-cis-registered"
            />
            <span>CIS registered</span>
          </label>
          {canSensitive && (
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">UTR (10 digits)</span>
              <input
                type="text" inputMode="numeric"
                className="w-full px-2 py-1 border rounded text-sm tabular-nums"
                value={form.utr ?? ''} onChange={onChange('utr')}
                data-testid="supplier-form-utr"
                placeholder="0123456789"
              />
              {utrError && (
                <span className="text-xs text-red-600" data-testid="supplier-form-utr-error">
                  {utrError}
                </span>
              )}
            </label>
          )}
        </div>
      )}

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">Payment terms (days)</span>
        <input
          type="number" min="0"
          className="w-full px-2 py-1 border rounded text-sm tabular-nums"
          value={form.payment_terms_days} onChange={onChange('payment_terms_days')}
          data-testid="supplier-form-payment-terms"
        />
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Contact email</span>
          <input
            type="email"
            className="w-full px-2 py-1 border rounded text-sm"
            value={form.contact_email ?? ''} onChange={onChange('contact_email')}
            data-testid="supplier-form-email"
          />
        </label>
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Contact phone</span>
          <input
            type="tel"
            className="w-full px-2 py-1 border rounded text-sm"
            value={form.contact_phone ?? ''} onChange={onChange('contact_phone')}
            data-testid="supplier-form-phone"
          />
        </label>
      </div>

      <fieldset
        className="space-y-2 p-2 border border-dashed rounded"
        data-testid="supplier-form-address-block"
      >
        <legend className="text-xs text-sy-grey-700 px-1">Address</legend>
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Address line 1</span>
          <input
            type="text"
            className="w-full px-2 py-1 border rounded text-sm"
            value={form.address_line1 ?? ''} onChange={onChange('address_line1')}
            data-testid="supplier-form-address-line1"
          />
        </label>
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Address line 2</span>
          <input
            type="text"
            className="w-full px-2 py-1 border rounded text-sm"
            value={form.address_line2 ?? ''} onChange={onChange('address_line2')}
            data-testid="supplier-form-address-line2"
          />
        </label>
        <div className="grid grid-cols-3 gap-2">
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">City</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={form.city ?? ''} onChange={onChange('city')}
              data-testid="supplier-form-city"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Postcode</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={form.postcode ?? ''} onChange={onChange('postcode')}
              data-testid="supplier-form-postcode"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Country</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={form.country ?? ''} onChange={onChange('country')}
              data-testid="supplier-form-country"
            />
          </label>
        </div>
      </fieldset>

      {canSensitive && (
        <div
          className="space-y-2 p-2 border border-dashed rounded"
          data-testid="supplier-form-sensitive-block"
        >
          <div className="text-xs text-sy-grey-700">Sensitive (visible because you have suppliers.view_sensitive)</div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">VAT number</span>
              <input
                type="text"
                className="w-full px-2 py-1 border rounded text-sm"
                value={form.vat_number ?? ''} onChange={onChange('vat_number')}
                data-testid="supplier-form-vat-number"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Company number</span>
              <input
                type="text"
                className="w-full px-2 py-1 border rounded text-sm"
                value={form.company_number ?? ''} onChange={onChange('company_number')}
                data-testid="supplier-form-company-number"
              />
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Bank name</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={form.bank_name ?? ''} onChange={onChange('bank_name')}
              data-testid="supplier-form-bank-name"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Bank sort code</span>
              <input
                type="text"
                className="w-full px-2 py-1 border rounded text-sm"
                value={form.bank_sort_code ?? ''} onChange={onChange('bank_sort_code')}
                data-testid="supplier-form-sort-code"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Bank account #</span>
              <input
                type="text"
                className="w-full px-2 py-1 border rounded text-sm"
                value={form.bank_account_no ?? ''}
                onChange={onChange('bank_account_no')}
                data-testid="supplier-form-account-number"
              />
            </label>
          </div>
        </div>
      )}

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">Notes</span>
        <textarea
          className="w-full px-2 py-1 border rounded text-sm" rows={3}
          value={form.notes ?? ''} onChange={onChange('notes')}
          data-testid="supplier-form-notes"
        />
      </label>

      {error && (
        <div className="text-sm text-red-600" data-testid="supplier-form-error">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="submit" disabled={create.isPending || patch.isPending || !!utrError}
          className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm disabled:opacity-50"
          data-testid="supplier-form-save"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="px-3 py-1.5 rounded border text-sm"
          data-testid="supplier-form-cancel"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
