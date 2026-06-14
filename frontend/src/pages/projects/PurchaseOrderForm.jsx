/**
 * PurchaseOrderForm — Chat 24 §R5.
 *
 * Create new draft PO. Edit is currently routed to the same component
 * (PATCH while status='draft' via a future enhancement); for now we
 * scope this to create-only and the detail page handles status-level
 * transitions inline.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import { useCreatePO } from '@/hooks/purchaseOrders';
import { canCreatePO, canViewSensitivePO } from '@/lib/poCapability';
import SupplierSelect from '@/components/po/SupplierSelect';
import POLineEditor from '@/components/po/POLineEditor';

function blankLine() {
  return {
    budget_line_id: '', description: '',
    quantity: '', unit_rate: '', vat_rate: '20',
  };
}

export default function PurchaseOrderForm() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const canSensitive = canViewSensitivePO(me);

  const [supplierId, setSupplierId] = useState('');
  const [budgetId, setBudgetId] = useState('');
  // Pack 3.5 §7.1 — "One front door": chooser between a simple
  // standalone PO and one linked to an existing package. The package
  // path adds an optional package_id field; server validates same-tenant
  // + same-project + UUID-coerce.
  const [createMode, setCreateMode] = useState('simple');
  const [packageId, setPackageId] = useState('');
  const [issueDate, setIssueDate] = useState('');
  const [lines, setLines] = useState([blankLine()]);
  const [error, setError] = useState(null);
  const create = useCreatePO(projectId);

  useEffect(() => {
    // Default issue_date to today.
    if (!issueDate) setIssueDate(new Date().toISOString().slice(0, 10));
  }, [issueDate]);

  if (!canCreatePO(me)) {
    return <div className="p-6 text-sm" data-testid="po-form-forbidden">
      You do not have permission to create purchase orders.
    </div>;
  }
  if (!canSensitive) {
    return <div className="p-6 text-sm" data-testid="po-form-needs-sensitive">
      Creating purchase orders requires pos.view_sensitive — you can see line totals
      while you're entering them. Ask your administrator for that grant.
    </div>;
  }

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!supplierId) { setError('Supplier required.'); return; }
    if (!budgetId)   { setError('Budget id required (paste from budget URL for now).'); return; }
    if (!lines.length) { setError('At least one line required.'); return; }
    const payload = {
      supplier_id: supplierId,
      budget_id: budgetId,
      issue_date: issueDate || null,
      lines: lines.map((l) => ({
        budget_line_id: l.budget_line_id,
        description: l.description || null,
        quantity: Number(l.quantity),
        unit_rate: Number(l.unit_rate),
        vat_rate: Number(l.vat_rate ?? 20),
      })),
    };
    // Pack 3.5 §7.1 — attach the package_id only when the user
    // explicitly chose the "From a package" path AND provided one.
    if (createMode === 'package' && packageId.trim()) {
      payload.package_id = packageId.trim();
    }
    try {
      const po = await create.mutateAsync(payload);
      navigate(`/projects/${projectId}/purchase-orders/${po.id}`);
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Create failed');
    }
  };

  return (
    <form onSubmit={onSubmit} className="p-6 space-y-4" data-testid="po-form">
      <h1 className="text-xl font-semibold">New purchase order</h1>

      {/* Pack 3.5 §7.1 — "One front door" chooser. */}
      <fieldset
        className="rounded border border-slate-200 bg-slate-50 px-4 py-3"
        data-testid="po-form-create-mode"
      >
        <legend className="px-1 text-xs font-medium uppercase tracking-wide text-slate-600">
          How are you creating this PO?
        </legend>
        <div className="mt-1 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-1.5">
            <input
              type="radio"
              name="po-create-mode"
              value="simple"
              checked={createMode === 'simple'}
              onChange={() => { setCreateMode('simple'); setPackageId(''); }}
              data-testid="po-form-mode-simple"
            />
            Simple order (standalone PO)
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="radio"
              name="po-create-mode"
              value="package"
              checked={createMode === 'package'}
              onChange={() => setCreateMode('package')}
              data-testid="po-form-mode-package"
            />
            From a Package (link by package id)
          </label>
        </div>
        {createMode === 'package' && (
          <label className="mt-2 block max-w-md text-sm">
            <span className="text-xs text-slate-600">Package id</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm font-mono"
              value={packageId}
              onChange={(e) => setPackageId(e.target.value)}
              placeholder="Paste the package UUID"
              data-testid="po-form-package-id"
            />
            <span className="mt-1 block text-xs text-slate-500">
              Server enforces same tenant + same project + valid UUID; a
              mismatch returns 422 pre-write.
            </span>
          </label>
        )}
      </fieldset>

      <div className="grid grid-cols-2 gap-3 max-w-2xl">
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Supplier *</span>
          <SupplierSelect
            value={supplierId} onChange={setSupplierId}
            allowCreate testid="po-form-supplier"
            onCreateRequested={() => window.open('/suppliers/new', '_blank')}
          />
        </label>
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Budget id *</span>
          <input
            type="text"
            className="w-full px-2 py-1 border rounded text-sm font-mono"
            value={budgetId} onChange={(e) => setBudgetId(e.target.value)}
            placeholder="Paste from /projects/{id}/budgets/{budget_id}"
            data-testid="po-form-budget-id"
          />
        </label>
      </div>

      <label className="block text-sm max-w-xs">
        <span className="text-xs text-sy-grey-700">Issue date</span>
        <input
          type="date"
          className="w-full px-2 py-1 border rounded text-sm"
          value={issueDate} onChange={(e) => setIssueDate(e.target.value)}
          data-testid="po-form-issue-date"
        />
      </label>

      <section>
        <h2 className="text-sm font-medium mb-1">Lines</h2>
        <POLineEditor
          lines={lines} onChange={setLines}
          testid="po-form-lines"
        />
      </section>

      {error && (
        <div className="text-sm text-red-600" data-testid="po-form-error">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={create.isPending}
          className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm disabled:opacity-50"
          data-testid="po-form-save"
        >Create draft</button>
        <button
          type="button" onClick={() => navigate(-1)}
          className="px-3 py-1.5 rounded border text-sm"
          data-testid="po-form-cancel"
        >Cancel</button>
      </div>
    </form>
  );
}
