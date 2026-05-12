/**
 * SensitiveBanner tests — visibility depends on `budgets.view_sensitive`.
 */
import { render, screen } from '@testing-library/react';
import { SensitiveBanner } from '../SensitiveBanner';
import { mockMe } from '../../../test/mocks/fixtures';

jest.mock('../../../context/AuthContext', () => ({
  useAuth: jest.fn(),
}));

const { useAuth } = require('../../../context/AuthContext');

describe('SensitiveBanner', () => {
  test('renders when user lacks budgets.view_sensitive', () => {
    useAuth.mockReturnValue({ me: mockMe(['budgets.view']) });
    render(<SensitiveBanner />);
    expect(screen.getByTestId('sensitive-banner')).toBeInTheDocument();
  });

  test('hides when user has budgets.view_sensitive', () => {
    useAuth.mockReturnValue({
      me: mockMe(['budgets.view', 'budgets.view_sensitive']),
    });
    render(<SensitiveBanner />);
    expect(screen.queryByTestId('sensitive-banner')).not.toBeInTheDocument();
  });
});
