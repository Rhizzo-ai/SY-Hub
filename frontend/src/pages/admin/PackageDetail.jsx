/**
 * PackageDetail — B88 Pack 3 §7 (Chat 53). Route: /admin/packages/:id.
 *
 * Three tabs:
 *   - Lines (editable in draft only)
 *   - Bids (visible from out_to_tender onwards)
 *   - Awards (visible once at least one award exists)
 *
 * Money discipline:
 *   - Client computes net = qty × rate for DISPLAY ONLY.
 *   - Server is the authority — every mutation re-derives net.
 *   - Award form has a hard visual block + disabled submit when
 *     Σ award > package.total_net + £0.01 (mirrors the server guard).
 *   - Every mutation handler surfaces server error via toast +
 *     inline; on 409/422 we refetch the package to resync UI state.
 */
import React, {
  useCallback, useEffect, useMemo, useState,
} from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  ArrowLeft, Plus, Trash2, Send, Ban, AlertTriangle, ExternalLink, X,
} from 'lucide-react';

import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import {
  getPackage, addPackageLine, removePackageLine, sendToTender,
  cancelPackage, deletePackage, inviteBidder, enterBid, declineBid,
  withdrawBid, awardPackage, cancelAward,
} from '@/lib/api/packages';
import { getBudgetGrid } from '@/lib/api/budgets';
import { listSuppliers } from '@/lib/api/suppliers';
import {
  fmtMoney, statusPillProps, bidPillProps, multiplyMoney, sumMoney,
  exceedsTotal, errorMessage,
} from '@/components/packages/packagesHelpers';
import { groupPackageLinesByCostCode } from '@/components/packages/packageLineGroup';

const TEAL = '#0F6A7A';
const ORANGE = '#FC7827';

export default function PackageDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { me, hasPerm } = useAuth();

  const canView = hasPerm('packages.view') || me?.is_super_admin;
  const canViewSensitive =
    hasPerm('packages.view_sensitive') || me?.is_super_admin;
  const canEdit = hasPerm('packages.edit') || me?.is_super_admin;
  const canAward = hasPerm('packages.award') || me?.is_super_admin;
  const canDelete = hasPerm('packages.delete') || me?.is_super_admin;

  const [pkg, setPkg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [activeTab, setActiveTab] = useState('lines');

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getPackage(id);
      setPkg(data);
      // Default tab on first load.
      if (data.status === 'draft') setActiveTab('lines');
      else if (data.awards && data.awards.length > 0) setActiveTab('awards');
      else setActiveTab('bids');
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (canView) reload();
    else setLoading(false);
  }, [canView, reload]);
  /* eslint-enable react-hooks/set-state-in-effect */

  if (!canView) {
    return (
      <div
        className="rounded-lg border border-slate-200 bg-white p-10 text-center"
        data-testid="package-detail-forbidden"
      >
        <AlertTriangle
          className="mx-auto mb-3 text-slate-400"
          size={28}
        />
        Missing <code>packages.view</code>.
      </div>
    );
  }

  if (loading) {
    return (
      <div
        className="p-10 text-center text-slate-500"
        data-testid="package-detail-loading"
      >
        Loading package…
      </div>
    );
  }

  if (loadError) {
    return (
      <div
        className="rounded border border-rose-200 bg-rose-50 p-6 text-rose-900"
        role="alert"
        data-testid="package-detail-load-error"
      >
        {loadError}
        <Button
          variant="outline"
          className="ml-3"
          onClick={reload}
          data-testid="package-detail-retry"
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!pkg) return null;

  const pill = statusPillProps(pkg.status);
  const isDraft = pkg.status === 'draft';
  const isTender = pkg.status === 'out_to_tender';
  const isPartial = pkg.status === 'partially_awarded';
  const showBids = !isDraft;
  const showAwards = (pkg.awards || []).length > 0;
  const canEditLines = canEdit && isDraft;

  return (
    <div data-testid="package-detail" className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => nav('/admin/packages')}
            data-testid="package-back"
            className="mb-2 gap-1"
          >
            <ArrowLeft size={14} /> All packages
          </Button>
          <h1
            className="font-heading text-2xl font-bold"
            style={{ color: TEAL }}
            data-testid="package-detail-title"
          >
            {pkg.reference} — {pkg.title}
          </h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-slate-600">
            <span className="capitalize">{pkg.kind}</span>
            <span
              className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium"
              style={{ backgroundColor: pill.bg, color: pill.fg }}
              data-testid="package-detail-status"
            >
              {pill.label}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="text-right text-sm">
            <div className="text-xs text-slate-500">Total net</div>
            <div
              className="text-xl font-semibold tabular-nums"
              data-testid="package-detail-total-net"
            >
              {fmtMoney(pkg.total_net)}
            </div>
            <div className="mt-1 text-xs text-slate-500">Awarded</div>
            <div
              className="tabular-nums text-slate-700"
              data-testid="package-detail-awarded-net"
            >
              {fmtMoney(pkg.awarded_net)}
            </div>
          </div>
          <PackageActions
            pkg={pkg}
            canEdit={canEdit}
            canDelete={canDelete}
            onChanged={reload}
          />
        </div>
      </div>

      {/* Description */}
      {pkg.description && (
        <div className="rounded border border-slate-200 bg-white p-4 text-sm text-slate-700">
          {pkg.description}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <nav className="flex gap-6" data-testid="package-detail-tabs">
          <TabBtn
            id="lines"
            active={activeTab}
            onClick={() => setActiveTab('lines')}
            label={`Lines (${(pkg.lines || []).length})`}
          />
          {showBids && (
            <TabBtn
              id="bids"
              active={activeTab}
              onClick={() => setActiveTab('bids')}
              label={`Bids (${(pkg.bids || []).length})`}
            />
          )}
          {(showAwards || canAward) && !isDraft && (
            <TabBtn
              id="award"
              active={activeTab}
              onClick={() => setActiveTab('award')}
              label={
                showAwards
                  ? `Awards (${pkg.awards.length})`
                  : 'Award'
              }
            />
          )}
        </nav>
      </div>

      {activeTab === 'lines' && (
        <LinesTab
          pkg={pkg}
          canEdit={canEditLines}
          canViewSensitive={canViewSensitive}
          onChanged={reload}
        />
      )}
      {activeTab === 'bids' && showBids && (
        <BidsTab
          pkg={pkg}
          canEdit={canEdit && (isTender || isPartial)}
          canViewSensitive={canViewSensitive}
          onChanged={reload}
        />
      )}
      {activeTab === 'award' && !isDraft && (
        <AwardTab
          pkg={pkg}
          canAward={canAward}
          canViewSensitive={canViewSensitive}
          onChanged={reload}
        />
      )}
    </div>
  );
}

function TabBtn({ id, active, onClick, label }) {
  const isActive = active === id;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`package-tab-${id}`}
      className={[
        'border-b-2 px-1 pb-2 text-sm font-medium transition-colors',
        isActive
          ? 'border-current text-slate-900'
          : 'border-transparent text-slate-500 hover:text-slate-700',
      ].join(' ')}
      style={isActive ? { borderColor: TEAL, color: TEAL } : undefined}
    >
      {label}
    </button>
  );
}

