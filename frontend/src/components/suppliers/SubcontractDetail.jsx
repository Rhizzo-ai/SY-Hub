/**
 * <SubcontractDetail/> — Chat 47 (Build Pack 2.8-FE-i §R4.2 + §R4.3).
 *
 * Inline detail panel rendered alongside the SubcontractsList. Owns:
 *   - field display (with sensitive-sum gating via canSensitive)
 *   - the lifecycle action buttons (delegated)
 *   - the "Edit" affordance
 *
 * Reads detail directly from the parent's list-row object initially;
 * also subscribes via `useSubcontract(id)` so we get the freshest view
 * after a mutation invalidates the cache. The hook's invalidation
 * (`onSettled`) is what guarantees status badge resync on 409.
 */
import React, { useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { useSubcontract } from '@/hooks/subcontracts';
import { canEditSubcontract, canViewSubcontractSums } from '@/lib/poCapability';
import { fmtGBP } from '@/lib/poFormat';
import SensitiveValue from '@/components/po/SensitiveValue';

import SubcontractStatusPill from './SubcontractStatusPill';
import SubcontractActionButtons from './SubcontractActionButtons';
import SubcontractFormDialog from './SubcontractFormDialog';
import ValuationsSection from './valuations/ValuationsSection';


function Field({ label, value, className = '', testid }) {
  return (
    <div className={`text-sm ${className}`}>
      <div className="text-xs text-sy-grey-700">{label}</div>
      <div className="tabular-nums" data-testid={testid}>{value}</div>
    </div>
  );
}

function fmtDate(d) {
  if (!d) return '\u2014';
  // backend serialises date as 'YYYY-MM-DD', datetime as ISO.
  return String(d).slice(0, 10);
}

function fmtPct(p) {
  if (p == null) return '\u2014';
  const n = Number(p);
  if (!Number.isFinite(n)) return '\u2014';
  // backend stores Numeric(7,4); show as plain percentage.
  return `${n}%`;
}


export default function SubcontractDetail({ subcontract, supplierId }) {
  const { me } = useAuth();
  const canSensitive = canViewSubcontractSums(me);
  const canEdit = canEditSubcontract(me);

  const [editOpen, setEditOpen] = useState(false);

  // Re-fetch the detail (hook key is per-id); fall back to the row
  // object we were handed by the list. This is the resync mechanism
  // after a 409 — when the list query invalidates we get the latest.
  const detailQ = useSubcontract(subcontract?.id, { enabled: !!subcontract?.id });
  const s = detailQ.data ?? subcontract;

  if (!s) {
    return (
      <div className="p-4 text-sm text-sy-grey-600" data-testid="subcontract-detail-empty">
        Select a subcontract to view its details.
      </div>
    );
  }

  return (
    <div
      className="p-4 border rounded space-y-4"
      data-testid={`subcontract-detail-${s.id}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-sy-grey-700">{s.reference ?? '\u2014'}</div>
          <h3 className="text-lg font-semibold">{s.title ?? '\u2014'}</h3>
          <div className="mt-1"><SubcontractStatusPill status={s.status} testid="subcontract-detail-status" /></div>
        </div>
        {canEdit && (
          <button
            type="button"
            className="px-3 py-1.5 border rounded text-sm"
            onClick={() => setEditOpen(true)}
            data-testid="subcontract-detail-edit-btn"
          >Edit</button>
        )}
      </header>

      <section className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Field
          label="Original contract sum"
          testid="subcontract-detail-original-sum"
          value={
            <SensitiveValue
              value={s.original_contract_sum}
              format={fmtGBP}
              hidden={!canSensitive}
            />
          }
        />
        <Field
          label="Current contract sum"
          testid="subcontract-detail-current-sum"
          value={
            <SensitiveValue
              value={s.current_contract_sum}
              format={fmtGBP}
              hidden={!canSensitive}
            />
          }
        />
        <Field
          label="Retention"
          value={fmtPct(s.retention_pct)}
          testid="subcontract-detail-retention"
        />
        <Field
          label="CIS applies"
          value={s.cis_applies ? 'Yes' : 'No'}
          testid="subcontract-detail-cis-applies"
        />
        <Field label="Start"        value={fmtDate(s.start_on)} testid="subcontract-detail-start" />
        <Field label="End"          value={fmtDate(s.end_on)}   testid="subcontract-detail-end" />
        <Field
          label="Signed at"
          value={s.signed_at ? String(s.signed_at).slice(0, 16).replace('T', ' ') : '\u2014'}
          testid="subcontract-detail-signed-at"
        />
        <Field
          label="Project"
          value={<span className="font-mono text-xs">{s.project_id}</span>}
          testid="subcontract-detail-project"
        />
        <Field
          label="Purchase order"
          value={s.purchase_order_id ? <span className="font-mono text-xs">{s.purchase_order_id}</span> : '\u2014'}
          testid="subcontract-detail-po"
        />
      </section>

      {s.scope_description && (
        <section data-testid="subcontract-detail-scope">
          <div className="text-xs text-sy-grey-700">Scope</div>
          <p className="text-sm whitespace-pre-wrap">{s.scope_description}</p>
        </section>
      )}

      <section className="pt-3 border-t">
        <SubcontractActionButtons subcontract={s} />
      </section>

      {/* ─── Valuations (Chat 48 — Build Pack 2.8-FE-ii) ───────────────
          Mounted below the lifecycle action block. Self-contained:
          owns its own list/detail layout (vertical to dodge B87), and
          gates all of: "New valuation" button (status ∈ {Active,
          Completed} + canCreateValuation), sensitive-sum visibility on
          5 fields, lifecycle buttons, dialogs and payment-notices
          panel. SubcontractDetail does NOT pass any money figures
          through — ValuationsSection talks to its own hooks. */}
      <ValuationsSection subcontract={s} />

      <SubcontractFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        supplierId={supplierId}
        subcontract={s}
      />
    </div>
  );
}
