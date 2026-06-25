/**
 * CreateActualSheet (Chat 19B §R3.2).
 *
 * Side-Sheet form on desktop; ActualNew route renders this same Sheet
 * always-open as the mobile / deep-link entry. Uses react-hook-form +
 * Zod validation against the backend `CreateActualRequestSchema`.
 *
 * Network: `useCreateActual()` mutation — on success, toast + reset + close.
 *          The hook's onSuccess invalidates `['actuals']` and
 *          `['actuals','project',projectId]` so ActualsList auto-refetches.
 */
import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { BudgetLinePicker } from './BudgetLinePicker';
import { CommitmentLinePicker } from './CommitmentLinePicker';
import { useCreateActual } from '@/hooks/actuals';
import { api } from '@/lib/api';
import { CreateActualRequestSchema } from '@/lib/schemas/actuals';

// Inline `useEntities` hook — no shared one exists; EntitiesList.jsx calls
// `api.get('/entities')` directly. Wrapped here so re-renders share the cache.
function useEntitiesList({ enabled = true } = {}) {
  return useQuery({
    queryKey: ['entities', 'all'],
    queryFn: async ({ signal }) => {
      const { data } = await api.get('/entities', {
        params: { page: 1, page_size: 200, sort: 'name', dir: 'asc' },
        signal,
      });
      return data;
    },
    enabled,
    staleTime: 60_000,
  });
}

const todayIso = () => new Date().toISOString().slice(0, 10);

const DEFAULTS = {
  budget_line_id: '',
  entity_id: '',
  source_type: 'Manual_Entry',
  transaction_date: todayIso(),
  description: '',
  net_amount: '',
  vat_amount: '0',
  vat_rate_pct: '20',
  is_vat_recoverable: true,
  currency: 'GBP',
  supplier_name_snapshot: '',
  supplier_invoice_ref: '',
  is_cis_applicable: false,
};

