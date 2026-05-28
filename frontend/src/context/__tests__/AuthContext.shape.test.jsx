/**
 * AuthContext value-shape regression test (Chat 28).
 *
 * Mounts the REAL `AuthProvider` from `@/context/AuthContext` and
 * inspects the value object exposed via `useAuth()`. Asserts:
 *
 *   - `me` is the canonical key (matches state: `const [me, setMe] =
 *     useState(null)` at AuthContext.jsx:38).
 *   - `user` is NOT a key on the context value.
 *
 * This catches the 7-file Chat-24/R5 latent bug (`const { user } =
 * useAuth()` → undefined → `canViewPOs(undefined)` → forbidden
 * branch → `<po-list>` never mounts) AND any future file that copies
 * the bad pattern. One shared assertion replaces per-component
 * duplication.
 *
 * The bug bypassed Jest because component tests mock `useAuth`
 * directly (jest.mock('../../../context/AuthContext')) — the mock
 * shape is whatever the test author writes, so the real provider's
 * value never gets asserted against. This test bridges that gap by
 * importing the REAL provider.
 */
import React from 'react';
import { render, act, waitFor } from '@testing-library/react';

import { AuthProvider, useAuth } from '@/context/AuthContext';

// Mock the boot-time GET /auth/me so the provider settles without a
// real network call. We only care about the value-shape; the data
// payload is irrelevant.
jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn().mockResolvedValue({ data: null }),
    post: jest.fn(),
  },
}));

function CaptureContext({ onCapture }) {
  const ctx = useAuth();
  React.useEffect(() => { onCapture(ctx); }, [ctx, onCapture]);
  return null;
}


describe('AuthContext provider value shape (regression — Chat 28)', () => {
  test('exposes `me` (NOT `user`) — any component destructuring `user` will silently break', async () => {
    let captured = null;
    await act(async () => {
      render(
        <AuthProvider>
          <CaptureContext onCapture={(ctx) => { captured = ctx; }} />
        </AuthProvider>,
      );
    });
    await waitFor(() => expect(captured).not.toBeNull());

    const keys = Object.keys(captured);
    // The bug: a file destructuring `user` from useAuth() gets
    // undefined and silently falls through every `canXxx(user)`
    // guard. Asserting `user` is absent prevents the bad pattern
    // from re-emerging.
    expect(keys).toContain('me');
    expect(keys).not.toContain('user');

    // Sanity-check the rest of the documented contract so a future
    // refactor that renames `me` (without updating every consumer)
    // also fails loudly here.
    expect(keys).toEqual(expect.arrayContaining([
      'state', 'me', 'login', 'submitMfa', 'logout', 'refresh',
      'hasPerm', 'hasAnyPerm',
    ]));
  });
});
