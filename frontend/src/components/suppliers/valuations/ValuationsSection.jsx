/**
 * <ValuationsSection/> — Chat 48 (Build Pack 2.8-FE-ii §R4.1, §R5).
 *
 * Mount point inside the 2.8-FE-i <SubcontractDetail/>. Renders the
 * list + the selected-row detail. Status filter and selection are
 * owned here (local state — not URL-bound, mirroring SubcontractsTab).
 *
 * Layout decision (B87 mitigation):
 *   We are already nested inside the 2.8-FE-i `md:col-span-3` right
 *   pane of <SubcontractsTab/>. Adding another horizontal split inside
 *   that pane is what triggered B87 in the first place. So we stack
 *   the list ABOVE and the selected-detail BELOW. This:
 *     a) avoids the parent grid collision entirely,
 *     b) gives the detail panel full width inside this pane,
 *     c) plays well on narrow screens (the list table also has its
 *        own min-w-0 / overflow-x-auto wrapper).
 *
 * "New valuation" gating (Build Pack §R4.1):
 *   Visible ONLY when canCreateValuation(me) AND
 *   subcontract.status ∈ {Active, Completed}. Otherwise: hidden, with
 *   a muted hint ("Valuations open once the subcontract is active.").
 *
 * Permissions surface (defence-in-depth):
 *   If the user lacks `subcontract_valuations.view`, render a forbidden
 *   line — the backend will 403, but we don't even fire the request.
 */
import React, { useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import {
  canViewValuations, canCreateValuation,
  SUBCONTRACT_STATUSES_ALLOWING_VALUATIONS,
} from '@/lib/poCapability';

import ValuationsList from './ValuationsList';
import ValuationDetail from './ValuationDetail';
import CreateValuationDialog from './CreateValuationDialog';


export default function ValuationsSection({ subcontract }) {
  const { me } = useAuth();
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedId, setSelectedId]     = useState(null);
  const [createOpen, setCreateOpen]     = useState(false);

  if (!subcontract?.id) return null;

  const canView   = canViewValuations(me);
  const canCreate = canCreateValuation(me)
    && SUBCONTRACT_STATUSES_ALLOWING_VALUATIONS.has(subcontract.status);

  if (!canView) {
    return (
      <section
        className="pt-4 border-t space-y-2"
        data-testid="valuations-section"
      >
        <h3 className="text-base font-semibold">Valuations</h3>
        <p
          className="text-sm text-sy-grey-600"
          data-testid="valuations-section-forbidden"
        >
          You do not have permission to view valuations.
        </p>
      </section>
    );
  }

  // Muted hint when the subcontract isn't yet eligible for valuations.
  const showHint = !SUBCONTRACT_STATUSES_ALLOWING_VALUATIONS.has(subcontract.status);

  return (
    <section
      className="pt-4 border-t space-y-3 min-w-0"
      data-testid="valuations-section"
    >
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="text-base font-semibold">Valuations</h3>
        {canCreate ? (
          <button
            type="button"
            className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
            onClick={() => setCreateOpen(true)}
            data-testid="valuations-section-new-btn"
          >+ New valuation</button>
        ) : showHint ? (
          <span
            className="text-xs text-sy-grey-600"
            data-testid="valuations-section-hint"
          >
            Valuations open once the subcontract is active.
          </span>
        ) : null}
      </header>

      <ValuationsList
        subcontractId={subcontract.id}
        status={statusFilter}
        onStatusChange={setStatusFilter}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />

      {selectedId && (
        <ValuationDetail
          valuationId={selectedId}
          projectId={subcontract.project_id}
        />
      )}

      <CreateValuationDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        subcontractId={subcontract.id}
      />
    </section>
  );
}
