/**
 * useUserPreferences — Chat 23 R6.1.
 *
 * React Query hooks for the user_preferences surface CRUD. All hooks
 * accept a `surfaceKey` (the BudgetGridV2 surface is `budgets.grid.v2`)
 * so a future surface (cost-codes grid, actuals grid, etc.) can reuse
 * the same plumbing.
 *
 * Important detail for the next agent:
 *   useSetCurrentPreference's onSuccess uses (_data, variables) —
 *   NOT arguments[0]. Build Pack §C2 audit fix. We do NOT mutate the
 *   query cache here; the autosave's only job is to persist, so we
 *   skip cache writes to avoid causing re-renders mid-typing.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as prefsApi from '@/lib/api/userPreferences';

export const userPreferencesKeys = {
  snapshot: (surfaceKey) => ['user-preferences', surfaceKey],
};

export function useUserPreferences(surfaceKey, { enabled = true } = {}) {
  return useQuery({
    queryKey: userPreferencesKeys.snapshot(surfaceKey),
    queryFn: ({ signal }) => prefsApi.getSurfaceSnapshot(surfaceKey, { signal }),
    enabled: enabled && !!surfaceKey,
    // The snapshot drives initial-state hydration. Don't refetch on
    // window focus — that would clobber unsaved column-resize drafts.
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
}

export function useSetCurrentPreference(surfaceKey) {
  // Autosave PUT — debounced upstream by BudgetGridV2Desktop. Build
  // Pack §C2 audit fix: use (_data, variables) signature on onSuccess
  // (NOT arguments[0]) so the next agent doesn't accidentally read
  // the response body when they meant to read the request payload.
  return useMutation({
    mutationFn: (payload) => prefsApi.putCurrentPreference(surfaceKey, payload),
    // Intentionally NO cache writes here — the autosave is fire-and-
    // forget. The grid renders from local state; we only persist.
    // Errors are surfaced by the cell via a toast.
    onSuccess: (_data, _variables) => {
      // intentionally empty — see header comment.
    },
  });
}

export function useCreateSavedView(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, payload }) =>
      prefsApi.createSavedView(surfaceKey, { name, payload }),
    onSuccess: (newView, _variables) => {
      qc.setQueryData(
        userPreferencesKeys.snapshot(surfaceKey),
        (old) => old
          ? { ...old, views: [newView, ...(old.views ?? [])] }
          : old,
      );
    },
  });
}

export function useUpdateSavedView(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, payload }) =>
      prefsApi.updateSavedView(surfaceKey, name, payload),
    onSuccess: (updated, _variables) => {
      qc.setQueryData(
        userPreferencesKeys.snapshot(surfaceKey),
        (old) => old
          ? {
              ...old,
              views: (old.views ?? []).map((v) =>
                v.name === updated.name ? updated : v,
              ),
            }
          : old,
      );
    },
  });
}

export function useDeleteSavedView(surfaceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name) => prefsApi.deleteSavedView(surfaceKey, name),
    onSuccess: (_data, name) => {
      qc.setQueryData(
        userPreferencesKeys.snapshot(surfaceKey),
        (old) => old
          ? { ...old, views: (old.views ?? []).filter((v) => v.name !== name) }
          : old,
      );
    },
  });
}
