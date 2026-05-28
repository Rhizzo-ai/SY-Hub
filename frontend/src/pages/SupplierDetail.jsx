/**
 * SupplierDetail — Chat 24 §R5.
 *
 * Read-only summary + edit/archive affordances. Sensitive banking /
 * VAT-number fields are masked via <SensitiveValue/> when the caller
 * lacks `suppliers.view_sensitive`.
 */
import React from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import {
  useArchiveSupplier, useSupplier,
} from '@/hooks/purchaseOrders';
import {
  canArchiveSupplier, canEditSupplier, canViewSensitiveSupplier,
} from '@/lib/poCapability';
import SensitiveValue from '@/components/po/SensitiveValue';

export default function SupplierDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const navigate = useNavigate();
  const canSensitive = canViewSensitiveSupplier(me);

  const { data: s, isLoading, isError } = useSupplier(id);
  const archive = useArchiveSupplier();

  if (isLoading) return <div className="p-6 text-sm" data-testid="supplier-detail-loading">Loading…</div>;
  if (isError || !s) return <div className="p-6 text-sm text-red-600" data-testid="supplier-detail-error">Supplier not found.</div>;

  const onArchive = async () => {
    if (!window.confirm(`Archive supplier "${s.name}"?`)) return;
    await archive.mutateAsync(s.id);
    navigate('/suppliers');
  };

  return (
    <div className="p-6 max-w-2xl space-y-4" data-testid="supplier-detail">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{s.name}</h1>
          <div className="text-xs text-sy-grey-600">{s.status} · CIS {s.cis_status ?? 'None'}</div>
        </div>
        <div className="flex gap-2">
          {canEditSupplier(me) && (
            <Link
              to={`/suppliers/${s.id}/edit`}
              className="px-3 py-1.5 rounded border text-sm"
              data-testid="supplier-detail-edit-btn"
            >Edit</Link>
          )}
          {canArchiveSupplier(me) && s.status !== 'Archived' && (
            <button
              type="button" onClick={onArchive}
              className="px-3 py-1.5 rounded border text-sm text-red-700"
              data-testid="supplier-detail-archive-btn"
            >Archive</button>
          )}
        </div>
      </header>

      <section className="grid grid-cols-2 gap-2 text-sm">
        <DetailRow label="Default VAT" testid="supplier-detail-vat-rate"
          value={s.default_vat_rate != null ? `${s.default_vat_rate}%` : null} />
        <DetailRow label="Payment terms" testid="supplier-detail-payment-terms"
          value={s.payment_terms_days != null ? `${s.payment_terms_days} days` : null} />
        <DetailRow label="Contact email" testid="supplier-detail-email" value={s.contact_email} />
        <DetailRow label="Contact phone" testid="supplier-detail-phone" value={s.contact_phone} />
      </section>

      <section
        className="grid grid-cols-2 gap-2 text-sm p-2 border border-dashed rounded"
        data-testid="supplier-detail-sensitive-block"
      >
        <div className="col-span-2 text-xs text-sy-grey-700">
          Sensitive
          {!canSensitive && (
            <span className="ml-2 text-sy-orange-700">(requires suppliers.view_sensitive)</span>
          )}
        </div>
        <DetailRow label="VAT number" testid="supplier-detail-vat-number">
          <SensitiveValue value={s.vat_number} hidden={!canSensitive} testid="supplier-detail-vat-number-val" />
        </DetailRow>
        <DetailRow label="Bank sort code" testid="supplier-detail-sort-code">
          <SensitiveValue value={s.bank_sort_code} hidden={!canSensitive} testid="supplier-detail-sort-code-val" />
        </DetailRow>
        <DetailRow label="Bank account #" testid="supplier-detail-account-number">
          <SensitiveValue value={s.bank_account_number} hidden={!canSensitive} testid="supplier-detail-account-number-val" />
        </DetailRow>
      </section>

      {s.notes && (
        <section data-testid="supplier-detail-notes">
          <div className="text-xs text-sy-grey-700">Notes</div>
          <div className="text-sm whitespace-pre-wrap">{s.notes}</div>
        </section>
      )}
    </div>
  );
}

function DetailRow({ label, value, children, testid }) {
  return (
    <div data-testid={testid}>
      <div className="text-xs text-sy-grey-700">{label}</div>
      <div className="tabular-nums">
        {children ?? (value ?? '—')}
      </div>
    </div>
  );
}
