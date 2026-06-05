/**
 * SupplierDetail — Chat 24 §R5 · Chat 40 §R4.3 · Chat 41 §R4
 *   (Build Pack 2.7-FE-revision).
 *
 * Tabs (rendered per visibility):
 *   - Overview (always): fixed fields, trade, vat-registered, address
 *     block (hidden if every address field is null), sensitive block,
 *     contractor sub-block (CIS registered, current_cis_status badge,
 *     UTR) iff Contractor.
 *   - CIS (iff supplier_type==='Contractor' && cis.view).
 *   - Documents (iff supplier_documents.view).
 *   - Contracts (iff supplier_type==='Contractor'): placeholder panel —
 *     Subcontracts arrive in 2.8-FE.
 *
 * Drops (rev-A backend stopped serving these):
 *   - Default VAT row + label
 *   - CIS sub-type row + label (labelCisSub*) usage
 *
 * Adds (backend has accepted these all along; rev-A surfaced them):
 *   - Trade, VAT registered, Trading name, Contact name
 *   - Address block (line1/2, city, postcode, country)
 *
 * Archive/Restore live in the header; archive navigates back to
 * `/suppliers`, restore stays + invalidates.
 */
import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '@/components/ui/tabs';

import { useAuth } from '@/context/AuthContext';
import {
  useArchiveSupplier, useDeleteSupplier, useUnarchiveSupplier, useSupplier,
} from '@/hooks/purchaseOrders';
import {
  canArchiveSupplier, canDeleteSupplier, canEditSupplier,
  canViewSensitiveSupplier, canViewCIS, canViewDocs,
} from '@/lib/poCapability';
import SensitiveValue from '@/components/po/SensitiveValue';
import CISStatusBadge from '@/components/suppliers/CISStatusBadge';
import CISTab from '@/components/suppliers/CISTab';
import DocumentsTab from '@/components/suppliers/DocumentsTab';
import {
  labelCisStatus, labelCurrentCisStatus,
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
  const del = useDeleteSupplier();

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

  const isContractor = s.supplier_type === 'Contractor';
  const showCisTab = isContractor && canViewCIS(me);
  const showDocsTab = canViewDocs(me);
  const showContractsTab = isContractor;

  const hasAnyAddress = !!(
    s.address_line1 || s.address_line2 || s.city || s.postcode || s.country
  );

  const onArchive = async () => {
    if (!window.confirm(`Archive supplier "${s.name}"?`)) return;
    await archive.mutateAsync(s.id);
    navigate('/suppliers');
  };

  const onRestore = async () => {
    if (!window.confirm(`Restore supplier "${s.name}"?`)) return;
    await unarchive.mutateAsync(s.id);
  };

  // Chat 41 §R-eyeball-2 (Prompt 2.7-FE-revision) — hard delete.
  // Backend returns 204 on success and 409 with a detail message when
  // any linked record blocks the delete. The 409 path surfaces the
  // backend's exact message via toast and does NOT navigate.
  const onDelete = async () => {
    if (!window.confirm(
      `Permanently delete supplier "${s.name}"?\n\n`
      + 'This cannot be undone. If the supplier has any linked records '
      + '(POs, actuals, subcontracts, CIS verifications, documents), '
      + 'the server will refuse and you should archive instead.',
    )) return;
    try {
      await del.mutateAsync(s.id);
      toast.success(`Supplier "${s.name}" deleted.`);
      navigate('/suppliers');
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Delete failed.';
      if (status === 409) {
        toast.error(detail);
      } else {
        toast.error(`Delete failed: ${detail}`);
      }
    }
  };

  return (
    <div className="p-6 max-w-3xl space-y-4" data-testid="supplier-detail">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{s.name}</h1>
          <div className="text-xs text-sy-grey-600" data-testid="supplier-detail-subtitle">
            {s.is_archived ? 'Archived' : 'Active'} · {s.supplier_type ?? 'Supplier'}
            {isContractor && (
              <span data-testid="supplier-detail-subtitle-cis">
                {' · CIS '}{labelCisStatus(s.cis_status)}
              </span>
            )}
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
          {canDeleteSupplier(me) && (
            <button
              type="button" onClick={onDelete}
              disabled={del.isPending}
              className="px-3 py-1.5 rounded border border-red-300 text-sm text-red-800 disabled:opacity-50"
              data-testid="supplier-detail-delete-btn"
            >Delete</button>
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
            <DetailRow label="Trade" testid="supplier-detail-trade"
              value={s.trade ?? '—'} />
            <DetailRow label="VAT registered" testid="supplier-detail-vat-registered"
              value={s.vat_registered ? 'Yes' : 'No'} />
            <DetailRow label="Trading name" testid="supplier-detail-trading-name"
              value={s.trading_name} />
            <DetailRow label="Contact name" testid="supplier-detail-contact-name"
              value={s.contact_name} />
            <DetailRow label="Payment terms" testid="supplier-detail-payment-terms"
              value={s.payment_terms_days != null ? `${s.payment_terms_days} days` : null} />
            <DetailRow label="Contact email" testid="supplier-detail-email" value={s.contact_email} />
            <DetailRow label="Contact phone" testid="supplier-detail-phone" value={s.contact_phone} />
          </section>

          {hasAnyAddress && (
            <section
              className="grid grid-cols-3 gap-2 text-sm p-2 border border-dashed rounded"
              data-testid="supplier-detail-address-block"
            >
              <div className="col-span-3 text-xs text-sy-grey-700">Address</div>
              <DetailRow label="Address line 1" testid="supplier-detail-address-line1"
                value={s.address_line1} />
              <DetailRow label="Address line 2" testid="supplier-detail-address-line2"
                value={s.address_line2} />
              <DetailRow label="City" testid="supplier-detail-city" value={s.city} />
              <DetailRow label="Postcode" testid="supplier-detail-postcode" value={s.postcode} />
              <DetailRow label="Country" testid="supplier-detail-country" value={s.country} />
            </section>
          )}

          {isContractor && (
            <section
              className="grid grid-cols-2 gap-2 text-sm p-2 border border-dashed rounded bg-slate-50"
              data-testid="supplier-detail-contractor-block"
            >
              <div className="col-span-2 text-xs text-sy-grey-700">CIS / contractor</div>
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
