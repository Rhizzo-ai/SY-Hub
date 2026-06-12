/**
 * CostCodePicker — field-name regression lock.
 *
 * B88 Pack 2 Gate 2 re-eyeball Defect 1: the picker was reading
 * `c.id`/`c.enabled`/`c.label` from `useCostCodes`, but the backend
 * `ProjectCostCodeRead` payload uses `cost_code_id`/`is_enabled`/`name`
 * — meaning the trigger label rendered empty even for a line with a
 * valid cost code. Selecting also pushed the WRONG id (the
 * project_cost_codes mapping row id, not the FK target).
 *
 * These tests pin the correct field-name reads so any future schema
 * drift fails loudly here.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { CostCodePicker } from '@/components/budgets/CostCodePicker';

jest.mock('@/hooks/costCodes', () => ({
  useCostCodes: jest.fn(),
}));
import { useCostCodes } from '@/hooks/costCodes';

const SAMPLE_ROWS = [
  {
    id: 'mapping-row-1',
    project_id: 'proj-1',
    cost_code_id: 'cc-target-1',
    code: 'SUB-01',
    name: 'Demolition',
    prefix: 'SUB',
    section_id: 'sec-4-00',
    is_enabled: true,
    cost_code_status: 'Active',
  },
  {
    id: 'mapping-row-2',
    project_id: 'proj-1',
    cost_code_id: 'cc-target-2',
    code: 'ACQ-01',
    name: 'Land cost',
    prefix: 'ACQ',
    section_id: 'sec-1',
    is_enabled: true,
    cost_code_status: 'Active',
  },
  {
    id: 'mapping-row-3',
    project_id: 'proj-1',
    cost_code_id: 'cc-target-3-disabled',
    code: 'OLD-01',
    name: 'Retired code',
    prefix: 'OLD',
    section_id: 'sec-9',
    is_enabled: false,
    cost_code_status: 'Retired',
  },
];

beforeEach(() => {
  useCostCodes.mockReset();
  useCostCodes.mockReturnValue({ data: SAMPLE_ROWS, isLoading: false });
});

describe('CostCodePicker — field-name regression', () => {
  test('renders the line\'s current cost code label (matches on cost_code_id, not id)', () => {
    render(
      <CostCodePicker
        projectId="proj-1"
        value="cc-target-1"
        onChange={() => {}}
      />,
    );
    // Trigger surfaces the current code via SelectValue placeholder; the
    // shadcn implementation puts the label inside the trigger.
    const trigger = screen.getByTestId('cost-code-picker-trigger');
    expect(trigger).toHaveTextContent('SUB-01');
    expect(trigger).toHaveTextContent('Demolition');
  });

  test('disabled (is_enabled=false) codes excluded UNLESS they are the current value', () => {
    const { rerender } = render(
      <CostCodePicker
        projectId="proj-1"
        value="cc-target-1"
        onChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId('cost-code-picker-trigger'));
    // Enabled codes present.
    expect(screen.getByTestId('cost-code-option-cc-target-1'))
      .toBeInTheDocument();
    expect(screen.getByTestId('cost-code-option-cc-target-2'))
      .toBeInTheDocument();
    // Disabled code absent.
    expect(screen.queryByTestId('cost-code-option-cc-target-3-disabled'))
      .not.toBeInTheDocument();

    // …unless the line currently holds the disabled code — then keep it
    // visible so the picker doesn't silently lose state.
    rerender(
      <CostCodePicker
        projectId="proj-1"
        value="cc-target-3-disabled"
        onChange={() => {}}
      />,
    );
    // (Trigger label test only — option list visibility re-toggles on click.)
    expect(screen.getByTestId('cost-code-picker-trigger'))
      .toHaveTextContent('OLD-01');
  });

  test('SelectItem value uses cost_code_id (NOT mapping row id)', () => {
    render(
      <CostCodePicker
        projectId="proj-1"
        value=""
        onChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId('cost-code-picker-trigger'));
    // The data-testid is keyed by cost_code_id, not the mapping `id`.
    expect(screen.queryByTestId('cost-code-option-mapping-row-1'))
      .not.toBeInTheDocument();
    expect(screen.getByTestId('cost-code-option-cc-target-1'))
      .toBeInTheDocument();
  });
});
