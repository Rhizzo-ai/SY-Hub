/**
 * ActualStateActions (Chat 19B §R4.3).
 *
 * Context-aware action buttons matching VALID_TRANSITIONS in
 * `app/models/actuals.py`. Each non-trivial action opens a Radix Dialog
 * with reason capture (paid_date / payment_reference / void_reason /
 * dispute_reason / retention_release_date).
 *
 * Permission gates are encapsulated in `lib/actualCapability.js` —
 * verified against live `app/routers/actuals.py` 2026-05-16.
 */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  canPostDraft, canMarkPaid, canVoid, canDispute, canUndispute,
  canReleaseRetention,
} from '@/lib/actualCapability';
import {
  usePostActual, useMarkPaid, useVoidActual, useDisputeActual,
  useUndisputeActual, useReleaseRetention,
} from '@/hooks/actuals';

export function ActualStateActions({ actual, me, isDesktop }) {
  const [activeAction, setActiveAction] = useState(null);
  const postMut = usePostActual(actual.id);
  const payMut = useMarkPaid(actual.id);
  const voidMut = useVoidActual(actual.id);
  const disputeMut = useDisputeActual(actual.id);
  const undisputeMut = useUndisputeActual(actual.id);
  const retentionMut = useReleaseRetention(actual.id);

  const close = () => setActiveAction(null);

  return (
    <div className="flex flex-wrap gap-2" data-testid="actual-state-actions">
      {canPostDraft(actual, me, isDesktop) && (
        <Button
          className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
          onClick={() => setActiveAction('post')}
          data-testid="action-post"
        >
          Post
        </Button>
      )}
      {canMarkPaid(actual, me, isDesktop) && (
        <Button
          className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
          onClick={() => setActiveAction('pay')}
          data-testid="action-mark-paid"
        >
          Mark Paid
        </Button>
      )}
      {canDispute(actual, me, isDesktop) && (
        <Button
          variant="outline"
          onClick={() => setActiveAction('dispute')}
          data-testid="action-dispute"
        >
          Dispute
        </Button>
      )}
      {canUndispute(actual, me, isDesktop) && (
        <Button
          className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
          onClick={() => setActiveAction('undispute')}
          data-testid="action-undispute"
        >
          Resolve dispute
        </Button>
      )}
      {canReleaseRetention(actual, me, isDesktop) && (
        <Button
          variant="outline"
          onClick={() => setActiveAction('release-retention')}
          data-testid="action-release-retention"
        >
          Release retention
        </Button>
      )}
      {canVoid(actual, me, isDesktop) && (
        <Button
          className="bg-sy-orange text-white hover:brightness-110 active:brightness-95"
          onClick={() => setActiveAction('void')}
          data-testid="action-void"
        >
          Void
        </Button>
      )}

      <ActionDialog
        action={activeAction}
        onClose={close}
        onSubmit={async (body) => {
          try {
            switch (activeAction) {
              case 'post':              await postMut.mutateAsync(body); break;
              case 'pay':               await payMut.mutateAsync(body); break;
              case 'void':              await voidMut.mutateAsync(body); break;
              case 'dispute':           await disputeMut.mutateAsync(body); break;
              case 'undispute':         await undisputeMut.mutateAsync(body); break;
              case 'release-retention': await retentionMut.mutateAsync(body); break;
              default: throw new Error('unknown action');
            }
            toast.success(`Action complete: ${activeAction}`);
            close();
          } catch (err) {
            const detail = err?.response?.data?.detail;
            const msg = typeof detail === 'string'
              ? detail
              : detail?.message ?? err?.message;
            toast.error(msg ?? 'Action failed');
          }
        }}
      />
    </div>
  );
}

