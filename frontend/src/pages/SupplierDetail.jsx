/**
 * SupplierDetail — Chat 24 §R5 · Chat 40 §R4.3 ADD half (tabbed).
 *
 * Tabs (rendered per visibility):
 *   - Overview (always): fixed fields (D3/D6) + Type, UTR (subcontractor),
 *     current_cis_status badge.
 *   - CIS (iff supplier_type==='Subcontractor' && cis.view).
 *   - Documents (iff supplier_documents.view).
 *   - Contracts (iff supplier_type==='Subcontractor'): placeholder
 *     panel — Subcontracts arrive in 2.8-FE.
 *
 * Archive/Restore live in the header; archive navigates back to
 * `/suppliers`, restore stays + invalidates.
 */
import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '@/components/ui/tabs';

import { useAuth } from '@/context/AuthContext';
import {
  useArchiveSupplier, useUnarchiveSupplier, useSupplier,
} from '@/hooks/purchaseOrders';
import {
  canArchiveSupplier, canEditSupplier, canViewSensitiveSupplier,
  canViewCIS, canViewDocs,
} from '@/lib/poCapability';
import SensitiveValue from '@/components/po/SensitiveValue';
import CISStatusBadge from '@/components/suppliers/CISStatusBadge';
import CISTab from '@/components/suppliers/CISTab';
import DocumentsTab from '@/components/suppliers/DocumentsTab';
import {
  labelCisStatus, labelCisSubtype, labelCurrentCisStatus,
} from '@/lib/cisFormat';

