/**
 * BudgetGridV2 — Chat 23 R3.1 top-level entry point.
 *
 * Replaces v1's BudgetLinesGrid. Picks between desktop and mobile
 * variants. LineDrawer (separate from this grid) continues to handle
 * non-Notes line-field edits.
 */
import { useIsDesktop } from '@/lib/useIsDesktop';
import { BudgetGridV2Desktop } from './BudgetGridV2Desktop';
import { BudgetGridMobileReadOnly } from './BudgetGridMobileReadOnly';

export function BudgetGridV2({ budget, projectId }) {
  const isDesktop = useIsDesktop();
  if (!isDesktop) {
    return <BudgetGridMobileReadOnly budget={budget} projectId={projectId} />;
  }
  return <BudgetGridV2Desktop budget={budget} projectId={projectId} />;
}
