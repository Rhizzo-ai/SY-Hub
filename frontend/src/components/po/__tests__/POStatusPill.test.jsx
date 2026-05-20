/**
 * <POStatusPill/> tests — Chat 24 §R5.
 */
import { render, screen } from '@testing-library/react';
import POStatusPill from '@/components/po/POStatusPill';


describe('<POStatusPill/>', () => {
  test('renders draft label and grey brand class', () => {
    const { container } = render(<POStatusPill status="draft" />);
    expect(screen.getByText(/draft/i)).toBeInTheDocument();
    expect(container.querySelector('.bg-sy-grey-100')).not.toBeNull();
  });

  test('renders partially_receipted as orange brand class', () => {
    const { container } = render(<POStatusPill status="partially_receipted" />);
    expect(screen.getByText(/partially receipted/i)).toBeInTheDocument();
    expect(container.querySelector('.bg-sy-orange-100')).not.toBeNull();
  });

  test('renders receipted as teal brand class', () => {
    const { container } = render(<POStatusPill status="receipted" />);
    expect(container.querySelector('.bg-sy-teal-100')).not.toBeNull();
  });

  test('renders voided as red', () => {
    const { container } = render(<POStatusPill status="voided" />);
    expect(container.querySelector('.bg-red-100')).not.toBeNull();
  });

  test('renders unknown status without crashing (grey fallback)', () => {
    const { container } = render(<POStatusPill status="weird_status" />);
    expect(screen.getByText('weird_status')).toBeInTheDocument();
    expect(container.querySelector('.bg-sy-grey-100')).not.toBeNull();
  });
});
