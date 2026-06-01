/**
 * <BCRLineEditor/> tests — Build Pack 2.6-FE-fix §R5.
 *
 * Asserts the fixes for the three BCR defects that affected this
 * component:
 *  - Bug 2: negative deltas reach state with the sign preserved,
 *           and Net is computed correctly.
 *  - Bug 3: budget-line picker shows distinguishable labels —
 *           `line_description` when present, else
 *           `Line ${display_order ?? id.slice(0,8)}` (operator
 *           decision, BuildPack §R0.2).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import BCRLineEditor from '../BCRLineEditor';
import { mockLine } from '../../../test/mocks/fixtures';

function lines(overrides = []) {
  return overrides;
}

describe('<BCRLineEditor/> — 2.6-FE-fix', () => {
  test('Bug 2: negative delta string is preserved in state and Net is negative', () => {
    const onChange = jest.fn();
    const { rerender } = render(
      <BCRLineEditor
        value={lines([{ budget_line_id: 'L1', delta: '' }])}
        onChange={onChange}
        changeType="Transfer"
        budgetLines={[mockLine({ id: 'L1', line_description: 'L1' })]}
      />,
    );
    const input = screen.getByTestId('bcr-line-editor-delta-0');
    // Plain text input — typing a leading minus is preserved.
    fireEvent.change(input, { target: { value: '-40000' } });
    expect(onChange).toHaveBeenCalledWith([
      { budget_line_id: 'L1', delta: '-40000' },
    ]);

    // Re-render with the new state and assert Net displays -£40,000.
    rerender(
      <BCRLineEditor
        value={lines([{ budget_line_id: 'L1', delta: '-40000' }])}
        onChange={onChange}
        changeType="Transfer"
        budgetLines={[mockLine({ id: 'L1', line_description: 'L1' })]}
      />,
    );
    expect(screen.getByTestId('bcr-line-editor-net').textContent)
      .toMatch(/-£40,000/);
  });

  test('Bug 2: Transfer with -40000 / +40000 nets to £0 and clears warn', () => {
    const onChange = jest.fn();
    render(
      <BCRLineEditor
        value={lines([
          { budget_line_id: 'L1', delta: '-40000' },
          { budget_line_id: 'L2', delta: '40000' },
        ])}
        onChange={onChange}
        changeType="Transfer"
        budgetLines={[
          mockLine({ id: 'L1', line_description: 'L1' }),
          mockLine({ id: 'L2', line_description: 'L2' }),
        ]}
      />,
    );
    expect(screen.getByTestId('bcr-line-editor-net').textContent)
      .toMatch(/£0\.00/);
    expect(screen.queryByTestId('bcr-line-editor-net-warn')).toBeNull();
  });

  test('Bug 2 edge case: pasted "-1,234" is stripped to "-1234" by onChange', () => {
    const onChange = jest.fn();
    render(
      <BCRLineEditor
        value={lines([{ budget_line_id: 'L1', delta: '' }])}
        onChange={onChange}
        changeType="Transfer"
        budgetLines={[mockLine({ id: 'L1', line_description: 'L1' })]}
      />,
    );
    fireEvent.change(screen.getByTestId('bcr-line-editor-delta-0'), {
      target: { value: '-1,234' },
    });
    expect(onChange).toHaveBeenCalledWith([
      { budget_line_id: 'L1', delta: '-1234' },
    ]);
  });

  test('Bug 2 edge case: lone "-" does not crash and is preserved', () => {
    const onChange = jest.fn();
    render(
      <BCRLineEditor
        value={lines([{ budget_line_id: 'L1', delta: '' }])}
        onChange={onChange}
        changeType="Transfer"
        budgetLines={[mockLine({ id: 'L1', line_description: 'L1' })]}
      />,
    );
    fireEvent.change(screen.getByTestId('bcr-line-editor-delta-0'), {
      target: { value: '-' },
    });
    expect(onChange).toHaveBeenCalledWith([
      { budget_line_id: 'L1', delta: '-' },
    ]);
  });

  test('Bug 3: picker uses line_description when present', () => {
    render(
      <BCRLineEditor
        value={lines([{ budget_line_id: undefined, delta: '' }])}
        onChange={() => {}}
        changeType="Transfer"
        budgetLines={[
          mockLine({ id: 'L1', line_description: 'Substructure',
            display_order: 5 }),
        ]}
      />,
    );
    // Radix Select renders option items into the DOM with role=option.
    // Open the trigger and assert label.
    fireEvent.click(screen.getByTestId('bcr-line-editor-line-0'));
    // The hidden SelectItem text node is still present in DOM —
    // assert via getAllByText to dodge portal/hidden issues.
    expect(screen.getAllByText('Substructure').length).toBeGreaterThan(0);
  });

  test('Bug 3: picker falls back to "Line ${display_order}" when description is null', () => {
    render(
      <BCRLineEditor
        value={lines([{ budget_line_id: undefined, delta: '' }])}
        onChange={() => {}}
        changeType="Transfer"
        budgetLines={[
          mockLine({ id: 'L1', line_description: null, display_order: 3 }),
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId('bcr-line-editor-line-0'));
    expect(screen.getAllByText('Line 3').length).toBeGreaterThan(0);
  });

  test('Bug 3: picker falls back to "Line ${short id}" when description and display_order are absent', () => {
    render(
      <BCRLineEditor
        value={lines([{ budget_line_id: undefined, delta: '' }])}
        onChange={() => {}}
        changeType="Transfer"
        budgetLines={[
          mockLine({
            id: 'abcdef12-3456-7890-abcd-ef1234567890',
            line_description: null,
            display_order: null,
          }),
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId('bcr-line-editor-line-0'));
    expect(screen.getAllByText('Line abcdef12').length).toBeGreaterThan(0);
  });

  test('Bug 3: lines with null descriptions stay distinguishable from one another', () => {
    render(
      <BCRLineEditor
        value={lines([{ budget_line_id: undefined, delta: '' }])}
        onChange={() => {}}
        changeType="Transfer"
        budgetLines={[
          mockLine({ id: 'L1', line_description: null, display_order: 1 }),
          mockLine({ id: 'L2', line_description: null, display_order: 2 }),
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId('bcr-line-editor-line-0'));
    expect(screen.getAllByText('Line 1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Line 2').length).toBeGreaterThan(0);
  });
});
