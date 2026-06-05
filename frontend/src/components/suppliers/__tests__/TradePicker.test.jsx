/**
 * <TradePicker/> tests — Chat 41 §R8 (Build Pack 2.7-FE-revision).
 *
 * Mocks the hooks + AuthContext, mirroring the CISTab.test.jsx pattern
 * (jest.mock + jest.requireMock). cmdk's CommandItem renders an option
 * whose onSelect fires on click — we drive the picker the same way.
 */
jest.mock('@/hooks/trades', () => ({
  useTrades: jest.fn(),
  useCreateTrade: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));

import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TradePicker from '@/components/suppliers/TradePicker';

const tradesHooks = jest.requireMock('@/hooks/trades');
const { useAuth } = jest.requireMock('@/context/AuthContext');

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

let createMutate;
beforeEach(() => {
  createMutate = jest.fn();
  tradesHooks.useTrades.mockReset();
  tradesHooks.useCreateTrade.mockReset()
    .mockReturnValue({ mutateAsync: createMutate, isPending: false });
  useAuth.mockReset();
});

// Lightweight controlled host — the picker is controlled by the parent.
function Host({ initial = '', perms = ['trades.view', 'trades.create'] }) {
  setMe(perms);
  const [value, setValue] = useState(initial);
  return (
    <div>
      <TradePicker value={value} onChange={setValue} testid="tp" />
      <div data-testid="tp-current">{value || '(empty)'}</div>
    </div>
  );
}

describe('<TradePicker/>', () => {
  test('renders existing trades from the hook', () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [
        { id: 'T1', name: 'Groundworks' },
        { id: 'T2', name: 'Roofing' },
      ]},
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId('tp-trigger'));
    expect(screen.getByTestId('tp-option-T1')).toHaveTextContent('Groundworks');
    expect(screen.getByTestId('tp-option-T2')).toHaveTextContent('Roofing');
  });

  test('selecting an existing trade calls onChange with that name', () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [{ id: 'T1', name: 'Groundworks' }] },
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId('tp-trigger'));
    fireEvent.click(screen.getByTestId('tp-option-T1'));
    expect(screen.getByTestId('tp-current')).toHaveTextContent('Groundworks');
  });

  test('"— None —" clears the value', () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [{ id: 'T1', name: 'Groundworks' }] },
    });
    render(<Host initial="Roofing" />);
    expect(screen.getByTestId('tp-current')).toHaveTextContent('Roofing');
    fireEvent.click(screen.getByTestId('tp-trigger'));
    fireEvent.click(screen.getByTestId('tp-clear'));
    expect(screen.getByTestId('tp-current')).toHaveTextContent('(empty)');
  });

  test('typing a non-existent name shows the Add affordance', () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [{ id: 'T1', name: 'Groundworks' }] },
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId('tp-trigger'));
    fireEvent.change(screen.getByTestId('tp-input'), {
      target: { value: 'Scaffolding' },
    });
    expect(screen.getByTestId('tp-add')).toHaveTextContent('Add "Scaffolding"');
  });

  test('selecting Add creates the trade and onChange uses the BACKEND canonical name', async () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [{ id: 'T1', name: 'Groundworks' }] },
    });
    // Server returns the canonical casing — picker must use it.
    createMutate.mockResolvedValueOnce({ id: 'T9', name: 'Scaffolding' });
    render(<Host />);
    fireEvent.click(screen.getByTestId('tp-trigger'));
    fireEvent.change(screen.getByTestId('tp-input'), {
      target: { value: 'scaffolding' },
    });
    fireEvent.click(screen.getByTestId('tp-add'));
    await waitFor(() => {
      expect(createMutate).toHaveBeenCalledWith('scaffolding');
    });
    await waitFor(() => {
      expect(screen.getByTestId('tp-current')).toHaveTextContent('Scaffolding');
    });
  });

  test('typing an existing name (different case) hides Add (case-insensitive match)', () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [{ id: 'T1', name: 'Groundworks' }] },
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId('tp-trigger'));
    fireEvent.change(screen.getByTestId('tp-input'), {
      target: { value: 'GROUNDWORKS' },
    });
    expect(screen.queryByTestId('tp-add')).toBeNull();
    // The existing row still renders for selection.
    expect(screen.getByTestId('tp-option-T1')).toHaveTextContent('Groundworks');
  });

  test('Add is hidden when the user lacks trades.create', () => {
    tradesHooks.useTrades.mockReturnValue({
      data: { items: [{ id: 'T1', name: 'Groundworks' }] },
    });
    render(<Host perms={['trades.view']} />);
    fireEvent.click(screen.getByTestId('tp-trigger'));
    fireEvent.change(screen.getByTestId('tp-input'), {
      target: { value: 'Scaffolding' },
    });
    expect(screen.queryByTestId('tp-add')).toBeNull();
  });
});
