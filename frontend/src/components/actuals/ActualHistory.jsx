/**
 * ActualHistory (Chat 19B §R4.5).
 *
 * Q9: collapsible change-log timeline; default closed; payload-fetching is
 * gated on `enabled: open` so the network call only fires once the user
 * clicks. Sensitive payload fields rendered only when caller has
 * `actuals.view_sensitive` (D26).
 */
import { useState } from 'react';
import { format } from 'date-fns';
import { useActualChangeLog } from '@/hooks/actuals';

const EVENT_LABELS = {
  Created: 'Created',
  Edited: 'Edited',
  Posted: 'Posted',
  Paid: 'Marked Paid',
  Voided: 'Voided',
  Disputed: 'Disputed',
  Undisputed: 'Resolved dispute',
  Reconciled: 'Reconciled to Xero',
  Retention_Released: 'Retention released',
  Attachment_Added: 'Attachment added',
  Attachment_Removed: 'Attachment removed',
};

export function ActualHistory({ actualId, includeSensitive }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useActualChangeLog(actualId, { enabled: open });
  const items = data?.items ?? [];

  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      data-testid="actual-history"
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between text-left"
        data-testid="actual-history-toggle"
      >
        <h2 className="font-heading text-lg text-slate-900">History</h2>
        <span className="text-sm text-slate-500">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <div className="mt-4">
          {isLoading ? (
            <p className="text-sm text-slate-500">Loading history…</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-slate-500">No history events yet.</p>
          ) : (
            <ol className="space-y-3" data-testid="actual-history-list">
              {items.map((evt) => (
                <li
                  key={evt.id}
                  className="flex gap-3"
                  data-testid={`history-event-${evt.id}`}
                >
                  <div className="mt-1 h-2 w-2 flex-none rounded-full bg-sy-teal" />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-slate-900">
                      {EVENT_LABELS[evt.event_type] ?? evt.event_type}
                    </div>
                    <div className="text-xs text-slate-500">
                      {evt.occurred_at && format(new Date(evt.occurred_at), 'd MMM yyyy, HH:mm')}
                    </div>
                    {includeSensitive &&
                      evt.event_payload &&
                      Object.keys(evt.event_payload).length > 0 && (
                        <pre
                          className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700"
                          data-testid={`history-payload-${evt.id}`}
                        >
                          {JSON.stringify(evt.event_payload, null, 2)}
                        </pre>
                      )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
