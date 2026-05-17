// frontend/src/lib/__tests__/aiCaptureCapability.test.js — Chat 19C §R6.1
import {
  canViewCaptures, canPromote, canDiscard, canRetry,
  isLowConfidence, CONFIDENCE_WARN_THRESHOLD,
} from '@/lib/aiCaptureCapability';

const admin = { permissions: ['actuals.admin'] };
const pm    = { permissions: ['actuals.edit'] };
const sup   = { is_super_admin: true };

describe('aiCaptureCapability', () => {
  test('canViewCaptures: admin yes, PM no, super_admin yes', () => {
    expect(canViewCaptures(admin)).toBe(true);
    expect(canViewCaptures(pm)).toBe(false);
    expect(canViewCaptures(sup)).toBe(true);
    expect(canViewCaptures(null)).toBe(false);
  });

  test('canPromote: only Awaiting_Review + admin', () => {
    expect(canPromote(admin, { status: 'Awaiting_Review' })).toBe(true);
    expect(canPromote(admin, { status: 'Queued' })).toBe(false);
    expect(canPromote(admin, { status: 'Failed' })).toBe(false);
    expect(canPromote(pm,    { status: 'Awaiting_Review' })).toBe(false);
  });

  test('canDiscard: Queued, Extracting, Awaiting_Review for admin', () => {
    ['Queued', 'Extracting', 'Awaiting_Review'].forEach((s) => {
      expect(canDiscard(admin, { status: s })).toBe(true);
    });
    ['Completed', 'Failed', 'Discarded'].forEach((s) => {
      expect(canDiscard(admin, { status: s })).toBe(false);
    });
  });

  test('canRetry: only Failed + admin', () => {
    expect(canRetry(admin, { status: 'Failed' })).toBe(true);
    expect(canRetry(admin, { status: 'Awaiting_Review' })).toBe(false);
    expect(canRetry(pm,    { status: 'Failed' })).toBe(false);
  });

  test('isLowConfidence: < 0.80 = true; >= 0.80 = false; null = false', () => {
    expect(isLowConfidence(0.79)).toBe(true);
    expect(isLowConfidence(0.80)).toBe(false);
    expect(isLowConfidence(0.99)).toBe(false);
    expect(isLowConfidence(null)).toBe(false);
    expect(isLowConfidence(undefined)).toBe(false);
  });

  test('CONFIDENCE_WARN_THRESHOLD constant === 0.80', () => {
    expect(CONFIDENCE_WARN_THRESHOLD).toBe(0.80);
  });
});
