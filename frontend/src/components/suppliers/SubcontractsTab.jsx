/**
 * <SubcontractsTab/> — Chat 47 (Build Pack 2.8-FE-i §R4.1 + §R5).
 *
 * The supplier-scoped Contracts tab. Inline master-detail layout
 * (list left, selected detail right) — matches the CISTab /
 * DocumentFolderView pattern inside SupplierDetail rather than the
 * POs separate-page pattern. No route changes.
 *
 * Scope fence (Build Pack 2.8-FE-i §R0.1, locked):
 *   This is the SUBCONTRACTS surface ONLY. Valuations, payment
 *   notices, retention movements, and variations are separate later
 *   packs (2.8-FE-ii / 2.8-FE-iii). Do NOT add stubs or placeholders
 *   for them here.
 *
 * Data flow:
 *   - List query is `useSubcontracts({ params: { projectId? } })`.
 *     Backend has no `subcontractor_id` filter → we fetch the visible
 *     set and FILTER client-side by `subcontractor_id === supplierId`.
 *     Surfaced in §R9 backlog: future backend filter to remove the
 *     client-side step at scale.
 *   - Status filter is local state (not URL-bound) because we're
 *     inside a tab inside another route; pushing to the URL would
 *     conflict with the parent supplier-tab querystring.
 *   - "New subcontract" button only shows when canCreateSubcontract.
 *     Per Build Pack §R4.4, project is REQUIRED on create — the form
 *     dialog enforces it via the existing ProjectPicker.
 */
import React, { useMemo, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { useSubcontracts } from '@/hooks/subcontracts';
import {
  canCreateSubcontract, canViewSubcontracts, canViewSubcontractSums,
} from '@/lib/poCapability';
import { fmtGBP } from '@/lib/poFormat';
import SensitiveValue from '@/components/po/SensitiveValue';

import SubcontractStatusPill from './SubcontractStatusPill';
import SubcontractDetail from './SubcontractDetail';
import SubcontractFormDialog from './SubcontractFormDialog';


const STATUS_OPTIONS = ['Draft', 'Active', 'Completed', 'Terminated'];


export default function SubcontractsTab({ supplierId, defaultProjectId }) {
  const { me } = useAuth();
  const [status, setStatus] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);

  const canSensitive = canViewSubcontractSums(me);

  // We don't have a subcontractor_id query param — pull the visible set
  // (filtered server-side by status if provided), then narrow client-side.
  const listQ = useSubcontracts({
    params: status ? { status } : undefined,
    enabled: canViewSubcontracts(me),
  });

  const rows = useMemo(() => {
    const items = listQ.data?.items ?? [];
    return items.filter((s) => s.subcontractor_id === supplierId);
  }, [listQ.data, supplierId]);

  const selected = useMemo(
    () => rows.find((r) => r.id === selectedId) ?? null,
    [rows, selectedId],
  );

  if (!canViewSubcontracts(me)) {
    return (
      <div className="p-4 text-sm" data-testid="subcontracts-tab-forbidden">
        You do not have permission to view subcontracts.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="subcontracts-tab">
      <div className="flex items-end justify-between gap-3">
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Status</span>
          <select
            className="px-2 py-1 border rounded text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            data-testid="subcontracts-tab-status-filter"
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        {canCreateSubcontract(me) && (
          <button
            type="button"
            className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
            onClick={() => setCreateOpen(true)}
            data-testid="subcontracts-tab-new-btn"
          >+ New subcontract</button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {/* List */}
        <div className="md:col-span-2 border rounded" data-testid="subcontracts-tab-list">
          {listQ.isLoading && (
            <div className="p-3 text-sm" data-testid="subcontracts-tab-loading">Loading…</div>
          )}
          {listQ.isError && (
            <div className="p-3 text-sm text-red-700" data-testid="subcontracts-tab-error">
              Failed to load subcontracts.
            </div>
          )}
          {!listQ.isLoading && !listQ.isError && (
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs text-sy-grey-700 border-b">
                  <th className="py-2 px-2 w-28">Ref</th>
                  <th className="py-2 px-2">Title</th>
                  <th className="py-2 px-2 w-28">Status</th>
                  <th className="py-2 px-2 w-28 text-right">Sum</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={4} className="py-3 px-2 text-sy-grey-500" data-testid="subcontracts-tab-empty">
                    No subcontracts for this supplier.
                  </td></tr>
                )}
                {rows.map((r) => {
                  const isActive = r.id === selectedId;
                  return (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedId(r.id)}
                      className={`border-b last:border-0 cursor-pointer ${isActive ? 'bg-sy-teal-50' : 'hover:bg-sy-grey-50'}`}
                      data-testid={`subcontracts-row-${r.id}`}
                    >
                      <td className="py-2 px-2 tabular-nums">{r.reference ?? '\u2014'}</td>
                      <td className="py-2 px-2">{r.title ?? '\u2014'}</td>
                      <td className="py-2 px-2">
                        <SubcontractStatusPill status={r.status} testid={`subcontracts-row-${r.id}-status`} />
                      </td>
                      <td className="py-2 px-2 text-right">
                        <SensitiveValue
                          value={r.current_contract_sum ?? r.original_contract_sum}
                          format={fmtGBP}
                          hidden={!canSensitive}
                          testid={`subcontracts-row-${r.id}-sum`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Detail */}
        <div className="md:col-span-3" data-testid="subcontracts-tab-detail-pane">
          <SubcontractDetail subcontract={selected} supplierId={supplierId} />
        </div>
      </div>

      <SubcontractFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        supplierId={supplierId}
        defaultProjectId={defaultProjectId}
        // mode="create" implicit via undefined `subcontract` prop
      />
    </div>
  );
}
