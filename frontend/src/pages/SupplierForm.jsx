/**
 * SupplierForm — Chat 24 §R5.
 *
 * One component handles both create (`/suppliers/new`) and edit
 * (`/suppliers/:id/edit`). Minimal fields; banking + VAT number sit
 * behind `suppliers.view_sensitive` (hidden in the form if the caller
 * can't see them, since editing what you can't see leaks info).
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

const CIS_STATUSES = ['None', 'Gross', 'Net_20', 'Net_30'];

function emptyForm() {
  return {
    name: '',
    cis_status: 'None',
    default_vat_rate: 20.0,
    payment_terms_days: 30,
    vat_number: '',
    bank_account_number: '',
    bank_sort_code: '',
    contact_email: '',
    contact_phone: '',
    notes: '',
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
    if (existing) setForm({ ...emptyForm(), ...existing });
  }, [existing]);

  if (!canSubmit) {
    return <div className="p-6 text-sm" data-testid="supplier-form-forbidden">
      You do not have permission to {isEdit ? 'edit' : 'create'} suppliers.
    </div>;
  }

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    const payload = {
      name: form.name?.trim(),
      cis_status: form.cis_status,
      default_vat_rate: Number(form.default_vat_rate),
      payment_terms_days: Number(form.payment_terms_days) || 0,
      contact_email: form.contact_email || null,
      contact_phone: form.contact_phone || null,
      notes: form.notes || null,
    };
    if (canSensitive) {
      payload.vat_number = form.vat_number || null;
      payload.bank_account_number = form.bank_account_number || null;
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
      className="p-6 max-w-xl space-y-3"
      data-testid="supplier-form"
    >
      <h1 className="text-xl font-semibold">{isEdit ? 'Edit supplier' : 'New supplier'}</h1>

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">Name *</span>
        <input
          type="text" required
          className="w-full px-2 py-1 border rounded text-sm"
          value={form.name} onChange={onChange('name')}
          data-testid="supplier-form-name"
        />
      </label>

      <label className="block text-sm">
        <span className="text-xs text-sy-grey-700">CIS status</span>
        <select
          className="w-full px-2 py-1 border rounded text-sm"
          value={form.cis_status} onChange={onChange('cis_status')}
          data-testid="supplier-form-cis"
        >
          {CIS_STATUSES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Default VAT %</span>
          <input
            type="number" step="0.1" min="0" max="100"
            className="w-full px-2 py-1 border rounded text-sm tabular-nums"
            value={form.default_vat_rate} onChange={onChange('default_vat_rate')}
            data-testid="supplier-form-vat-rate"
          />
        </label>
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Payment terms (days)</span>
          <input
            type="number" min="0"
            className="w-full px-2 py-1 border rounded text-sm tabular-nums"
            value={form.payment_terms_days} onChange={onChange('payment_terms_days')}
            data-testid="supplier-form-payment-terms"
          />
        </label>
      </div>

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

      {canSensitive && (
        <div
          className="space-y-2 p-2 border border-dashed rounded"
          data-testid="supplier-form-sensitive-block"
        >
          <div className="text-xs text-sy-grey-700">Sensitive (visible because you have suppliers.view_sensitive)</div>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">VAT number</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={form.vat_number ?? ''} onChange={onChange('vat_number')}
              data-testid="supplier-form-vat-number"
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
                value={form.bank_account_number ?? ''}
                onChange={onChange('bank_account_number')}
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
          type="submit" disabled={create.isPending || patch.isPending}
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
