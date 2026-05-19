// frontend/src/components/ai-capture/PromoteForm.jsx — Chat 19C §R3.2
//
// E8-CRITICAL component. The form has 16 fields (8 required, 8 optional)
// mapped to PromoteCaptureToActualRequestSchema. Invariant I5 / Failure F2
// applies: useForm.defaultValues MUST seed every required field listed in
// the schema. Empty-string optionals are converted to null before POST
// (Zod's decimal regex rejects '').
//
// CIS section: when `is_cis_applicable` is OFF, all three CIS fields are
// zeroed (null) wholesale. When ON, each field is independently blank-to-
// null cleaned — the operator may legitimately fill rate-only or amount-
// only and leave the others blank (PASS-3 H6).
//
// Retention: has NO toggle. Each field is per-field blank-to-null cleaned.
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { BudgetLinePicker } from '@/components/actuals/BudgetLinePicker';
import { ProjectPicker } from '@/components/ai-capture/ProjectPicker';
import { usePromoteCapture } from '@/hooks/aiCapture';
import { PromoteCaptureToActualRequestSchema } from '@/lib/schemas/aiCapture';
import { api } from '@/lib/api';

function useEntities() {
  return useQuery({
    queryKey: ['entities'],
    // Backend: `entities_router` is mounted under `api_router` directly
    // (server.py:138 — NO `/v1/` prefix). Axios baseURL already resolves
    // to `${REACT_APP_BACKEND_URL}/api`, so the call becomes
    // `${REACT_APP_BACKEND_URL}/api/entities`. The previous `/v1/entities`
    // path 404'd silently (caught by the `?? []` fallback) → see
    // Future_Tasks §11 audit.
    queryFn: async () => (await api.get('/entities')).data?.items ?? [],
    staleTime: 60_000,
  });
}

