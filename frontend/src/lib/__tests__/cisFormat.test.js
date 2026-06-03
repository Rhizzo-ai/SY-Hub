/**
 * cisFormat — label maps + date helpers (Chat 40 §R5 #8).
 */
import {
  labelCisStatus, labelCisSubtype, labelCurrentCisStatus, labelDocType,
  formatDate, CIS_STATUS_LABEL, MATCH_STATUS_LABEL, DOC_TYPE_OPTIONS,
} from '@/lib/cisFormat';

describe('cisFormat — label maps', () => {
  test.each([
    ['gross', 'Gross'],
    ['net_20', 'Net 20%'],
    ['net_30', 'Net 30%'],
    ['not_registered', 'Not registered'],
  ])('labelCisStatus(%s) → %s', (input, expected) => {
    expect(labelCisStatus(input)).toBe(expected);
    expect(CIS_STATUS_LABEL[input]).toBe(expected);
  });

  test.each([null, undefined, ''])('labelCisStatus(%s) → "—"', (v) => {
    expect(labelCisStatus(v)).toBe('—');
  });

  test('labelCisStatus passes unknown values through verbatim (no crash)', () => {
    expect(labelCisStatus('mystery')).toBe('mystery');
  });

  test.each([
    ['Labour_Only', 'Labour only'],
    ['Labour_And_Plant', 'Labour and plant'],
    ['Supply_And_Fix', 'Supply and fix'],
  ])('labelCisSubtype(%s) → %s', (input, expected) => {
    expect(labelCisSubtype(input)).toBe(expected);
  });

  test('labelCisSubtype(null) → "—"', () => {
    expect(labelCisSubtype(null)).toBe('—');
  });

  test('labelCurrentCisStatus collapses null → Unverified', () => {
    expect(labelCurrentCisStatus(null)).toBe('Unverified');
    expect(labelCurrentCisStatus(undefined)).toBe('Unverified');
    expect(labelCurrentCisStatus('Gross')).toBe('Gross');
    expect(labelCurrentCisStatus('Net')).toBe('Net');
    expect(labelCurrentCisStatus('Unmatched')).toBe('Unmatched');
    expect(labelCurrentCisStatus('Unverified')).toBe('Unverified');
  });

  test('MATCH_STATUS_LABEL has exactly the 3 backend values', () => {
    expect(Object.keys(MATCH_STATUS_LABEL).sort())
      .toEqual(['Gross', 'Net', 'Unmatched']);
  });

  test('DOC_TYPE_OPTIONS contains all 7 frozen backend enums in order', () => {
    expect(DOC_TYPE_OPTIONS).toEqual([
      'Public_Liability', 'Employers_Liability', 'Professional_Indemnity',
      'CIS_Certificate', 'Accreditation', 'Insurance_Other', 'Other',
    ]);
  });

  test.each([
    ['Public_Liability', 'Public liability'],
    ['CIS_Certificate', 'CIS certificate'],
    ['Insurance_Other', 'Insurance (other)'],
  ])('labelDocType(%s) → %s', (input, expected) => {
    expect(labelDocType(input)).toBe(expected);
  });
});

describe('cisFormat — formatDate', () => {
  test('formats an ISO date as en-GB short month', () => {
    // 2026-02-15 → "15 Feb 2026"
    expect(formatDate('2026-02-15')).toBe('15 Feb 2026');
  });

  test('returns "—" for null/undefined/empty', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatDate('')).toBe('—');
  });

  test('returns "—" for unparseable input (no crash)', () => {
    expect(formatDate('not-a-date')).toBe('—');
  });
});
