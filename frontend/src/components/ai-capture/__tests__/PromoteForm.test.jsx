// frontend/src/components/ai-capture/__tests__/PromoteForm.test.jsx — Chat 19C §R6.5
//
// E8 PREVENTION CRITICAL. The build pack §R3.2 I5/F2 invariant: useForm
// defaultValues MUST seed every required field listed in
// PromoteCaptureToActualRequestSchema. Test 2 below empirically asserts
// the full payload gets POSTed — if a future refactor drops a default,
// this test catches it.
//
// §R6.5 H11: BudgetLinePicker is stubbed (top of file) because its real
// implementation runs api.get responses through Zod schemas; mocking the
// budget endpoints triggers schema drift. The production picker is
// exercised by 19B's CreateActualSheet integration tests.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PromoteForm } from '@/components/ai-capture/PromoteForm';
import { makeAwaitingReviewJob } from '@/test/mocks/fixtures';

jest.mock('@/lib/api', () => ({
  api: {
    get:  jest.fn(),
    post: jest.fn(),
  },
}));
import { api } from '@/lib/api';

// §R6.5 H11 stub — see file header.
// UUIDs are real (schema validates project_id/entity_id/budget_line_id as
// z.string().uuid() — short ids like 'bl-1' fail validation and silently
// block form submission, which would mask the very payload assertion we're
// making here. PASS-4 erratum E10.
const PROJECT_UUID = '11111111-1111-1111-1111-111111111111';
const ENTITY_UUID  = '22222222-2222-2222-2222-222222222222';
const LINE_UUID_1  = '33333333-3333-3333-3333-333333333333';
const LINE_UUID_2  = '44444444-4444-4444-4444-444444444444';

jest.mock('@/components/actuals/BudgetLinePicker', () => ({
  BudgetLinePicker: ({ projectId, value, onChange, error }) => (
    <div data-testid="budget-line-picker">
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        data-testid="budget-line-picker-select"
        disabled={!projectId}
      >
        <option value="">Select a budget line…</option>
        <option value="33333333-3333-3333-3333-333333333333">Materials</option>
        <option value="44444444-4444-4444-4444-444444444444">Labour</option>
      </select>
      {error && <p data-testid="budget-line-picker-error">{error}</p>}
    </div>
  ),
}));

function renderForm(job, onPromoted = jest.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // §R6.5 H9: mock URLs must match `/v1/` prefix (lib/api.js baseURL=/api convention)
  api.get.mockImplementation((url) => {
    if (url.startsWith('/v1/entities')) return Promise.resolve({ data: { items: [{ id: ENTITY_UUID, name: 'SY Parent' }] } });
    if (url.startsWith('/v1/projects')) return Promise.resolve({ data: { items: [{ id: PROJECT_UUID, name: 'Demo Project' }] } });
    return Promise.resolve({ data: {} });
  });
  return {
    onPromoted,
    ...render(
      <QueryClientProvider client={qc}>
        <PromoteForm job={job} onPromoted={onPromoted} />
      </QueryClientProvider>,
    ),
  };
}

