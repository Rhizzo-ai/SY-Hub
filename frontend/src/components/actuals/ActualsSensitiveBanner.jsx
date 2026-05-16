/**
 * ActualsSensitiveBanner (Chat 19B §R2.6a).
 *
 * Slate banner shown when the current user lacks `actuals.view_sensitive`.
 * Mirrors the Budgets SensitiveBanner styling but uses Actuals-specific
 * copy (CIS, retention, dispute/void reasons, payment references).
 *
 * Backend `_serialise_actual` strips those fields when the caller lacks
 * `actuals.view_sensitive`. The Zod schema treats them as
 * `.nullable().optional()` so the UI handles "absent" gracefully.
 */
import { useAuth } from '@/context/AuthContext';

export function ActualsSensitiveBanner() {
  const { me } = useAuth();
  const hasSensitive =
    (me?.permissions || []).includes('actuals.view_sensitive') ||
    !!me?.is_super_admin;
  if (hasSensitive) return null;
  return (
    <div
      data-testid="actuals-sensitive-banner"
      className="rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-600"
    >
      Some sensitive figures (CIS deductions, retention amounts, dispute /
      void reasons, payment references) are hidden under your role. Contact a
      director to request elevated access.
    </div>
  );
}
