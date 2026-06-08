/**
 * <SubcontractFormDialog/> — Chat 47 (Build Pack 2.8-FE-i §R4.4).
 *
 * Create + edit a subcontract. Single dialog, two modes:
 *
 *   mode="create" (no `subcontract` prop)
 *     Required:  Project (via existing ProjectPicker — projects come
 *                from /projects, NOT /v1/projects; the v1 path 404s.
 *                §R0.3 landmine.), Title.
 *     Optional:  Scope, Purchase order, Original contract sum,
 *                Retention %, CIS applies (default on), Start, End.
 *     Fixed:     subcontractor_id = supplierId (no picker — this IS
 *                the supplier's Contracts tab).
 *     MUST NOT send `reference` (backend generates SC-NNNN) or
 *     `status` (defaults to Draft; transitions go via action
 *     endpoints).
 *
 *   mode="edit"  (`subcontract` prop present)
 *     All fields from the SubcontractUpdateBody allowed set ONLY.
 *     `extra:"forbid"` server-side → sending anything else is 422.
 *     `project_id` and `subcontractor_id` are IMMUTABLE after create
 *     so they render as read-only context, never as inputs.
 *     `signed_at` and `signed_by` live ONLY in the edit form (FLAG 2a):
 *     unsigned subcontracts cannot be Activated (backend 409 from
 *     services/subcontracts.py:524-526).
 *
 * Sensitive contract-sum fields render in edit ONLY when the user
 * has `subcontracts.view_sensitive` (the backend returns them as
 * null otherwise — we hide the input entirely so the user doesn't
 * appear to be clearing the field). On create the user types the
 * sum directly; there's no "hidden value" risk.
 *
 * Money input contract:
 *   - String submitted (Pydantic Decimal serialisation is string).
 *   - Client-side: accepts digits + at most one decimal point + ≤2
 *     decimal places. Rejects anything else (the test pin in §R6).
 *   - No float arithmetic anywhere.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import {
  useCreateSubcontract,
  useUpdateSubcontract,
} from '@/hooks/subcontracts';
import { canViewSubcontractSums } from '@/lib/poCapability';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ProjectPicker } from '@/components/ai-capture/ProjectPicker';


// Allowed fields on PATCH (SubcontractUpdateBody, extra:"forbid").
// The form trims to this set before submit; anything else would 422.
const UPDATE_ALLOWED = new Set([
  'title', 'scope_description',
  'original_contract_sum', 'retention_pct', 'cis_applies',
  'start_on', 'end_on',
  'signed_at', 'signed_by',
  'purchase_order_id',
]);

// Money — string in, validated to ≤2dp. Empty string treated as null
// only on edit (clearing); on create we default to "0".
const MONEY_RE = /^-?\d+(\.\d{1,2})?$/;
function isValidMoney(s) {
  if (s == null) return false;
  const t = String(s).trim();
  if (t === '') return false;
  return MONEY_RE.test(t);
}

// Pct — string in, 0..100 with at most 4dp (DB stores Numeric(7,4)).
const PCT_RE = /^-?\d+(\.\d{1,4})?$/;
function isValidPct(s) {
  if (s == null) return false;
  const t = String(s).trim();
  if (t === '') return false;
  if (!PCT_RE.test(t)) return false;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 && n <= 100;
}


export default function SubcontractFormDialog({
  open, onOpenChange,
  supplierId,
  subcontract,  // undefined → create; present → edit
  defaultProjectId,
}) {
  const isEdit = !!subcontract;
  const { me } = useAuth();
  const canSensitive = canViewSubcontractSums(me);

  const create = useCreateSubcontract();
  const update = useUpdateSubcontract(subcontract?.id);

  // ─── Form state ────────────────────────────────────────────────────
  const [projectId, setProjectId]       = useState(defaultProjectId ?? '');
  const [title, setTitle]               = useState('');
  const [scope, setScope]               = useState('');
  const [poId, setPoId]                 = useState('');
  const [contractSum, setContractSum]   = useState('0');
  const [retentionPct, setRetentionPct] = useState('0');
  const [cisApplies, setCisApplies]     = useState(true);
  const [startOn, setStartOn]           = useState('');
  const [endOn, setEndOn]               = useState('');
  // Edit-only:
  const [signedAt, setSignedAt]         = useState(''); // local datetime string
  // signed_by is auto-set to current user when the user ticks "I signed it"
  // — keeps the form simple while letting the user explicitly mark a
  // signed date. Audit row carries the actor regardless.
  const [signedByMe, setSignedByMe]     = useState(false);

  // Reset/seed when dialog opens or when switching the underlying record.
  useEffect(() => {
    if (!open) return;
    if (isEdit) {
      setProjectId(subcontract.project_id ?? '');
      setTitle(subcontract.title ?? '');
      setScope(subcontract.scope_description ?? '');
      setPoId(subcontract.purchase_order_id ?? '');
      setContractSum(
        subcontract.original_contract_sum != null
          ? String(subcontract.original_contract_sum) : '',
      );
      setRetentionPct(
        subcontract.retention_pct != null
          ? String(subcontract.retention_pct) : '0',
      );
      setCisApplies(subcontract.cis_applies !== false);
      setStartOn(subcontract.start_on ?? '');
      setEndOn(subcontract.end_on ?? '');
      // signed_at comes back as ISO datetime; <input type="datetime-local">
      // wants yyyy-mm-ddThh:mm (no timezone), so trim.
      setSignedAt(
        subcontract.signed_at ? String(subcontract.signed_at).slice(0, 16) : '',
      );
      setSignedByMe(!!subcontract.signed_by && subcontract.signed_by === me?.id);
    } else {
      setProjectId(defaultProjectId ?? '');
      setTitle('');
      setScope('');
      setPoId('');
      setContractSum('0');
      setRetentionPct('0');
      setCisApplies(true);
      setStartOn('');
      setEndOn('');
      setSignedAt('');
      setSignedByMe(false);
    }
  }, [open, isEdit, subcontract, defaultProjectId, me?.id]);

  // ─── Validation (client-side; backend is authoritative) ───────────
  const errors = useMemo(() => {
    const e = {};
    if (!isEdit) {
      if (!projectId) e.projectId = 'Project is required.';
    }
    if (!title.trim()) e.title = 'Title is required.';
    if (title.length > 200) e.title = 'Title must be 200 characters or fewer.';
    // Money: required on create (default '0' is valid); on edit, blank
    // means "leave unchanged" — we won't send it.
    if (!isEdit && !isValidMoney(contractSum)) {
      e.contractSum = 'Enter a valid amount (digits, up to 2 decimal places).';
    } else if (isEdit && contractSum !== '' && !isValidMoney(contractSum)) {
      e.contractSum = 'Enter a valid amount or leave blank to keep unchanged.';
    }
    if (!isEdit && !isValidPct(retentionPct)) {
      e.retentionPct = 'Enter a percentage between 0 and 100.';
    } else if (isEdit && retentionPct !== '' && !isValidPct(retentionPct)) {
      e.retentionPct = 'Enter a percentage between 0 and 100.';
    }
    if (startOn && endOn && endOn < startOn) {
      e.endOn = 'End date must be on or after start date.';
    }
    return e;
  }, [isEdit, projectId, title, contractSum, retentionPct, startOn, endOn]);

  const isValid = Object.keys(errors).length === 0;

  // ─── Submit ───────────────────────────────────────────────────────
  const buildCreateBody = () => ({
    // §R4.4 lockdown — no `reference`, no `status`.
    project_id: projectId,
    subcontractor_id: supplierId,
    title: title.trim(),
    scope_description: scope.trim() || null,
    purchase_order_id: poId || null,
    original_contract_sum: contractSum.trim() || '0',
    retention_pct: retentionPct.trim() || '0',
    cis_applies: !!cisApplies,
    start_on: startOn || null,
    end_on: endOn || null,
  });

  const buildPatchBody = () => {
    // Build a candidate body from the form, then trim to UPDATE_ALLOWED.
    // Only include fields that actually CHANGED (PATCH semantics).
    const cand = {};
    const orig = subcontract;
    if (title.trim() !== (orig.title ?? '')) cand.title = title.trim();
    if (scope.trim() !== (orig.scope_description ?? '')) {
      cand.scope_description = scope.trim() || null;
    }
    if (contractSum !== '' && contractSum !== String(orig.original_contract_sum ?? '')) {
      cand.original_contract_sum = contractSum.trim();
    }
    if (retentionPct !== '' && retentionPct !== String(orig.retention_pct ?? '')) {
      cand.retention_pct = retentionPct.trim();
    }
    if (cisApplies !== !!orig.cis_applies) cand.cis_applies = !!cisApplies;
    if ((startOn || null) !== (orig.start_on ?? null)) cand.start_on = startOn || null;
    if ((endOn   || null) !== (orig.end_on   ?? null)) cand.end_on   = endOn   || null;
    // signed_at: datetime-local → ISO (append seconds + Z if absent so
    // the server's pydantic datetime parser accepts it).
    const origSignedAt = orig.signed_at ? String(orig.signed_at).slice(0, 16) : '';
    if (signedAt !== origSignedAt) {
      cand.signed_at = signedAt
        ? new Date(signedAt).toISOString()
        : null;
    }
    // signed_by: if user ticked the "I signed it" box AND signed_at is set,
    // set signed_by = me.id; if they untick OR clear signed_at, null it.
    const desiredSignedBy = (signedByMe && signedAt) ? (me?.id ?? null) : null;
    if (desiredSignedBy !== (orig.signed_by ?? null)) {
      cand.signed_by = desiredSignedBy;
    }
    if ((poId || null) !== (orig.purchase_order_id ?? null)) {
      cand.purchase_order_id = poId || null;
    }
    // Final trim — be defensive against a future field being added to
    // `cand` without being added to UPDATE_ALLOWED. Send only fields the
    // backend explicitly allows.
    const out = {};
    Object.keys(cand).forEach((k) => {
      if (UPDATE_ALLOWED.has(k)) out[k] = cand[k];
    });
    return out;
  };

  const onSubmit = async () => {
    if (!isValid) return;
    try {
      if (isEdit) {
        const body = buildPatchBody();
        if (Object.keys(body).length === 0) {
          toast.info?.('Nothing to save');
          onOpenChange(false);
          return;
        }
        await update.mutateAsync(body);
        toast.success('Subcontract updated');
      } else {
        await create.mutateAsync(buildCreateBody());
        toast.success('Subcontract created');
      }
      onOpenChange(false);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Save failed';
      const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
      if (status === 409) {
        // Build-pack §R4.5 — state error; the hook's onSettled invalidates
        // both the detail and list namespaces so the displayed status
        // resyncs after the toast clears.
        toast.error(text);
      } else if (status === 422) {
        toast.error(text);
      } else if (status === 403) {
        toast.error('You don\u2019t have permission to do that.');
      } else if (status === 404) {
        toast.error('That subcontract no longer exists.');
        onOpenChange(false);
      } else {
        toast.error(text);
      }
    }
  };

  const isPending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="subcontract-form-dialog">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? `Edit subcontract ${subcontract?.reference ?? ''}` : 'New subcontract'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          {/* Project — create only; immutable on edit. */}
          {!isEdit ? (
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Project *</span>
              <ProjectPicker value={projectId} onChange={setProjectId} />
              {errors.projectId && (
                <span className="text-xs text-red-700" data-testid="subcontract-form-error-projectId">
                  {errors.projectId}
                </span>
              )}
            </label>
          ) : (
            <div className="text-xs text-sy-grey-600" data-testid="subcontract-form-project-readonly">
              Project &amp; subcontractor are fixed after creation.
            </div>
          )}

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Title *</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              data-testid="subcontract-form-title"
            />
            {errors.title && (
              <span className="text-xs text-red-700" data-testid="subcontract-form-error-title">
                {errors.title}
              </span>
            )}
          </label>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Scope description</span>
            <Textarea
              rows={3}
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              data-testid="subcontract-form-scope"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Purchase order (optional)</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm font-mono"
              value={poId}
              placeholder="Purchase order UUID (optional)"
              onChange={(e) => setPoId(e.target.value)}
              data-testid="subcontract-form-po-id"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            {/* Contract sum — sensitive on edit (hidden if user can't view sensitive). */}
            {(!isEdit || canSensitive) && (
              <label className="block text-sm">
                <span className="text-xs text-sy-grey-700">
                  Original contract sum (£) {!isEdit && '*'}
                </span>
                <input
                  type="text"
                  inputMode="decimal"
                  className="w-full px-2 py-1 border rounded text-sm tabular-nums"
                  value={contractSum}
                  onChange={(e) => setContractSum(e.target.value)}
                  placeholder="0.00"
                  data-testid="subcontract-form-contract-sum"
                />
                {errors.contractSum && (
                  <span className="text-xs text-red-700" data-testid="subcontract-form-error-contract-sum">
                    {errors.contractSum}
                  </span>
                )}
              </label>
            )}
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Retention %</span>
              <input
                type="text"
                inputMode="decimal"
                className="w-full px-2 py-1 border rounded text-sm tabular-nums"
                value={retentionPct}
                onChange={(e) => setRetentionPct(e.target.value)}
                placeholder="0"
                data-testid="subcontract-form-retention-pct"
              />
              {errors.retentionPct && (
                <span className="text-xs text-red-700" data-testid="subcontract-form-error-retention-pct">
                  {errors.retentionPct}
                </span>
              )}
            </label>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={cisApplies}
              onChange={(e) => setCisApplies(e.target.checked)}
              data-testid="subcontract-form-cis-applies"
            />
            <span>CIS applies to this subcontract</span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Start date</span>
              <input
                type="date"
                className="w-full px-2 py-1 border rounded text-sm"
                value={startOn}
                onChange={(e) => setStartOn(e.target.value)}
                data-testid="subcontract-form-start-on"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">End date</span>
              <input
                type="date"
                className="w-full px-2 py-1 border rounded text-sm"
                value={endOn}
                onChange={(e) => setEndOn(e.target.value)}
                data-testid="subcontract-form-end-on"
              />
              {errors.endOn && (
                <span className="text-xs text-red-700" data-testid="subcontract-form-error-end-on">
                  {errors.endOn}
                </span>
              )}
            </label>
          </div>

          {/* FLAG 2a — signed_at + signed_by are EDIT-ONLY. Activating an
              unsigned subcontract returns 409 with a guidance message
              in <SubcontractActionButtons/>. */}
          {isEdit && (
            <div
              className="grid grid-cols-2 gap-3 p-2 border border-dashed rounded"
              data-testid="subcontract-form-signature-block"
            >
              <div className="col-span-2 text-xs text-sy-grey-700">
                Signature (required before activation)
              </div>
              <label className="block text-sm">
                <span className="text-xs text-sy-grey-700">Signed at</span>
                <input
                  type="datetime-local"
                  className="w-full px-2 py-1 border rounded text-sm"
                  value={signedAt}
                  onChange={(e) => setSignedAt(e.target.value)}
                  data-testid="subcontract-form-signed-at"
                />
              </label>
              <label className="flex items-end gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={signedByMe}
                  onChange={(e) => setSignedByMe(e.target.checked)}
                  disabled={!signedAt}
                  data-testid="subcontract-form-signed-by-me"
                />
                <span>I signed this contract</span>
              </label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="subcontract-form-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!isValid || isPending}
            onClick={onSubmit}
            data-testid="subcontract-form-submit"
          >{isEdit ? 'Save changes' : 'Create subcontract'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