describe('PromoteForm', () => {
  // E8 CRITICAL TEST 1: form renders with defaultValues all seeded
  test('E8: form renders with all required defaultValues populated from job.extracted_data', async () => {
    const job = makeAwaitingReviewJob({
      extracted_data: {
        supplier_name: 'Acme Ltd',
        invoice_date: '2026-04-15',
        net_amount: '500.00',
        vat_amount: '100.00',
        vat_rate_pct: '20',
        description: 'Materials',
      },
    });
    renderForm(job);
    await waitFor(() => screen.getByTestId('promote-form'));

    expect(screen.getByTestId('promote-supplier')).toHaveValue('Acme Ltd');
    expect(screen.getByTestId('promote-date')).toHaveValue('2026-04-15');
    expect(screen.getByTestId('promote-net')).toHaveValue('500.00');
    expect(screen.getByTestId('promote-vat')).toHaveValue('100.00');
    expect(screen.getByTestId('promote-vat-rate')).toHaveValue('20');
    expect(screen.getByTestId('promote-description')).toHaveValue('Materials');
  });

  // E8 CRITICAL TEST 2: with everything filled, submit actually POSTs
  test('E8: submitting filled form dispatches POST /v1/ai-capture-jobs/:id/promote', async () => {
    const job = makeAwaitingReviewJob({
      suggested_project_id: PROJECT_UUID,
      suggested_entity_id: ENTITY_UUID,
      extracted_data: {
        supplier_name: 'Acme', invoice_date: '2026-04-15',
        net_amount: '500.00', vat_amount: '100.00', vat_rate_pct: '20',
        description: 'Materials',
      },
    });
    api.get.mockImplementation((url) => {
      if (url.startsWith('/v1/entities')) return Promise.resolve({ data: { items: [{ id: ENTITY_UUID, name: 'SY Parent' }] } });
      if (url.startsWith('/v1/projects')) return Promise.resolve({ data: { items: [{ id: PROJECT_UUID, name: 'Demo Project' }] } });
      return Promise.resolve({ data: {} });
    });
    api.post.mockResolvedValue({ data: { job, actual_id: 'a-1', actual_status: 'Draft' } });

    const onPromoted = jest.fn();
    renderForm(job, onPromoted);
    await waitFor(() => screen.getByTestId('promote-form'));
    await waitFor(() => screen.getByTestId('budget-line-picker'));

    fireEvent.change(screen.getByTestId('budget-line-picker-select'), { target: { value: LINE_UUID_1 } });
    fireEvent.click(screen.getByTestId('promote-submit'));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/v1/ai-capture-jobs/${job.id}/promote`,
        expect.objectContaining({
          project_id: PROJECT_UUID,
          budget_line_id: LINE_UUID_1,
          entity_id: ENTITY_UUID,
          supplier_name_snapshot: 'Acme',
          net_amount: '500.00',
        }),
      );
    });
    await waitFor(() => {
      expect(onPromoted).toHaveBeenCalledWith(
        expect.objectContaining({ actualId: 'a-1', projectId: PROJECT_UUID }),
      );
    });
  });

  test('E8: submit with missing required field surfaces error, no POST', async () => {
    const job = makeAwaitingReviewJob({ extracted_data: {} });
    renderForm(job);
    await waitFor(() => screen.getByTestId('promote-form'));
    fireEvent.click(screen.getByTestId('promote-submit'));
    await waitFor(() => {
      expect(screen.queryByTestId('promote-project-error')).toBeTruthy();
    });
    expect(api.post).not.toHaveBeenCalled();
  });

  test('CIS toggle hides/shows CIS fields', async () => {
    renderForm(makeAwaitingReviewJob());
    await waitFor(() => screen.getByTestId('promote-form'));
    expect(screen.queryByTestId('promote-cis-rate')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('promote-cis-toggle'));
    await waitFor(() => screen.getByTestId('promote-cis-rate'));
  });

  test('Suggested project_id pre-populates picker', async () => {
    const job = makeAwaitingReviewJob({ suggested_project_id: PROJECT_UUID });
    renderForm(job);
    await waitFor(() => screen.getByTestId('project-picker'));
  });

  test('Empty optional fields submit as null (supplier_invoice_ref, retention)', async () => {
    const job = makeAwaitingReviewJob({
      suggested_project_id: PROJECT_UUID,
      suggested_entity_id: ENTITY_UUID,
      extracted_data: {
        supplier_name: 'Acme', invoice_date: '2026-04-15',
        net_amount: '500.00', vat_amount: '100.00', vat_rate_pct: '20',
        description: 'Materials',
        supplier_invoice_ref: '',
      },
    });
    api.get.mockImplementation((url) => {
      if (url.startsWith('/v1/entities')) return Promise.resolve({ data: { items: [{ id: ENTITY_UUID, name: 'SY Parent' }] } });
      if (url.startsWith('/v1/projects')) return Promise.resolve({ data: { items: [{ id: PROJECT_UUID, name: 'Demo Project' }] } });
      return Promise.resolve({ data: {} });
    });
    api.post.mockResolvedValue({ data: { job, actual_id: 'a-1', actual_status: 'Draft' } });

    renderForm(job);
    await waitFor(() => screen.getByTestId('promote-form'));
    await waitFor(() => screen.getByTestId('budget-line-picker'));

    fireEvent.change(screen.getByTestId('budget-line-picker-select'), { target: { value: LINE_UUID_1 } });
    fireEvent.click(screen.getByTestId('promote-submit'));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/v1/ai-capture-jobs/${job.id}/promote`,
        expect.objectContaining({
          supplier_invoice_ref: null,
          retention_rate_pct: null,
          retention_amount: null,
          cis_deduction_rate_pct: null,
          cis_labour_amount: null,
          cis_materials_amount: null,
        }),
      );
    });
  });
});
