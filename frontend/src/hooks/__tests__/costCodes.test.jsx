/**
 * costCodes hook contract tests — regression pins for the bug found
 * during the §R7 spot-check (cost-code labels rendered as "—
 * Uncategorised —" for every line on a real seeded budget).
 *
 * Two contracts pinned here:
 *
 *   1. `useCostCodes(projectId)` MUST call the path
 *      `/projects/${projectId}/cost-codes` against the axios instance
 *      whose baseURL is `${REACT_APP_BACKEND_URL}/api`. Resolved
 *      browser URL: `/api/projects/.../cost-codes`. NOT `/v1/...`.
 *
 *      Why: `cost_codes_router` is mounted under `api_router`
 *      (server.py:140), NOT under the `v1_router` (server.py:148-158).
 *      A `/v1/...` call returns 404, the hook resolves to empty array,
 *      and `groupLinesByCategory` falls back to "Uncategorised" for
 *      every line. The §R3 grid contract relied on this hook being
 *      correct; Jest didn't catch it because every component test
 *      either mocked `useCostCodes` directly or hit an MSW handler
 *      keyed on a normalised path.
 *
 *   2. `buildCostCodeMap(rows)` MUST key by `cost_code_id` (the FK
 *      column on `budget_lines`), NOT the row's own `id` (which is
 *      the project_cost_codes join-table primary key).
 *
 *      Why: `BudgetLine.cost_code_id` references `cost_codes.id`. The
 *      ProjectCostCodeRead payload carries BOTH fields — its `id` is
 *      the mapping-row id, separate from `cost_code_id`. Keying the
 *      map by `id` means line lookups all miss and the grid falls
 *      back to "Uncategorised".
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('@/lib/api', () => {
  const get = jest.fn();
  return { api: { get }, __getMock: get };
});
// eslint-disable-next-line import/first
import { useCostCodes, buildCostCodeMap } from '../costCodes';
// eslint-disable-next-line import/first
import { api } from '@/lib/api';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  api.get.mockReset();
});

describe('useCostCodes — URL contract (regression pin from §R7 spot-check)', () => {
  test('calls /projects/:projectId/cost-codes (NOT /v1/projects/:projectId/cost-codes)', async () => {
    api.get.mockResolvedValueOnce({ data: [] });
    const { result } = renderHook(
      () => useCostCodes('proj-123'),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The exact axios call: path is /projects/proj-123/cost-codes (NO /v1).
    // baseURL is configured upstream as `${REACT_APP_BACKEND_URL}/api`
    // so this resolves to `${REACT_APP_BACKEND_URL}/api/projects/proj-123/cost-codes`.
    expect(api.get).toHaveBeenCalledWith(
      '/projects/proj-123/cost-codes',
      expect.any(Object),
    );

    // Hard negative — the previous buggy path MUST NOT be in use.
    expect(api.get.mock.calls[0][0]).not.toMatch(/^\/v1\//);
  });
});

describe('buildCostCodeMap — key contract (regression pin from §R7 spot-check)', () => {
  test('keys by cost_code_id (the FK), NOT the join-table row id', () => {
    const rows = [
      {
        id: 'mapping-row-aaa',                   // project_cost_codes.id
        cost_code_id: 'cost-code-uuid-aaa',      // FK target on budget_lines
        code: 'ACQ-01',
        name: 'Land',
        project_id: 'proj-1',
      },
      {
        id: 'mapping-row-bbb',
        cost_code_id: 'cost-code-uuid-bbb',
        code: 'EXT-01',
        name: 'Drainage',
        project_id: 'proj-1',
      },
    ];
    const map = buildCostCodeMap(rows);

    // Lookups by FK succeed.
    expect(map.get('cost-code-uuid-aaa')?.code).toBe('ACQ-01');
    expect(map.get('cost-code-uuid-bbb')?.code).toBe('EXT-01');

    // Lookups by the OLD wrong key (mapping-row id) MUST miss.
    expect(map.get('mapping-row-aaa')).toBeUndefined();
    expect(map.get('mapping-row-bbb')).toBeUndefined();
  });

  test('falls back to `id` when `cost_code_id` absent (test-fixture shape)', () => {
    // Existing component tests pass minimal `{ id, code, name }` shapes
    // without `cost_code_id` (see BudgetGridV2-R6.test.jsx). Keep that
    // green so this regression fix doesn't cascade.
    const rows = [
      { id: 'cc-1', code: 'ACQ-01', name: 'Land' },
      { id: 'cc-2', code: 'EXT-01', name: 'Drainage' },
    ];
    const map = buildCostCodeMap(rows);
    expect(map.get('cc-1')?.code).toBe('ACQ-01');
    expect(map.get('cc-2')?.code).toBe('EXT-01');
  });

  test('skips rows with neither cost_code_id nor id', () => {
    const map = buildCostCodeMap([
      null,
      undefined,
      {},
      { code: 'ACQ-01' },           // no id, no cost_code_id
      { cost_code_id: 'cc-a', code: 'ACQ-01' },
    ]);
    expect(map.size).toBe(1);
    expect(map.get('cc-a')?.code).toBe('ACQ-01');
  });
});
