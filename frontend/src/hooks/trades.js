/**
 * Trades hooks — Chat 41 §R1.2 (Build Pack 2.7-FE-revision).
 *
 * TanStack Query wrappers, mirroring the suppliersKeys pattern in
 * hooks/purchaseOrders.js. `tradesKeys` is exported so <TradePicker>
 * can read the cache without a second fetch.
 *
 * `staleTime: 60_000` because trades are a small, slow-moving vocabulary
 * (tens, not thousands); a one-minute window keeps the picker snappy.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as tradesApi from '@/lib/api/trades';

export const tradesKeys = {
  all: ['trades'],
  list: (params) => ['trades', 'list', params ?? {}],
};

export function useTrades({ params, enabled = true } = {}) {
  return useQuery({
    queryKey: tradesKeys.list(params),
    queryFn: ({ signal }) => tradesApi.listTrades({ signal, params }),
    enabled,
    staleTime: 60_000,
  });
}

export function useCreateTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name) => tradesApi.createTrade(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tradesKeys.all });
    },
  });
}
