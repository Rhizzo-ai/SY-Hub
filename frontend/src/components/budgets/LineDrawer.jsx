/**
 * LineDrawer — Prompt 2.4B-i §R7.
 *
 * shadcn Sheet with rhf+Zod form on top + LineItemsPanel below.
 *
 * Erratas applied to spec:
 *   - E7  : `description` → `line_description`; `ftc_value` does NOT
 *           exist — Manual mode uses `forecast_to_complete` directly.
 *   - E8  : permission for edit is `budgets.edit`, NOT `budgets.create`.
 *   - E9  : Backend has NO `version` column on lines. Conflict-detect
 *           via `updated_at` instead. Capture `loadedAt = line.updated_at`
 *           when the drawer opens; on every render compare to the
 *           latest `line.updated_at` from cache. If it changed AND the
 *           form is dirty AND we didn't just save → show non-blocking
 *           "Reload" banner. Save success bumps loadedAt so we don't
 *           false-trigger after our own write.
 *   - Auth: `@/context/AuthContext` (singular `context`).
 *   - Items field rename: `unit_cost` → `rate` (E11, see LineItemsPanel).
 *
 * Spec-locked behaviour preserved:
 *   - dirtyFields-only patch body
 *   - defensive cost_code_id filter (only sent when costCodeMutable)
 *   - rhf form.reset on line identity change
 *   - close-with-dirty AlertDialog confirm
 *   - sensitive field gates (notes + ftc_method + manual FTC value)
 *   - Keyboard shortcuts (operator addition): Esc close,
 *     Ctrl/Cmd+S save. Standard, low-cost, finance/PM live here.
 */
import { useEffect, useRef, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter,
} from '@/components/ui/sheet';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { usePatchBudgetLine } from '@/hooks/budgets';
import { LineItemsPanel } from './LineItemsPanel';
import { CostCodePicker } from './CostCodePicker';
import { isBudgetEditable, isCostCodeMutable } from '@/lib/budgetCapability';

const FTC_METHODS = [
  { value: 'Budget_Remaining',    label: 'Budget remaining' },
  { value: 'Committed_Only',      label: 'Committed only' },
  { value: 'Percentage_Complete', label: 'Percentage complete' },
  { value: 'Manual',              label: 'Manual entry' },
];

// Client-side validation. Backend validates again — this catches typos
// early. `forecast_to_complete` is required-money at the schema level
// but optional in PATCH bodies (only sent when ftc_method=Manual).
const FormSchema = z.object({
  line_description: z.string().max(2000).nullable().optional(),
  notes: z.string().max(5000).nullable().optional(),
  ftc_method: z.enum(['Budget_Remaining','Committed_Only','Percentage_Complete','Manual']).nullable().optional(),
  forecast_to_complete: z.union([z.coerce.number().min(0), z.null()]).optional(),
  cost_code_id: z.string().uuid().optional(),
  percentage_complete: z.union([
    z.coerce.number().min(0).max(100),
    z.null(),
  ]).optional(),
});