export function CreateActualSheet({ open, onOpenChange, projectId }) {
  const createMut = useCreateActual();
  const { data: entitiesData } = useEntitiesList({ enabled: !!open });
  const entities = entitiesData?.items ?? [];

  const {
    register, handleSubmit, watch, setValue, reset,
    formState: { errors },
  } = useForm({
    // `project_id` is required by `CreateActualRequestSchema` (uuid). Seed it
    // into the form defaults so Zod validation passes before onSubmit runs —
    // otherwise the form would silently reject every submit (no POST fires).
    defaultValues: { ...DEFAULTS, project_id: projectId },
    resolver: zodResolver(CreateActualRequestSchema),
  });

  const isCis = watch('is_cis_applicable');

  // C1-front §R4.3 — force-the-choice commitment link. `linkedCommitmentId`
  // and `isStandalone` are held locally (not RHF fields): `linked_commitment_id`
  // is an OPTIONAL uuid in the schema, so seeding it as "" would fail Zod —
  // we send it explicitly at submit instead. `isStandalone` is UI-only and is
  // never sent on the wire.
  const budgetLineId = watch('budget_line_id');
  const [linkedCommitmentId, setLinkedCommitmentId] = useState(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [commitmentError, setCommitmentError] = useState('');
  const [resetNote, setResetNote] = useState(false);

  const clearCommitmentChoice = () => {
    setLinkedCommitmentId(null);
    setIsStandalone(false);
    setCommitmentError('');
    setResetNote(false);
  };

  // Locked decision 4 — changing the budget line after a choice was made
  // clears the PO-line choice and shows a brief note. Guard the initial set
  // (no prior value ⇒ nothing to reset).
  const prevBudgetLineRef = useRef(budgetLineId);
  useEffect(() => {
    const prev = prevBudgetLineRef.current;
    if (prev && budgetLineId && prev !== budgetLineId) {
      setLinkedCommitmentId(null);
      setIsStandalone(false);
      setCommitmentError('');
      setResetNote(true);
    }
    prevBudgetLineRef.current = budgetLineId;
  }, [budgetLineId]);

  // Auto-dismiss the transient reset note.
  useEffect(() => {
    if (!resetNote) return undefined;
    const t = setTimeout(() => setResetNote(false), 4000);
    return () => clearTimeout(t);
  }, [resetNote]);

  const onSubmit = (data) => {
    // C1-front §R4.3 gate — block submit until the user picks a PO line OR
    // explicitly chooses "No PO available". Inline error explains why.
    const hasChoice = !!linkedCommitmentId || isStandalone === true;
    if (!hasChoice) {
      setCommitmentError(
        "Choose the purchase order this bill pays, or tick 'No PO available'.",
      );
      return;
    }
    // Strip blank optional fields so backend doesn't trip on "" vs absent.
    const body = {
      project_id: projectId,
      ...data,
      supplier_invoice_ref: data.supplier_invoice_ref || undefined,
      // Standalone ⇒ omit the link entirely; PO-line selected ⇒ send its id.
      linked_commitment_id: isStandalone ? undefined : (linkedCommitmentId || undefined),
      cis_deduction_rate_pct: data.is_cis_applicable
        ? data.cis_deduction_rate_pct
        : undefined,
      cis_labour_amount: data.is_cis_applicable
        ? data.cis_labour_amount
        : undefined,
      cis_materials_amount: data.is_cis_applicable
        ? data.cis_materials_amount
        : undefined,
    };
    createMut.mutate(body, {
      onSuccess: () => {
        toast.success('Draft actual created');
        reset();
        clearCommitmentChoice();
        onOpenChange(false);
      },
      onError: (err) => {
        const detail = err?.response?.data?.detail;
        const msg =
          typeof detail === 'string'
            ? detail
            : detail?.message ?? err?.message ?? 'Failed to create actual';
        toast.error(msg);
      },
    });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Create Draft actual</SheetTitle>
        </SheetHeader>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="space-y-4 py-4"
          data-testid="create-actual-form"
        >
          <div>
            <Label>Budget line</Label>
            <BudgetLinePicker
              projectId={projectId}
              value={watch('budget_line_id')}
              onChange={(v) =>
                setValue('budget_line_id', v || '', { shouldValidate: true })
              }
              error={errors.budget_line_id?.message}
            />
          </div>

          <div>
            <Label>Purchase order</Label>
            <CommitmentLinePicker
              projectId={projectId}
              budgetLineId={budgetLineId}
              value={linkedCommitmentId}
              onChange={(v) => {
                setLinkedCommitmentId(v);
                setCommitmentError('');
                setResetNote(false);
              }}
              standalone={isStandalone}
              onStandaloneChange={(v) => {
                setIsStandalone(v);
                if (v) {
                  setLinkedCommitmentId(null);
                  setCommitmentError('');
                }
                setResetNote(false);
              }}
              error={commitmentError}
            />
            {resetNote && (
              <p
                className="mt-1 text-xs text-amber-700"
                data-testid="commitment-reset-note"
              >
                Purchase order choice reset — budget line changed.
              </p>
            )}
          </div>

          <div>
            <Label>Entity</Label>
            <Select
              value={watch('entity_id') || undefined}
              onValueChange={(v) =>
                setValue('entity_id', v, { shouldValidate: true })
              }
            >
              <SelectTrigger data-testid="create-actual-entity">
                <SelectValue placeholder="Select an entity…" />
              </SelectTrigger>
              <SelectContent>
                {entities.map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.display_name || e.legal_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.entity_id && (
              <p className="mt-1 text-sm text-rose-600">
                {errors.entity_id.message}
              </p>
            )}
          </div>

          <div>
            <Label>Source type</Label>
            <Select
              value={watch('source_type')}
              onValueChange={(v) => setValue('source_type', v)}
            >
              <SelectTrigger data-testid="create-actual-source-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Manual_Entry">Manual entry</SelectItem>
                <SelectItem value="Day_Rate_Timesheet">Day-rate timesheet</SelectItem>
                <SelectItem value="Expense_Claim">Expense claim</SelectItem>
                <SelectItem value="Journal">Journal</SelectItem>
                <SelectItem value="Internal_Recharge">Internal recharge</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Transaction date</Label>
              <Input
                type="date"
                {...register('transaction_date')}
                data-testid="create-actual-date"
              />
            </div>
            <div>
              <Label>Currency</Label>
              <Input
                {...register('currency')}
                data-testid="create-actual-currency"
              />
            </div>
          </div>

          <div>
            <Label>Description</Label>
            <Textarea
              {...register('description')}
              rows={3}
              data-testid="create-actual-description"
            />
            {errors.description && (
              <p className="mt-1 text-sm text-rose-600">
                {errors.description.message}
              </p>
            )}
          </div>

          <div>
            <Label>Supplier name</Label>
            <Input
              {...register('supplier_name_snapshot')}
              data-testid="create-actual-supplier"
            />
            {errors.supplier_name_snapshot && (
              <p className="mt-1 text-sm text-rose-600">
                {errors.supplier_name_snapshot.message}
              </p>
            )}
          </div>

          <div>
            <Label>Supplier invoice ref</Label>
            <Input
              {...register('supplier_invoice_ref')}
              data-testid="create-actual-invoice-ref"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Net</Label>
              <Input
                {...register('net_amount')}
                inputMode="decimal"
                placeholder="0.00"
                data-testid="create-actual-net"
              />
              {errors.net_amount && (
                <p className="mt-1 text-xs text-rose-600">
                  {errors.net_amount.message}
                </p>
              )}
            </div>
            <div>
              <Label>VAT</Label>
              <Input
                {...register('vat_amount')}
                inputMode="decimal"
                placeholder="0.00"
                data-testid="create-actual-vat"
              />
            </div>
            <div>
              <Label>VAT rate %</Label>
              <Input
                {...register('vat_rate_pct')}
                inputMode="decimal"
                data-testid="create-actual-vat-rate"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="is-vat-recoverable"
              checked={watch('is_vat_recoverable')}
              onCheckedChange={(v) => setValue('is_vat_recoverable', !!v)}
              data-testid="create-actual-vat-recoverable"
            />
            <Label htmlFor="is-vat-recoverable" className="font-normal">
              VAT is recoverable
            </Label>
          </div>

          <div className="rounded-md border border-slate-200 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Checkbox
                id="cis-applicable"
                checked={!!isCis}
                onCheckedChange={(v) => setValue('is_cis_applicable', !!v)}
                data-testid="create-actual-cis-applicable"
              />
              <Label htmlFor="cis-applicable" className="font-normal">
                CIS applies
              </Label>
            </div>
            {isCis && (
              <div className="grid grid-cols-3 gap-3 pt-2" data-testid="cis-fields">
                <div>
                  <Label className="text-xs">Rate %</Label>
                  <Select
                    value={watch('cis_deduction_rate_pct') ?? ''}
                    onValueChange={(v) =>
                      setValue('cis_deduction_rate_pct', v || undefined)
                    }
                  >
                    <SelectTrigger data-testid="create-actual-cis-rate">
                      <SelectValue placeholder="Rate" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">0%</SelectItem>
                      <SelectItem value="20">20%</SelectItem>
                      <SelectItem value="30">30%</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Labour amount</Label>
                  <Input
                    {...register('cis_labour_amount')}
                    inputMode="decimal"
                    data-testid="create-actual-cis-labour"
                  />
                </div>
                <div>
                  <Label className="text-xs">Materials amount</Label>
                  <Input
                    {...register('cis_materials_amount')}
                    inputMode="decimal"
                    data-testid="create-actual-cis-materials"
                  />
                </div>
              </div>
            )}
          </div>

          <SheetFooter className="pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={createMut.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={createMut.isPending}
              className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
              data-testid="create-actual-submit"
            >
              {createMut.isPending ? 'Creating…' : 'Create Draft'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
