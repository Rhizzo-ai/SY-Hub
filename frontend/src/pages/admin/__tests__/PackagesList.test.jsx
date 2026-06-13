/**
 * PackagesList component tests — B88 Pack 3 §7 (Chat 53).
 *
 * Covers (per operator gate):
 *   - List renders empty + populated states.
 *   - Sensitive redaction: a `packages.view`-only caller sees no
 *     pricing (em-dash placeholders), while `packages.view_sensitive`
 *     reveals real pounds.
 *   - Forbidden state when `packages.view` is missing.
 *   - Filter changes refetch with the right query params.
 *   - Load error surfaces VISIBLY (no silent onError).
 *   - "New package" button gated by `packages.create`.
 *   - Row click navigates to detail.
 */
import React from 'react';
import {
  render, screen, fireEvent, waitFor, within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

jest.mock('@/lib/api/packages', () => ({
  listPackagesGlobal: jest.fn(),
  createPackage: jest.fn(),
  // Re-exported for child dialog.
  inviteBidder: jest.fn(), enterBid: jest.fn(),
  declineBid: jest.fn(), withdrawBid: jest.fn(),
  awardPackage: jest.fn(), cancelAward: jest.fn(),
  getPackage: jest.fn(), addPackageLine: jest.fn(),
  removePackageLine: jest.fn(), updatePackageLine: jest.fn(),
  sendToTender: jest.fn(), cancelPackage: jest.fn(),
  deletePackage: jest.fn(), updatePackage: jest.fn(),
  listBids: jest.fn(), listPackagesForProject: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(), error: jest.fn(), info: jest.fn(),
  },
}));
// The list page reads `NewPackageDialog` lazily on click; mock its
// underlying API requests so the dialog never tries to load projects.
jest.mock('@/lib/api', () => ({
  api: { get: jest.fn() },
}));
jest.mock('@/lib/api/budgets', () => ({
  listProjectBudgets: jest.fn(() => Promise.resolve({ items: [] })),
}));

import PackagesList from '@/pages/admin/PackagesList';
import { listPackagesGlobal, createPackage } from '@/lib/api/packages';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import { api } from '@/lib/api';

const mockNav = jest.fn();
jest.mock('react-router-dom', () => {
  const real = jest.requireActual('react-router-dom');
  return { ...real, useNavigate: () => mockNav };
});

const SAMPLE_PACKAGES = [
  {
    id: 'pkg-1', tenant_id: 't1', project_id: 'p1', budget_id: 'b1',
    reference: 'PKG-0001', title: 'Roofing — Block A',
    kind: 'materials', status: 'out_to_tender',
    description: 'demo',
    total_net: '200000.00', awarded_net: '0.00',
    out_to_tender_at: null, awarded_at: null, cancelled_at: null,
    created_at: '2026-02-01T00:00:00Z', updated_at: '2026-02-01T00:00:00Z',
    lines: [], bids: [], awards: [],
  },
  {
    id: 'pkg-2', tenant_id: 't1', project_id: 'p1', budget_id: 'b1',
    reference: 'PKG-0002', title: 'Roof labour — Block A',
    kind: 'labour', status: 'partially_awarded',
    description: null,
    total_net: '180000.00', awarded_net: '90000.00',
    out_to_tender_at: null, awarded_at: null, cancelled_at: null,
    created_at: '2026-02-02T00:00:00Z', updated_at: '2026-02-02T00:00:00Z',
    lines: [], bids: [], awards: [],
  },
];

const SAMPLE_REDACTED = SAMPLE_PACKAGES.map((p) => ({
  ...p,
  total_net: null,
  awarded_net: null,
}));

function setAuth({ perms = [], superAdmin = false } = {}) {
  useAuth.mockReturnValue({
    me: { is_super_admin: superAdmin, email: 'pm@test' },
    hasPerm: (code) => perms.includes(code),
  });
}

