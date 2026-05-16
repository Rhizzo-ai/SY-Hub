/**
 * PaymentsView (Chat 19B §R5.2).
 *
 * Louise's global "what needs paying" view across all projects. Pulls
 * status=Posted,Disputed via the global /api/v1/actuals endpoint (D32
 * extended in §R0.6 to accept comma-separated statuses), groups by
 * project, and lets desktop users with actuals.approve bulk-mark-paid
 * via N-call loop (D30).
 */
import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { useActuals } from '@/hooks/actuals';
import { canViewPaymentsPage } from '@/lib/actualCapability';
import { fmtGBP } from '@/lib/format';
import { ActualStatusBadge } from '@/components/actuals/ActualStatusBadge';
import { BulkPayDialog } from '@/components/payments/BulkPayDialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';

export default function PaymentsView() {
  const { me } = useAuth();
  const isDesktop = useIsDesktop();
  const [selected, setSelected] = useState(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);

  const canView = canViewPaymentsPage(me);

  // Server-side: status=Posted,Disputed (D32 — backend extended in §R0.6).
  const { data, isLoading, isError, error } = useActuals({
    params: { status: 'Posted,Disputed', limit: 500, offset: 0 },
    enabled: canView,
  });

  const items = data?.items ?? [];

  // Group by project for the table sections.
  const byProject = useMemo(() => {
    const map = new Map();
    for (const a of items) {
      if (!map.has(a.project_id)) map.set(a.project_id, []);
      map.get(a.project_id).push(a);
    }
    return Array.from(map.entries()).map(([projectId, rows]) => ({
      projectId,
      rows: rows.sort((x, y) => x.transaction_date.localeCompare(y.transaction_date)),
    }));
  }, [items]);

  const totalSelected = selected.size;
  const selectedTotal = useMemo(() => {
    let sum = 0;
    for (const a of items) {
      if (selected.has(a.id) && a.gross_amount) {
        sum += Number(a.gross_amount);
      }
    }
    return sum;
  }, [items, selected]);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleAll = (rows) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const allSelected = rows.every((r) => next.has(r.id));
      if (allSelected) {
        for (const r of rows) next.delete(r.id);
      } else {
        for (const r of rows) next.add(r.id);
      }
      return next;
    });
  };

  // Explicit perm check (avoids feeding fake actuals into the state-machine
  // helpers, which would break if those helpers grow more preconditions).
  const userCanPay = isDesktop && (
    !!me?.is_super_admin ||
    (Array.isArray(me?.permissions) && me.permissions.includes('actuals.approve'))
  );

  if (!canView) {
    return (
      <div
        className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600"
        data-testid="payments-no-access"
      >
        You don't have access to the payments view.
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 md:p-6" data-testid="payments-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl text-slate-900">Ready to Pay</h1>
          <p className="text-sm text-slate-600">
            Posted and Disputed bills across all projects. Tick rows to mark them paid in bulk.
          </p>
        </div>
        {userCanPay && (
          <Button
            disabled={totalSelected === 0}
            onClick={() => setBulkOpen(true)}
            className="bg-sy-teal text-white hover:brightness-110 disabled:bg-slate-300"
            data-testid="payments-bulk-pay-button"
          >
            Mark {totalSelected || 0} as Paid
            {totalSelected > 0 && ` (${fmtGBP(String(selectedTotal.toFixed(2)))})`}
          </Button>
        )}
      </div>

      {!isDesktop && (
        <div
          data-testid="payments-mobile-banner"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          Mark Paid is desktop-only. Tap a row to view detail.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
             data-testid="payments-loading">
          Loading bills…
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
             data-testid="payments-error">
          Failed to load: {error?.message ?? 'unknown error'}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-12 text-center"
             data-testid="payments-empty">
          <p className="text-slate-600">Nothing to pay. Inbox zero — well played.</p>
        </div>
      ) : (
        byProject.map(({ projectId, rows }) => (
          <ProjectSection
            key={projectId}
            projectId={projectId}
            rows={rows}
            selected={selected}
            onToggle={toggle}
            onToggleAll={() => toggleAll(rows)}
            canSelect={userCanPay && isDesktop}
          />
        ))
      )}

      <BulkPayDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        actuals={items.filter((a) => selected.has(a.id))}
        onComplete={(succeededIds) => {
          setSelected((prev) => {
            const next = new Set(prev);
            for (const id of succeededIds) next.delete(id);
            return next;
          });
        }}
      />
    </div>
  );
}

function ProjectSection({ projectId, rows, selected, onToggle, onToggleAll, canSelect }) {
  const allSelected = rows.every((r) => selected.has(r.id));
  const someSelected = rows.some((r) => selected.has(r.id));
  return (
    <section
      data-testid={`payments-project-section-${projectId}`}
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <header className="mb-2 flex items-center justify-between">
        <Link
          to={`/projects/${projectId}/actuals?status=Posted`}
          className="text-sm font-medium text-slate-700 hover:text-sy-teal"
          data-testid={`payments-project-link-${projectId}`}
        >
          Project {projectId.slice(0, 8)}…
        </Link>
        <span className="text-xs text-slate-500">
          {rows.length} bill{rows.length === 1 ? '' : 's'}
        </span>
      </header>
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50 text-xs text-slate-500">
          <tr>
            <th className="w-8 p-2">
              {canSelect && (
                // Radix Checkbox tri-state: pass the string "indeterminate"
                // via `checked` to show the indeterminate styling.
                <Checkbox
                  checked={allSelected ? true : (someSelected ? 'indeterminate' : false)}
                  onCheckedChange={onToggleAll}
                  data-testid={`payments-toggle-all-${projectId}`}
                />
              )}
            </th>
            <th className="p-2 text-left">Date</th>
            <th className="p-2 text-left">Supplier</th>
            <th className="p-2 text-left">Ref</th>
            <th className="p-2 text-right">Gross</th>
            <th className="p-2 text-left">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((a) => (
            <tr
              key={a.id}
              data-testid={`payments-row-${a.id}`}
              className={selected.has(a.id) ? 'bg-sy-teal/5' : ''}
            >
              <td className="p-2">
                {canSelect && (
                  <Checkbox
                    checked={selected.has(a.id)}
                    onCheckedChange={() => onToggle(a.id)}
                    data-testid={`payments-select-${a.id}`}
                  />
                )}
              </td>
              <td className="p-2 tabular text-sm">{a.transaction_date}</td>
              <td className="p-2 text-sm font-medium text-slate-900">
                {a.supplier_name_snapshot}
              </td>
              <td className="p-2 text-xs text-slate-500">{a.supplier_invoice_ref || '—'}</td>
              <td className="p-2 text-right tabular text-sm">{fmtGBP(a.gross_amount)}</td>
              <td className="p-2"><ActualStatusBadge status={a.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
