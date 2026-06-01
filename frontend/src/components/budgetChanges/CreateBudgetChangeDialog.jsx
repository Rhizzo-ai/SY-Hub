/**
 * <CreateBudgetChangeDialog/> — Surface C.
 *
 * Modal form for POST /api/v1/budget-changes. Mirrors the backend
 * BCRCreateBody shape exactly:
 *   { budget_id, change_type, title, reason?, lines: [{budget_line_id, delta}] }
 *
 * Client-side mirrors the backend invariants so the user gets fast
 * feedback (backend remains the authority — server 422 surfaces as a
 * toast):
 *   - Transfer       — ≥2 lines, net == 0
 *   - ContingencyDrawdown — ≥2 lines, net == 0, every negative source
 *                            line must be is_contingency
 *   - Adjustment     — net != 0
 *
 * On success: invalidates the queue + change log; redirects to the
 * new BCR's detail page (Surface B) via `onCreated(bcr)` callback.
 */
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';

import BCRLineEditor from '@/components/budgetChanges/BCRLineEditor';
import { useCreateBCR } from '@/hooks/budgetChanges';
import { useBudget } from '@/hooks/budgets';

const CHANGE_TYPES = [
  { value: 'Transfer',
    label: 'Transfer',
    hint: 'Move budget between lines. Net must be £0.' },
  { value: 'ContingencyDrawdown',
    label: 'Contingency drawdown',
    hint: 'Draw from a contingency line into another. Net must be £0.' },
  { value: 'Adjustment',
    label: 'Adjustment',
    hint: 'Net change to the budget total. Net must be non-zero.' },
];

function validateBeforeSubmit({ changeType, title, lines, budgetLinesById }) {
  if (!changeType) return 'Choose a change type.';
  if (!title.trim()) return 'Title is required.';
  if (!Array.isArray(lines) || lines.length === 0) {
    return 'Add at least one line.';
  }
  for (const ln of lines) {
    if (!ln.budget_line_id) return 'Every line needs a budget-line selection.';
    const n = Number(ln.delta);
    if (!Number.isFinite(n) || n === 0) {
      return 'Every line needs a non-zero delta.';
    }
  }
  const net = lines.reduce((acc, ln) => acc + Number(ln.delta), 0);
  if (changeType === 'Transfer') {
    if (lines.length < 2) return 'Transfer requires at least 2 lines.';
    if (Math.abs(net) > 0.001) return 'Transfer net must be £0.';
  } else if (changeType === 'ContingencyDrawdown') {
    if (lines.length < 2) {
      return 'ContingencyDrawdown requires at least 2 lines.';
    }
    if (Math.abs(net) > 0.001) {
      return 'ContingencyDrawdown net must be £0.';
    }
    // Every negative line must reference a contingency budget-line.
    for (const ln of lines) {
      const delta = Number(ln.delta);
      if (delta < 0) {
        const target = budgetLinesById[ln.budget_line_id];
        if (target && !target.is_contingency) {
          return 'Source lines on a contingency drawdown must be flagged is_contingency.';
        }
      }
    }
  } else if (changeType === 'Adjustment') {
    if (Math.abs(net) < 0.001) return 'Adjustment must have a non-zero net.';
  }
  return null;
}

export default function CreateBudgetChangeDialog({
  open, onOpenChange, budgetId, onCreated,
}) {
  const { data: budget } = useBudget(budgetId, { enabled: !!budgetId && open });
  const createMut = useCreateBCR();

  const [changeType, setChangeType] = useState(undefined);
  const [title, setTitle] = useState('');
  const [reason, setReason] = useState('');
  const [lines, setLines] = useState([]);

  const budgetLines = budget?.lines ?? [];
  const budgetLinesById = useMemo(
    () => Object.fromEntries(budgetLines.map((bl) => [bl.id, bl])),
    [budgetLines],
  );

  const reset = () => {
    setChangeType('');
    setTitle('');
    setReason('');
    setLines([]);
  };

  const close = () => {
    reset();
    onOpenChange(false);
  };

  const submit = async () => {
    const err = validateBeforeSubmit({
      changeType, title, lines, budgetLinesById,
    });
    if (err) {
      toast.error(err);
      return;
    }
    try {
      const bcr = await createMut.mutateAsync({
        budget_id: budgetId,
        change_type: changeType,
        title: title.trim(),
        reason: reason.trim() || null,
        lines: lines.map((ln) => ({
          budget_line_id: ln.budget_line_id,
          delta: String(ln.delta),
        })),
      });
      toast.success(`BCR ${bcr.reference} created`);
      close();
      onCreated?.(bcr);
    } catch (e) {
      toast.error(
        e?.response?.data?.detail
        ?? e?.friendlyMessage
        ?? 'Create failed',
      );
    }
  };

  const selectedType = CHANGE_TYPES.find((t) => t.value === changeType);

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(o) : close())}>
      <DialogContent
        data-testid="bcr-create-dialog"
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>New budget change</DialogTitle>
          <DialogDescription>
            Raise a draft change against this budget. Transfer and
            Contingency drawdowns must net to £0; an Adjustment must
            have a non-zero net.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="bcr-create-change-type">Change type</Label>
              <Select
                value={changeType}
                onValueChange={setChangeType}
              >
                <SelectTrigger
                  id="bcr-create-change-type"
                  data-testid="bcr-create-change-type"
                >
                  <SelectValue placeholder="Choose…" />
                </SelectTrigger>
                <SelectContent>
                  {CHANGE_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedType ? (
                <p className="mt-1 text-xs text-slate-500">
                  {selectedType.hint}
                </p>
              ) : null}
            </div>
            <div>
              <Label htmlFor="bcr-create-title">Title</Label>
              <Input
                id="bcr-create-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Short, human title"
                maxLength={200}
                data-testid="bcr-create-title"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="bcr-create-reason">Reason (optional)</Label>
            <Textarea
              id="bcr-create-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              placeholder="Context, link to RFI / variation, etc."
              data-testid="bcr-create-reason"
            />
          </div>

          <div>
            <Label>Lines</Label>
            <BCRLineEditor
              value={lines}
              onChange={setLines}
              changeType={changeType}
              budgetLines={budgetLines}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={close}
            data-testid="bcr-create-cancel"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={submit}
            disabled={createMut.isPending}
            data-testid="bcr-create-submit"
          >
            {createMut.isPending ? 'Creating…' : 'Create draft'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