export function PromoteForm({ job, onPromoted }) {
  const { data: entities = [] } = useEntities();
  const promote = usePromoteCapture(job.id);

  // E8 lesson — every required field in the schema must be present in
  // defaultValues. Zod's required fields don't honour .default() when
  // the form's initial value is `undefined`.
  const defaultValues = {
    project_id: job.suggested_project_id ?? '',
    budget_line_id: '',
    entity_id: job.suggested_entity_id ?? '',
    transaction_date:
      job.extracted_data?.invoice_date
      ?? new Date().toISOString().slice(0, 10),
    description: job.extracted_data?.description ?? '',
    net_amount: job.extracted_data?.net_amount ?? '',
    vat_amount: job.extracted_data?.vat_amount ?? '0',
    vat_rate_pct: job.extracted_data?.vat_rate_pct ?? '20',
    supplier_name_snapshot: job.extracted_data?.supplier_name ?? '',
    supplier_invoice_ref: job.extracted_data?.supplier_invoice_ref ?? '',
    is_cis_applicable: false,
    cis_deduction_rate_pct: null,
    cis_labour_amount: null,
    cis_materials_amount: null,
    retention_rate_pct: null,
    retention_amount: null,
  };

  const {
    register, handleSubmit, control, watch, formState: { errors },
  } = useForm({
    resolver: zodResolver(PromoteCaptureToActualRequestSchema),
    defaultValues,
    mode: 'onBlur',
  });

  const projectId = watch('project_id');
  const isCisOn = watch('is_cis_applicable');

  async function onSubmit(values) {
    const payload = { ...values };
    const blankToNull = (v) => (v === '' || v == null ? null : v);

    if (!payload.supplier_invoice_ref) payload.supplier_invoice_ref = null;

    if (!isCisOn) {
      payload.cis_deduction_rate_pct = null;
      payload.cis_labour_amount = null;
      payload.cis_materials_amount = null;
    } else {
      payload.cis_deduction_rate_pct = blankToNull(payload.cis_deduction_rate_pct);
      payload.cis_labour_amount = blankToNull(payload.cis_labour_amount);
      payload.cis_materials_amount = blankToNull(payload.cis_materials_amount);
    }

    // Retention has no toggle — per-field independent cleanup.
    payload.retention_rate_pct = blankToNull(payload.retention_rate_pct);
    payload.retention_amount = blankToNull(payload.retention_amount);

    try {
      const result = await promote.mutateAsync(payload);
      // PASS-2 H1: read project_id from the operator's chosen value, not
      // from stale job.suggested_project_id (the operator may have overridden).
      onPromoted?.({ ...result, projectId: values.project_id });
    } catch {
      // toast surfaced by the hook
    }
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      data-testid="promote-form"
      className="space-y-3 rounded-md border border-slate-200 bg-white p-4"
    >
      <h2 className="font-heading text-base text-slate-900">
        Promote to Draft actual
      </h2>

      <div>
        <Label htmlFor="project_id">Project*</Label>
        <Controller
          name="project_id"
          control={control}
          render={({ field }) => (
            <ProjectPicker
              value={field.value}
              onChange={field.onChange}
              suggested={job.suggested_project_id}
            />
          )}
        />
        {errors.project_id && (
          <p className="mt-1 text-sm text-rose-600" data-testid="promote-project-error">
            {errors.project_id.message}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="entity_id">Entity*</Label>
        <Controller
          name="entity_id"
          control={control}
          render={({ field }) => (
            <Select value={field.value || ''} onValueChange={field.onChange}>
              <SelectTrigger data-testid="promote-entity">
                <SelectValue placeholder="Select entity…" />
              </SelectTrigger>
              <SelectContent>
                {entities.map((e) => (
                  <SelectItem
                    key={e.id}
                    value={e.id}
                    data-testid={`promote-entity-${e.id}`}
                  >
                    {e.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        {errors.entity_id && (
          <p className="mt-1 text-sm text-rose-600" data-testid="promote-entity-error">
            {errors.entity_id.message}
          </p>
        )}
      </div>

      <div>
        <Label>Budget line*</Label>
        {projectId ? (
          <Controller
            name="budget_line_id"
            control={control}
            render={({ field }) => (
              <BudgetLinePicker
                projectId={projectId}
                value={field.value}
                onChange={field.onChange}
                error={errors.budget_line_id?.message}
              />
            )}
          />
        ) : (
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
            Select a project first.
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="transaction_date">Date*</Label>
          <Input
            id="transaction_date"
            type="date"
            data-testid="promote-date"
            {...register('transaction_date')}
          />
          {errors.transaction_date && (
            <p className="mt-1 text-sm text-rose-600">{errors.transaction_date.message}</p>
          )}
        </div>
        <div>
          <Label htmlFor="supplier_invoice_ref">Invoice ref</Label>
          <Input
            id="supplier_invoice_ref"
            data-testid="promote-invoice-ref"
            {...register('supplier_invoice_ref')}
          />
        </div>
      </div>

      <div>
        <Label htmlFor="supplier_name_snapshot">Supplier name*</Label>
        <Input
          id="supplier_name_snapshot"
          data-testid="promote-supplier"
          {...register('supplier_name_snapshot')}
        />
        {errors.supplier_name_snapshot && (
          <p className="mt-1 text-sm text-rose-600">
            {errors.supplier_name_snapshot.message}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="description">Description*</Label>
        <Textarea
          id="description"
          rows={3}
          data-testid="promote-description"
          {...register('description')}
        />
        {errors.description && (
          <p className="mt-1 text-sm text-rose-600">{errors.description.message}</p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <Label htmlFor="net_amount">Net (£)*</Label>
          <Input id="net_amount" data-testid="promote-net" {...register('net_amount')} />
          {errors.net_amount && (
            <p className="mt-1 text-sm text-rose-600">{errors.net_amount.message}</p>
          )}
        </div>
        <div>
          <Label htmlFor="vat_amount">VAT (£)</Label>
          <Input id="vat_amount" data-testid="promote-vat" {...register('vat_amount')} />
        </div>
        <div>
          <Label htmlFor="vat_rate_pct">VAT rate (%)</Label>
          <Input id="vat_rate_pct" data-testid="promote-vat-rate" {...register('vat_rate_pct')} />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Controller
          name="is_cis_applicable"
          control={control}
          render={({ field }) => (
            <Checkbox
              id="is_cis_applicable"
              checked={field.value}
              onCheckedChange={field.onChange}
              data-testid="promote-cis-toggle"
            />
          )}
        />
        <Label htmlFor="is_cis_applicable">CIS applies</Label>
      </div>
      {isCisOn && (
        <div className="grid grid-cols-3 gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
          <div>
            <Label>CIS rate (%)</Label>
            <Input data-testid="promote-cis-rate" {...register('cis_deduction_rate_pct')} />
          </div>
          <div>
            <Label>CIS labour (£)</Label>
            <Input data-testid="promote-cis-labour" {...register('cis_labour_amount')} />
          </div>
          <div>
            <Label>CIS materials (£)</Label>
            <Input data-testid="promote-cis-materials" {...register('cis_materials_amount')} />
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button
          type="submit"
          disabled={promote.isPending}
          className="bg-sy-teal text-white hover:brightness-110"
          data-testid="promote-submit"
        >
          {promote.isPending ? 'Promoting…' : 'Promote to Draft actual'}
        </Button>
      </div>
    </form>
  );
}
