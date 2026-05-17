// frontend/src/lib/__tests__/aiCaptureCapability-costs.test.js — Chat 20 §R5.1 (B38)
import { canViewCaptureCosts } from '@/lib/aiCaptureCapability';

describe('canViewCaptureCosts', () => {
  test('returns false for null / undefined', () => {
    expect(canViewCaptureCosts(null)).toBe(false);
    expect(canViewCaptureCosts(undefined)).toBe(false);
  });

  test('returns true when is_super_admin is true regardless of perms', () => {
    expect(canViewCaptureCosts({ is_super_admin: true })).toBe(true);
    expect(canViewCaptureCosts({ is_super_admin: true, permissions: [] })).toBe(true);
  });

  test('returns true when permissions include ai_capture.view_costs', () => {
    expect(
      canViewCaptureCosts({ permissions: ['ai_capture.view_costs'] })
    ).toBe(true);
  });

  test('returns false when only adjacent (actuals.admin) perm present', () => {
    expect(
      canViewCaptureCosts({ permissions: ['actuals.admin', 'actuals.view'] })
    ).toBe(false);
  });

  test('returns false for empty / missing permissions array', () => {
    expect(canViewCaptureCosts({})).toBe(false);
    expect(canViewCaptureCosts({ permissions: [] })).toBe(false);
  });
});
