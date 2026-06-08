/**
 * Subcontract Valuations API client tests — Build Pack 2.8-FE-ii §R6,
 * Gate 1.
 *
 * Wire-level contract pins for `lib/api/subcontractValuations.js`. Same
 * pattern as `lib/api/__tests__/subcontracts.test.js`: the real api fns
 * run against a mocked axios `api`, asserting the exact URL + params +
 * body sent on the wire.
 *
 * Coverage (Build Pack §R6 Gate 1):
 *   1.  list forwards `subcontract_id` + `status` snake_case params.
 *   2.  list strips undefined params.
 *   3.  AbortSignal forwarded.
 *   4.  create body sends money as STRINGS; no auto-injected keys.
 *   5.  submit POSTs /{id}/submit with empty body.
 *   6.  certify POSTs /{id}/certify with `budget_line_id` present.
 *   7.  certify pass-through — client never strips `budget_line_id`
 *       (the wire layer is dumb; dialog enforces presence).
 *   8.  reject POSTs /{id}/reject with `reason`.
 *   9.  409 / 422 errors propagate unchanged (component layer maps).
 *
 * The money-as-strings + budget_line_id-on-the-wire pins are the two
 * critical safety rails this file exists for. Any future refactor that
 * starts coercing numbers, stripping keys, or "helpfully" injecting a
 * default budget_line_id breaks these tests.
 */
import * as valApi from '@/lib/api/subcontractValuations';

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));
const { api } = jest.requireMock('@/lib/api');


beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.get.mockResolvedValue({ data: { items: [], total: 0 } });
  api.post.mockResolvedValue({ data: {} });
});


// ════════════════════════════════════════════════════════════════════
// listValuations — §R3.1 query-param contract
// ════════════════════════════════════════════════════════════════════

describe('listValuations — §R3.1 query-param contract', () => {
  test('GETs /v1/subcontract-valuations with no params when none supplied', async () => {
    await valApi.listValuations();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontract-valuations',
      { signal: undefined, params: {} },
    );
  });

  test('forwards subcontractId as `subcontract_id` (snake_case, NOT camelCase)', async () => {
    await valApi.listValuations({ subcontractId: 'SC-1' });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontract-valuations',
      { signal: undefined, params: { subcontract_id: 'SC-1' } },
    );
  });

  test('forwards status / limit / offset under their snake_case keys', async () => {
    await valApi.listValuations({
      subcontractId: 'SC-1', status: 'Submitted', limit: 25, offset: 50,
    });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontract-valuations',
      {
        signal: undefined,
        params: {
          subcontract_id: 'SC-1',
          status: 'Submitted',
          limit: 25,
          offset: 50,
        },
      },
    );
  });

  test('does NOT send undefined params (no `subcontractor_id`, no camelCase leaks)', async () => {
    await valApi.listValuations({
      subcontractId: undefined, status: undefined, limit: undefined,
    });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.params).toEqual({});
    expect(Object.prototype.hasOwnProperty.call(opts.params, 'subcontractId')).toBe(false);
  });

  test('forwards AbortSignal so list queries are cancellable', async () => {
    const ac = new AbortController();
    await valApi.listValuations({ subcontractId: 'SC-1', signal: ac.signal });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.signal).toBe(ac.signal);
  });

  test('returns the raw response body ({items,total})', async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [{ id: 'V1', status: 'Draft' }], total: 1 },
    });
    const out = await valApi.listValuations({ subcontractId: 'SC-1' });
    expect(out).toEqual({
      items: [{ id: 'V1', status: 'Draft' }], total: 1,
    });
  });
});


// ════════════════════════════════════════════════════════════════════
// getValuation — §R3.1 URL contract
// ════════════════════════════════════════════════════════════════════

describe('getValuation — §R3.1 URL contract', () => {
  test('GETs /v1/subcontract-valuations/{id}', async () => {
    api.get.mockResolvedValueOnce({ data: { id: 'V1' } });
    const out = await valApi.getValuation('V1');
    expect(api.get).toHaveBeenCalledWith(
      '/v1/subcontract-valuations/V1', { signal: undefined },
    );
    expect(out).toEqual({ id: 'V1' });
  });

  test('forwards AbortSignal', async () => {
    const ac = new AbortController();
    await valApi.getValuation('V1', { signal: ac.signal });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.signal).toBe(ac.signal);
  });
});