export default function SupplierDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const navigate = useNavigate();
  const canSensitive = canViewSensitiveSupplier(me);
  const [searchParams, setSearchParams] = useSearchParams();

  const { data: s, isLoading, isError } = useSupplier(id);
  const archive = useArchiveSupplier();
  const unarchive = useUnarchiveSupplier();

  const initialTab = searchParams.get('tab') || 'overview';
  const [tab, setTab] = useState(initialTab);

  useEffect(() => {
    // Sync URL so ?tab= deep-links + reload stay consistent.
    const next = new URLSearchParams(searchParams);
    if (tab === 'overview') next.delete('tab'); else next.set('tab', tab);
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  if (isLoading) return <div className="p-6 text-sm" data-testid="supplier-detail-loading">Loading…</div>;
  if (isError || !s) return <div className="p-6 text-sm text-red-600" data-testid="supplier-detail-error">Supplier not found.</div>;

  const isSub = s.supplier_type === 'Subcontractor';
  const showCisTab = isSub && canViewCIS(me);
  const showDocsTab = canViewDocs(me);
  const showContractsTab = isSub;

  const onArchive = async () => {
    if (!window.confirm(`Archive supplier "${s.name}"?`)) return;
    await archive.mutateAsync(s.id);
    navigate('/suppliers');
  };

  const onRestore = async () => {
    if (!window.confirm(`Restore supplier "${s.name}"?`)) return;
    await unarchive.mutateAsync(s.id);
  };

  return (
    <div className="p-6 max-w-3xl space-y-4" data-testid="supplier-detail">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{s.name}</h1>
          <div className="text-xs text-sy-grey-600">
            {s.is_archived ? 'Archived' : 'Active'} · {s.supplier_type ?? 'Supplier'} · CIS {labelCisStatus(s.cis_status)}
          </div>
        </div>
        <div className="flex gap-2">
          {canEditSupplier(me) && (
            <Link
              to={`/suppliers/${s.id}/edit`}
              className="px-3 py-1.5 rounded border text-sm"
              data-testid="supplier-detail-edit-btn"
            >Edit</Link>
          )}
          {canArchiveSupplier(me) && !s.is_archived && (
            <button
              type="button" onClick={onArchive}
              className="px-3 py-1.5 rounded border text-sm text-red-700"
              data-testid="supplier-detail-archive-btn"
            >Archive</button>
          )}
          {canArchiveSupplier(me) && s.is_archived && (
            <button
              type="button" onClick={onRestore}
              className="px-3 py-1.5 rounded border text-sm text-sy-teal-700"
              data-testid="supplier-detail-restore-btn"
            >Restore</button>
          )}
        </div>
      </header>

      <Tabs value={tab} onValueChange={setTab} data-testid="supplier-detail-tabs">
        <TabsList>
          <TabsTrigger value="overview" data-testid="supplier-tab-overview">Overview</TabsTrigger>
          {showCisTab && <TabsTrigger value="cis" data-testid="supplier-tab-cis">CIS</TabsTrigger>}
          {showDocsTab && <TabsTrigger value="documents" data-testid="supplier-tab-documents">Documents</TabsTrigger>}
          {showContractsTab && <TabsTrigger value="contracts" data-testid="supplier-tab-contracts">Contracts</TabsTrigger>}
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <section className="grid grid-cols-2 gap-2 text-sm">
            <DetailRow label="Default VAT" testid="supplier-detail-vat-rate"
              value={s.default_vat_rate != null ? `${s.default_vat_rate}%` : null} />
            <DetailRow label="Payment terms" testid="supplier-detail-payment-terms"
              value={s.payment_terms_days != null ? `${s.payment_terms_days} days` : null} />
            <DetailRow label="Contact email" testid="supplier-detail-email" value={s.contact_email} />
            <DetailRow label="Contact phone" testid="supplier-detail-phone" value={s.contact_phone} />
          </section>

          {isSub && (
            <section
              className="grid grid-cols-2 gap-2 text-sm p-2 border border-dashed rounded bg-slate-50"
              data-testid="supplier-detail-subcontractor-block"
            >
              <div className="col-span-2 text-xs text-sy-grey-700">Subcontractor</div>
              <DetailRow label="CIS sub-type" testid="supplier-detail-cis-subtype"
                value={labelCisSubtype(s.cis_subtype)} />
              <DetailRow label="CIS registered" testid="supplier-detail-cis-registered"
                value={s.cis_registered ? 'Yes' : 'No'} />
              <DetailRow label="Current CIS status" testid="supplier-detail-current-cis-status">
                <CISStatusBadge
                  status={s.current_cis_status}
                  testid="supplier-detail-current-cis-badge"
                />
                <span className="ml-2 text-xs text-sy-grey-600">
                  {labelCurrentCisStatus(s.current_cis_status)}
                </span>
              </DetailRow>
              <DetailRow label="UTR" testid="supplier-detail-utr">
                <SensitiveValue value={s.utr} hidden={!canSensitive} testid="supplier-detail-utr-val" />
              </DetailRow>
            </section>
          )}

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
            <DetailRow label="Company number" testid="supplier-detail-company-number">
              <SensitiveValue value={s.company_number} hidden={!canSensitive} testid="supplier-detail-company-number-val" />
            </DetailRow>
            <DetailRow label="Bank name" testid="supplier-detail-bank-name">
              <SensitiveValue value={s.bank_name} hidden={!canSensitive} testid="supplier-detail-bank-name-val" />
            </DetailRow>
            <DetailRow label="Bank sort code" testid="supplier-detail-sort-code">
              <SensitiveValue value={s.bank_sort_code} hidden={!canSensitive} testid="supplier-detail-sort-code-val" />
            </DetailRow>
            <DetailRow label="Bank account #" testid="supplier-detail-account-number">
              <SensitiveValue value={s.bank_account_no} hidden={!canSensitive} testid="supplier-detail-account-number-val" />
            </DetailRow>
          </section>

          {s.notes && (
            <section data-testid="supplier-detail-notes">
              <div className="text-xs text-sy-grey-700">Notes</div>
              <div className="text-sm whitespace-pre-wrap">{s.notes}</div>
            </section>
          )}
        </TabsContent>

        {showCisTab && (
          <TabsContent value="cis" className="mt-4">
            <CISTab supplierId={s.id} />
          </TabsContent>
        )}

        {showDocsTab && (
          <TabsContent value="documents" className="mt-4">
            <DocumentsTab supplierId={s.id} />
          </TabsContent>
        )}

        {showContractsTab && (
          <TabsContent value="contracts" className="mt-4">
            <div
              className="p-6 text-sm text-sy-grey-600 border border-dashed rounded"
              data-testid="supplier-contracts-placeholder"
            >
              Subcontracts arrive in 2.8-FE.
            </div>
          </TabsContent>
        )}
      </Tabs>
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