// ─── Package header actions (send-to-tender / cancel / delete) ────────

function PackageActions({ pkg, canEdit, canDelete, onChanged }) {
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true);
    try {
      await sendToTender(pkg.id);
      toast.success(`${pkg.reference} sent to tender`);
      onChanged?.();
    } catch (err) {
      toast.error(`Send-to-tender failed: ${errorMessage(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const doCancel = async () => {
    const reason = window.prompt('Reason for cancelling this package?');
    if (reason == null) return;
    setBusy(true);
    try {
      await cancelPackage(pkg.id, { reason });
      toast.success(`${pkg.reference} cancelled`);
      onChanged?.();
    } catch (err) {
      toast.error(`Cancel failed: ${errorMessage(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    if (!window.confirm(`Delete ${pkg.reference}? This cannot be undone.`)) {
      return;
    }
    setBusy(true);
    try {
      await deletePackage(pkg.id);
      toast.success(`${pkg.reference} deleted`);
      window.location.assign('/admin/packages');
    } catch (err) {
      toast.error(`Delete failed: ${errorMessage(err)}`);
      setBusy(false);
    }
  };

  return (
    <div className="flex gap-2">
      {canEdit && pkg.status === 'draft' && (
        <Button
          size="sm"
          disabled={busy || (pkg.lines || []).length === 0}
          onClick={send}
          data-testid="package-send-to-tender"
          className="gap-1"
          style={{ backgroundColor: TEAL, color: 'white' }}
        >
          <Send size={14} /> Send to tender
        </Button>
      )}
      {canEdit &&
        pkg.status !== 'cancelled' &&
        pkg.status !== 'awarded' && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={doCancel}
            data-testid="package-cancel"
            className="gap-1"
          >
            <Ban size={14} /> Cancel
          </Button>
        )}
      {canDelete &&
        (pkg.status === 'draft' || pkg.status === 'cancelled') && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={doDelete}
            data-testid="package-delete"
            className="gap-1 text-rose-700"
          >
            <Trash2 size={14} /> Delete
          </Button>
        )}
    </div>
  );
}

// ─── Lines tab ────────────────────────────────────────────────────────