function ActionDialog({ action, onClose, onSubmit }) {
  const [reason, setReason] = useState('');
  const [paidDate, setPaidDate] = useState(new Date().toISOString().slice(0, 10));
  const [paymentRef, setPaymentRef] = useState('');
  const [retentionReleaseDate, setRetentionReleaseDate] = useState(
    new Date().toISOString().slice(0, 10),
  );

  // Reset all fields when the active action changes — prevents stale
  // "dispute reason" text from leaking into the void dialog if the
  // operator opens them sequentially.
  useEffect(() => {
    setReason('');
    setPaymentRef('');
    setPaidDate(new Date().toISOString().slice(0, 10));
    setRetentionReleaseDate(new Date().toISOString().slice(0, 10));
  }, [action]);

  const config = {
    post: {
      title: 'Post this Draft?',
      message:
        'Posting locks the financial fields and reconciles against the budget. Continue?',
      submit: 'Post',
      destructive: false,
      payload: () => ({}),
      valid: () => true,
    },
    pay: {
      title: 'Mark as Paid',
      message: null,
      submit: 'Mark Paid',
      destructive: false,
      payload: () => ({ paid_date: paidDate, payment_reference: paymentRef.trim() }),
      valid: () => !!paidDate && paymentRef.trim().length > 0,
      fields: (
        <div className="space-y-3">
          <div>
            <Label>Payment date</Label>
            <Input
              type="date"
              value={paidDate}
              onChange={(e) => setPaidDate(e.target.value)}
              data-testid="mark-paid-date"
            />
          </div>
          <div>
            <Label>Payment reference</Label>
            <Input
              value={paymentRef}
              onChange={(e) => setPaymentRef(e.target.value)}
              placeholder="BACS-12345 / cheque ref / Stripe ID"
              data-testid="mark-paid-reference"
            />
          </div>
        </div>
      ),
    },
    void: {
      title: 'Void this actual?',
      message:
        'Voiding is irreversible. The row stays in the ledger but is excluded from all totals.',
      submit: 'Void',
      destructive: true,
      payload: () => ({ void_reason: reason.trim() }),
      valid: () => reason.trim().length >= 3,
      fields: (
        <div>
          <Label>Void reason (required, min 3 chars)</Label>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            data-testid="void-reason"
          />
        </div>
      ),
    },
    dispute: {
      title: 'Mark as Disputed',
      message: null,
      submit: 'Dispute',
      destructive: false,
      payload: () => ({ dispute_reason: reason.trim() }),
      valid: () => reason.trim().length >= 3,
      fields: (
        <div>
          <Label>Dispute reason (required, min 3 chars)</Label>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            data-testid="dispute-reason"
          />
        </div>
      ),
    },
    undispute: {
      title: 'Resolve dispute and return to Posted',
      message: null,
      submit: 'Resolve',
      destructive: false,
      payload: () => ({ notes: reason.trim() || undefined }),
      valid: () => true,
      fields: (
        <div>
          <Label>Resolution notes (optional)</Label>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            data-testid="undispute-notes"
          />
        </div>
      ),
    },
    'release-retention': {
      title: 'Release retention',
      message: 'Marks the retention as released on the date below.',
      submit: 'Release',
      destructive: false,
      payload: () => ({ retention_release_date: retentionReleaseDate }),
      valid: () => !!retentionReleaseDate,
      fields: (
        <div>
          <Label>Release date</Label>
          <Input
            type="date"
            value={retentionReleaseDate}
            onChange={(e) => setRetentionReleaseDate(e.target.value)}
            data-testid="release-retention-date"
          />
        </div>
      ),
    },
  };

  if (!action) return null;
  const cfg = config[action];

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid={`action-dialog-${action}`}>
        <DialogHeader>
          <DialogTitle>{cfg.title}</DialogTitle>
        </DialogHeader>
        {cfg.message && <p className="text-sm text-slate-600">{cfg.message}</p>}
        {cfg.fields}
        <DialogFooter className="pt-3">
          <Button
            variant="ghost"
            onClick={onClose}
            data-testid="action-dialog-cancel"
          >
            Cancel
          </Button>
          <Button
            disabled={!cfg.valid()}
            className={
              cfg.destructive
                ? 'bg-sy-orange text-white hover:brightness-110 active:brightness-95'
                : 'bg-sy-teal text-white hover:brightness-110 active:brightness-95'
            }
            onClick={() => onSubmit(cfg.payload())}
            data-testid="action-dialog-submit"
          >
            {cfg.submit}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
