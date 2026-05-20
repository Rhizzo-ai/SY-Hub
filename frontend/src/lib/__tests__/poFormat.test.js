/**
 * poFormat tests — Chat 24 §R5.
 */
import { computeNet, computeVat, fmtGBP, fmtNumber } from '@/lib/poFormat';


describe('fmtGBP', () => {
  test('null/undefined → null (so SensitiveValue renders em-dash)', () => {
    expect(fmtGBP(null)).toBeNull();
    expect(fmtGBP(undefined)).toBeNull();
    expect(fmtGBP('')).toBeNull();
  });

  test('number → £-prefixed string with 2dp', () => {
    expect(fmtGBP(1234.5)).toMatch(/£1,234\.50/);
    expect(fmtGBP('1000')).toMatch(/£1,000\.00/);
  });

  test('non-numeric string → null', () => {
    expect(fmtGBP('abc')).toBeNull();
  });
});

describe('fmtNumber', () => {
  test('4dp for quantities', () => {
    expect(fmtNumber(3.1234, 4)).toBe('3.1234');
  });
  test('null → null', () => {
    expect(fmtNumber(null)).toBeNull();
  });
});

describe('computeNet', () => {
  test('qty × rate', () => {
    expect(computeNet(3, 100)).toBe('300.00');
    expect(computeNet('2.5', '40')).toBe('100.00');
  });
  test('empty inputs → empty string (avoid NaN flash)', () => {
    expect(computeNet('', '5')).toBe('');
    expect(computeNet('5', '')).toBe('');
  });
});

describe('computeVat', () => {
  test('net × VAT%', () => {
    expect(computeVat(100, 20)).toBe('20.00');
    expect(computeVat('250', '5')).toBe('12.50');
  });
});