export function LineDrawer({ budget, projectId, lineId, focus, onClose }) {
  const { me } = useAuth();
  const isDesktop = useIsDesktop();
  const canEdit = !!me?.permissions?.includes('budgets.edit') && isDesktop;
  const canSensitive = !!me?.permissions?.includes('budgets.view_sensitive');
  const editable = isBudgetEditable(budget.status) && canEdit;
  const costCodeMutable = isCostCodeMutable(budget.status) && canEdit;

  const line = budget.lines?.find((l) => l.id === lineId);
  const patchMut = usePatchBudgetLine(budget.id);

  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);

  // E9: conflict-detect via updated_at watermark. Bumped on (a) drawer
  // open with a new lineId, (b) successful save (so our own write
  // doesn't trip the banner), (c) user clicking Reload (form resets).
  const [loadedAt, setLoadedAt] = useState(line?.updated_at ?? null);
  // True for the brief window between Save success and the next
  // useEffect that bumps loadedAt — prevents the banner flashing.
  const justSavedRef = useRef(false);

  const form = useForm({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      line_description: line?.line_description ?? '',
      notes: line?.notes ?? '',
      ftc_method: line?.ftc_method ?? 'Budget_Remaining',
      forecast_to_complete: line?.forecast_to_complete ?? null,
      cost_code_id: line?.cost_code_id ?? '',
      percentage_complete: line?.percentage_complete ?? null,
    },
  });

  // Reset form + loadedAt when line identity changes (drawer opens on a
  // different row) OR when the user clicks Reload (handled inline below).
  useEffect(() => {
    if (!line) return;
    form.reset({
      line_description: line.line_description ?? '',
      notes: line.notes ?? '',
      ftc_method: line.ftc_method ?? 'Budget_Remaining',
      forecast_to_complete: line.forecast_to_complete ?? null,
      cost_code_id: line.cost_code_id ?? '',
      percentage_complete: line.percentage_complete ?? null,
    });
    setLoadedAt(line.updated_at ?? null);
    justSavedRef.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line?.id]);

  // After Save success, the parent cache re-fetches and `line.updated_at`
  // bumps. We bump loadedAt to match and re-baseline the form so dirty
  // state is fresh.
  useEffect(() => {
    if (!line || !justSavedRef.current) return;
    if (line.updated_at && line.updated_at !== loadedAt) {
      setLoadedAt(line.updated_at);
      form.reset({
        line_description: line.line_description ?? '',
        notes: line.notes ?? '',
        ftc_method: line.ftc_method ?? 'Budget_Remaining',
        forecast_to_complete: line.forecast_to_complete ?? null,
        cost_code_id: line.cost_code_id ?? '',
        percentage_complete: line.percentage_complete ?? null,
      });
      justSavedRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line?.updated_at]);

  const isDirty = form.formState.isDirty;
  const isConflict = !!line
    && loadedAt != null
    && line.updated_at != null
    && line.updated_at !== loadedAt
    && !justSavedRef.current;

  // Conflict reload: refresh form from cache, bump loadedAt.
  function handleReload() {
    if (!line) return;
    form.reset({
      line_description: line.line_description ?? '',
      notes: line.notes ?? '',
      ftc_method: line.ftc_method ?? 'Budget_Remaining',
      forecast_to_complete: line.forecast_to_complete ?? null,
      cost_code_id: line.cost_code_id ?? '',
      percentage_complete: line.percentage_complete ?? null,
    });
    setLoadedAt(line.updated_at ?? null);
  }

  // Build PATCH body from dirtyFields only. Defensive cost_code filter:
  // only include cost_code_id if (a) dirty AND (b) status permits.
  function buildPatchBody(values, dirtyFields) {
    const body = {};
    if (dirtyFields.line_description) body.line_description = values.line_description || null;
    if (dirtyFields.notes) body.notes = values.notes || null;
    if (dirtyFields.ftc_method) body.ftc_method = values.ftc_method;
    if (dirtyFields.forecast_to_complete) {
      body.forecast_to_complete = values.forecast_to_complete;
    }
    if (dirtyFields.percentage_complete) {
      body.percentage_complete = values.percentage_complete;
    }
    if (dirtyFields.cost_code_id && costCodeMutable) {
      body.cost_code_id = values.cost_code_id;
    }
    return body;
  }

  async function onSave(values) {
    if (!line) return;
    const body = buildPatchBody(values, form.formState.dirtyFields);
    if (Object.keys(body).length === 0) return;
    justSavedRef.current = true;
    try {
      await patchMut.mutateAsync({ lineId: line.id, body });
      toast.success('Line saved.');
    } catch (err) {
      justSavedRef.current = false;
      toast.error(
        err?.response?.data?.detail
        || err?.message
        || 'Save failed. Please retry.',
      );
    }
  }

  // Close handler with dirty-confirm
  function handleSheetOpenChange(open) {
    if (open) return;
    if (isDirty) {
      setCloseConfirmOpen(true);
      return;
    }
    onClose();
  }

  function discardAndClose() {
    setCloseConfirmOpen(false);
    onClose();
  }

  // Keyboard shortcuts: Esc close (handled natively by Sheet via
  // onOpenChange — confirms when dirty), Ctrl/Cmd+S save.
  useEffect(() => {
    if (!lineId) return;
    function onKey(e) {
      const isSave = (e.key === 's' || e.key === 'S')
        && (e.ctrlKey || e.metaKey);
      if (isSave) {
        e.preventDefault();
        if (!editable || patchMut.isPending || !isDirty) return;
        form.handleSubmit(onSave)();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineId, editable, patchMut.isPending, isDirty]);

  if (!line) return null;
  const ftcMethod = form.watch('ftc_method');

  // M6: disable inputs while pending so the form-reset doesn't clobber
  // mid-typing input state.
  const fieldsDisabled = !editable || patchMut.isPending;

  return (
    <>
      <Sheet open={!!lineId} onOpenChange={handleSheetOpenChange}>
        <SheetContent
          side="right"
          className="w-full max-w-xl overflow-y-auto sm:max-w-2xl"
          data-testid="line-drawer"
        >
          <SheetHeader>
            <SheetTitle data-testid="line-drawer-title">
              {(line.line_description?.trim() || 'Untitled line')}
              {' '}
              <span className="font-mono text-xs text-slate-500">
                · {line.cost_code_id.slice(-6)}
              </span>
            </SheetTitle>
          </SheetHeader>

          {/* E9 conflict banner */}
          {isConflict && (
            <div
              data-testid="line-drawer-conflict-banner"
              className="mt-4 flex items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
            >
              <span>
                This line was updated elsewhere since you opened it.
                {isDirty
                  ? ' Reload to discard your draft and refresh.'
                  : ' Reload to refresh.'}
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleReload}
                data-testid="line-drawer-reload"
              >
                Reload
              </Button>
            </div>
          )}

          <form
            onSubmit={form.handleSubmit(onSave, () => {
              toast.error('Please fix the highlighted errors before saving.');
            })}
            className="space-y-4 py-4"
          >
            <div className="space-y-1">
              <Label htmlFor="line-description">Description</Label>
              <Input
                id="line-description"
                {...form.register('line_description')}
                disabled={fieldsDisabled}
                maxLength={2000}
                data-testid="line-drawer-description"
              />
            </div>

            {canSensitive && (
              <div className="space-y-1">
                <Label htmlFor="line-notes">Notes (sensitive)</Label>
                <Textarea
                  id="line-notes"
                  rows={4}
                  {...form.register('notes')}
                  disabled={fieldsDisabled}
                  maxLength={5000}
                  data-testid="line-drawer-notes"
                />
              </div>
            )}

            <div className="space-y-1">
              <Label>
                FTC method
                {!canSensitive && (
                  <span className="ml-1 text-xs text-slate-500">
                    (hidden — request elevated access)
                  </span>
                )}
              </Label>
              <Controller
                name="ftc_method"
                control={form.control}
                render={({ field }) => (
                  <Select
                    value={field.value ?? 'Budget_Remaining'}
                    onValueChange={field.onChange}
                    disabled={fieldsDisabled || !canSensitive}
                  >
                    <SelectTrigger data-testid="line-drawer-ftc-method">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FTC_METHODS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            {ftcMethod === 'Manual' && canSensitive && (
              <div className="space-y-1">
                <Label htmlFor="line-ftc-value">Manual FTC (£)</Label>
                <Input
                  id="line-ftc-value"
                  type="number"
                  step="0.01"
                  min={0}
                  {...form.register('forecast_to_complete')}
                  disabled={fieldsDisabled}
                  data-testid="line-drawer-ftc-value"
                />
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="line-pct">% Complete</Label>
              <Input
                id="line-pct"
                type="number"
                min={0}
                max={100}
                step={1}
                {...form.register('percentage_complete')}
                disabled={fieldsDisabled}
                data-testid="line-drawer-pct"
              />
            </div>

            <div className="space-y-1">
              <Label>Cost code</Label>
              <Controller
                name="cost_code_id"
                control={form.control}
                render={({ field }) => (
                  <CostCodePicker
                    projectId={projectId ?? budget.project_id}
                    value={field.value}
                    onChange={(v) => form.setValue('cost_code_id', v,
                      { shouldDirty: true, shouldValidate: true })}
                    disabled={fieldsDisabled || !costCodeMutable}
                  />
                )}
              />
              {!costCodeMutable && (
                <p className="text-xs text-slate-500">
                  Cost code can only be changed while budget is Draft.
                </p>
              )}
            </div>

            <SheetFooter className="sticky bottom-0 -mx-6 border-t border-slate-200 bg-white px-6 py-3">
              <div className="flex w-full items-center justify-between">
                <span
                  className="text-xs text-slate-500"
                  data-testid="line-drawer-dirty-state"
                >
                  {isDirty ? 'Unsaved changes' : 'No changes'}
                  <span className="ml-2 text-slate-400">
                    · Cmd/Ctrl+S to save · Esc to close
                  </span>
                </span>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => handleSheetOpenChange(false)}
                    data-testid="line-drawer-close"
                  >
                    Close
                  </Button>
                  <Button
                    type="submit"
                    className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
                    disabled={!editable || patchMut.isPending || !isDirty}
                    data-testid="line-drawer-save"
                  >
                    {patchMut.isPending ? 'Saving…' : 'Save'}
                  </Button>
                </div>
              </div>
            </SheetFooter>
          </form>

          <div className="border-t border-slate-200 pt-6">
            <LineItemsPanel
              budget={budget}
              line={line}
              initialFocus={focus === 'items'}
            />
          </div>
        </SheetContent>
      </Sheet>

      <DiscardChangesDialog
        open={closeConfirmOpen}
        onConfirm={discardAndClose}
        onCancel={() => setCloseConfirmOpen(false)}
      />
    </>
  );
}

function DiscardChangesDialog({ open, onConfirm, onCancel }) {
  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <AlertDialogContent data-testid="line-drawer-discard-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
          <AlertDialogDescription>
            You have unsaved edits. Closing now will lose them.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            onClick={onCancel}
            data-testid="line-drawer-discard-cancel"
          >
            Keep editing
          </AlertDialogCancel>
          <AlertDialogAction
            className="bg-sy-orange text-white hover:brightness-110 active:brightness-95"
            onClick={onConfirm}
            data-testid="line-drawer-discard-confirm"
          >
            Discard
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
