/**
 * ActualNew page (Chat 19B §R2 stub; full impl in §R3.3).
 *
 * Mobile entry point for creating an actual — a standalone route since
 * Sheets are desktop-only (Q2). On desktop, this URL also opens the
 * create flow (no fallback notice).
 */
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function ActualNew() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  return (
    <div className="space-y-4 p-4 md:p-6" data-testid="actual-new-page">
      <h1 className="font-heading text-2xl text-slate-900">Create actual</h1>
      <div
        data-testid="actual-new-placeholder"
        className="rounded-md border border-dashed border-slate-300 p-6 text-sm text-slate-500"
      >
        The full create form lands in §R3 — this is a stub for §R2 STOP gate 2.
      </div>
      <Button
        variant="outline"
        onClick={() => navigate(`/projects/${projectId}/actuals`)}
      >
        Back to actuals
      </Button>
    </div>
  );
}
