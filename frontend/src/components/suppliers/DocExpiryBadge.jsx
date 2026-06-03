/**
 * <DocExpiryBadge/> — Chat 40 §R3 #15 / §R4.6 / §R6 enhancement (a).
 *
 * Pure frontend computation — backend stores `expires_on` but never
 * flags. Buckets:
 *   - `expires_on` null/absent → no badge
 *   - `expires_on` < today     → destructive  ("Expired")
 *   - `expires_on` ≤ 30 days   → orange       ("Expiring soon")
 *   - else                     → no badge (subtle absence == valid)
 *
 * Today is computed once per render (`new Date()`); fine for a list.
 */
import React from 'react';
import { Badge } from '@/components/ui/badge';

const MS_PER_DAY = 24 * 60 * 60 * 1000;

function bucket(expiresOn, now = new Date()) {
  if (!expiresOn) return null;
  const exp = new Date(expiresOn);
  if (Number.isNaN(exp.getTime())) return null;
  // Compare at day granularity to avoid HH:MM:SS flicker on the boundary.
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const expDay = new Date(exp.getFullYear(), exp.getMonth(), exp.getDate());
  const diffDays = Math.round((expDay - today) / MS_PER_DAY);
  if (diffDays < 0) return 'expired';
  if (diffDays <= 30) return 'expiring';
  return 'valid';
}

export default function DocExpiryBadge({ expiresOn, testid }) {
  const b = bucket(expiresOn);
  if (b === null || b === 'valid') return null;
  if (b === 'expired') {
    return (
      <Badge variant="destructive" data-testid={testid ?? 'doc-expiry-badge-expired'}>
        Expired
      </Badge>
    );
  }
  // Expiring soon — shadcn doesn't ship an "orange" variant; use a
  // class-override Badge with the SY orange-700 token.
  return (
    <Badge
      variant="outline"
      className="border-orange-400 bg-orange-50 text-orange-800"
      data-testid={testid ?? 'doc-expiry-badge-expiring'}
    >
      Expiring soon
    </Badge>
  );
}

// Exported for unit tests — pure bucketing logic.
export { bucket as _bucketForTests };
