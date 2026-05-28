/**
 * R7.6 optimistic layer tests — usePoTransition + useCreateReceipt.
 *
 * Asserts:
 *   - Commitment-changing verbs (void, sendBack, approve, close)
 *     invalidate `['budgets']` on settle (AC5).
 *   - Void's optimistic patch flips po.status to 'voided' on onMutate
 *     and rolls back to the prior snapshot when the mutation rejects.
 *   - useCreateReceipt invalidates `['budgets']` on success.
 *   - The submit verb (non-commitment) does NOT invalidate ['budgets'].
 */
import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { usePoTransition, useCreateReceipt, poKeys } from '../purchaseOrders';
import * as poApi from '@/lib/api/purchaseOrders';

jest.mock('@/lib/api/purchaseOrders');


function wrapper(qc) {
  return ({ children }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}


describe('usePoTransition + useCreateReceipt — R7.6 optimistic + budgets invalidate', () => {

  test('void: optimistic status=voided on onMutate; rolls back on error', async () => {
    const qc = makeClient();
    // Seed PO detail cache.
    qc.setQueryData(poKeys.detail('po-1'), { id: 'po-1', status: 'issued' });

    poApi.voidPO.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(
      () => usePoTransition('po-1', 'void'), { wrapper: wrapper(qc) },
    );

    // onMutate fires synchronously inside the mutateAsync promise chain
    // before the awaited mutationFn. We wrap the call in try/catch so
    // the rejection doesn't unhandled-fail the test.
    await act(async () => {
      try {
        await result.current.mutateAsync({ reason: 'duplicate' });
      } catch { /* expected */ }
    });

    // After rollback, the cache snapshot must match the pre-mutate state.
    const cached = qc.getQueryData(poKeys.detail('po-1'));
    expect(cached).toEqual({ id: 'po-1', status: 'issued' });
  });

  test('void: optimistic patch applies status=voided while in flight', async () => {
    const qc = makeClient();
    qc.setQueryData(poKeys.detail('po-1'), { id: 'po-1', status: 'issued' });

    // Resolve the API call manually so we can observe the optimistic
    // state between onMutate and onSettled.
    let resolveFn;
    poApi.voidPO.mockReturnValue(new Promise((res) => { resolveFn = res; }));

    const { result } = renderHook(
      () => usePoTransition('po-1', 'void'), { wrapper: wrapper(qc) },
    );

    let mutationPromise;
    act(() => {
      mutationPromise = result.current.mutateAsync({ reason: 'x' });
    });

    // Wait until onMutate has had a chance to run.
    await waitFor(() => {
      expect(qc.getQueryData(poKeys.detail('po-1'))?.status).toBe('voided');
    });

    // Resolve the API and let onSettled invalidate.
    await act(async () => {
      resolveFn({});
      await mutationPromise;
    });
  });

  test('void: ["budgets"] invalidated on settle (AC5)', async () => {
    const qc = makeClient();
    qc.setQueryData(poKeys.detail('po-1'), { id: 'po-1', status: 'issued' });
    const spy = jest.spyOn(qc, 'invalidateQueries');
    poApi.voidPO.mockResolvedValue({});

    const { result } = renderHook(
      () => usePoTransition('po-1', 'void'), { wrapper: wrapper(qc) },
    );
    await act(async () => {
      await result.current.mutateAsync({ reason: 'x' });
    });

    const calls = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(calls).toContain(JSON.stringify(['budgets']));
    expect(calls).toContain(JSON.stringify(poKeys.detail('po-1')));
    expect(calls).toContain(JSON.stringify(poKeys.all));
  });

  test('sendBack: ["budgets"] invalidated on settle (commitment verb)', async () => {
    const qc = makeClient();
    qc.setQueryData(poKeys.detail('po-1'), { id: 'po-1', status: 'approved' });
    const spy = jest.spyOn(qc, 'invalidateQueries');
    poApi.sendBackPO.mockResolvedValue({});

    const { result } = renderHook(
      () => usePoTransition('po-1', 'sendBack'), { wrapper: wrapper(qc) },
    );
    await act(async () => {
      await result.current.mutateAsync({ notes: 'wrong supplier' });
    });

    const calls = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(calls).toContain(JSON.stringify(['budgets']));
  });

  test('submit (non-commitment verb): does NOT invalidate ["budgets"]', async () => {
    const qc = makeClient();
    const spy = jest.spyOn(qc, 'invalidateQueries');
    poApi.submitPO.mockResolvedValue({});

    const { result } = renderHook(
      () => usePoTransition('po-1', 'submit'), { wrapper: wrapper(qc) },
    );
    await act(async () => {
      await result.current.mutateAsync();
    });

    const calls = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(calls).not.toContain(JSON.stringify(['budgets']));
  });

  test('useCreateReceipt: invalidates ["budgets"] on success (AC5)', async () => {
    const qc = makeClient();
    const spy = jest.spyOn(qc, 'invalidateQueries');
    poApi.createReceipt.mockResolvedValue({});

    const { result } = renderHook(
      () => useCreateReceipt('po-1'), { wrapper: wrapper(qc) },
    );
    await act(async () => {
      await result.current.mutateAsync({
        received_date: '2026-02-01',
        lines: [{ po_line_id: 'l1', quantity_received: 1 }],
      });
    });

    const calls = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(calls).toContain(JSON.stringify(['budgets']));
    expect(calls).toContain(JSON.stringify(poKeys.receipts('po-1')));
  });
});
