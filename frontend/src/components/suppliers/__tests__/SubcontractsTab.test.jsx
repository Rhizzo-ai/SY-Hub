/**
 * <SubcontractsTab/> tests — Build Pack 2.8-FE-i §R6, Gate 2.
 *
 * Single-file integration suite spanning list + detail + form +
 * actions. Mocks the hook layer (lib/api/__tests__/subcontracts.test.js
 * pins the wire) so we can assert UI invariants without round-tripping.
 *
 * Coverage map (Build Pack §R6, Gate 2 lockdown):
 *   1.  list renders rows scoped to supplier (client-side filter,
 *       §R4.1) — rows for OTHER suppliers are NOT shown.
 *   2.  status filter forwards into the hook params.
 *   3.  selecting a row mounts the detail panel.
 *   4.  empty state copy when no rows match.
 *   5.  loading state.
 *   6.  forbidden state when subcontracts.view missing.
 *   7.  sensitive-sum gating: non-sensitive user sees em-dash in the
 *       sum column (list + detail).
 *   8.  + New button hidden without subcontracts.create.
 *   9.  Edit button hidden without subcontracts.edit.
 *   10. Draft → buttons = [Activate, Terminate] (FLAG 1b: Activate
 *       requires .approve; Terminate requires .approve).
 *   11. Active → buttons = [Complete, Terminate]; Complete is shown
 *       to a user with `subcontracts.edit` only (FLAG 1b).
 *   12. Completed → no buttons, terminal line shown.
 *   13. Terminated → no buttons, terminal line shown.
 *   14. Activate confirm → on success: toast.success, hook called.
 *   15. Activate confirm → unsigned 409: friendly FLAG-2a message in
 *       toast.error ("A signed date is required…").
 *   16. Terminate confirm → 409 propagates server detail to toast.error.
 *   17. signature block is rendered in Edit mode ONLY (FLAG 2a).
 *   18. PATCH body on Edit is trimmed to UPDATE_ALLOWED — `project_id`,
 *       `subcontractor_id`, `status` would NEVER appear in the body
 *       (extra:"forbid" guard).
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../../../test/renderWithProviders';
import SubcontractsTab from '../SubcontractsTab';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/subcontracts', () => ({
  scKeys: { all: ['subcontracts'], list: () => [], detail: () => [] },
  useSubcontracts: jest.fn(),
  useSubcontract: jest.fn(),
  useCreateSubcontract: jest.fn(),
  useUpdateSubcontract: jest.fn(),
  useActivateSubcontract: jest.fn(),
  useCompleteSubcontract: jest.fn(),
  useTerminateSubcontract: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
// ProjectPicker hits the network in real life — stub it to a simple
// controlled input so the create-form test can drive the value.
jest.mock('@/components/ai-capture/ProjectPicker', () => ({
  ProjectPicker: ({ value, onChange }) => (
    <input
      data-testid="mock-project-picker"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

const { useAuth } = require('../../../context/AuthContext');
const subcontractsHooks = require('../../../hooks/subcontracts');
const { toast } = require('sonner');


// ─── Personas (mirror seeded RBAC) ───────────────────────────────────
const ME_FULL = {
  id: 'user-pm',
  permissions: [
    'subcontracts.view', 'subcontracts.view_sensitive',
    'subcontracts.create', 'subcontracts.edit',
    'subcontracts.approve',
  ],
};
const ME_EDITOR_ONLY = {  // FLAG 1b: should still SEE Complete button.
  id: 'user-edit',
  permissions: [
    'subcontracts.view', 'subcontracts.view_sensitive',
    'subcontracts.create', 'subcontracts.edit',
    // No subcontracts.approve.
  ],
};
const ME_NON_SENSITIVE = {
  id: 'user-ns',
  permissions: ['subcontracts.view'],
};
const ME_NONE = { id: 'user-none', permissions: [] };

const SUP_ID    = 'sup-1';
const OTHER_SUP = 'sup-other';
const PROJ_ID   = 'proj-1';

function makeSubcontract(over = {}) {
  return {
    id: 's-1',
    reference: 'SC-0001',
    project_id: PROJ_ID,
    subcontractor_id: SUP_ID,
    title: 'Groundworks package',
    scope_description: 'Strip + foundations',
    status: 'Draft',
    original_contract_sum: '125000.00',
    current_contract_sum: '125000.00',
    retention_pct: '5',
    cis_applies: true,
    start_on: '2026-05-01',
    end_on: '2026-09-30',
    signed_at: null,
    signed_by: null,
    purchase_order_id: null,
    ...over,
  };
}

// Standard mutation-hook stub.
function stubMutation({ mutateAsync = jest.fn().mockResolvedValue({}), isPending = false } = {}) {
  return { mutateAsync, isPending };
}

function setListData(items, { isLoading = false, isError = false } = {}) {
  subcontractsHooks.useSubcontracts.mockReturnValue({
    data: { items, total: items.length }, isLoading, isError,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  // Default detail = pass-through (the list row is the source of truth).
  subcontractsHooks.useSubcontract.mockReturnValue({ data: null });
  // Default mutation stubs — overridden in specific tests.
  subcontractsHooks.useCreateSubcontract.mockReturnValue(stubMutation());
  subcontractsHooks.useUpdateSubcontract.mockReturnValue(stubMutation());
  subcontractsHooks.useActivateSubcontract.mockReturnValue(stubMutation());
  subcontractsHooks.useCompleteSubcontract.mockReturnValue(stubMutation());
  subcontractsHooks.useTerminateSubcontract.mockReturnValue(stubMutation());
});


// ════════════════════════════════════════════════════════════════════
// LIST + filtering + selection
// ════════════════════════════════════════════════════════════════════

describe('list rendering, scope fence, filtering, selection (§R4.1)', () => {
  test('rows are filtered client-side to this supplier — rows for OTHER suppliers do not appear', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const sMine  = makeSubcontract({ id: 's-mine',  subcontractor_id: SUP_ID });
    const sOther = makeSubcontract({ id: 's-other', subcontractor_id: OTHER_SUP, title: 'Not mine' });
    setListData([sMine, sOther]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} defaultProjectId={PROJ_ID} />);

    expect(screen.getByTestId('subcontracts-row-s-mine')).toBeInTheDocument();
    expect(screen.queryByTestId('subcontracts-row-s-other')).toBeNull();
    expect(screen.queryByText('Not mine')).toBeNull();
  });

  test('status filter passes a `status` param into useSubcontracts (server-side filter, §R3.2)', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} defaultProjectId={PROJ_ID} />);

    // First render: no status filter.
    expect(subcontractsHooks.useSubcontracts).toHaveBeenLastCalledWith({
      params: undefined, enabled: true,
    });

    fireEvent.change(screen.getByTestId('subcontracts-tab-status-filter'), {
      target: { value: 'Active' },
    });

    expect(subcontractsHooks.useSubcontracts).toHaveBeenLastCalledWith({
      params: { status: 'Active' }, enabled: true,
    });
  });

  test('clicking a row mounts the detail panel for that subcontract', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const s = makeSubcontract({ id: 's-sel', status: 'Active', title: 'Selected one' });
    setListData([s]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} defaultProjectId={PROJ_ID} />);

    // Empty detail panel before selection.
    expect(screen.getByTestId('subcontract-detail-empty')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('subcontracts-row-s-sel'));

    const detail = screen.getByTestId('subcontract-detail-s-sel');
    expect(detail).toBeInTheDocument();
    // Title is present both in the list row and the detail panel; scope
    // the assertion to the detail node so the test isn't ambiguous.
    expect(detail.querySelector('h3').textContent).toBe('Selected one');
  });

  test('empty row state when no subcontracts match', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} defaultProjectId={PROJ_ID} />);

    expect(screen.getByTestId('subcontracts-tab-empty')).toBeInTheDocument();
  });

  test('loading state', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    subcontractsHooks.useSubcontracts.mockReturnValue({
      data: undefined, isLoading: true, isError: false,
    });

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    expect(screen.getByTestId('subcontracts-tab-loading')).toBeInTheDocument();
  });

  test('forbidden state when subcontracts.view perm missing', () => {
    useAuth.mockReturnValue({ me: ME_NONE });
    setListData([]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    expect(screen.getByTestId('subcontracts-tab-forbidden')).toBeInTheDocument();
    expect(screen.queryByTestId('subcontracts-tab')).toBeNull();
  });
});


// ════════════════════════════════════════════════════════════════════
// Sensitive-sum gating (§R4.2 / Build Pack §5.5)
// ════════════════════════════════════════════════════════════════════

describe('sensitive contract-sum gating', () => {
  test('non-sensitive user sees em-dash in the sum column (list)', () => {
    useAuth.mockReturnValue({ me: ME_NON_SENSITIVE });
    // Even if backend leaks the value, defence-in-depth hides it.
    setListData([makeSubcontract({ id: 's-1', original_contract_sum: '125000.00' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    const cell = screen.getByTestId('subcontracts-row-s-1-sum');
    expect(cell.textContent).toBe('\u2014');
    expect(cell.textContent).not.toMatch(/125,?000/);
  });

  test('sensitive user sees the formatted GBP value in the sum column', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([makeSubcontract({ id: 's-1', original_contract_sum: '125000.00' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    expect(screen.getByTestId('subcontracts-row-s-1-sum').textContent).toMatch(/£\s?125,000(\.00)?/);
  });

  test('non-sensitive user sees em-dash in BOTH original AND current sum on detail panel', () => {
    useAuth.mockReturnValue({ me: ME_NON_SENSITIVE });
    setListData([makeSubcontract({ id: 's-1' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    expect(screen.getByTestId('subcontract-detail-original-sum').textContent).toBe('\u2014');
    expect(screen.getByTestId('subcontract-detail-current-sum').textContent).toBe('\u2014');
  });
});


// ════════════════════════════════════════════════════════════════════
// Capability-gated buttons (§R4.3, FLAG 1b)
// ════════════════════════════════════════════════════════════════════

describe('button visibility — perms × status', () => {
  test('New subcontract hidden when subcontracts.create missing', () => {
    useAuth.mockReturnValue({ me: ME_NON_SENSITIVE });  // .view only
    setListData([]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    expect(screen.queryByTestId('subcontracts-tab-new-btn')).toBeNull();
  });

  test('Edit (detail) hidden when subcontracts.edit missing', () => {
    useAuth.mockReturnValue({
      me: { id: 'u', permissions: ['subcontracts.view', 'subcontracts.view_sensitive', 'subcontracts.approve'] },
    });
    setListData([makeSubcontract({ id: 's-1', status: 'Draft' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    expect(screen.queryByTestId('subcontract-detail-edit-btn')).toBeNull();
  });

  test('Draft status → renders Activate + Terminate, no Complete', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([makeSubcontract({ id: 's-1', status: 'Draft' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    expect(screen.getByTestId('subcontract-actions-activate-btn')).toBeInTheDocument();
    expect(screen.getByTestId('subcontract-actions-terminate-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('subcontract-actions-complete-btn')).toBeNull();
  });

  test('Active status → renders Complete + Terminate, no Activate', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([makeSubcontract({ id: 's-1', status: 'Active' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    expect(screen.getByTestId('subcontract-actions-complete-btn')).toBeInTheDocument();
    expect(screen.getByTestId('subcontract-actions-terminate-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('subcontract-actions-activate-btn')).toBeNull();
  });

  test('FLAG 1b — user with subcontracts.edit but NOT .approve still sees Complete on Active', () => {
    useAuth.mockReturnValue({ me: ME_EDITOR_ONLY });
    setListData([makeSubcontract({ id: 's-1', status: 'Active' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    // Complete is gated `.edit OR .approve` — must be visible.
    expect(screen.getByTestId('subcontract-actions-complete-btn')).toBeInTheDocument();
    // But Terminate is gated `.approve` only — must be hidden.
    expect(screen.queryByTestId('subcontract-actions-terminate-btn')).toBeNull();
  });

  test('Completed status → terminal line, no action buttons', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([makeSubcontract({ id: 's-1', status: 'Completed' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    expect(screen.getByTestId('subcontract-actions-terminal-line')).toBeInTheDocument();
    expect(screen.queryByTestId('subcontract-actions-activate-btn')).toBeNull();
    expect(screen.queryByTestId('subcontract-actions-complete-btn')).toBeNull();
    expect(screen.queryByTestId('subcontract-actions-terminate-btn')).toBeNull();
  });

  test('Terminated status → terminal line, no action buttons', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([makeSubcontract({ id: 's-1', status: 'Terminated' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    expect(screen.getByTestId('subcontract-actions-terminal-line')).toBeInTheDocument();
  });
});


// ════════════════════════════════════════════════════════════════════
// Lifecycle action flows (§R4.5 + FLAG 2a)
// ════════════════════════════════════════════════════════════════════

describe('lifecycle actions — confirm dialog → 200 path', () => {
  test('Activate happy path: opens dialog, confirm calls hook, success toast', async () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const mutateAsync = jest.fn().mockResolvedValue({ id: 's-1', status: 'Active' });
    subcontractsHooks.useActivateSubcontract.mockReturnValue(stubMutation({ mutateAsync }));
    setListData([makeSubcontract({ id: 's-1', status: 'Draft' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    fireEvent.click(screen.getByTestId('subcontract-actions-activate-btn'));
    expect(screen.getByTestId('subcontract-activate-dialog')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('subcontract-activate-confirm'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith('Subcontract activated');
  });

  test('FLAG 2a — Activate against unsigned subcontract: 409 is mapped to friendly "signed date required" message', async () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const mutateAsync = jest.fn().mockRejectedValue({
      response: {
        status: 409,
        data: { detail: 'Cannot activate an unsigned subcontract (set signed_at first)' },
      },
    });
    subcontractsHooks.useActivateSubcontract.mockReturnValue(stubMutation({ mutateAsync }));
    setListData([makeSubcontract({ id: 's-1', status: 'Draft' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    fireEvent.click(screen.getByTestId('subcontract-actions-activate-btn'));
    fireEvent.click(screen.getByTestId('subcontract-activate-confirm'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    const msg = toast.error.mock.calls[0][0];
    expect(msg).toMatch(/signed date is required/i);
    expect(msg).toMatch(/edit the subcontract/i);
    expect(toast.success).not.toHaveBeenCalled();
  });

  test('Terminate 409 surfaces the server detail verbatim (Build Pack §R4.5 — 409 distinct from 422)', async () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const mutateAsync = jest.fn().mockRejectedValue({
      response: { status: 409, data: { detail: 'Subcontract is already terminal' } },
    });
    subcontractsHooks.useTerminateSubcontract.mockReturnValue(stubMutation({ mutateAsync }));
    setListData([makeSubcontract({ id: 's-1', status: 'Draft' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    fireEvent.click(screen.getByTestId('subcontract-actions-terminate-btn'));
    fireEvent.click(screen.getByTestId('subcontract-terminate-confirm'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(toast.error.mock.calls[0][0]).toBe('Subcontract is already terminal');
  });

  test('Complete happy path under FLAG 1b editor-only persona', async () => {
    useAuth.mockReturnValue({ me: ME_EDITOR_ONLY });
    const mutateAsync = jest.fn().mockResolvedValue({ id: 's-1', status: 'Completed' });
    subcontractsHooks.useCompleteSubcontract.mockReturnValue(stubMutation({ mutateAsync }));
    setListData([makeSubcontract({ id: 's-1', status: 'Active' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    fireEvent.click(screen.getByTestId('subcontract-actions-complete-btn'));
    fireEvent.click(screen.getByTestId('subcontract-complete-confirm'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith('Subcontract completed');
  });
});


// ════════════════════════════════════════════════════════════════════
// Edit form — FLAG 2a signature block + PATCH body trim
// ════════════════════════════════════════════════════════════════════

describe('edit form — signature block + PATCH body trim (§R4.4, FLAG 2a)', () => {
  test('FLAG 2a — signature block (signed_at, signed_by) renders ONLY in Edit mode', () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    setListData([makeSubcontract({ id: 's-1' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    // CREATE — open via the + New button.
    fireEvent.click(screen.getByTestId('subcontracts-tab-new-btn'));
    expect(screen.getByTestId('subcontract-form-dialog')).toBeInTheDocument();
    expect(screen.queryByTestId('subcontract-form-signature-block')).toBeNull();
    expect(screen.queryByTestId('subcontract-form-signed-at')).toBeNull();
    // Close the create dialog.
    fireEvent.click(screen.getByTestId('subcontract-form-cancel'));

    // EDIT — open via the detail panel's Edit button.
    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    fireEvent.click(screen.getByTestId('subcontract-detail-edit-btn'));
    expect(screen.getByTestId('subcontract-form-signature-block')).toBeInTheDocument();
    expect(screen.getByTestId('subcontract-form-signed-at')).toBeInTheDocument();
  });

  test('PATCH body NEVER includes forbidden fields (project_id / subcontractor_id / status) — extra:"forbid" guard', async () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const mutateAsync = jest.fn().mockResolvedValue({});
    subcontractsHooks.useUpdateSubcontract.mockReturnValue(stubMutation({ mutateAsync }));
    setListData([makeSubcontract({ id: 's-1' })]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-row-s-1'));
    fireEvent.click(screen.getByTestId('subcontract-detail-edit-btn'));

    // Edit the title.
    const titleInput = screen.getByTestId('subcontract-form-title');
    fireEvent.change(titleInput, { target: { value: 'Groundworks (revised)' } });

    fireEvent.click(screen.getByTestId('subcontract-form-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const sent = mutateAsync.mock.calls[0][0];
    // Only the changed allowed field should be in the body.
    expect(sent).toEqual({ title: 'Groundworks (revised)' });
    // Hard guards against accidental injection of forbidden keys.
    expect(Object.prototype.hasOwnProperty.call(sent, 'project_id')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(sent, 'subcontractor_id')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(sent, 'status')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(sent, 'reference')).toBe(false);
  });

  test('Create body has NO `reference` and NO `status`; subcontractor_id is set from the supplier prop (§R4.4 / §R0.3)', async () => {
    useAuth.mockReturnValue({ me: ME_FULL });
    const mutateAsync = jest.fn().mockResolvedValue({});
    subcontractsHooks.useCreateSubcontract.mockReturnValue(stubMutation({ mutateAsync }));
    setListData([]);

    renderWithProviders(<SubcontractsTab supplierId={SUP_ID} defaultProjectId={PROJ_ID} />);

    fireEvent.click(screen.getByTestId('subcontracts-tab-new-btn'));
    fireEvent.change(screen.getByTestId('mock-project-picker'), { target: { value: PROJ_ID } });
    fireEvent.change(screen.getByTestId('subcontract-form-title'), { target: { value: 'New scope' } });

    fireEvent.click(screen.getByTestId('subcontract-form-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const sent = mutateAsync.mock.calls[0][0];
    expect(sent.project_id).toBe(PROJ_ID);
    expect(sent.subcontractor_id).toBe(SUP_ID);
    expect(sent.title).toBe('New scope');
    expect(Object.prototype.hasOwnProperty.call(sent, 'reference')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(sent, 'status')).toBe(false);
  });
});
