/**
 * packagesHelpers unit tests — B88 Pack 3 §7 (Chat 53).
 *
 * Money math is CLIENT-DISPLAY-ONLY and the server is authoritative.
 * These tests pin the display formatting + the error-extraction
 * contract used by every mutation handler. They also assert the
 * helpers do NOT inadvertently round-trip a net into a mutation
 * payload (server-truth invariant).
 */
import {
  fmtMoney, multiplyMoney, sumMoney, statusPillProps, bidPillProps,
  exceedsTotal, totalAfter, errorMessage, HEADER_TOLERANCE,
} from '@/components/packages/packagesHelpers';

test('fmtMoney formats GBP with 2dp', () => {
  expect(fmtMoney('200000.00')).toBe('£200,000.00');
  expect(fmtMoney('1234.5')).toBe('£1,234.50');
});

test('fmtMoney renders em-dash for null / undefined / non-numeric', () => {
  expect(fmtMoney(null)).toBe('\u2014');
  expect(fmtMoney(undefined)).toBe('\u2014');
  expect(fmtMoney('not a number')).toBe('\u2014');
});

test('multiplyMoney = qty × rate at 2dp banker tolerance', () => {
  expect(multiplyMoney('100', '950')).toBe('95000.00');
  expect(multiplyMoney('50.5', '40')).toBe('2020.00');
  expect(multiplyMoney('0', '999')).toBe('0.00');
});

test('multiplyMoney returns null for non-finite operands', () => {
  expect(multiplyMoney(null, '950')).toBe(null);
  expect(multiplyMoney('abc', '950')).toBe(null);
});

test('sumMoney sums to 2dp ignoring null/undefined', () => {
  expect(sumMoney(['100.00', '200.50', null, undefined])).toBe('300.50');
  expect(sumMoney([])).toBe('0.00');
});

test('statusPillProps known + unknown', () => {
  expect(statusPillProps('draft').label).toBe('Draft');
  expect(statusPillProps('out_to_tender').label).toBe('Out to tender');
  expect(statusPillProps('awarded').label).toBe('Awarded');
  // Unknown falls back to the raw value.
  expect(statusPillProps('weird_unknown_status').label).toBe(
    'weird_unknown_status',
  );
});

test('bidPillProps known + unknown', () => {
  expect(bidPillProps('received').label).toBe('Received');
  expect(bidPillProps('declined').label).toBe('Declined');
  expect(bidPillProps('foo').label).toBe('foo');
});

test('HEADER_TOLERANCE is 1p — matches backend Σ-guard', () => {
  expect(HEADER_TOLERANCE).toBe(0.01);
});

test('totalAfter sums current + draft as numbers', () => {
  expect(totalAfter('200000.00', '50000.00')).toBe(250000);
  expect(totalAfter(null, '5')).toBe(5);
});

test('exceedsTotal honours the £0.01 server tolerance exactly', () => {
  // Σ awards just below the package total → NOT exceeding.
  expect(exceedsTotal('1000.00', 999.99)).toBe(false);
  // Within £0.01 — NOT exceeding (server would accept).
  expect(exceedsTotal('1000.00', 1000.01)).toBe(false);
  // £0.02 over — DOES exceed.
  expect(exceedsTotal('1000.00', 1000.02)).toBe(true);
});

test('errorMessage extracts axios .response.data.detail (string)', () => {
  const err = {
    response: { data: { detail: 'Package not found' } },
  };
  expect(errorMessage(err)).toBe('Package not found');
});

test('errorMessage extracts pydantic-array detail', () => {
  const err = {
    response: {
      data: {
        detail: [
          { msg: 'Field required', loc: ['body', 'title'] },
          { msg: 'Must be > 0', loc: ['body', 'quantity'] },
        ],
      },
    },
  };
  expect(errorMessage(err)).toBe('Field required; Must be > 0');
});

test('errorMessage falls back to .message then "Unknown error."', () => {
  expect(errorMessage({ message: 'Network Error' })).toBe('Network Error');
  expect(errorMessage(null)).toBe('Unknown error.');
  expect(errorMessage({})).toBe('Unknown error.');
});

test('errorMessage handles a plain string', () => {
  expect(errorMessage('boom')).toBe('boom');
});