// ════════════════════════════════════════════════════════════════════
// createValuation — §R3.1 / §R0.3 body contract (money as STRINGS)
// ════════════════════════════════════════════════════════════════════

describe('createValuation — body contract (money as STRINGS)', () => {
  test('POSTs to /v1/subcontract-valuations with the body verbatim — money fields are STRINGS', async () => {
    const body = {
      subcontract_id: 'SC-1',
      gross_applied_to_date: '50000.00',
      labour_portion: '30000.00',
      materials_portion: '20000.00',
      period_start: '2026-05-01',
      period_end: '2026-05-31',
    };
    api.post.mockResolvedValueOnce({
      data: { id: 'V1', status: 'Draft', ...body },
    });

    const out = await valApi.createValuation(body);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/subcontract-valuations', body,
    );
    expect(out).toEqual(expect.objectContaining({
      id: 'V1', status: 'Draft',
    }));
    // Sanity — the money fields on the wire are strings, NOT numbers.
    // This is the platform's financial-correctness rule encoded as a
    // wire-level pin: if a refactor ever coerces them to floats, this
    // assertion fires.
    const [, sent] = api.post.mock.calls[0];
    expect(typeof sent.gross_applied_to_date).toBe('string');
    expect(typeof sent.labour_portion).toBe('string');
    expect(typeof sent.materials_portion).toBe('string');
  });

  test('client is a thin pass-through — does NOT inject status / reference / valuation_number / over_claim_flag', async () => {
    const body = {
      subcontract_id: 'SC-1',
      gross_applied_to_date: '1000.00',
      labour_portion: '0',
      materials_portion: '1000.00',
    };
    await valApi.createValuation(body);
    const [, sent] = api.post.mock.calls[0];
    // None of the server-owned keys should appear in the request body.
    [
      'status', 'reference', 'valuation_number',
      'over_claim_flag', 'over_claim_note',
      'gross_this_cert', 'retention_this_cert',
      'cis_deduction_this_cert', 'net_payable_this_cert',
      'previous_certified_net', 'cis_rate_pct', 'retention_rate_pct',
      'submitted_at', 'certified_at', 'rejected_at',
      'created_at', 'created_by', 'tenant_id', 'id',
    ].forEach((k) => {
      expect(Object.prototype.hasOwnProperty.call(sent, k)).toBe(false);
    });
  });

  test('propagates 422 axios errors so the create form can surface server detail', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('Invalid'), {
        response: {
          status: 422,
          data: { detail: 'gross_applied_to_date must be >= 0' },
        },
      }),
    );
    await expect(
      valApi.createValuation({ subcontract_id: 'SC-1', gross_applied_to_date: '-1' }),
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: { detail: 'gross_applied_to_date must be >= 0' },
      },
    });
  });

  test('propagates 409 axios errors (parent subcontract not Active/Completed)', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: {
            detail: 'Cannot create a valuation on a Draft subcontract (must be Active or Completed)',
          },
        },
      }),
    );
    await expect(
      valApi.createValuation({ subcontract_id: 'SC-1', gross_applied_to_date: '100' }),
    ).rejects.toMatchObject({ response: { status: 409 } });
  });
});


// ════════════════════════════════════════════════════════════════════
// submitValuation — empty-body POST
// ════════════════════════════════════════════════════════════════════

describe('submitValuation — §R3.1 path + empty-body contract', () => {
  test('POSTs /v1/subcontract-valuations/{id}/submit with {} (empty body)', async () => {
    api.post.mockResolvedValueOnce({
      data: { id: 'V1', status: 'Submitted' },
    });
    const out = await valApi.submitValuation('V1');
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/subcontract-valuations/V1/submit', {},
    );
    expect(out).toEqual({ id: 'V1', status: 'Submitted' });
  });

  test('propagates 409 when valuation is not Draft', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: { detail: 'Cannot submit a Certified valuation' },
        },
      }),
    );
    await expect(valApi.submitValuation('V1')).rejects.toMatchObject({
      response: { status: 409 },
    });
  });
});


// ════════════════════════════════════════════════════════════════════
// certifyValuation — body MUST carry budget_line_id (Build-Pack lockdown)
// ════════════════════════════════════════════════════════════════════

