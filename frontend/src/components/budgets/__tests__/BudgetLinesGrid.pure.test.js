/**
 * Pure-fn tests — components/budgets/BudgetLinesGrid.buildReorderedIds
 * (Build Pack §R8.4 TestReorder + H8 fix).
 *
 * Tests the pure handler extracted in §R6.3 — no DOM-level drag,
 * no dnd-kit mocking. Pure JS in/out.
 */
import { buildReorderedIds } from '../../../lib/buildReorderedIds';

const lines = [
  { id: 'a' }, { id: 'b' }, { id: 'c' },
];

describe('buildReorderedIds (H8)', () => {
  test('returns null when over is missing', () => {
    expect(buildReorderedIds(lines, { active: { id: 'a' }, over: null })).toBeNull();
  });

  test('returns null when active === over (no-op drag)', () => {
    expect(
      buildReorderedIds(lines, { active: { id: 'b' }, over: { id: 'b' } }),
    ).toBeNull();
  });

  test('swaps two adjacent ids in array', () => {
    const result = buildReorderedIds(lines, {
      active: { id: 'a' }, over: { id: 'b' },
    });
    expect(result).toEqual(['b', 'a', 'c']);
  });

  test('moves an id over a non-adjacent target', () => {
    const result = buildReorderedIds(lines, {
      active: { id: 'a' }, over: { id: 'c' },
    });
    expect(result).toEqual(['b', 'c', 'a']);
  });

  test('returns null when active id not in list', () => {
    const result = buildReorderedIds(lines, {
      active: { id: 'z' }, over: { id: 'b' },
    });
    expect(result).toBeNull();
  });
});