function renderList() {
  return render(
    <MemoryRouter>
      <PackagesList />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

test('forbids users without packages.view', async () => {
  setAuth({ perms: [] });
  renderList();
  expect(
    await screen.findByTestId('packages-list-forbidden'),
  ).toBeInTheDocument();
  expect(listPackagesGlobal).not.toHaveBeenCalled();
});

test('renders empty state when API returns no packages', async () => {
  setAuth({ perms: ['packages.view', 'packages.view_sensitive'] });
  listPackagesGlobal.mockResolvedValue({ items: [], total: 0 });
  renderList();
  expect(
    await screen.findByTestId('packages-list-empty'),
  ).toBeInTheDocument();
  expect(listPackagesGlobal).toHaveBeenCalledTimes(1);
});

test('renders populated list with pricing for view_sensitive callers', async () => {
  setAuth({ perms: ['packages.view', 'packages.view_sensitive'] });
  listPackagesGlobal.mockResolvedValue({
    items: SAMPLE_PACKAGES, total: 2,
  });
  renderList();
  await screen.findByTestId('packages-row-PKG-0001');
  const row1 = screen.getByTestId('packages-row-PKG-0001');
  expect(within(row1).getByText('PKG-0001')).toBeInTheDocument();
  expect(within(row1).getByText('Roofing — Block A')).toBeInTheDocument();
  expect(within(row1).getByText(/£200,000\.00/)).toBeInTheDocument();
  const row2 = screen.getByTestId('packages-row-PKG-0002');
  expect(within(row2).getByText(/£180,000\.00/)).toBeInTheDocument();
  expect(within(row2).getByText(/£90,000\.00/)).toBeInTheDocument();
});

test('redacts pricing to em-dash for callers without view_sensitive', async () => {
  setAuth({ perms: ['packages.view'] });
  listPackagesGlobal.mockResolvedValue({
    items: SAMPLE_REDACTED, total: 2,
  });
  renderList();
  const row = await screen.findByTestId('packages-row-PKG-0001');
  // No pound signs anywhere in the row.
  expect(within(row).queryByText(/£/)).toBeNull();
  // em-dash placeholder (\u2014) IS shown for sensitive cells.
  const emDashes = within(row).queryAllByText('\u2014');
  expect(emDashes.length).toBeGreaterThanOrEqual(2);
});

test('shows status pill with the correct label per row', async () => {
  setAuth({ perms: ['packages.view', 'packages.view_sensitive'] });
  listPackagesGlobal.mockResolvedValue({
    items: SAMPLE_PACKAGES, total: 2,
  });
  renderList();
  await screen.findByTestId('packages-row-PKG-0001');
  expect(
    screen.getByTestId('packages-row-status-PKG-0001'),
  ).toHaveTextContent('Out to tender');
  expect(
    screen.getByTestId('packages-row-status-PKG-0002'),
  ).toHaveTextContent('Partially awarded');
});

test('row click navigates to the package detail', async () => {
  setAuth({ perms: ['packages.view', 'packages.view_sensitive'] });
  listPackagesGlobal.mockResolvedValue({
    items: SAMPLE_PACKAGES, total: 2,
  });
  renderList();
  const row = await screen.findByTestId('packages-row-PKG-0001');
  fireEvent.click(row);
  expect(mockNav).toHaveBeenCalledWith('/admin/packages/pkg-1');
});

test('"New package" button hidden without packages.create', async () => {
  setAuth({ perms: ['packages.view'] });
  listPackagesGlobal.mockResolvedValue({ items: [], total: 0 });
  renderList();
  await screen.findByTestId('packages-list-empty');
  expect(screen.queryByTestId('packages-new-btn')).toBeNull();
});

test('"New package" button visible with packages.create', async () => {
  setAuth({ perms: ['packages.view', 'packages.create'] });
  listPackagesGlobal.mockResolvedValue({ items: [], total: 0 });
  renderList();
  expect(
    await screen.findByTestId('packages-new-btn'),
  ).toBeInTheDocument();
});

test('status filter change refetches with the new filter value', async () => {
  setAuth({ perms: ['packages.view'] });
  listPackagesGlobal.mockResolvedValue({ items: [], total: 0 });
  renderList();
  await screen.findByTestId('packages-list-empty');
  expect(listPackagesGlobal).toHaveBeenLastCalledWith(
    expect.objectContaining({ status: undefined }),
  );
  fireEvent.change(screen.getByTestId('packages-filter-status'), {
    target: { value: 'awarded' },
  });
  await waitFor(() => {
    expect(listPackagesGlobal).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'awarded' }),
    );
  });
});

test('kind filter change refetches with the new filter value', async () => {
  setAuth({ perms: ['packages.view'] });
  listPackagesGlobal.mockResolvedValue({ items: [], total: 0 });
  renderList();
  await screen.findByTestId('packages-list-empty');
  fireEvent.change(screen.getByTestId('packages-filter-kind'), {
    target: { value: 'labour' },
  });
  await waitFor(() => {
    expect(listPackagesGlobal).toHaveBeenLastCalledWith(
      expect.objectContaining({ kind: 'labour' }),
    );
  });
});

test('load error surfaces visibly — no silent onError', async () => {
  setAuth({ perms: ['packages.view'] });
  listPackagesGlobal.mockRejectedValue({
    response: { data: { detail: 'database offline' } },
  });
  renderList();
  const banner = await screen.findByTestId('packages-list-error');
  expect(banner).toHaveTextContent('database offline');
});

test('opens NewPackageDialog when "New package" clicked', async () => {
  setAuth({ perms: ['packages.view', 'packages.create'] });
  listPackagesGlobal.mockResolvedValue({ items: [], total: 0 });
  api.get.mockResolvedValue({ data: { items: [] } });
  renderList();
  fireEvent.click(await screen.findByTestId('packages-new-btn'));
  expect(
    await screen.findByTestId('new-package-dialog'),
  ).toBeInTheDocument();
});
