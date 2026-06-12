/**
 * Roles API client URL contracts — B83 (Chat 52).
 *
 * The roles/permissions routers mount on bare `/api` (server.py) — NOT
 * `/v1`. These tests pin the exact paths so a future refactor that
 * prefixes `/v1` (the suppliers/budgets convention) fails loudly here
 * instead of silently 404ing in production.
 */
import {
  listRoles, getRole, listPermissions, saveRolePermissionsBatch,
  createRole, patchRole, deleteRole,
} from '@/lib/api/roles';
import { api } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));

// CRA jest defaults to resetMocks=true, which strips factory
// implementations before each test — re-prime here, not in the factory.
beforeEach(() => {
  api.get.mockResolvedValue({ data: {} });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
  api.delete.mockResolvedValue({ data: {} });
});

describe('roles API client URL contracts (no /v1)', () => {
  test('listRoles → GET /roles', async () => {
    await listRoles();
    expect(api.get).toHaveBeenCalledWith('/roles', expect.any(Object));
  });

  test('getRole → GET /roles/{id}', async () => {
    await getRole('abc-123');
    expect(api.get).toHaveBeenCalledWith('/roles/abc-123', expect.any(Object));
  });

  test('listPermissions → GET /permissions', async () => {
    await listPermissions();
    expect(api.get).toHaveBeenCalledWith('/permissions', expect.any(Object));
  });

  test('saveRolePermissionsBatch → POST /roles/permissions-batch with {changes}', async () => {
    const changes = [{ role_id: 'r1', add: ['a.b'], remove: [] }];
    await saveRolePermissionsBatch(changes);
    expect(api.post).toHaveBeenCalledWith('/roles/permissions-batch', { changes });
  });

  test('createRole → POST /roles', async () => {
    await createRole({ name: 'X', description: 'Y' });
    expect(api.post).toHaveBeenCalledWith('/roles', { name: 'X', description: 'Y' });
  });

  test('patchRole → PATCH /roles/{id}', async () => {
    await patchRole('r9', { name: 'Z' });
    expect(api.patch).toHaveBeenCalledWith('/roles/r9', { name: 'Z' });
  });

  test('deleteRole → DELETE /roles/{id}', async () => {
    await deleteRole('r9');
    expect(api.delete).toHaveBeenCalledWith('/roles/r9');
  });

  test('no path contains /v1 (mount-point regression)', async () => {
    await listRoles(); await getRole('x'); await listPermissions();
    await saveRolePermissionsBatch([]); await createRole({});
    await patchRole('x', {}); await deleteRole('x');
    const allCalls = [
      ...api.get.mock.calls, ...api.post.mock.calls,
      ...api.patch.mock.calls, ...api.delete.mock.calls,
    ];
    for (const call of allCalls) {
      expect(String(call[0])).not.toContain('/v1');
    }
  });
});
