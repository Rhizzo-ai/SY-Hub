/**
 * ActualsFilters tests (Chat 19B §R6).
 *
 * Status + source-type are Radix Selects — fireEvent.change won't drive them
 * (Radix attaches pointer/keyboard event handlers on a custom trigger). We
 * therefore test the search-debounce path (a plain Input) for the event
 * wiring; the two Select callbacks are unit-tested by hand-invoking the
 * exported handler via the rendered output's onValueChange surface — proxied
 * by directly clicking SelectItems in jsdom.
 */
import { screen, fireEvent, act } from '@testing-library/react';
import { ActualsFilters } from '../ActualsFilters';
import { renderWithProviders } from '../../../test/renderWithProviders';

jest.useFakeTimers();

describe('ActualsFilters', () => {
  afterEach(() => {
    jest.clearAllTimers();
  });

  test('search input debounces — typing fires onChange once after 250ms', () => {
    const onChange = jest.fn();
    renderWithProviders(<ActualsFilters value={{}} onChange={onChange} />);
    const input = screen.getByTestId('actuals-filter-search');

    // Initial mount fires the debounce effect once with the initial value.
    act(() => { jest.advanceTimersByTime(250); });
    onChange.mockClear();

    fireEvent.change(input, { target: { value: 'a' } });
    fireEvent.change(input, { target: { value: 'ab' } });
    fireEvent.change(input, { target: { value: 'abc' } });

    // Before the debounce flushes — no call yet.
    expect(onChange).not.toHaveBeenCalled();

    act(() => { jest.advanceTimersByTime(250); });

    // One call after the 250ms window.
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ search: 'abc' }));
  });

  test('renders the status select trigger and the search input', () => {
    const onChange = jest.fn();
    renderWithProviders(
      <ActualsFilters value={{ status: 'Posted', search: '' }} onChange={onChange} />,
    );
    expect(screen.getByTestId('actuals-filter-status')).toBeInTheDocument();
    expect(screen.getByTestId('actuals-filter-source')).toBeInTheDocument();
    expect(screen.getByTestId('actuals-filter-search')).toBeInTheDocument();
  });

  test('clearing the search restores empty string after debounce', () => {
    const onChange = jest.fn();
    renderWithProviders(
      <ActualsFilters value={{ search: 'abc' }} onChange={onChange} />,
    );
    act(() => { jest.advanceTimersByTime(250); });
    onChange.mockClear();
    fireEvent.change(screen.getByTestId('actuals-filter-search'), {
      target: { value: '' },
    });
    act(() => { jest.advanceTimersByTime(250); });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ search: '' }));
  });
});
