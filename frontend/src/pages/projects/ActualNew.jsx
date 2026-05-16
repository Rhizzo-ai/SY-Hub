/**
 * ActualNew page (Chat 19B §R3.3).
 *
 * Mobile primary entry for creating an actual; desktop deep-link fallback.
 * Renders the same `CreateActualSheet` always-open — the Sheet's Cancel
 * button + onSuccess close both navigate back to the list. Avoids
 * duplicating ~250 lines of form code.
 */
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { CreateActualSheet } from '@/components/actuals/CreateActualSheet';
import { canCreateActual } from '@/lib/actualCapability';

export default function ActualNew() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const isDesktop = useIsDesktop();

  if (!canCreateActual(me, isDesktop)) {
    return (
      <div
        data-testid="actual-new-no-perm"
        className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600"
      >
        You don't have permission to create actuals.
      </div>
    );
  }

  return (
    <CreateActualSheet
      open
      onOpenChange={(o) => {
        if (!o) navigate(`/projects/${projectId}/actuals`);
      }}
      projectId={projectId}
    />
  );
}
