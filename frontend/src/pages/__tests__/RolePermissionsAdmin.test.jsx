/**
 * RolePermissionsAdmin component tests — B83 §R5 (frontend block).
 *
 * Covers: matrix renders groups + roles; super_admin column disabled;
 * draft diff + pending bar; review modal sensitive warnings +
 * zero-permission warning; save error surfaces visibly and preserves the
 * draft; create-role dialog validation; tooltips render descriptions.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

jest.mock('@/lib/api/roles', () => ({
  listRoles: jest.fn(),
  getRole: jest.fn(),
  listPermissions: jest.fn(),
  saveRolePermissionsBatch: jest.fn(),
  createRole: jest.fn(),
  patchRole: jest.fn(),
  deleteRole: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(), error: jest.fn(), info: jest.fn(),
  },
}));

import RolePermissionsAdmin from '@/pages/admin/RolePermissionsAdmin';
import {
  listRoles, getRole, listPermissions, saveRolePermissionsBatch, createRole,
} from '@/lib/api/roles';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

const PERMS = [
  { id: 'p1', code: 'budgets.view', resource: 'budgets', action: 'view',
    description: 'View budget lines within scope', is_sensitive: false },
  { id: 'p2', code: 'budgets.create', resource: 'budgets', action: 'create',
    description: 'Create budget lines', is_sensitive: false },
  { id: 'p3', code: 'budgets.view_sensitive', resource: 'budgets',
    action: 'view_sensitive', description: 'See full budget money',
    is_sensitive: true },
  { id: 'p4', code: 'projects.view', resource: 'projects', action: 'view',
    description: 'View projects', is_sensitive: false },
];

const ROLES = [
  { id: 'role-sa', code: 'super_admin', name: 'Super Administrator',
    description: 'Everything', is_system_role: true, priority: 10,
    permission_count: 4, user_count: 1 },
  { id: 'role-pm', code: 'project_manager', name: 'Project Manager',
    description: 'PM', is_system_role: true, priority: 30,
    permission_count: 2, user_count: 2 },
  { id: 'role-cu', code: 'b83_custom', name: 'B83 Custom',
    description: 'Custom role', is_system_role: false, priority: 40,
    permission_count: 1, user_count: 0 },
];

const DETAILS = {
  'role-sa': { ...ROLES[0], permissions: PERMS, user_count: 1 },
  'role-pm': {
    ...ROLES[1],
    permissions: [PERMS[0], PERMS[1]], // budgets.view + budgets.create
    user_count: 2,
  },
  'role-cu': { ...ROLES[2], permissions: [PERMS[3]], user_count: 0 },
};

function setAuth(perms, isSuper = false) {
  useAuth.mockReturnValue({
    me: { permissions: perms, is_super_admin: isSuper },
    hasPerm: (c) => perms.includes(c),
  });
}

function primeApi() {
  listPermissions.mockResolvedValue(PERMS);
  listRoles.mockResolvedValue(ROLES);
  getRole.mockImplementation((id) => Promise.resolve(DETAILS[id]));
}

async function renderPage() {
  render(
    <MemoryRouter>
      <RolePermissionsAdmin />
    </MemoryRouter>
  );
  await waitFor(() =>
    expect(screen.getByTestId('matrix-table')).toBeInTheDocument());
}

beforeEach(() => {
  jest.clearAllMocks();
  setAuth(['roles.view', 'roles.admin']);
  primeApi();
});

describe('matrix rendering', () => {
  test('renders resource groups and role columns', async () => {
    await renderPage();
    expect(screen.getByTestId('group-row-budgets')).toBeInTheDocument();
    expect(screen.getByTestId('group-row-projects')).toBeInTheDocument();
    expect(screen.getByTestId('role-col-super_admin')).toBeInTheDocument();
    expect(screen.getByTestId('role-col-project_manager')).toBeInTheDocument();
    expect(screen.getByTestId('role-col-b83_custom')).toBeInTheDocument();
    expect(screen.getByTestId('matrix-footnote')).toHaveTextContent(
      /Custom roles do not automatically receive permissions/);
  });

  test('collapsing a group hides its permission rows', async () => {
    await renderPage();
    expect(screen.getByTestId('perm-row-budgets.view')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('group-toggle-budgets'));
    expect(screen.queryByTestId('perm-row-budgets.view')).not.toBeInTheDocument();
    expect(screen.getByTestId('perm-row-projects.view')).toBeInTheDocument();
  });

  test('super_admin column is fully ticked, disabled and lock-labelled', async () => {
    await renderPage();
    expect(screen.getByTestId('super-admin-lock')).toHaveAttribute(
      'title', 'Super admin always has every permission');
    for (const p of PERMS) {
      const cell = screen.getByTestId(`cell-super_admin-${p.code}`);
      expect(cell).toBeChecked();
      expect(cell).toBeDisabled();
    }
  });

  test('tooltips render descriptions (title attr + tap-to-expand)', async () => {
    await renderPage();
    expect(screen.getByTestId('perm-label-budgets.view')).toHaveAttribute(
      'title', 'View budget lines within scope');
    // Sensitive row title carries the consequence line too (D8/D10).
    expect(
      screen.getByTestId('perm-label-budgets.view_sensitive').getAttribute('title'),
    ).toContain('Grants full-budget money visibility (Tier 1).');
    // Tap-to-expand inline description for touch devices.
    fireEvent.click(screen.getByTestId('perm-label-budgets.view'));
    expect(screen.getByTestId('perm-desc-budgets.view')).toHaveTextContent(
      'View budget lines within scope');
  });

  test('orange sensitive dot renders only on sensitive rows', async () => {
    await renderPage();
    expect(screen.getByTestId('sensitive-dot-budgets.view_sensitive')).toBeInTheDocument();
    expect(screen.queryByTestId('sensitive-dot-budgets.view')).not.toBeInTheDocument();
  });
});

describe('draft + pending bar', () => {
  test('toggling a cell shows the pending bar; discard resets', async () => {
    await renderPage();
    expect(screen.queryByTestId('pending-bar')).not.toBeInTheDocument();
    const cell = screen.getByTestId('cell-project_manager-budgets.create');
    expect(cell).toBeChecked();
    fireEvent.click(cell); // untick = pending remove
    expect(screen.getByTestId('pending-bar')).toBeInTheDocument();
    expect(screen.getByTestId('pending-count')).toHaveTextContent('1');
    fireEvent.click(screen.getByTestId('discard-draft-btn'));
    expect(screen.queryByTestId('pending-bar')).not.toBeInTheDocument();
    expect(screen.getByTestId('cell-project_manager-budgets.create')).toBeChecked();
  });
});

describe('review modal', () => {
  test('shows sensitive add warning with consequence line', async () => {
    await renderPage();
    fireEvent.click(screen.getByTestId('cell-project_manager-budgets.view_sensitive')); // tick = add
    fireEvent.click(screen.getByTestId('review-save-btn'));
    expect(screen.getByTestId('review-modal')).toBeInTheDocument();
    expect(screen.getByTestId(
      'review-add-project_manager-budgets.view_sensitive')).toBeInTheDocument();
    expect(screen.getByTestId('review-consequence-budgets.view_sensitive'))
      .toHaveTextContent('Grants full-budget money visibility (Tier 1).');
  });

  test('zero-permission role requires explicit checkbox confirm', async () => {
    await renderPage();
    // b83_custom holds only projects.view — remove it → ends at zero.
    fireEvent.click(screen.getByTestId('cell-b83_custom-projects.view'));
    fireEvent.click(screen.getByTestId('review-save-btn'));
    expect(screen.getByTestId('review-zero-warning-b83_custom')).toBeInTheDocument();
    const saveBtn = screen.getByTestId('review-confirm-save');
    expect(saveBtn).toBeDisabled();
    fireEvent.click(screen.getByTestId('review-zero-confirm'));
    expect(saveBtn).not.toBeDisabled();
  });

  test('successful save reconciles from the updated payload', async () => {
    saveRolePermissionsBatch.mockResolvedValue({
      updated: [{
        ...DETAILS['role-pm'],
        permissions: [PERMS[0]], // budgets.create removed server-side
      }],
    });
    await renderPage();
    fireEvent.click(screen.getByTestId('cell-project_manager-budgets.create'));
    fireEvent.click(screen.getByTestId('review-save-btn'));
    fireEvent.click(screen.getByTestId('review-confirm-save'));
    await waitFor(() => expect(saveRolePermissionsBatch).toHaveBeenCalledWith([
      { role_id: 'role-pm', add: [], remove: ['budgets.create'] },
    ]));
    await waitFor(() =>
      expect(screen.queryByTestId('pending-bar')).not.toBeInTheDocument());
    expect(screen.getByTestId('cell-project_manager-budgets.create')).not.toBeChecked();
    expect(toast.success).toHaveBeenCalled();
  });

  test('save error surfaces visibly (toast + inline) and preserves draft', async () => {
    saveRolePermissionsBatch.mockRejectedValue({
      response: { data: { detail: 'Unknown permission code(s): nope.bad' } },
    });
    await renderPage();
    fireEvent.click(screen.getByTestId('cell-project_manager-budgets.create'));
    fireEvent.click(screen.getByTestId('review-save-btn'));
    fireEvent.click(screen.getByTestId('review-confirm-save'));
    await waitFor(() =>
      expect(screen.getByTestId('review-save-error')).toBeInTheDocument());
    expect(screen.getByTestId('review-save-error')).toHaveTextContent(
      'Unknown permission code(s): nope.bad');
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining('Unknown permission code(s): nope.bad'));
    // Draft preserved: close the modal — pending bar still shows the change.
    fireEvent.click(screen.getByTestId('review-cancel'));
    expect(screen.getByTestId('pending-bar')).toBeInTheDocument();
    expect(screen.getByTestId('cell-project_manager-budgets.create')).not.toBeChecked();
  });
});

describe('create-role dialog', () => {
  test('client-side validation blocks short names and empty descriptions', async () => {
    await renderPage();
    fireEvent.click(screen.getByTestId('new-role-btn'));
    expect(screen.getByTestId('create-role-dialog')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('create-role-name'),
      { target: { value: 'ab' } });
    fireEvent.change(screen.getByTestId('create-role-description'),
      { target: { value: 'desc' } });
    fireEvent.click(screen.getByTestId('create-role-submit'));
    expect(await screen.findByTestId('create-role-error')).toHaveTextContent(
      /3.100 characters/);
    expect(createRole).not.toHaveBeenCalled();
  });

  test('server 409 (slug collision) surfaces inline and preserves input', async () => {
    createRole.mockRejectedValue({
      response: { data: { detail:
        "A role with code 'site_manager' already exists — choose a different name" } },
    });
    await renderPage();
    fireEvent.click(screen.getByTestId('new-role-btn'));
    fireEvent.change(screen.getByTestId('create-role-name'),
      { target: { value: 'Site Manager' } });
    fireEvent.change(screen.getByTestId('create-role-description'),
      { target: { value: 'duplicate' } });
    fireEvent.click(screen.getByTestId('create-role-submit'));
    expect(await screen.findByTestId('create-role-error')).toHaveTextContent(
      /already exists/);
    expect(screen.getByTestId('create-role-name')).toHaveValue('Site Manager');
    expect(toast.error).toHaveBeenCalled();
  });
});

describe('permission gating', () => {
  test('roles.view only → read-only: disabled cells, no edit affordances', async () => {
    setAuth(['roles.view']);
    await renderPage();
    expect(screen.getByTestId('read-only-badge')).toBeInTheDocument();
    expect(screen.queryByTestId('new-role-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('role-kebab-b83_custom')).not.toBeInTheDocument();
    const cell = screen.getByTestId('cell-project_manager-budgets.create');
    expect(cell).toBeDisabled();
    fireEvent.click(cell);
    expect(screen.queryByTestId('pending-bar')).not.toBeInTheDocument();
  });

  test('no roles.view → forbidden state', async () => {
    setAuth([]);
    render(
      <MemoryRouter>
        <RolePermissionsAdmin />
      </MemoryRouter>
    );
    expect(screen.getByTestId('roles-admin-forbidden')).toBeInTheDocument();
  });

  test('custom role column shows kebab; system columns do not', async () => {
    await renderPage();
    expect(screen.getByTestId('role-kebab-b83_custom')).toBeInTheDocument();
    expect(screen.queryByTestId('role-kebab-project_manager')).not.toBeInTheDocument();
    expect(screen.queryByTestId('role-kebab-super_admin')).not.toBeInTheDocument();
  });
});
