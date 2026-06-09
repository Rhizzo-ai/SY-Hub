/**
 * <ValuationsList/> — Chat 48 (Build Pack 2.8-FE-ii §R4.2).
 *
 * Tabular list of valuations for a parent subcontract. Mirrors the
 * 2.8-FE-i SubcontractsTab list style (border-collapse, hover-row,
 * sy-teal-50 selected-row tint, em-dash for null money).
 *
 * Columns (Build Pack §R4.2):
 *   - No.                 (`valuation_number`)
 *   - Reference           (`reference`, e.g. VAL-0001 — backend-gen)
 *   - Status              (<ValuationStatusPill/>)
 *   - Period              (`period_start`–`period_end`, formatDate)
 *   - Gross applied to date (`fmtGBP` — visible to ALL view users)
 *   - Net payable this cert (`fmtGBP` — SENSITIVE; em-dash without
 *     `subcontract_valuations.view_sensitive`. Backend returns the
 *     field as null without the perm; we defence-in-depth render the
 *     em-dash regardless of value.)
 *   - Over-claim flag chip (`over_claim_flag`; non-sensitive)
 *
 * Status filter sits ABOVE the table; filter value is owned by the
 * parent <ValuationsSection/>. The list passes the status param into
 * `useValuations` via the parent so a 'Submitted' filter doesn't
 * accidentally pass through any other key (the backend 422s on
 * unrecognised status values).
 *
 * B87 mitigation: outer wrapper sets `min-w-0` and `overflow-x-auto`
 * so the table can scroll horizontally inside the nested 2.8-FE-i
 * col-span-3 pane without forcing the parent grid wider.
 */
import React from 'react';

import { useAuth } from '@/context/AuthContext';
import { useValuations } from '@/hooks/subcontractValuations';
import { canViewValuationSums } from '@/lib/poCapability';
import { fmtGBP } from '@/lib/format';
import { formatDate } from '@/lib/cisFormat';

import ValuationStatusPill from './ValuationStatusPill';


const STATUS_OPTIONS = ['Draft', 'Submitted', 'Certified', 'Rejected'];


function formatPeriod(start, end) {
  if (!start && !end) return '\u2014';
  return `${formatDate(start)} \u2013 ${formatDate(end)}`;
}


/**
 * <SensitiveMoney/> — local helper.
 *
 * Two reasons we don't reuse <SensitiveValue/> from po/:
 *   1. The valuation sensitive contract is "backend nulls the key
 *      without the perm" — by the time the row reaches us, the value
 *      is already null. We still want defence-in-depth (em-dash even
 *      if a future backend leak ever happens), so we check the perm
 *      flag AND the null.
 *   2. We render '\u2014' (em-dash) directly here so the test can match
 *      it without depending on SensitiveValue's internal markup.
 */
function SensitiveMoney({ value, canView, testid }) {
  const txt = (canView && value != null) ? fmtGBP(value) : null;
  return (
    <span className="tabular-nums" data-testid={testid}>
      {txt ?? '\u2014'}
    </span>
  );
}


export default function ValuationsList({
  subcontractId,
  status,                 // current status filter (parent-owned)
  onStatusChange,
  selectedId,
  onSelect,
}) {
  const { me } = useAuth();
  const canSensitive = canViewValuationSums(me);

  // The status param goes onto the wire only when set — the API client
  // strips undefined keys; we still keep the surrounding hook params
  // tidy here.
  const listQ = useValuations({
    params: status
      ? { subcontractId, status }
      : { subcontractId },
    enabled: !!subcontractId,
  });

  const items = listQ.data?.items ?? [];

  return (
    <div className="space-y-2" data-testid="valuations-list-wrap">
      <div className="flex items-end justify-between gap-3">
        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Status</span>
          <select
            className="block px-2 py-1 border rounded text-sm"
            value={status ?? ''}
            onChange={(e) => onStatusChange(e.target.value || '')}
            data-testid="valuations-list-status-filter"
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="border rounded min-w-0 overflow-x-auto" data-testid="valuations-list-table-wrap">
        {listQ.isLoading && (
          <div className="p-3 text-sm" data-testid="valuations-list-loading">
            {'Loading\u2026'}
          </div>
        )}
        {listQ.isError && (
          <div className="p-3 text-sm text-red-700" data-testid="valuations-list-error">
            Failed to load valuations.
          </div>
        )}
        {!listQ.isLoading && !listQ.isError && (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-xs text-sy-grey-700 border-b">
                <th className="py-2 px-2 w-12">No.</th>
                <th className="py-2 px-2 w-28">Reference</th>
                <th className="py-2 px-2 w-28">Status</th>
                <th className="py-2 px-2">Period</th>
                <th className="py-2 px-2 text-right">Gross applied</th>
                <th className="py-2 px-2 text-right">Net payable</th>
                <th className="py-2 px-2 w-12" aria-label="Over-claim flag" />
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="py-3 px-2 text-sy-grey-500"
                    data-testid="valuations-list-empty"
                  >
                    No valuations yet.
                  </td>
                </tr>
              )}
              {items.map((v) => {
                const isActive = v.id === selectedId;
                return (
                  <tr
                    key={v.id}
                    onClick={() => onSelect(v.id)}
                    className={`border-b last:border-0 cursor-pointer ${isActive ? 'bg-sy-teal-50' : 'hover:bg-sy-grey-50'}`}
                    data-testid={`valuations-row-${v.id}`}
                  >
                    <td className="py-2 px-2 tabular-nums">{v.valuation_number ?? '\u2014'}</td>
                    <td className="py-2 px-2 tabular-nums">{v.reference ?? '\u2014'}</td>
                    <td className="py-2 px-2">
                      <ValuationStatusPill
                        status={v.status}
                        testid={`valuations-row-${v.id}-status`}
                      />
                    </td>
                    <td className="py-2 px-2">
                      {formatPeriod(v.period_start, v.period_end)}
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums">
                      {fmtGBP(v.gross_applied_to_date) ?? '\u2014'}
                    </td>
                    <td className="py-2 px-2 text-right">
                      <SensitiveMoney
                        value={v.net_payable_this_cert}
                        canView={canSensitive}
                        testid={`valuations-row-${v.id}-net`}
                      />
                    </td>
                    <td className="py-2 px-2">
                      {v.over_claim_flag && (
                        <span
                          className="inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800"
                          title={v.over_claim_note ?? 'Over-claim flagged'}
                          data-testid={`valuations-row-${v.id}-overclaim`}
                        >
                          !
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
