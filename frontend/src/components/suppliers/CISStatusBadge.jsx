/**
 * <CISStatusBadge/> — Chat 40 §R3 #14 / §R4.6.
 *
 * Maps the supplier-side `current_cis_status` (1 of 4 states +
 * null) to a shadcn Badge variant. Single source of truth so the same
 * mapping renders identically on the list, the Overview tab and the
 * CIS-tab banner.
 *
 * State machine (§R1):
 *   Gross       → default     ("Gross")
 *   Net         → secondary   ("Net")
 *   Unmatched   → destructive ("Unmatched")
 *   Unverified  → outline     ("Unverified")
 *   null        → outline     ("Unverified")   ← no verification on record
 *
 * `match_status` history rows (verifications table) reuse the same
 * mapping minus the null case — pass the match_status string directly.
 */
import React from 'react';
import { Badge } from '@/components/ui/badge';
import { labelCurrentCisStatus } from '@/lib/cisFormat';

const VARIANT = {
  Gross: 'default',
  Net: 'secondary',
  Unmatched: 'destructive',
  Unverified: 'outline',
};

export default function CISStatusBadge({ status, testid }) {
  // null / undefined collapse to "Unverified"; everything else uses
  // the literal value so unknown future enums still render (no crash).
  const effective = status ?? 'Unverified';
  const variant = VARIANT[effective] ?? 'outline';
  const label = labelCurrentCisStatus(status);
  return (
    <Badge variant={variant} data-testid={testid ?? `cis-status-badge-${effective}`}>
      {label}
    </Badge>
  );
}
