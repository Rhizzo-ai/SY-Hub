/**
 * R7-polish-mini-v2 §R4 — PIN TESTS for the approve/close
 * `['budgets']` invalidation contract in `usePoTransition`.
 *
 * Why pin:
 *   - R7-polish-mini-v2 §R1 pruned `issue` out of COMMITMENT_VERBS.
 *     The surviving commitment-changing verbs (void, sendBack,
 *     approve, close) MUST keep invalidating `['budgets']` on settle
 *     so the R6 Budgets grid's committed column refreshes.
 *   - `void` and `sendBack` are already pinned by
 *     `purchaseOrders.optimistic.test.jsx`. This file adds the two
 *     remaining commitment verbs — `approve` and `close` — so a
 *     regression that drops either invalidation will fail a
 *     dedicated test.
 *
 * Contract test, not behaviour test:
 *   - We don't assert UI; we assert the cache-invalidation surface
 *     emitted by the hook on a settled mutation. The matcher is
 *     version-agnostic (TanStack v4 positional vs v5 options-object)
 *     so an internal refactor that flips signature doesn't break the
 *     pin — only an actual loss of the `['budgets']` invalidation
 *     does.
 *
 * Acceptance:
 *   - Both tests pass against the current hook (post-§R1 set).
 *   - Deleting the `qc.invalidateQueries({ queryKey: ['budgets'] })`
 *     line inside `onSettled` (or removing the verb from
 *     `COMMITMENT_VERBS`) fails the matching test.
 */
import React from 'react';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { usePoTransition, poKeys } from '../purchaseOrders';
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
      queries:   { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

/**
 * Version-agnostic matcher: returns true iff `spy` was called at
 * least once with a query-key that contains the literal string
 * `'budgets'`.
 *
 * Tolerates both call shapes:
 *   - TanStack v4:  qc.invalidateQueries(['budgets'])
 *   - TanStack v5:  qc.invalidateQueries({ queryKey: ['budgets'] })
 *
 * Tolerates extra options-object fields and predicate-only filters
 * (those return `undefined` for queryKey and are correctly ignored).
 */
function calledWithBudgetsKey(spy) {
  return spy.mock.calls.some((call) => {
    const arg = call[0];
    if (!arg) return false;
    const key = Array.isArray(arg) ? arg : arg.queryKey;
    return Array.isArray(key) && key.includes('budgets');
  });
}


describe('usePoTransition — approve/close [budgets] invalidation (R7-polish §R4 PIN)', () => {

  test('approve: invalidates a query-key containing "budgets" on settle', async () => {
    const qc = makeClient();
    qc.setQueryData(poKeys.detail('po-1'), { id: 'po-1', status: 'pending_approval' });
    const spy = jest.spyOn(qc, 'invalidateQueries');

    poApi.approvePO.mockResolvedValue({});

    const { result } = renderHook(
      () => usePoTransition('po-1', 'approve'),
      { wrapper: wrapper(qc) },
    );
    await act(async () => {
      await result.current.mutateAsync({});
    });

    if (!calledWithBudgetsKey(spy)) {
      // STOP-gate per pack §R4: if approve does NOT invalidate
      // ['budgets'], that's a real regression — report, don't patch.
      // We surface the full call log to make triage trivial.
      const dump = spy.mock.calls.map((c) => JSON.stringify(c[0]));
      throw new Error(
        `[R7-polish §R4 PIN FAIL] approve did not invalidate any queryKey containing "budgets". ` +
        `invalidateQueries call log: ${dump.join(' | ')}`,
      );
    }
    expect(calledWithBudgetsKey(spy)).toBe(true);
  });

  test('close: invalidates a query-key containing "budgets" on settle', async () => {
    const qc = makeClient();
    qc.setQueryData(poKeys.detail('po-1'), { id: 'po-1', status: 'receipted' });
    const spy = jest.spyOn(qc, 'invalidateQueries');

    poApi.closePO.mockResolvedValue({});

    const { result } = renderHook(
      () => usePoTransition('po-1', 'close'),
      { wrapper: wrapper(qc) },
    );
    await act(async () => {
      await result.current.mutateAsync();
    });

    if (!calledWithBudgetsKey(spy)) {
      const dump = spy.mock.calls.map((c) => JSON.stringify(c[0]));
      throw new Error(
        `[R7-polish §R4 PIN FAIL] close did not invalidate any queryKey containing "budgets". ` +
        `invalidateQueries call log: ${dump.join(' | ')}`,
      );
    }
    expect(calledWithBudgetsKey(spy)).toBe(true);
  });
});