function LinesTab({ pkg, canEdit, canViewSensitive, onChanged }) {
  const [showAdd, setShowAdd] = useState(false);
  const [adding, setAdding] = useState(false);
  const [budgetLines, setBudgetLines] = useState([]);
  const [budgetLoadError, setBudgetLoadError] = useState(null);
  const [picked, setPicked] = useState('');

  useEffect(() => {
    if (!showAdd) return;
    let cancelled = false;
    (async () => {
      try {
        const grid = await getBudgetGrid(pkg.budget_id);
        if (cancelled) return;
        // Flatten the grouped tree into a list of leaf budget_lines.
        const lines = [];
        const usedIds = new Set(
          (pkg.lines || []).map((l) => l.budget_line_id),
        );
        function walk(node) {
          if (Array.isArray(node)) {
            node.forEach(walk);
            return;
          }
          if (node?.lines) node.lines.forEach(walk);
          if (node?.children) node.children.forEach(walk);
          if (node?.subgroups) node.subgroups.forEach(walk);
          if (node?.groups) node.groups.forEach(walk);
          if (node?.id && (node.cost_code || node.line_description)) {
            if (!usedIds.has(node.id)) lines.push(node);
          }
        }
        if (grid?.groups) walk(grid.groups);
        else if (grid?.lines) walk(grid.lines);
        else if (Array.isArray(grid)) walk(grid);
        else walk(grid);
        setBudgetLines(lines);
      } catch (err) {
        if (!cancelled) setBudgetLoadError(errorMessage(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showAdd, pkg.budget_id, pkg.lines]);

  const onAddLine = async () => {
    if (!picked) return;
    setAdding(true);
    try {
      await addPackageLine(pkg.id, { budget_line_id: picked });
      toast.success('Line added');
      setShowAdd(false);
      setPicked('');
      onChanged?.();
    } catch (err) {
      toast.error(`Add line failed: ${errorMessage(err)}`);
    } finally {
      setAdding(false);
    }
  };

  const onRemoveLine = async (lineId) => {
    if (!window.confirm('Remove this package line?')) return;
    try {
      await removePackageLine(pkg.id, lineId);
      toast.success('Line removed');
      onChanged?.();
    } catch (err) {
      toast.error(`Remove failed: ${errorMessage(err)}`);
    }
  };

  return (
    <div data-testid="package-lines-tab" className="space-y-4">
      {canEdit && (
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => setShowAdd(true)}
            data-testid="package-add-line"
            className="gap-1"
            style={{ backgroundColor: TEAL, color: 'white' }}
          >
            <Plus size={14} /> Add line
          </Button>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-semibold">#</th>
              <th className="px-4 py-3 font-semibold">Cost code</th>
              <th className="px-4 py-3 font-semibold">Description</th>
              <th className="px-4 py-3 text-right font-semibold">Qty</th>
              <th className="px-4 py-3 font-semibold">Unit</th>
              <th className="px-4 py-3 text-right font-semibold">Rate</th>
              <th className="px-4 py-3 text-right font-semibold">Net</th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {(pkg.lines || []).length === 0 && (
              <tr>
                <td
                  colSpan={canEdit ? 8 : 7}
                  className="px-4 py-12 text-center text-slate-500"
                  data-testid="package-lines-empty"
                >
                  No lines yet. Add at least one before sending to tender.
                </td>
              </tr>
            )}
            {/* Pack 3.5 §5.2 — group by cost_code, dotted-code sort,
                per-group net subtotal row. */}
            {groupPackageLinesByCostCode(pkg.lines || []).map((g) => (
              <React.Fragment key={`grp-${g.code}`}>
                <tr
                  className="bg-slate-100/80 border-t border-slate-200"
                  data-testid={`package-line-group-header-${g.code}`}
                >
                  <td
                    colSpan={canEdit ? 8 : 7}
                    className="px-4 py-2 font-semibold text-slate-800"
                  >
                    <span className="font-mono text-xs text-slate-600 mr-2">
                      {g.code}
                    </span>
                    {g.name || (
                      <span className="italic text-slate-500">
                        (no cost-code name)
                      </span>
                    )}
                  </td>
                </tr>
                {g.lines.map((ln) => (
                  <tr
                    key={ln.id}
                    className="border-t border-slate-100"
                    data-testid={`package-line-row-${ln.line_number}`}
                  >
                    <td className="px-4 py-2 text-slate-500">
                      {ln.line_number}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-slate-700">
                      {ln.cost_code}
                    </td>
                    <td className="px-4 py-2 text-slate-800">
                      {ln.description}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {ln.quantity}
                    </td>
                    <td className="px-4 py-2 text-slate-600">
                      {ln.unit || '\u2014'}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {fmtMoney(ln.budgeted_unit_rate)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums font-medium">
                      {fmtMoney(ln.budgeted_net_amount)}
                    </td>
                    {canEdit && (
                      <td className="px-4 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => onRemoveLine(ln.id)}
                          data-testid={`package-line-remove-${ln.line_number}`}
                          className="rounded p-1 text-rose-600 hover:bg-rose-50"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
                <tr
                  className="bg-slate-50 border-t border-slate-200"
                  data-testid={`package-line-group-subtotal-${g.code}`}
                >
                  <td
                    colSpan={canEdit ? 6 : 5}
                    className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-500"
                  >
                    Subtotal {g.code}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold text-slate-900">
                    {fmtMoney(g.subtotalNet)}
                  </td>
                  {canEdit && <td />}
                </tr>
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
          role="dialog"
          data-testid="package-add-line-dialog"
        >
          <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-heading text-lg font-semibold">
                Add package line
              </h3>
              <button
                type="button"
                onClick={() => setShowAdd(false)}
                className="rounded p-1 text-slate-500 hover:bg-slate-100"
                data-testid="package-add-line-close"
              >
                <X size={18} />
              </button>
            </div>
            {budgetLoadError && (
              <div
                className="mb-3 rounded border border-rose-200 bg-rose-50 p-2 text-sm text-rose-900"
                role="alert"
              >
                {budgetLoadError}
              </div>
            )}
            <label className="block">
              <span className="block text-xs font-medium text-slate-600">
                Budget line
              </span>
              <select
                value={picked}
                onChange={(e) => setPicked(e.target.value)}
                data-testid="package-add-line-select"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">— select —</option>
                {budgetLines.map((bl) => (
                  <option key={bl.id} value={bl.id}>
                    {(bl.cost_code || bl.code || '')} — {bl.line_description || bl.description}
                  </option>
                ))}
              </select>
              {budgetLines.length === 0 && !budgetLoadError && (
                <span className="mt-1 block text-xs text-slate-500">
                  No remaining budget lines to add.
                </span>
              )}
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setShowAdd(false)}
              >
                Cancel
              </Button>
              <Button
                onClick={onAddLine}
                disabled={!picked || adding}
                data-testid="package-add-line-submit"
                style={{ backgroundColor: TEAL, color: 'white' }}
              >
                {adding ? 'Adding…' : 'Add line'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Bids tab ─────────────────────────────────────────────────────────

function BidsTab({ pkg, canEdit, canViewSensitive, onChanged }) {
  const [inviteOpen, setInviteOpen] = useState(false);
  const [enterFor, setEnterFor] = useState(null); // bid id

  return (
    <div data-testid="package-bids-tab" className="space-y-4">
      {canEdit && (
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => setInviteOpen(true)}
            data-testid="package-invite-bidder"
            className="gap-1"
            style={{ backgroundColor: TEAL, color: 'white' }}
          >
            <Plus size={14} /> Invite bidder
          </Button>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-semibold">Bidder</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 text-right font-semibold">
                Total net
              </th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {(pkg.bids || []).length === 0 && (
              <tr>
                <td
                  colSpan={canEdit ? 4 : 3}
                  className="px-4 py-12 text-center text-slate-500"
                  data-testid="package-bids-empty"
                >
                  No bidders invited yet.
                </td>
              </tr>
            )}
            {(pkg.bids || []).map((b) => (
              <BidRow
                key={b.id}
                pkg={pkg}
                bid={b}
                canEdit={canEdit}
                onEnter={() => setEnterFor(b.id)}
                onChanged={onChanged}
              />
            ))}
          </tbody>
        </table>
      </div>

      {inviteOpen && (
        <InviteBidderDialog
          pkg={pkg}
          onClose={() => setInviteOpen(false)}
          onInvited={() => {
            setInviteOpen(false);
            onChanged?.();
          }}
        />
      )}

      {enterFor && (
        <EnterBidDialog
          pkg={pkg}
          bid={pkg.bids.find((b) => b.id === enterFor)}
          onClose={() => setEnterFor(null)}
          onSaved={() => {
            setEnterFor(null);
            onChanged?.();
          }}
        />
      )}
    </div>
  );
}

function BidRow({ pkg, bid, canEdit, onEnter, onChanged }) {
  const pill = bidPillProps(bid.status);
  const [supplierName, setSupplierName] = useState(null);
  useEffect(() => {
    // Best-effort fetch for the supplier name; ignore errors.
    api
      .get(`/v1/suppliers/${bid.supplier_id}`)
      .then((r) => setSupplierName(r.data?.name || null))
      .catch(() => {});
  }, [bid.supplier_id]);

  const action = async (fn, label) => {
    try {
      await fn(bid.id);
      toast.success(`Bid ${label}`);
      onChanged?.();
    } catch (err) {
      toast.error(`${label} failed: ${errorMessage(err)}`);
    }
  };

  return (
    <tr
      className="border-t border-slate-100"
      data-testid={`package-bid-row-${bid.id}`}
    >
      <td className="px-4 py-2 text-slate-900">
        {supplierName || (
          <span className="font-mono text-xs text-slate-500">
            {bid.supplier_id.slice(0, 8)}…
          </span>
        )}
      </td>
      <td className="px-4 py-2">
        <span
          className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium"
          style={{ backgroundColor: pill.bg, color: pill.fg }}
        >
          {pill.label}
        </span>
      </td>
      <td className="px-4 py-2 text-right tabular-nums">
        {fmtMoney(bid.total_net)}
      </td>
      {canEdit && (
        <td className="space-x-2 px-4 py-2 text-right">
          {(bid.status === 'invited' || bid.status === 'received') && (
            <Button
              size="sm"
              variant="outline"
              onClick={onEnter}
              data-testid={`bid-enter-${bid.id}`}
            >
              {bid.status === 'received' ? 'Edit bid' : 'Enter bid'}
            </Button>
          )}
          {bid.status === 'invited' && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => action(declineBid, 'declined')}
              data-testid={`bid-decline-${bid.id}`}
            >
              Decline
            </Button>
          )}
          {bid.status === 'received' && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => action(withdrawBid, 'withdrawn')}
              data-testid={`bid-withdraw-${bid.id}`}
            >
              Withdraw
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}

function InviteBidderDialog({ pkg, onClose, onInvited }) {
  const [suppliers, setSuppliers] = useState([]);
  const [supplierId, setSupplierId] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    listSuppliers({ params: { limit: 200 } })
      .then((data) => {
        // Pack 3.5 §6.3 — kind-aware bidder filter (server is the
        // ultimate authority — `_supplier_kind_guard` will 422 anything
        // we let through; this just keeps the UI honest).
        const items = (data?.items || data || []).filter((s) => {
          if (pkg.kind === 'subcontract') {
            return s.supplier_type === 'Contractor';
          }
          if (pkg.kind === 'materials') {
            return ['Supplier', 'Contractor'].includes(s.supplier_type);
          }
          if (pkg.kind === 'consultant') {
            return s.supplier_type === 'Consultant';
          }
          return false;
        });
        setSuppliers(items);
      })
      .catch((e) => setErr(errorMessage(e)));
  }, [pkg.kind]);

  const onSubmit = async (e) => {
    e?.preventDefault();
    if (!supplierId) return;
    setBusy(true);
    setErr(null);
    try {
      await inviteBidder(pkg.id, { supplier_id: supplierId });
      toast.success('Bidder invited');
      onInvited?.();
    } catch (e2) {
      setErr(errorMessage(e2));
      toast.error(`Invite failed: ${errorMessage(e2)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
      role="dialog"
      data-testid="invite-bidder-dialog"
    >
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-heading text-lg font-semibold">
            Invite bidder
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
          >
            <X size={18} />
          </button>
        </div>
        <label className="block">
          <span className="block text-xs font-medium text-slate-600">
            Supplier{' '}
            {pkg.kind === 'subcontract'
              ? '(Contractor only — CIS counterparty)'
              : pkg.kind === 'consultant'
                ? '(Consultant only)'
                : '(Supplier / Contractor)'}
          </span>
          <select
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            data-testid="invite-bidder-select"
            required
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">— select —</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.supplier_type})
              </option>
            ))}
          </select>
        </label>
        {err && (
          <div
            className="mt-3 rounded border border-rose-200 bg-rose-50 p-2 text-sm text-rose-900"
            role="alert"
            data-testid="invite-bidder-error"
          >
            {err}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!supplierId || busy}
            data-testid="invite-bidder-submit"
            style={{ backgroundColor: TEAL, color: 'white' }}
          >
            {busy ? 'Inviting…' : 'Invite'}
          </Button>
        </div>
      </form>
    </div>
  );
}

function EnterBidDialog({ pkg, bid, onClose, onSaved }) {
  const [rates, setRates] = useState(() => {
    const initial = {};
    (bid?.lines || []).forEach((bl) => {
      initial[bl.package_line_id] = bl.quoted_unit_rate || '';
    });
    // Ensure every package line is represented.
    (pkg.lines || []).forEach((ln) => {
      if (!(ln.id in initial)) initial[ln.id] = '';
    });
    return initial;
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const onSubmit = async (e) => {
    e?.preventDefault();
    const lines = Object.entries(rates)
      .filter(([_, v]) => v !== '' && v != null)
      .map(([package_line_id, quoted_unit_rate]) => ({
        package_line_id,
        quoted_unit_rate: String(quoted_unit_rate),
      }));
    if (lines.length === 0) {
      setErr('Enter at least one rate.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await enterBid(bid.id, { lines });
      toast.success('Bid recorded');
      onSaved?.();
    } catch (e2) {
      setErr(errorMessage(e2));
      toast.error(`Save bid failed: ${errorMessage(e2)}`);
    } finally {
      setBusy(false);
    }
  };

  const totalLive = sumMoney(
    (pkg.lines || []).map((ln) =>
      multiplyMoney(ln.quantity, rates[ln.id] || 0),
    ),
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
      role="dialog"
      data-testid="enter-bid-dialog"
    >
      <form
        onSubmit={onSubmit}
        className="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-heading text-lg font-semibold">
            Enter bid
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
          >
            <X size={18} />
          </button>
        </div>
        <p className="mb-3 text-xs text-slate-500">
          Enter rate per line — net is computed server-side from
          qty × rate. Client preview shown only.
        </p>
        <div className="max-h-72 overflow-y-auto rounded border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Line</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-right">Rate</th>
                <th className="px-3 py-2 text-right">Net (preview)</th>
              </tr>
            </thead>
            <tbody>
              {(pkg.lines || []).map((ln) => {
                const net = multiplyMoney(ln.quantity, rates[ln.id] || 0);
                return (
                  <tr
                    key={ln.id}
                    className="border-t border-slate-100"
                    data-testid={`enter-bid-line-${ln.line_number}`}
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium">{ln.description}</div>
                      <div className="text-xs text-slate-500">
                        {ln.cost_code}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {ln.quantity}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <input
                        type="number"
                        min="0"
                        step="0.0001"
                        value={rates[ln.id] || ''}
                        onChange={(e) =>
                          setRates({
                            ...rates,
                            [ln.id]: e.target.value,
                          })
                        }
                        data-testid={`enter-bid-rate-${ln.line_number}`}
                        className="w-28 rounded border border-slate-300 px-2 py-1 text-right text-sm"
                      />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {fmtMoney(net)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="bg-slate-50">
                <td colSpan={3} className="px-3 py-2 text-right font-medium">
                  Total (preview)
                </td>
                <td
                  className="px-3 py-2 text-right font-semibold tabular-nums"
                  data-testid="enter-bid-total-preview"
                >
                  {fmtMoney(totalLive)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        {err && (
          <div
            className="mt-3 rounded border border-rose-200 bg-rose-50 p-2 text-sm text-rose-900"
            role="alert"
            data-testid="enter-bid-error"
          >
            {err}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={busy}
            data-testid="enter-bid-submit"
            style={{ backgroundColor: TEAL, color: 'white' }}
          >
            {busy ? 'Saving…' : 'Save bid'}
          </Button>
        </div>
      </form>
    </div>
  );
}

// ─── Award tab ────────────────────────────────────────────────────────

function AwardTab({ pkg, canAward, canViewSensitive, onChanged }) {
  const [showForm, setShowForm] = useState(false);
  const activeAwards = (pkg.awards || []).filter(
    (a) => a.status === 'active',
  );

  const onCancelAward = async (award) => {
    const reason = window.prompt('Reason for cancelling this award?');
    if (!reason || !reason.trim()) {
      toast.error('Reason is required to cancel an award.');
      return;
    }
    try {
      await cancelAward(award.id, { reason: reason.trim() });
      toast.success('Award cancelled');
      onChanged?.();
    } catch (err) {
      toast.error(`Cancel award failed: ${errorMessage(err)}`);
    }
  };

  return (
    <div data-testid="package-award-tab" className="space-y-4">
      {canAward && pkg.status !== 'awarded' && pkg.status !== 'cancelled' && (
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => setShowForm(true)}
            data-testid="package-award-open"
            className="gap-1"
            style={{ backgroundColor: ORANGE, color: 'white' }}
          >
            <Plus size={14} /> Award winner(s)
          </Button>
        </div>
      )}

      {/* Existing awards table */}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-semibold">Supplier</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 text-right font-semibold">
                Awarded net
              </th>
              <th className="px-4 py-3 font-semibold">Downstream</th>
              {canAward && <th />}
            </tr>
          </thead>
          <tbody>
            {(pkg.awards || []).length === 0 && (
              <tr>
                <td
                  colSpan={canAward ? 5 : 4}
                  className="px-4 py-12 text-center text-slate-500"
                  data-testid="package-awards-empty"
                >
                  No awards yet.
                </td>
              </tr>
            )}
            {(pkg.awards || []).map((aw) => (
              <AwardRow
                key={aw.id}
                aw={aw}
                canAward={canAward}
                onCancel={() => onCancelAward(aw)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <AwardFormDialog
          pkg={pkg}
          onClose={() => setShowForm(false)}
          onAwarded={() => {
            setShowForm(false);
            onChanged?.();
          }}
        />
      )}
    </div>
  );
}

function AwardRow({ aw, canAward, onCancel }) {
  const [supplierName, setSupplierName] = useState(null);
  useEffect(() => {
    api
      .get(`/v1/suppliers/${aw.supplier_id}`)
      .then((r) => setSupplierName(r.data?.name || null))
      .catch(() => {});
  }, [aw.supplier_id]);

  const downstreamLink = aw.created_purchase_order_id ? (
    <a
      href={`/purchase-orders/${aw.created_purchase_order_id}`}
      className="inline-flex items-center gap-1 text-sm text-blue-700 hover:underline"
      data-testid={`award-po-link-${aw.id}`}
    >
      PO <ExternalLink size={12} />
    </a>
  ) : aw.created_subcontract_id ? (
    <a
      href={`/subcontracts/${aw.created_subcontract_id}`}
      className="inline-flex items-center gap-1 text-sm text-blue-700 hover:underline"
      data-testid={`award-sc-link-${aw.id}`}
    >
      Subcontract <ExternalLink size={12} />
    </a>
  ) : (
    <span className="text-xs text-slate-400">{'\u2014'}</span>
  );

  const pill =
    aw.status === 'active'
      ? { label: 'Active', bg: '#D1FAE5', fg: '#065F46' }
      : { label: 'Cancelled', bg: '#FEE2E2', fg: '#991B1B' };

  return (
    <tr
      className="border-t border-slate-100"
      data-testid={`package-award-row-${aw.id}`}
    >
      <td className="px-4 py-2 text-slate-900">
        {supplierName || (
          <span className="font-mono text-xs text-slate-500">
            {aw.supplier_id.slice(0, 8)}…
          </span>
        )}
      </td>
      <td className="px-4 py-2">
        <span
          className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium"
          style={{ backgroundColor: pill.bg, color: pill.fg }}
        >
          {pill.label}
        </span>
      </td>
      <td className="px-4 py-2 text-right tabular-nums">
        {fmtMoney(aw.awarded_net)}
      </td>
      <td className="px-4 py-2">{downstreamLink}</td>
      {canAward && (
        <td className="px-4 py-2 text-right">
          {aw.status === 'active' && (
            <Button
              size="sm"
              variant="outline"
              onClick={onCancel}
              data-testid={`award-cancel-${aw.id}`}
            >
              Cancel award
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}

function AwardFormDialog({ pkg, onClose, onAwarded }) {
  // Allow split awards across multiple suppliers/bids. The form gathers
  // one "spec" per supplier; each spec defines per-line quantity+rate.
  const [nextKey, setNextKey] = useState(2);
  const makeSpec = useCallback(
    (key) => ({
      key: `spec-${key}`,
      supplier_id: '',
      source_bid_id: '', // '' → fast-track (null)
      lines: (pkg.lines || []).map((ln) => ({
        package_line_id: ln.id,
        quantity: '',
        awarded_unit_rate: '',
      })),
    }),
    [pkg.lines],
  );
  const [specs, setSpecs] = useState(() => [makeSpec(1)]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const receivedBids = (pkg.bids || []).filter(
    (b) => b.status === 'received',
  );
  const supplierOptions = useMemo(() => {
    const map = new Map();
    receivedBids.forEach((b) => map.set(b.supplier_id, b));
    return Array.from(map.values());
  }, [receivedBids]);

  const totalNew = useMemo(() => {
    let total = 0;
    specs.forEach((s) => {
      s.lines.forEach((ln) => {
        const n = multiplyMoney(ln.quantity || 0, ln.awarded_unit_rate || 0);
        total += Number(n || 0);
      });
    });
    return Math.round(total * 100) / 100;
  }, [specs]);

  const currentAwarded = Number(pkg.awarded_net || 0);
  const totalAfter = currentAwarded + totalNew;
  const cap = Number(pkg.total_net || 0);
  const overTotal = totalAfter > cap + 0.01;

  const canSubmit =
    !busy &&
    !overTotal &&
    specs.length > 0 &&
    specs.every(
      (s) =>
        s.supplier_id &&
        s.lines.some(
          (ln) => Number(ln.quantity || 0) > 0 && Number(ln.awarded_unit_rate || 0) >= 0,
        ),
    );

  const setSpec = (i, patch) => {
    setSpecs((cur) => cur.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  };

  const setSpecLine = (i, j, patch) => {
    setSpecs((cur) =>
      cur.map((s, idx) =>
        idx !== i
          ? s
          : {
              ...s,
              lines: s.lines.map((ln, ldx) =>
                ldx === j ? { ...ln, ...patch } : ln,
              ),
            },
      ),
    );
  };

  const onApplyBidRates = (i, bidId) => {
    const bid = pkg.bids.find((b) => b.id === bidId);
    if (!bid) return;
    setSpecs((cur) =>
      cur.map((s, idx) => {
        if (idx !== i) return s;
        const lines = s.lines.map((ln) => {
          const bl = (bid.lines || []).find(
            (x) => x.package_line_id === ln.package_line_id,
          );
          return {
            ...ln,
            awarded_unit_rate: bl ? String(bl.quoted_unit_rate || '') : '',
            quantity:
              ln.quantity ||
              String(
                (pkg.lines.find((l) => l.id === ln.package_line_id) || {})
                  .quantity || '',
              ),
          };
        });
        return {
          ...s,
          supplier_id: bid.supplier_id,
          source_bid_id: bidId,
          lines,
        };
      }),
    );
  };

  const onSubmit = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const awards = specs.map((s) => ({
        supplier_id: s.supplier_id,
        source_bid_id: s.source_bid_id || null,
        lines: s.lines
          .filter((ln) => Number(ln.quantity || 0) > 0)
          .map((ln) => ({
            package_line_id: ln.package_line_id,
            quantity: String(ln.quantity),
            awarded_unit_rate: String(ln.awarded_unit_rate || 0),
          })),
      }));
      await awardPackage(pkg.id, { awards });
      toast.success('Award recorded — downstream PO/SC created');
      onAwarded?.();
    } catch (e2) {
      const msg = errorMessage(e2);
      setErr(msg);
      toast.error(`Award failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4 py-8"
      role="dialog"
      data-testid="award-form-dialog"
    >
      <form
        onSubmit={onSubmit}
        className="max-h-full w-full max-w-3xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-heading text-lg font-semibold">
            Award package
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mb-3 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
          <div className="flex justify-between">
            <span>Package total</span>
            <span className="font-medium tabular-nums">
              {fmtMoney(pkg.total_net)}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Already awarded</span>
            <span className="tabular-nums">{fmtMoney(currentAwarded)}</span>
          </div>
          <div className="flex justify-between">
            <span>This award (preview)</span>
            <span className="tabular-nums">{fmtMoney(totalNew)}</span>
          </div>
          <div className="mt-1 flex justify-between border-t border-slate-200 pt-1 font-semibold">
            <span>Total after</span>
            <span
              className="tabular-nums"
              data-testid="award-form-total-after"
              style={overTotal ? { color: '#B91C1C' } : undefined}
            >
              {fmtMoney(totalAfter)}
            </span>
          </div>
          {overTotal && (
            <div
              className="mt-2 flex items-center gap-2 rounded border border-rose-300 bg-rose-50 p-2 text-xs text-rose-900"
              role="alert"
              data-testid="award-form-over-total-block"
            >
              <AlertTriangle size={14} />
              Total exceeds package by{' '}
              {fmtMoney(totalAfter - cap)} — submission blocked. Server
              enforces this guard with £0.01 tolerance.
            </div>
          )}
        </div>

        {specs.map((spec, i) => (
          <div
            key={spec.key}
            className="mb-3 rounded border border-slate-200 p-3"
            data-testid={`award-spec-${i}`}
          >
            <div className="mb-2 flex items-center justify-between">
              <strong className="text-sm">Award #{i + 1}</strong>
              {specs.length > 1 && (
                <button
                  type="button"
                  onClick={() =>
                    setSpecs((cur) => cur.filter((_, idx) => idx !== i))
                  }
                  className="rounded p-1 text-rose-600 hover:bg-rose-50"
                  data-testid={`award-spec-remove-${i}`}
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="mb-2 grid grid-cols-2 gap-2">
              <label className="block">
                <span className="block text-xs font-medium text-slate-600">
                  Supplier (received bids)
                </span>
                <select
                  value={spec.supplier_id}
                  onChange={(e) =>
                    setSpec(i, { supplier_id: e.target.value, source_bid_id: '' })
                  }
                  data-testid={`award-spec-supplier-${i}`}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                >
                  <option value="">— select —</option>
                  {supplierOptions.map((b) => (
                    <option key={b.id} value={b.supplier_id}>
                      {b.supplier_id.slice(0, 8)}… ({fmtMoney(b.total_net)})
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-slate-600">
                  Source bid (or fast-track)
                </span>
                <select
                  value={spec.source_bid_id}
                  onChange={(e) => onApplyBidRates(i, e.target.value)}
                  data-testid={`award-spec-bid-${i}`}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                >
                  <option value="">Fast-track (no source bid)</option>
                  {(pkg.bids || [])
                    .filter(
                      (b) =>
                        b.status === 'received' &&
                        (!spec.supplier_id ||
                          b.supplier_id === spec.supplier_id),
                    )
                    .map((b) => (
                      <option key={b.id} value={b.id}>
                        bid {b.id.slice(0, 8)}… ({fmtMoney(b.total_net)})
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-2 py-1">Line</th>
                    <th className="px-2 py-1 text-right">Available</th>
                    <th className="px-2 py-1 text-right">Award qty</th>
                    <th className="px-2 py-1 text-right">Rate</th>
                    <th className="px-2 py-1 text-right">Net</th>
                  </tr>
                </thead>
                <tbody>
                  {spec.lines.map((ln, j) => {
                    const pkgLine = pkg.lines.find(
                      (l) => l.id === ln.package_line_id,
                    );
                    const net = multiplyMoney(
                      ln.quantity || 0,
                      ln.awarded_unit_rate || 0,
                    );
                    return (
                      <tr
                        key={ln.package_line_id}
                        className="border-t border-slate-100"
                      >
                        <td className="px-2 py-1">
                          {pkgLine?.description}
                          <div className="text-[10px] text-slate-500">
                            {pkgLine?.cost_code}
                          </div>
                        </td>
                        <td className="px-2 py-1 text-right tabular-nums">
                          {pkgLine?.quantity}
                        </td>
                        <td className="px-2 py-1 text-right">
                          <input
                            type="number"
                            min="0"
                            step="0.0001"
                            value={ln.quantity}
                            onChange={(e) =>
                              setSpecLine(i, j, { quantity: e.target.value })
                            }
                            data-testid={`award-spec-${i}-qty-${j}`}
                            className="w-24 rounded border border-slate-300 px-1 py-0.5 text-right text-xs"
                          />
                        </td>
                        <td className="px-2 py-1 text-right">
                          <input
                            type="number"
                            min="0"
                            step="0.0001"
                            value={ln.awarded_unit_rate}
                            onChange={(e) =>
                              setSpecLine(i, j, {
                                awarded_unit_rate: e.target.value,
                              })
                            }
                            data-testid={`award-spec-${i}-rate-${j}`}
                            className="w-24 rounded border border-slate-300 px-1 py-0.5 text-right text-xs"
                          />
                        </td>
                        <td className="px-2 py-1 text-right tabular-nums">
                          {fmtMoney(net)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))}

        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setSpecs((cur) => [...cur, makeSpec(nextKey)]);
            setNextKey((n) => n + 1);
          }}
          data-testid="award-add-spec"
          className="mb-3 gap-1"
          size="sm"
        >
          <Plus size={14} /> Add another supplier
        </Button>

        {err && (
          <div
            className="mb-3 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
            role="alert"
            data-testid="award-form-error"
          >
            {err}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!canSubmit}
            data-testid="award-form-submit"
            style={{
              backgroundColor: overTotal ? '#94A3B8' : ORANGE,
              color: 'white',
            }}
          >
            {busy ? 'Awarding…' : 'Confirm award'}
          </Button>
        </div>
      </form>
    </div>
  );
}
