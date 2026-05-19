/**
 * useUserPreferences hook tests — Chat 23 R6.1.
 *
 * Pins the 5 hook contracts:
 *   - useUserPreferences: GETs snapshot, caches by surface key,
 *     refetchOnWindowFocus disabled.
 *   - useSetCurrentPreference: PUT current, NO cache write (autosave
 *     is fire-and-forget).
 *   - useCreateSavedView: POST + prepend to cached views.
 *   - useUpdateSavedView: PUT + replace in cached views.
 *   - useDeleteSavedView: DELETE + filter out of cached views.
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useUserPreferences, useSetCurrentPreference,
  useCreateSavedView, useUpdateSavedView, useDeleteSavedView,
  userPreferencesKeys,
} from '@/hooks/userPreferences';

jest.mock('@/lib/api/userPreferences', () => ({
  getSurfaceSnapshot: jest.fn(),
  putCurrentPreference: jest.fn(),
  createSavedView: jest.fn(),
  updateSavedView: jest.fn(),
  deleteSavedView: jest.fn(),
}));
import * as prefsApi from '@/lib/api/userPreferences';

const SURFACE = 'budgets.grid.v2';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    wrapper: ({ children }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('useUserPreferences', () => {
  test('fetches snapshot for the surface key', async () => {
    prefsApi.getSurfaceSnapshot.mockResolvedValueOnce({
      surface_key: SURFACE, current: { foo: 1 }, views: [],
    });
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUserPreferences(SURFACE), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(prefsApi.getSurfaceSnapshot).toHaveBeenCalledWith(
      SURFACE, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(result.current.data.current).toEqual({ foo: 1 });
  });
});

describe('useSetCurrentPreference', () => {
  test('PUT fires with payload; cache is NOT mutated', async () => {
    prefsApi.putCurrentPreference.mockResolvedValueOnce({
      id: '1', payload: { x: 99 },
    });
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(userPreferencesKeys.snapshot(SURFACE), {
      surface_key: SURFACE, current: { x: 1 }, views: [],
    });

    const { result } = renderHook(() => useSetCurrentPreference(SURFACE), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ x: 99 });
    });
    expect(prefsApi.putCurrentPreference).toHaveBeenCalledWith(SURFACE, { x: 99 });
    // Cache should NOT have been mutated by the hook (autosave fire-and-forget).
    expect(qc.getQueryData(userPreferencesKeys.snapshot(SURFACE)).current)
      .toEqual({ x: 1 });
  });
});

describe('useCreateSavedView', () => {
  test('POST + prepend to cached views', async () => {
    const newView = { id: '2', name: 'My view', payload: { v: 1 } };
    prefsApi.createSavedView.mockResolvedValueOnce(newView);
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(userPreferencesKeys.snapshot(SURFACE), {
      surface_key: SURFACE, current: {},
      views: [{ id: '1', name: 'Existing', payload: {} }],
    });

    const { result } = renderHook(() => useCreateSavedView(SURFACE), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ name: 'My view', payload: { v: 1 } });
    });
    expect(prefsApi.createSavedView).toHaveBeenCalledWith(SURFACE, {
      name: 'My view', payload: { v: 1 },
    });
    expect(qc.getQueryData(userPreferencesKeys.snapshot(SURFACE)).views)
      .toEqual([newView, { id: '1', name: 'Existing', payload: {} }]);
  });

  test('409 conflict surfaces error without mutating cache', async () => {
    const err = Object.assign(new Error('409 conflict'), {
      response: { status: 409 },
    });
    prefsApi.createSavedView.mockRejectedValueOnce(err);
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(userPreferencesKeys.snapshot(SURFACE), {
      surface_key: SURFACE, current: {}, views: [],
    });

    const { result } = renderHook(() => useCreateSavedView(SURFACE), { wrapper });
    await expect(
      result.current.mutateAsync({ name: 'dup', payload: {} }),
    ).rejects.toThrow(/409/);
    expect(qc.getQueryData(userPreferencesKeys.snapshot(SURFACE)).views)
      .toEqual([]);
  });
});

describe('useUpdateSavedView', () => {
  test('PUT + replace matching view in cache', async () => {
    const updated = { id: '1', name: 'V1', payload: { v: 999 } };
    prefsApi.updateSavedView.mockResolvedValueOnce(updated);
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(userPreferencesKeys.snapshot(SURFACE), {
      surface_key: SURFACE, current: {},
      views: [{ id: '1', name: 'V1', payload: { v: 1 } }],
    });

    const { result } = renderHook(() => useUpdateSavedView(SURFACE), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ name: 'V1', payload: { v: 999 } });
    });
    expect(prefsApi.updateSavedView).toHaveBeenCalledWith(
      SURFACE, 'V1', { v: 999 },
    );
    expect(qc.getQueryData(userPreferencesKeys.snapshot(SURFACE)).views[0])
      .toEqual(updated);
  });
});

describe('useDeleteSavedView', () => {
  test('DELETE + filter out of cache', async () => {
    prefsApi.deleteSavedView.mockResolvedValueOnce(undefined);
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(userPreferencesKeys.snapshot(SURFACE), {
      surface_key: SURFACE, current: {},
      views: [
        { id: '1', name: 'Keep' },
        { id: '2', name: 'Goner' },
      ],
    });

    const { result } = renderHook(() => useDeleteSavedView(SURFACE), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('Goner');
    });
    expect(prefsApi.deleteSavedView).toHaveBeenCalledWith(SURFACE, 'Goner');
    const remaining = qc.getQueryData(userPreferencesKeys.snapshot(SURFACE)).views;
    expect(remaining.map((v) => v.name)).toEqual(['Keep']);
  });
});
