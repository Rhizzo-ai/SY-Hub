/**
 * PackageDetail component tests — B88 Pack 3 §7 (Chat 53).
 *
 * Covers the live-eyeball acceptance criteria:
 *   - Detail header + status pill + totals + tabs render.
 *   - Lines tab editable in draft only; locked once status moves on.
 *   - Bid entry preview computes net = qty × rate client-side.
 *   - Award form Σ summary recomputes on every keystroke.
 *   - Over-total visual block: red banner + disabled submit when
 *     `Total after > total_net + £0.01`.
 *   - Submit handlers NEVER send `net_amount` — server-truth invariant.
 *   - If a caller bypasses the disabled state, server 422 surfaces
 *     verbatim (no silent onError).
 *   - Sensitive redaction: a `packages.view`-only caller sees no
 *     numbers in totals.
 *   - Permission gates: edit/delete/award affordances appear only for
 *     the right perms.
 */
import React from 'react';
import {
  render, screen, fireEvent, waitFor, within, act,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

jest.mock('@/lib/api/packages', () => ({
  getPackage: jest.fn(),
  addPackageLine: jest.fn(), removePackageLine: jest.fn(),
  updatePackageLine: jest.fn(),
  sendToTender: jest.fn(), cancelPackage: jest.fn(),
  deletePackage: jest.fn(),
  inviteBidder: jest.fn(), enterBid: jest.fn(),
  declineBid: jest.fn(), withdrawBid: jest.fn(),
  awardPackage: jest.fn(), cancelAward: jest.fn(),
  listBids: jest.fn(),
}));
jest.mock('@/lib/api/budgets', () => ({
  getBudgetGrid: jest.fn(() => Promise.resolve({ groups: [] })),
  listProjectBudgets: jest.fn(() => Promise.resolve({ items: [] })),
}));
jest.mock('@/lib/api/suppliers', () => ({
  listSuppliers: jest.fn(() => Promise.resolve({ items: [] })),
}));
jest.mock('@/lib/api', () => ({
  api: { get: jest.fn(() => Promise.resolve({ data: { name: 'Acme' } })) },
}));
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(), error: jest.fn(), info: jest.fn(),
  },
}));

import PackageDetail from '@/pages/admin/PackageDetail';
import {
  getPackage, addPackageLine, sendToTender, awardPackage, enterBid,
} from '@/lib/api/packages';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

jest.mock('react-router-dom', () => {
  const real = jest.requireActual('react-router-dom');
  return {
    ...real,
    useNavigate: () => jest.fn(),
    useParams: () => ({ id: 'pkg-1' }),
  };
});

function setAuth({ perms = [], superAdmin = false } = {}) {
  useAuth.mockReturnValue({
    me: { is_super_admin: superAdmin, email: 'pm@test' },
    hasPerm: (code) => perms.includes(code),
  });
}

function makePkg(overrides = {}) {
  return {
    id: 'pkg-1', tenant_id: 't1', project_id: 'p1', budget_id: 'b1',
    reference: 'PKG-0001', title: 'UI Demo',
    kind: 'materials', status: 'out_to_tender',
    description: null,
    total_net: '200000.00', awarded_net: '0.00',
    out_to_tender_at: '2026-02-01T00:00:00Z',
    out_to_tender_by: null,
    awarded_at: null, awarded_by: null,
    cancelled_at: null, cancelled_by: null, cancelled_reason: null,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    lines: [
      {
        id: 'pl-1', package_id: 'pkg-1', budget_line_id: 'bl-1',
        cost_code: 'ROOF-01', line_number: 1,
        description: 'Roof tiles',
        quantity: '100.0000', unit: 'm2',
        budgeted_unit_rate: '1000.0000',
        budgeted_net_amount: '100000.00', notes: null,
      },
      {
        id: 'pl-2', package_id: 'pkg-1', budget_line_id: 'bl-2',
        cost_code: 'ROOF-02', line_number: 2,
        description: 'Roof labour',
        quantity: '100.0000', unit: 'm2',
        budgeted_unit_rate: '1000.0000',
        budgeted_net_amount: '100000.00', notes: null,
      },
    ],
    bids: [
      {
        id: 'bid-1', package_id: 'pkg-1', supplier_id: 'sup-1',
        status: 'received', total_net: '190000.00',
        received_at: '2026-02-02T00:00:00Z', notes: null,
        lines: [
          {
            id: 'bl1', package_line_id: 'pl-1',
            quoted_unit_rate: '950.0000', quoted_net_amount: '95000.00',
          },
          {
            id: 'bl2', package_line_id: 'pl-2',
            quoted_unit_rate: '950.0000', quoted_net_amount: '95000.00',
          },
        ],
      },
    ],
    awards: [],
    ...overrides,
  };
}

