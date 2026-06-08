/**
 * Subcontracts API client tests — Build Pack 2.8-FE-i §R6, Gate 1.
 *
 * Wire-level contract pins for `lib/api/subcontracts.js`. Same shape as
 * `lib/api/__tests__/supplierDocuments.test.js`: the real api fns run
 * against a mocked axios `api`, asserting the exact URL + params + body
 * sent on the wire.
 *
 * Coverage (Build Pack §R6 Gate 1):
 *   - list params forwarded under the right keys (project_id, status,
 *     limit, offset); undefined params are stripped.
 *   - getSubcontract URL pin.
 *   - createSubcontract body: MUST NOT include `reference` or `status`
 *     (Build Pack §R0.3 / §R4.4 lockdown — backend generates reference
 *     and transitions happen via action endpoints).
 *   - updateSubcontract body: forbidden fields (project_id /
 *     subcontractor_id / status) are NOT auto-injected by the client;
 *     the caller's payload is passed straight through, so we pin the
 *     "the client is a thin pass-through" contract — the caller is
 *     responsible for trimming to the allowed set (backend would 422
 *     under Pydantic extra:"forbid").
 *   - activate / complete / terminate POST paths.
 *   - Action endpoints POST with an empty body (axios convention).
 *   - Errors propagate unchanged (component layer maps 404/409/422).
 */
import * as scApi from '@/lib/api/subcontracts';

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
  },
}));
const { api } = jest.requireMock('@/lib/api');


beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
  api.get.mockResolvedValue({ data: { items: [], total: 0 } });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
});


describe('listSubcontracts — §R3.1 query-param contract', () => {
  test('GETs /v1/subcontracts with no params when none supplied', async () => {
    await scApi.listSubcontracts();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontracts',
      { signal: undefined, params: {} },
    );
  });

  test('forwards projectId as project_id (NOT projectId)', async () => {
    await scApi.listSubcontracts({ projectId: 'P-1' });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontracts',
      { signal: undefined, params: { project_id: 'P-1' } },
    );
  });

  test('forwards status / limit / offset under their snake_case keys', async () => {
    await scApi.listSubcontracts({
      status: 'Active', limit: 25, offset: 50,
    });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontracts',
      { signal: undefined, params: { status: 'Active', limit: 25, offset: 50 } },
    );
  });

  test('does NOT send undefined params (no `subcontractor_id` key — the endpoint has no such filter, §R4.1)', async () => {
    await scApi.listSubcontracts({ projectId: undefined, status: undefined });
    const [, opts] = api.get.mock.calls[0];
    // Defensive — neither key should appear in the params object.
    expect(opts.params).toEqual({});
    expect(Object.prototype.hasOwnProperty.call(opts.params, 'subcontractor_id')).toBe(false);
  });

  test('forwards AbortSignal so list queries are cancellable', async () => {
    const ac = new AbortController();
    await scApi.listSubcontracts({ projectId: 'P-1', signal: ac.signal });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.signal).toBe(ac.signal);
  });

  test('returns the raw response body ({items,total})', async () => {
    api.get.mockResolvedValueOnce({ data: { items: [{ id: 'S1' }], total: 1 } });
    const out = await scApi.listSubcontracts();
    expect(out).toEqual({ items: [{ id: 'S1' }], total: 1 });
  });
});


describe('getSubcontract — §R3.1 URL contract', () => {
  test('GETs /v1/subcontracts/{id}', async () => {
    api.get.mockResolvedValueOnce({ data: { id: 'S1' } });
    const out = await scApi.getSubcontract('S1');
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontracts/S1', { signal: undefined },
    );
    expect(out).toEqual({ id: 'S1' });
  });

  test('forwards AbortSignal', async () => {
    const ac = new AbortController();
    await scApi.getSubcontract('S1', { signal: ac.signal });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.signal).toBe(ac.signal);
  });
});


describe('createSubcontract — §R4.4 / §R0.3 body contract', () => {
  test('POSTs to /v1/subcontracts with the supplied body verbatim', async () => {
    const body = {
      project_id: 'P-1',
      subcontractor_id: 'SUP-9',
      title: 'Groundworks package',
      scope_description: 'Strip + foundations',
      purchase_order_id: null,
      original_contract_sum: '125000.00',
      retention_pct: '5',
      cis_applies: true,
      start_on: '2026-05-01',
      end_on: '2026-09-30',
    };
    api.post.mockResolvedValueOnce({ data: { id: 'S1', ...body, status: 'Draft' } });

    const out = await scApi.createSubcontract(body);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith('/v1/subcontracts', body);
    expect(out).toEqual(expect.objectContaining({ id: 'S1', status: 'Draft' }));
  });

  test('client does NOT inject `reference` or `status` (backend generates the ref; status defaults to Draft, transitions go via action endpoints)', async () => {
    const body = {
      project_id: 'P-1', subcontractor_id: 'SUP-9', title: 'Roofing',
    };
    await scApi.createSubcontract(body);
    const [, sent] = api.post.mock.calls[0];
    expect(Object.prototype.hasOwnProperty.call(sent, 'reference')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(sent, 'status')).toBe(false);
  });

  test('propagates 422 axios errors so the form can surface server detail', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('Invalid'), {
        response: { status: 422, data: { detail: 'title: required' } },
      }),
    );
    await expect(
      scApi.createSubcontract({ project_id: 'P-1', subcontractor_id: 'SUP-9' }),
    ).rejects.toMatchObject({
      response: { status: 422, data: { detail: 'title: required' } },
    });
  });
});


