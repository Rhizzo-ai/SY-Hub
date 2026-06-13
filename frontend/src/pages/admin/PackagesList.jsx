/**
 * PackagesList — B88 Pack 3 §7 (Chat 53). Route: /admin/packages.
 *
 * List screen for tendering packages with status / kind / project
 * filters and a "New package" affordance. Pricing columns redact to
 * em-dash for callers without `packages.view_sensitive`.
 *
 * Error discipline (Pack 3 live-eyeball rule): every mutation handler
 * surfaces failures via a toast + inline message. No silent onError.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Package as PackageIcon, AlertTriangle } from 'lucide-react';

import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import {
  listPackagesGlobal, createPackage,
} from '@/lib/api/packages';
import {
  fmtMoney, statusPillProps, errorMessage,
} from '@/components/packages/packagesHelpers';
import NewPackageDialog from '@/components/packages/NewPackageDialog';

const TEAL = '#0F6A7A';

export default function PackagesList() {
  const { me, hasPerm } = useAuth();
  const nav = useNavigate();

  const canView = hasPerm('packages.view') || me?.is_super_admin;
  const canViewSensitive =
    hasPerm('packages.view_sensitive') || me?.is_super_admin;
  const canCreate = hasPerm('packages.create') || me?.is_super_admin;

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterKind, setFilterKind] = useState('');
  const [newOpen, setNewOpen] = useState(false);

  const reload = React.useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await listPackagesGlobal({
        status: filterStatus || undefined,
        kind: filterKind || undefined,
        limit: 200,
      });
      setItems(data.items || []);
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterKind]);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!canView) {
      setLoading(false);
      return;
    }
    reload();
  }, [canView, reload]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const filtered = useMemo(() => items, [items]);

  if (!canView) {
    return (
      <div
        className="rounded-lg border border-slate-200 bg-white p-10 text-center"
        data-testid="packages-list-forbidden"
      >
        <AlertTriangle className="mx-auto mb-3 text-slate-400" size={28} />
        <div className="font-medium text-slate-700">
          You don&apos;t have permission to view packages.
        </div>
        <div className="mt-1 text-sm text-slate-500">
          Required: <code>packages.view</code>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="packages-list" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="font-heading text-3xl font-bold"
            style={{ color: TEAL }}
            data-testid="packages-list-heading"
          >
            Packages
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Tendering spine — issue packages, collect bids, strike awards
            into POs &amp; subcontracts.
          </p>
        </div>
        {canCreate && (
          <Button
            onClick={() => setNewOpen(true)}
            data-testid="packages-new-btn"
            className="gap-2"
            style={{ backgroundColor: TEAL, color: 'white' }}
          >
            <Plus size={16} />
            New package
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-3 rounded-lg border border-slate-200 bg-white p-3">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          Status:
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            data-testid="packages-filter-status"
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="out_to_tender">Out to tender</option>
            <option value="partially_awarded">Partially awarded</option>
            <option value="awarded">Awarded</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          Kind:
          <select
            value={filterKind}
            onChange={(e) => setFilterKind(e.target.value)}
            data-testid="packages-filter-kind"
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="">All</option>
            <option value="materials">Materials</option>
            <option value="labour">Labour</option>
          </select>
        </label>
      </div>

      {loadError && (
        <div
          className="rounded border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
          role="alert"
          data-testid="packages-list-error"
        >
          Failed to load packages: {loadError}
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white overflow-x-auto">
        <table
          className="min-w-full text-sm"
          data-testid="packages-list-table"
        >
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-semibold">Reference</th>
              <th className="px-4 py-3 font-semibold">Title</th>
              <th className="px-4 py-3 font-semibold">Kind</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 text-right font-semibold">Total net</th>
              <th className="px-4 py-3 text-right font-semibold">Awarded</th>
              <th className="px-4 py-3 text-right font-semibold">Progress</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-12 text-center text-slate-500"
                  data-testid="packages-list-loading"
                >
                  Loading packages…
                </td>
              </tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-12 text-center text-slate-500"
                  data-testid="packages-list-empty"
                >
                  <PackageIcon
                    className="mx-auto mb-2 text-slate-300"
                    size={32}
                  />
                  No packages yet.
                </td>
              </tr>
            )}
            {!loading &&
              filtered.map((p) => {
                const pill = statusPillProps(p.status);
                const totalNum = Number(p.total_net || 0);
                const awardNum = Number(p.awarded_net || 0);
                const progress =
                  canViewSensitive && totalNum > 0
                    ? Math.min(100, Math.round((awardNum / totalNum) * 100))
                    : null;
                return (
                  <tr
                    key={p.id}
                    onClick={() => nav(`/admin/packages/${p.id}`)}
                    className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                    data-testid={`packages-row-${p.reference}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">
                      {p.reference}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {p.title}
                    </td>
                    <td className="px-4 py-3 capitalize text-slate-700">
                      {p.kind}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium"
                        style={{
                          backgroundColor: pill.bg,
                          color: pill.fg,
                        }}
                        data-testid={`packages-row-status-${p.reference}`}
                      >
                        {pill.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-800">
                      {fmtMoney(p.total_net)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-800">
                      {fmtMoney(p.awarded_net)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {progress == null ? (
                        <span className="text-slate-400">{'\u2014'}</span>
                      ) : (
                        <span className="text-xs text-slate-600">
                          {progress}%
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>

      {newOpen && (
        <NewPackageDialog
          onClose={() => setNewOpen(false)}
          onCreated={async (pkg) => {
            setNewOpen(false);
            toast.success(`Package ${pkg.reference} created`);
            await reload();
            nav(`/admin/packages/${pkg.id}`);
          }}
          onCreateError={(err) => {
            toast.error(`Create failed: ${errorMessage(err)}`);
          }}
        />
      )}
    </div>
  );
}