function renderDetail() {
  return render(
    <MemoryRouter>
      <PackageDetail />
    </MemoryRouter>,
  );
}

import { api } from '@/lib/api';
import { listSuppliers } from '@/lib/api/suppliers';
import { getBudgetGrid, listProjectBudgets } from '@/lib/api/budgets';

beforeEach(() => {
  jest.clearAllMocks();
  // Re-prime mocks that BidRow / dialogs call on mount; clearAllMocks
  // wipes their implementations.
  api.get.mockResolvedValue({ data: { name: 'Acme' } });
  listSuppliers.mockResolvedValue({ items: [] });
  getBudgetGrid.mockResolvedValue({ groups: [] });
  listProjectBudgets.mockResolvedValue({ items: [] });
});

test('renders header, status pill, totals and tabs', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.edit'],
  });
  getPackage.mockResolvedValue(makePkg());
  renderDetail();
  await screen.findByTestId('package-detail-title');
  expect(screen.getByTestId('package-detail-title')).toHaveTextContent(
    'PKG-0001 — UI Demo',
  );
  expect(screen.getByTestId('package-detail-status')).toHaveTextContent(
    'Out to tender',
  );
  expect(
    screen.getByTestId('package-detail-total-net'),
  ).toHaveTextContent('£200,000.00');
  expect(screen.getByTestId('package-tab-lines')).toBeInTheDocument();
  expect(screen.getByTestId('package-tab-bids')).toBeInTheDocument();
});

test('forbids users without packages.view', async () => {
  setAuth({ perms: [] });
  renderDetail();
  expect(
    await screen.findByTestId('package-detail-forbidden'),
  ).toBeInTheDocument();
  expect(getPackage).not.toHaveBeenCalled();
});

test('load error surfaces visibly — no silent onError', async () => {
  setAuth({ perms: ['packages.view'] });
  getPackage.mockRejectedValue({
    response: { data: { detail: 'forbidden cross-tenant' } },
  });
  renderDetail();
  const err = await screen.findByTestId('package-detail-load-error');
  expect(err).toHaveTextContent('forbidden cross-tenant');
});

test('Lines tab read-only for non-draft status (no Add line button)', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.edit'],
  });
  getPackage.mockResolvedValue(makePkg({ status: 'out_to_tender' }));
  renderDetail();
  // Non-draft starts on 'bids' tab — click Lines to switch.
  fireEvent.click(await screen.findByTestId('package-tab-lines'));
  await screen.findByTestId('package-lines-tab');
  expect(screen.queryByTestId('package-add-line')).toBeNull();
});

test('Lines tab editable in draft for edit-perm callers', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.edit'],
  });
  getPackage.mockResolvedValue(makePkg({
    status: 'draft', bids: [], awards: [],
  }));
  renderDetail();
  expect(
    await screen.findByTestId('package-add-line'),
  ).toBeInTheDocument();
});

test('Send-to-tender button visible only when draft and >=1 line', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.edit'],
  });
  getPackage.mockResolvedValue(makePkg({
    status: 'draft', bids: [], awards: [],
  }));
  renderDetail();
  const btn = await screen.findByTestId('package-send-to-tender');
  expect(btn).toBeEnabled();
});

test('Delete button gated by packages.delete', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.edit'],
  });
  getPackage.mockResolvedValue(makePkg({
    status: 'draft', bids: [], awards: [],
  }));
  renderDetail();
  await screen.findByTestId('package-tab-lines');
  expect(screen.queryByTestId('package-delete')).toBeNull();
});