describe('updateSubcontract — §R3.1 PATCH passthrough contract', () => {
  test('PATCHes /v1/subcontracts/{id} with the body verbatim (caller responsible for trimming to the allowed set)', async () => {
    const body = {
      title: 'Updated title',
      original_contract_sum: '130000.00',
      signed_at: '2026-04-15T10:00:00Z',
      signed_by: 'USR-3',
    };
    api.patch.mockResolvedValueOnce({ data: { id: 'S1', ...body } });

    const out = await scApi.updateSubcontract('S1', body);

    expect(api.patch).toHaveBeenCalledTimes(1);
    expect(api.patch).toHaveBeenCalledWith('/v1/subcontracts/S1', body);
    expect(out).toEqual(expect.objectContaining({ id: 'S1', title: 'Updated title' }));
  });

  test('client is a thin pass-through — no field stripping; the FormDialog (§R4.4) is the trim point', async () => {
    // Hard pin: if a future change starts stripping `status`/`project_id`
    // here, that's wrong — the FormDialog should never put them in.
    // Keep the wire layer dumb so the test surface is the form, not the client.
    const body = { title: 'X', extra_garbage_field: 'should pass through' };
    await scApi.updateSubcontract('S1', body);
    const [, sent] = api.patch.mock.calls[0];
    expect(sent).toEqual(body);
  });

  test('propagates 409 state-error axios responses', async () => {
    api.patch.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: { status: 409, data: { detail: 'Cannot edit a terminal subcontract' } },
      }),
    );
    await expect(
      scApi.updateSubcontract('S1', { title: 'X' }),
    ).rejects.toMatchObject({
      response: { status: 409, data: { detail: 'Cannot edit a terminal subcontract' } },
    });
  });
});


describe('Lifecycle action endpoints — §R3.1 path + empty-body contract', () => {
  test('activateSubcontract POSTs /v1/subcontracts/{id}/activate with {}', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 'S1', status: 'Active' } });
    const out = await scApi.activateSubcontract('S1');
    expect(api.post).toHaveBeenCalledWith('/v1/subcontracts/S1/activate', {});
    expect(out).toEqual({ id: 'S1', status: 'Active' });
  });

  test('completeSubcontract POSTs /v1/subcontracts/{id}/complete with {}', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 'S1', status: 'Completed' } });
    const out = await scApi.completeSubcontract('S1');
    expect(api.post).toHaveBeenCalledWith('/v1/subcontracts/S1/complete', {});
    expect(out).toEqual({ id: 'S1', status: 'Completed' });
  });

  test('terminateSubcontract POSTs /v1/subcontracts/{id}/terminate with {}', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 'S1', status: 'Terminated' } });
    const out = await scApi.terminateSubcontract('S1');
    expect(api.post).toHaveBeenCalledWith('/v1/subcontracts/S1/terminate', {});
    expect(out).toEqual({ id: 'S1', status: 'Terminated' });
  });

  test('propagates 409 from activate (e.g. unsigned subcontract) so the UI can surface the state-error message', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: { detail: 'Cannot activate an unsigned subcontract (set signed_at first)' },
        },
      }),
    );
    await expect(scApi.activateSubcontract('S1')).rejects.toMatchObject({
      response: {
        status: 409,
        data: { detail: 'Cannot activate an unsigned subcontract (set signed_at first)' },
      },
    });
  });

  test('propagates 409 from complete (e.g. not Active)', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: { status: 409, data: { detail: 'Can only complete an Active subcontract' } },
      }),
    );
    await expect(scApi.completeSubcontract('S1')).rejects.toMatchObject({
      response: { status: 409 },
    });
  });

  test('propagates 409 from terminate (already terminal)', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: { status: 409, data: { detail: 'Subcontract is already terminal' } },
      }),
    );
    await expect(scApi.terminateSubcontract('S1')).rejects.toMatchObject({
      response: { status: 409 },
    });
  });
});
