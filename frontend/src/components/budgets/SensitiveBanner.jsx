/**
 * SensitiveBanner — Prompt 2.4B-i §R5.5.
 *
 * Renders when the current user lacks `budgets.view_sensitive`. The
 * backend strips sensitive numbers (FTC, FFC, variance, actuals, CNI,
 * notes-internal) from the payload for these users — every sensitive
 * field in the schema is `.nullable().optional()` so render code handles
 * missing keys via "—".
 *
 * The banner alerts users that the numbers they see are partial.
 */
import { useAuth } from '@/context/AuthContext';

export function SensitiveBanner() {
  const { me } = useAuth();
  const hasSensitive = me?.permissions?.includes('budgets.view_sensitive');
  if (hasSensitive) return null;
  return (
    <div
      data-testid="sensitive-banner"
      className="rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-600"
    >
      Some sensitive figures (actuals, committed-not-invoiced, forecast-to-complete,
      forecast final cost, variance) are hidden under your role. Contact a
      director to request elevated access.
    </div>
  );
}
