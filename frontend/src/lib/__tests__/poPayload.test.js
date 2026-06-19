/**
 * mapLinesToPayload tests — B107 §8.2 (guards the §0.4 regression).
 */
import { mapLinesToPayload, validatePoLines } from '@/lib/poPayload';

describe('mapLinesToPayload (B107 §5.2 / §0.4)', () => {
  test('sends cost_code_id and NEVER budget_line_id', () => {
    const out = mapLinesToPayload([
      { cost_code_id: 'cc-1', description: 'x', quantity: '2', unit_rate: '50', vat_rate: '20' },
    ]);
    expect(out[0].cost_code_id).toBe('cc-1');
    expect(out[0]).not.toHaveProperty('budget_line_id');
    expect(out[0].quantity).toBe(2);
    expect(out[0].unit_rate).toBe(50);
    expect(out[0].vat_rate).toBe(20);
  });

  test('omits empty cost_code_subcategory_id + unentered qty/rate; description null', () => {
    const out = mapLinesToPayload([
      { cost_code_id: 'cc-1', cost_code_subcategory_id: '', description: '', quantity: '', unit_rate: '' },
    ]);
    expect(out[0]).not.toHaveProperty('cost_code_subcategory_id');
    expect(out[0]).not.toHaveProperty('quantity');
    expect(out[0]).not.toHaveProperty('unit_rate');
    expect(out[0].description).toBeNull();
    expect(out[0].vat_rate).toBe(20);
  });

  test('includes cost_code_subcategory_id only when set', () => {
    const out = mapLinesToPayload([
      { cost_code_id: 'cc-1', cost_code_subcategory_id: 'sub-9' },
    ]);
    expect(out[0].cost_code_subcategory_id).toBe('sub-9');
  });

  test('blank quantity is NEVER emitted as 0 (the §10.5 defect)', () => {
    const out = mapLinesToPayload([
      { cost_code_id: 'cc-1', quantity: '', unit_rate: '', vat_rate: '20' },
    ]);
    expect(out[0]).not.toHaveProperty('quantity');
    expect(out[0].quantity).toBeUndefined();
    expect(out[0]).not.toHaveProperty('unit_rate');
  });
});

describe('validatePoLines (B107 §10.5 — blank qty/rate is MISSING, not 0)', () => {
  const base = { cost_code_id: 'cc-1', vat_rate: '20' };

  test('blank quantity is rejected (not coerced to 0)', () => {
    expect(validatePoLines([{ ...base, quantity: '', unit_rate: '100' }]))
      .toMatch(/^Line 1: quantity is required and must be greater than 0\.$/);
  });

  test('zero and negative quantity are rejected', () => {
    expect(validatePoLines([{ ...base, quantity: '0', unit_rate: '100' }])).toMatch(/quantity/);
    expect(validatePoLines([{ ...base, quantity: '-2', unit_rate: '100' }])).toMatch(/quantity/);
  });

  test('blank or negative unit price is rejected', () => {
    expect(validatePoLines([{ ...base, quantity: '1', unit_rate: '' }])).toMatch(/unit price/);
    expect(validatePoLines([{ ...base, quantity: '1', unit_rate: '-5' }])).toMatch(/unit price/);
  });

  test('a complete line passes (qty > 0, rate >= 0; rate 0 allowed)', () => {
    expect(validatePoLines([{ ...base, quantity: '1', unit_rate: '0' }])).toBeNull();
    expect(validatePoLines([{ ...base, quantity: '2', unit_rate: '100' }])).toBeNull();
  });

  test('names the correct offending line (1-based)', () => {
    expect(validatePoLines([
      { ...base, quantity: '1', unit_rate: '100' },
      { ...base, quantity: '', unit_rate: '50' },
    ])).toMatch(/^Line 2: quantity/);
  });
});
