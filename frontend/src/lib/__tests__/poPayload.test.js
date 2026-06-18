/**
 * mapLinesToPayload tests — B107 §8.2 (guards the §0.4 regression).
 */
import { mapLinesToPayload } from '@/lib/poPayload';

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
});