describe('certifyValuation — §R3.1 / §R4.4 body contract', () => {
  test('POSTs /v1/subcontract-valuations/{id}/certify with budget_line_id in the body', async () => {
    const body = {
      budget_line_id: 'BL-1',
      transaction_date: '2026-05-31',
      description: 'May valuation',
    };
    api.post.mockResolvedValueOnce({
      data: {
        id: 'V1', status: 'Certified', posted_actual_id: 'ACT-1',
      },
    });

    const out = await valApi.certifyValuation('V1', body);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/subcontract-valuations/V1/certify', body,
    );
    expect(out).toEqual(expect.objectContaining({
      id: 'V1', status: 'Certified', posted_actual_id: 'ACT-1',
    }));
  });

  test('thin pass-through: budget_line_id is the ONLY required key; client never strips it nor injects a default', async () => {
    // Build-pack lockdown: backend REFUSES to guess. The wire layer
    // must NOT helpfully inject a default budget_line_id, and must
    // NOT strip it when supplied. Confirm both halves.
    const onlyRequired = { budget_line_id: 'BL-1' };
    await valApi.certifyValuation('V1', onlyRequired);
    const [, sent] = api.post.mock.calls[0];
    expect(sent).toEqual(onlyRequired);
    expect(sent.budget_line_id).toBe('BL-1');
  });

  test('passes the body verbatim — no auto-injected actor / tenant / status', async () => {
    await valApi.certifyValuation('V1', {
      budget_line_id: 'BL-1', description: 'x',
    });
    const [, sent] = api.post.mock.calls[0];
    ['status', 'tenant_id', 'created_by', 'id'].forEach((k) => {
      expect(Object.prototype.hasOwnProperty.call(sent, k)).toBe(false);
    });
  });

  test('propagates 409 when budget_line_id missing on the server side', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: { detail: 'budget_line_id is required to certify a valuation' },
        },
      }),
    );
    await expect(
      valApi.certifyValuation('V1', { description: 'x' }),
    ).rejects.toMatchObject({
      response: {
        status: 409,
        data: { detail: 'budget_line_id is required to certify a valuation' },
      },
    });
  });

  test('propagates 422 — the labour + materials != gross_this_cert maths guard', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('Invalid'), {
        response: {
          status: 422,
          data: {
            detail:
              'labour_portion + materials_portion (£40,000.00) must equal gross_this_cert (£30,000.00)',
          },
        },
      }),
    );
    await expect(
      valApi.certifyValuation('V1', { budget_line_id: 'BL-1' }),
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: {
          detail:
            'labour_portion + materials_portion (£40,000.00) must equal gross_this_cert (£30,000.00)',
        },
      },
    });
  });

  test('propagates 409 when status is not Submitted', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: {
            detail: 'Cannot certify a Draft valuation (must be Submitted)',
          },
        },
      }),
    );
    await expect(
      valApi.certifyValuation('V1', { budget_line_id: 'BL-1' }),
    ).rejects.toMatchObject({ response: { status: 409 } });
  });
});


// ════════════════════════════════════════════════════════════════════
// rejectValuation — body { reason }
// ════════════════════════════════════════════════════════════════════

describe('rejectValuation — §R3.1 body contract', () => {
  test('POSTs /v1/subcontract-valuations/{id}/reject with { reason }', async () => {
    const body = { reason: 'Numbers do not reconcile with the certified packs' };
    api.post.mockResolvedValueOnce({
      data: {
        id: 'V1', status: 'Rejected',
        rejection_reason: body.reason,
      },
    });

    const out = await valApi.rejectValuation('V1', body);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/subcontract-valuations/V1/reject', body,
    );
    expect(out).toEqual(expect.objectContaining({
      status: 'Rejected', rejection_reason: body.reason,
    }));
  });

  test('thin pass-through: reason key is the ONLY field; client never injects a default', async () => {
    await valApi.rejectValuation('V1', { reason: 'x' });
    const [, sent] = api.post.mock.calls[0];
    expect(sent).toEqual({ reason: 'x' });
  });

  test('propagates 422 when reason is blank server-side', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('Invalid'), {
        response: {
          status: 422,
          data: { detail: 'rejection reason is required' },
        },
      }),
    );
    await expect(
      valApi.rejectValuation('V1', { reason: '' }),
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: { detail: 'rejection reason is required' },
      },
    });
  });

  test('propagates 409 when status is not Submitted', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: {
            detail: 'Cannot reject a Draft valuation (must be Submitted)',
          },
        },
      }),
    );
    await expect(
      valApi.rejectValuation('V1', { reason: 'x' }),
    ).rejects.toMatchObject({ response: { status: 409 } });
  });
});