test('sensitive redaction: view-only caller sees em-dash for totals', async () => {
  setAuth({ perms: ['packages.view'] });
  const redacted = makePkg();
  redacted.total_net = null;
  redacted.awarded_net = null;
  redacted.lines = redacted.lines.map((ln) => ({
    ...ln,
    budgeted_unit_rate: null,
    budgeted_net_amount: null,
  }));
  redacted.bids = redacted.bids.map((b) => ({
    ...b,
    total_net: null,
    lines: b.lines.map((bl) => ({
      ...bl,
      quoted_unit_rate: null,
      quoted_net_amount: null,
    })),
  }));
  getPackage.mockResolvedValue(redacted);
  renderDetail();
  await screen.findByTestId('package-detail-title');
  expect(
    screen.getByTestId('package-detail-total-net'),
  ).toHaveTextContent('\u2014');
  expect(
    screen.getByTestId('package-detail-awarded-net'),
  ).toHaveTextContent('\u2014');
});

test('bid entry preview computes net = qty × rate client-side', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.edit'],
  });
  // Reset bid to "invited" so the Enter bid button is shown.
  const pkg = makePkg();
  pkg.bids = [
    {
      ...pkg.bids[0], status: 'invited', total_net: '0.00', lines: [],
    },
  ];
  getPackage.mockResolvedValue(pkg);
  renderDetail();
  fireEvent.click(await screen.findByTestId('package-tab-bids'));
  await screen.findByTestId('package-bids-tab');
  fireEvent.click(screen.getByTestId('bid-enter-bid-1'));
  await screen.findByTestId('enter-bid-dialog');
  // Set rates per line.
  fireEvent.change(screen.getByTestId('enter-bid-rate-1'), {
    target: { value: '950' },
  });
  fireEvent.change(screen.getByTestId('enter-bid-rate-2'), {
    target: { value: '1100' },
  });
  // 100 × 950 + 100 × 1100 = 95000 + 110000 = 205000.
  expect(
    screen.getByTestId('enter-bid-total-preview'),
  ).toHaveTextContent('£205,000.00');
});

test('award form Σ summary recomputes on rate input', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.award'],
  });
  getPackage.mockResolvedValue(makePkg());
  renderDetail();
  fireEvent.click(await screen.findByTestId('package-tab-award'));
  await screen.findByTestId('package-award-tab');
  fireEvent.click(screen.getByTestId('package-award-open'));
  await screen.findByTestId('award-form-dialog');
  // 60 × 800 = 48000 → Total after = 48000.
  fireEvent.change(screen.getByTestId('award-spec-0-qty-0'), {
    target: { value: '60' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-rate-0'), {
    target: { value: '800' },
  });
  expect(
    screen.getByTestId('award-form-total-after'),
  ).toHaveTextContent('£48,000.00');
  // Adjust: 100 × 800 = 80000.
  fireEvent.change(screen.getByTestId('award-spec-0-qty-0'), {
    target: { value: '100' },
  });
  expect(
    screen.getByTestId('award-form-total-after'),
  ).toHaveTextContent('£80,000.00');
});

test('award form OVER-TOTAL: red block visible AND submit disabled', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.award'],
  });
  getPackage.mockResolvedValue(makePkg());
  renderDetail();
  fireEvent.click(await screen.findByTestId('package-tab-award'));
  fireEvent.click(await screen.findByTestId('package-award-open'));
  await screen.findByTestId('award-form-dialog');
  // 1 × 999999 = 999_999 — well above the £200,000 total_net.
  fireEvent.change(screen.getByTestId('award-spec-0-qty-0'), {
    target: { value: '1' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-rate-0'), {
    target: { value: '999999' },
  });
  expect(
    screen.getByTestId('award-form-over-total-block'),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId('award-form-over-total-block'),
  ).toHaveTextContent('Total exceeds package');
  expect(
    screen.getByTestId('award-form-submit'),
  ).toBeDisabled();
});

