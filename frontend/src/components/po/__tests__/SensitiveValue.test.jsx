/**
 * <SensitiveValue/> tests — Chat 24 §R5.
 *
 * Validates the em-dash placeholder behaviour that anchors the
 * sensitive-field gating pattern across the PO surfaces.
 */
import { render, screen } from '@testing-library/react';
import SensitiveValue from '@/components/po/SensitiveValue';


describe('<SensitiveValue/>', () => {
  test('renders the value when not hidden and value present', () => {
    render(<SensitiveValue value={100} format={(v) => `£${v}`} testid="sv" />);
    expect(screen.getByTestId('sv')).toHaveTextContent('£100');
  });

  test('renders em-dash when hidden=true regardless of value', () => {
    render(<SensitiveValue value={100} format={(v) => `£${v}`} hidden testid="sv" />);
    expect(screen.getByTestId('sv')).toHaveTextContent('—');
  });

  test('renders em-dash when value is null', () => {
    render(<SensitiveValue value={null} testid="sv" />);
    expect(screen.getByTestId('sv')).toHaveTextContent('—');
  });

  test('renders em-dash when format returns null', () => {
    render(<SensitiveValue value="abc" format={() => null} testid="sv" />);
    expect(screen.getByTestId('sv')).toHaveTextContent('—');
  });

  test('keeps stable layout via tabular-nums class', () => {
    const { container } = render(<SensitiveValue value={123} testid="sv" />);
    expect(container.querySelector('.tabular-nums')).not.toBeNull();
  });
});
