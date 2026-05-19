/**
 * ProjectPicker URL-contract regression pin — Chat 23 §R7.5
 * (Future_Tasks §11 audit).
 *
 * `useProjects` (the internal hook in ProjectPicker.jsx) MUST call
 * `/projects` because `projects_router` is mounted under `api_router`
 * directly (server.py:139). The previous `/v1/projects` path 404'd and
 * the `?? []` fallback silently emptied the dropdown.
 *
 * The bug class is documented in `/app/docs/SY_Homes_Future_Tasks.md` §11.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('@/lib/api', () => ({
  api: { get: jest.fn() },
}));
// eslint-disable-next-line import/first
import { api } from '@/lib/api';
// eslint-disable-next-line import/first
import { ProjectPicker } from '../ProjectPicker';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  api.get.mockReset();
});

describe('ProjectPicker — URL contract (regression pin)', () => {
  test('useProjects calls /projects (NOT /v1/projects)', async () => {
    api.get.mockResolvedValue({
      data: { items: [{ id: 'p-1', name: 'Demo Project' }] },
    });
    wrap(<ProjectPicker value={null} onChange={() => {}} suggested={null} />);

    // Wait for the Select trigger to appear (means the query resolved
    // and the dropdown rendered).
    await waitFor(() =>
      expect(screen.queryByTestId('project-picker-loading')).toBeNull(),
    );

    const urls = api.get.mock.calls.map((c) => c[0]);
    expect(urls).toContain('/projects');
    // Hard negative — the previous buggy path MUST NOT be used.
    for (const u of urls) {
      expect(u).not.toMatch(/^\/v1\/projects/);
    }
  });

  test('useProjects passes page_size=200 query param', async () => {
    api.get.mockResolvedValue({ data: { items: [] } });
    wrap(<ProjectPicker value={null} onChange={() => {}} suggested={null} />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    // Second-positional axios-options arg.
    const opts = api.get.mock.calls[0][1];
    expect(opts).toEqual(
      expect.objectContaining({
        params: expect.objectContaining({ page_size: 200 }),
      }),
    );
  });
});
