/**
 * PaymentsView (Chat 19B §R2 stub; full impl in §R5).
 *
 * Louise's global "what needs paying" view across all projects.
 */
import { Link } from 'react-router-dom';

export default function PaymentsView() {
  return (
    <div className="space-y-4 p-4 md:p-6" data-testid="payments-view-page">
      <h1 className="font-heading text-2xl text-slate-900">Payments</h1>
      <div
        data-testid="payments-view-placeholder"
        className="rounded-md border border-dashed border-slate-300 p-6 text-sm text-slate-500"
      >
        Louise's global cross-project payments list lands in §R5 — this is a
        stub for §R2 STOP gate 2.
      </div>
      <Link
        to="/projects"
        className="text-sm text-sy-teal hover:brightness-110"
      >
        ← Projects
      </Link>
    </div>
  );
}
