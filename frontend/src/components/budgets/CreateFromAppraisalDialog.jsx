/**
 * CreateFromAppraisalDialog — Prompt 2.4B-i §R4.5.
 *
 * shadcn Dialog with a lazy `enabled` flag (D12 / H3 fix). The appraisals
 * list only fetches when the dialog opens. Excludes appraisals already
 * linked to an existing budget via `existingSourceAppraisalIds` (E7.1).
 *
 * Backend body shape (verified):
 *   { source_appraisal_id: UUID, notes?: string }
 *
 * Permission gate happens at the call-site (BudgetsList) — this component
 * trusts that the trigger is only rendered for users with `budgets.create`
 * + desktop.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useApprovedAppraisals } from '@/hooks/appraisals';
import { useCreateBudgetFromAppraisal } from '@/hooks/budgets';
import { formatMoney } from '@/lib/format';

export function CreateFromAppraisalDialog({ projectId, budgets = [], trigger }) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const navigate = useNavigate();

  // Exclude appraisals already linked as source for an existing
  // non-superseded budget.
  const existingSourceAppraisalIds = useMemo(() => {
    const s = new Set();
    for (const b of budgets ?? []) {
      if (b?.source_appraisal_id && b?.status !== 'Superseded') {
        s.add(b.source_appraisal_id);
      }
    }
    return s;
  }, [budgets]);

  const { data: appraisals = [], isLoading } = useApprovedAppraisals(
    projectId,
    { enabled: open, existingSourceAppraisalIds },
  );
  const createMut = useCreateBudgetFromAppraisal(projectId);

  async function handleCreate() {
    if (!selectedId) return;
    setErrorMsg('');
    try {
      const newBudget = await createMut.mutateAsync({
        source_appraisal_id: selectedId,
      });
      setOpen(false);
      setSelectedId(null);
      if (newBudget?.id) {
        navigate(`/projects/${projectId}/budgets/${newBudget.id}`);
      }
    } catch (err) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Failed to create budget.');
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) {
          setSelectedId(null);
          setErrorMsg('');
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent data-testid="create-budget-dialog">
        <DialogHeader>
          <DialogTitle>Create budget from approved appraisal</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <p className="text-sm text-slate-500" data-testid="create-budget-loading">
            Loading appraisals…
          </p>
        ) : appraisals.length === 0 ? (
          <p className="text-sm text-slate-500" data-testid="create-budget-empty">
            No approved appraisals available. An appraisal must be{' '}
            <code>Approved</code> and not already linked to a current budget.
          </p>
        ) : (
          <RadioGroup
            value={selectedId ?? ''}
            onValueChange={setSelectedId}
            data-testid="create-budget-appraisal-list"
          >
            {appraisals.map((a) => (
              <div key={a.id} className="flex items-center space-x-2 py-1">
                <RadioGroupItem
                  value={a.id}
                  id={`appraisal-${a.id}`}
                  data-testid={`create-budget-option-${a.id}`}
                />
                <Label htmlFor={`appraisal-${a.id}`} className="cursor-pointer">
                  <span className="font-medium text-slate-900">{a.name}</span>
                  {a.total_cost != null && (
                    <span className="ml-2 font-mono text-xs text-slate-500">
                      {formatMoney(a.total_cost)}
                    </span>
                  )}
                </Label>
              </div>
            ))}
          </RadioGroup>
        )}

        {errorMsg && (
          <p
            data-testid="create-budget-error"
            className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
          >
            {errorMsg}
          </p>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setOpen(false)}
            data-testid="create-budget-cancel"
          >
            Cancel
          </Button>
          <Button
            className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
            disabled={!selectedId || createMut.isPending}
            onClick={handleCreate}
            data-testid="create-budget-confirm"
          >
            {createMut.isPending ? 'Creating…' : 'Create budget'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
