/**
 * POSubmitErrorPanel — B107 §6.
 *
 * Structured surface for the three B105/B106 submit-time wire errors,
 * keyed on `detail.type`. NEVER JSON.stringifies an object at the user
 * (B107 §1.2 / §6.4) — unknown/string details are handled by the caller's
 * toast fallback, so this panel only renders for the three known shapes.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { formatMoney } from '@/lib/format';

export function POSubmitErrorPanel({
  error, onRetry, onDismiss, canClear, budgetHref,
}) {
  if (!error?.detail?.type) return null;
  const { detail } = error;

  // (a) 409 unbudgeted_ack_required — director sign-off needed.
  if (detail.type === 'unbudgeted_ack_required') {
    const lines = Array.isArray(detail.lines) ? detail.lines : [];
    return (
      <div
        className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
        data-testid="po-error-ack-required"
        role="alert"
      >
        {/* B112: notify directors holding budgets.clear_unbudgeted — a PO is
            waiting on their sign-off (see Build Pack B107 §9). */}
        <p className="font-semibold">This order can&apos;t be submitted yet.</p>
        <p className="mt-1">
          {lines.length} line{lines.length === 1 ? '' : 's'} need director sign-off:
        </p>
        <ul className="mt-2 space-y-1">
          {lines.map((l, i) => (
            <li
              key={l.budget_line_id ?? i}
              className="font-mono text-xs"
              data-testid={`po-error-ack-line-${i}`}
            >
              Cost code {l.cost_code} — committed {formatMoney(l.committed_not_invoiced)}{' '}
              (floor {formatMoney(l.floor)})
            </li>
          ))}
        </ul>
        <p className="mt-2">
          A director with clear-unbudgeted permission must sign these off on the
          budget grid before this PO can be submitted.
        </p>
        <div className="mt-3 flex gap-2">
          {canClear && budgetHref && (
            <Link
              to={budgetHref}
              className="px-3 py-1.5 rounded bg-rose-600 text-white text-xs"
              data-testid="po-error-ack-budget-link"
            >
              Go to budget grid
            </Link>
          )}
          <button
            type="button"
            onClick={onDismiss}
            className="px-3 py-1.5 rounded border border-rose-300 text-xs"
            data-testid="po-error-ack-dismiss"
          >
            Got it
          </button>
        </div>
      </div>
    );
  }

  // (b) 422 po_line_incomplete — a line is missing required fields.
  if (detail.type === 'po_line_incomplete') {
    const nums = Array.isArray(detail.incomplete_line_numbers)
      ? detail.incomplete_line_numbers
      : [];
    return (
      <div
        className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        data-testid="po-error-line-incomplete"
        role="alert"
      >
        <p className="font-semibold">PO line(s) incomplete</p>
        <p className="mt-1">
          Line{nums.length === 1 ? '' : 's'} {nums.join(', ')}{' '}
          {nums.length === 1 ? 'is' : 'are'} incomplete. Add a description,
          quantity, and unit price to each, then submit again.
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="mt-2 px-3 py-1.5 rounded border border-amber-300 text-xs"
          data-testid="po-error-incomplete-dismiss"
        >
          Dismiss
        </button>
      </div>
    );
  }

  // (c) 409 budget_line_race — concurrent mint; one-click retry.
  if (detail.type === 'budget_line_race') {
    return (
      <div
        className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800"
        data-testid="po-error-race"
        role="alert"
      >
        <p className="font-semibold">Just a moment — please retry</p>
        <p className="mt-1">
          Another order just created a budget line for this cost code. Click
          retry to finish submitting — your lines are unchanged.
        </p>
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1.5 rounded bg-sky-600 text-white text-xs"
            data-testid="po-error-race-retry"
          >
            Retry
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="px-3 py-1.5 rounded border border-sky-300 text-xs"
            data-testid="po-error-race-dismiss"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return null;
}

export default POSubmitErrorPanel;