test('award form submit NEVER sends net_amount (server-truth invariant)', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.award'],
  });
  getPackage.mockResolvedValue(makePkg());
  awardPackage.mockResolvedValue(makePkg({ status: 'partially_awarded' }));
  renderDetail();
  fireEvent.click(await screen.findByTestId('package-tab-award'));
  fireEvent.click(await screen.findByTestId('package-award-open'));
  await screen.findByTestId('award-form-dialog');
  // Set supplier from the dropdown (option index 1 = first non-empty).
  fireEvent.change(screen.getByTestId('award-spec-supplier-0'), {
    target: { value: 'sup-1' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-qty-0'), {
    target: { value: '50' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-rate-0'), {
    target: { value: '950' },
  });
  await waitFor(() => {
    expect(screen.getByTestId('award-form-submit')).toBeEnabled();
  });
  fireEvent.click(screen.getByTestId('award-form-submit'));
  await waitFor(() => {
    expect(awardPackage).toHaveBeenCalled();
  });
  const [pkgArg, body] = awardPackage.mock.calls[0];
  expect(pkgArg).toBe('pkg-1');
  expect(Array.isArray(body.awards)).toBe(true);
  // Recursively walk the body and ASSERT NO `net_amount`/`awarded_net`
  // key is present client-side — server computes these.
  function walk(node, path = '') {
    if (node && typeof node === 'object' && !Array.isArray(node)) {
      for (const k of Object.keys(node)) {
        if (k === 'net_amount' || k === 'awarded_net') {
          throw new Error(
            `client sent forbidden net key ${k} at ${path}`,
          );
        }
        walk(node[k], `${path}/${k}`);
      }
    } else if (Array.isArray(node)) {
      node.forEach((x, i) => walk(x, `${path}[${i}]`));
    }
  }
  walk(body);
});

test('award form submit surfaces server 422 verbatim (no silent onError)', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.award'],
  });
  getPackage.mockResolvedValue(makePkg());
  awardPackage.mockRejectedValue({
    response: {
      status: 422,
      data: { detail: 'Award would exceed package total: ...' },
    },
  });
  renderDetail();
  fireEvent.click(await screen.findByTestId('package-tab-award'));
  fireEvent.click(await screen.findByTestId('package-award-open'));
  await screen.findByTestId('award-form-dialog');
  fireEvent.change(screen.getByTestId('award-spec-supplier-0'), {
    target: { value: 'sup-1' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-qty-0'), {
    target: { value: '50' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-rate-0'), {
    target: { value: '950' },
  });
  await waitFor(() => {
    expect(screen.getByTestId('award-form-submit')).toBeEnabled();
  });
  fireEvent.click(screen.getByTestId('award-form-submit'));
  // 1) Inline error block visible with the server's verbatim text.
  const err = await screen.findByTestId('award-form-error');
  expect(err).toHaveTextContent('exceed package total');
  // 2) Toast also fired — no silent onError.
  expect(toast.error).toHaveBeenCalledWith(
    expect.stringContaining('Award failed'),
  );
});

test('add-line button hidden for callers without packages.edit', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive'],
  });
  getPackage.mockResolvedValue(makePkg({
    status: 'draft', bids: [], awards: [],
  }));
  renderDetail();
  await screen.findByTestId('package-tab-lines');
  expect(screen.queryByTestId('package-add-line')).toBeNull();
});

test('award form requires a supplier — submit stays disabled', async () => {
  setAuth({
    perms: ['packages.view', 'packages.view_sensitive', 'packages.award'],
  });
  getPackage.mockResolvedValue(makePkg());
  renderDetail();
  fireEvent.click(await screen.findByTestId('package-tab-award'));
  fireEvent.click(await screen.findByTestId('package-award-open'));
  await screen.findByTestId('award-form-dialog');
  // Fill qty + rate but leave supplier empty.
  fireEvent.change(screen.getByTestId('award-spec-0-qty-0'), {
    target: { value: '50' },
  });
  fireEvent.change(screen.getByTestId('award-spec-0-rate-0'), {
    target: { value: '950' },
  });
  expect(
    screen.getByTestId('award-form-submit'),
  ).toBeDisabled();
});
