/**
 * Payment Notices API client tests — Build Pack 2.8-FE-ii §R6, Gate 1.
 *
 * Wire-level contract pins for `lib/api/paymentNotices.js`. Same shape
 * as `lib/api/__tests__/subcontractValuations.test.js`: real api fns
 * run against mocked axios, asserting exact URL + params + body sent.
 *
 * Coverage (Build Pack §R6 Gate 1):
 *   - list forwards `subcontract_valuation_id` snake_case.
 *   - get URL contract.
 *   - payless POSTs /payment-notices/payless with withhold_amount as
 *     a STRING + reason (the financial-correctness rule encoded at the
 *     wire layer).
 *   - 409 (non-Certified) and 422 (bad amount/reason) propagate.
 *
 * Scope fence: retention-release endpoints are explicitly OUT OF SCOPE
 * in 2.8-FE-ii (Build Pack §R0.2). No wrappers for them in
 * paymentNotices.js, so no wire tests for them here either.
 */
import * as noticesApi from '@/lib/api/paymentNotices';

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
// listPaymentNotices — §R3.2 query-param contract
// ════════════════════════════════════════════════════════════════════

describe('listPaymentNotices — §R3.2 query-param contract', () => {
  test('GETs /v1/payment-notices with no params when none supplied', async () => {
    await noticesApi.listPaymentNotices();
    expect(api.get).toHaveBeenCalledWith(
      '/v1/payment-notices', { signal: undefined, params: {} },
    );
  });

  test('forwards subcontractValuationId as `subcontract_valuation_id` (snake_case)', async () => {
    await noticesApi.listPaymentNotices({
      subcontractValuationId: 'V1',
    });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/payment-notices',
      { signal: undefined, params: { subcontract_valuation_id: 'V1' } },
    );
  });

  test('forwards limit / offset under snake_case keys', async () => {
    await noticesApi.listPaymentNotices({
      subcontractValuationId: 'V1', limit: 50, offset: 100,
    });
    expect(api.get).toHaveBeenCalledWith(
      '/v1/payment-notices',
      {
        signal: undefined,
        params: {
          subcontract_valuation_id: 'V1', limit: 50, offset: 100,
        },
      },
    );
  });

  test('strips undefined params (no camelCase leaks)', async () => {
    await noticesApi.listPaymentNotices({
      subcontractValuationId: undefined, limit: undefined,
    });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.params).toEqual({});
    expect(Object.prototype.hasOwnProperty.call(opts.params, 'subcontractValuationId')).toBe(false);
  });

  test('forwards AbortSignal', async () => {
    const ac = new AbortController();
    await noticesApi.listPaymentNotices({
      subcontractValuationId: 'V1', signal: ac.signal,
    });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.signal).toBe(ac.signal);
  });

  test('returns the raw response body ({items,total})', async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [{ id: 'N1', notice_type: 'Payment' }], total: 1 },
    });
    const out = await noticesApi.listPaymentNotices({
      subcontractValuationId: 'V1',
    });
    expect(out).toEqual({
      items: [{ id: 'N1', notice_type: 'Payment' }], total: 1,
    });
  });
});


// ════════════════════════════════════════════════════════════════════
// getPaymentNotice — URL contract
// ════════════════════════════════════════════════════════════════════

describe('getPaymentNotice — §R3.2 URL contract', () => {
  test('GETs /v1/payment-notices/{id}', async () => {
    api.get.mockResolvedValueOnce({ data: { id: 'N1' } });
    const out = await noticesApi.getPaymentNotice('N1');
    expect(api.get).toHaveBeenCalledWith(
      '/v1/payment-notices/N1', { signal: undefined },
    );
    expect(out).toEqual({ id: 'N1' });
  });

  test('forwards AbortSignal', async () => {
    const ac = new AbortController();
    await noticesApi.getPaymentNotice('N1', { signal: ac.signal });
    const [, opts] = api.get.mock.calls[0];
    expect(opts.signal).toBe(ac.signal);
  });
});


// ════════════════════════════════════════════════════════════════════
// createPayLessNotice — withhold_amount MUST be a STRING
// ════════════════════════════════════════════════════════════════════

describe('createPayLessNotice — §R3.2 body contract (amount as STRING)', () => {
  test('POSTs /v1/payment-notices/payless with the body verbatim; withhold_amount is a STRING', async () => {
    const body = {
      subcontract_valuation_id: 'V1',
      withhold_amount: '2500.00',
      reason: 'Defective workmanship — see snag list ref SNAG-42',
      due_date: '2026-06-15',
    };
    api.post.mockResolvedValueOnce({
      data: { id: 'N2', notice_type: 'PayLess', ...body },
    });

    const out = await noticesApi.createPayLessNotice(body);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(
      '/v1/payment-notices/payless', body,
    );
    expect(out).toEqual(expect.objectContaining({
      id: 'N2', notice_type: 'PayLess',
    }));
    // Financial-correctness rail: never let withhold_amount become a
    // number on the wire.
    const [, sent] = api.post.mock.calls[0];
    expect(typeof sent.withhold_amount).toBe('string');
    expect(typeof sent.reason).toBe('string');
  });

  test('thin pass-through: client never auto-injects `notice_type`, `reference`, `issued_at`, etc.', async () => {
    const body = {
      subcontract_valuation_id: 'V1',
      withhold_amount: '100.00',
      reason: 'x',
    };
    await noticesApi.createPayLessNotice(body);
    const [, sent] = api.post.mock.calls[0];
    [
      'notice_type', 'reference', 'issued_at', 'issued_by',
      'gross_certified', 'retention', 'cis_deducted', 'net_due',
      'tenant_id', 'id', 'created_at',
    ].forEach((k) => {
      expect(Object.prototype.hasOwnProperty.call(sent, k)).toBe(false);
    });
  });

  test('propagates 409 when valuation is not Certified', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('State'), {
        response: {
          status: 409,
          data: {
            detail:
              'PayLess notices can only be issued against a Certified valuation (current status: Submitted)',
          },
        },
      }),
    );
    await expect(
      noticesApi.createPayLessNotice({
        subcontract_valuation_id: 'V1', withhold_amount: '100', reason: 'x',
      }),
    ).rejects.toMatchObject({
      response: {
        status: 409,
        data: {
          detail:
            'PayLess notices can only be issued against a Certified valuation (current status: Submitted)',
        },
      },
    });
  });

  test('propagates 422 on negative amount / blank reason', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('Invalid'), {
        response: {
          status: 422,
          data: { detail: 'withhold_amount must be >= 0' },
        },
      }),
    );
    await expect(
      noticesApi.createPayLessNotice({
        subcontract_valuation_id: 'V1',
        withhold_amount: '-1',
        reason: 'x',
      }),
    ).rejects.toMatchObject({
      response: { status: 422, data: { detail: 'withhold_amount must be >= 0' } },
    });
  });
});
