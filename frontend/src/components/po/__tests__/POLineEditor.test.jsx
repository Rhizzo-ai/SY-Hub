/**
 * POLineEditor tests — B107 §8.5 (cost-code-first picker + §7.4 mint hint).
 * `useCostCodes` is mocked so the embedded CostCodePicker renders without a
 * QueryClient.
 */
jest.mock('@/hooks/costCodes', () => ({ useCostCodes: jest.fn() }));

import React from 'react';
import { render, screen } from '@testing-library/react';
import POLineEditor from '@/components/po/POLineEditor';

const { useCostCodes } = jest.requireMock('@/hooks/costCodes');

beforeEach(() => {
  useCostCodes.mockReset().mockReturnValue({ data: [], isLoading: false });
});

const line = (over) => ({
  cost_code_id: '', cost_code_subcategory_id: '', description: '',
  quantity: '', unit_rate: '', vat_rate: '20', ...over,
});

describe('POLineEditor (B107 §5.3 / §7.4)', () => {
  test('renders a cost-code picker per line (not a budget-line dropdown)', () => {
    render(<POLineEditor
      lines={[line()]} onChange={() => {}}
      projectId="p1" existingCostCodeIds={new Set()} floor={1000}
    />);
    expect(screen.getByTestId('po-line-editor-cc-0-trigger')).toBeInTheDocument();
    expect(screen.queryByTestId('po-line-editor-budget-line-0')).toBeNull();
  });

  test('shows the mint hint when the chosen code has NO existing budget line', () => {
    render(<POLineEditor
      lines={[line({ cost_code_id: 'cc-new' })]} onChange={() => {}}
      projectId="p1" existingCostCodeIds={new Set(['cc-existing'])} floor={1000}
    />);
    expect(screen.getByTestId('cost-code-mint-hint-0')).toBeInTheDocument();
  });

  test('no mint hint when the chosen code already has a budget line', () => {
    render(<POLineEditor
      lines={[line({ cost_code_id: 'cc-existing' })]} onChange={() => {}}
      projectId="p1" existingCostCodeIds={new Set(['cc-existing'])} floor={1000}
    />);
    expect(screen.queryByTestId('cost-code-mint-hint-0')).toBeNull();
  });

  test('falls back to the generic hint when budget lines are unavailable', () => {
    render(<POLineEditor
      lines={[line({ cost_code_id: 'cc-new' })]} onChange={() => {}}
      projectId="p1" existingCostCodeIds={null} floor={1000}
    />);
    expect(screen.getByTestId('cost-code-mint-hint-0'))
      .toHaveTextContent('no budget line');
  });
});
