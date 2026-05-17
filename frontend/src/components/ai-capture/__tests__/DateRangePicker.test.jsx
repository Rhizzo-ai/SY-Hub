// frontend/src/components/ai-capture/__tests__/DateRangePicker.test.jsx — Chat 20 §R5.4
import { render, screen, fireEvent } from '@testing-library/react';
import { DateRangePicker } from '@/components/ai-capture/DateRangePicker';

describe('DateRangePicker', () => {
  test('renders all four preset buttons', () => {
    render(<DateRangePicker value="30d" onChange={() => {}} />);
    expect(screen.getByTestId('date-range-7d')).toBeInTheDocument();
    expect(screen.getByTestId('date-range-30d')).toBeInTheDocument();
    expect(screen.getByTestId('date-range-90d')).toBeInTheDocument();
    expect(screen.getByTestId('date-range-all')).toBeInTheDocument();
  });

  test('marks active value with aria-checked=true', () => {
    render(<DateRangePicker value="7d" onChange={() => {}} />);
    expect(screen.getByTestId('date-range-7d')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('date-range-30d')).toHaveAttribute('aria-checked', 'false');
  });

  test('fires onChange with new value when a button is clicked', () => {
    const spy = jest.fn();
    render(<DateRangePicker value="30d" onChange={spy} />);
    fireEvent.click(screen.getByTestId('date-range-90d'));
    expect(spy).toHaveBeenCalledWith('90d');
  });
});
