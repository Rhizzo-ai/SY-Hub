/**
 * ActualHistory tests (Chat 19B §R6).
 *
 * Verifies: closed by default; opens on toggle and triggers the fetch
 * (enabled: open); sensitive event_payload is gated by includeSensitive.
 */
import { screen, fireEvent } from '@testing-library/react';
import { ActualHistory } from '../ActualHistory';
import { renderWithProviders } from '../../../test/renderWithProviders';

jest.mock('../../../hooks/actuals', () => ({
  useActualChangeLog: jest.fn(),
}));
const { useActualChangeLog } = require('../../../hooks/actuals');

const ACTUAL_ID = '11111111-1111-4111-8111-111111111111';
const EVT_ID    = '99999999-9999-4999-8999-999999999999';

describe('ActualHistory', () => {
  beforeEach(() => jest.clearAllMocks());

  test('collapsed by default; clicking the header opens', () => {
    useActualChangeLog.mockReturnValue({ data: { items: [] }, isLoading: false });
    renderWithProviders(
      <ActualHistory actualId={ACTUAL_ID} includeSensitive={false} />,
    );
    expect(screen.queryByText('No history events yet.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('actual-history-toggle'));
    expect(screen.getByText('No history events yet.')).toBeInTheDocument();
  });

  test('when open, calls hook with enabled=true', () => {
    useActualChangeLog.mockReturnValue({ data: { items: [] }, isLoading: false });
    renderWithProviders(
      <ActualHistory actualId={ACTUAL_ID} includeSensitive={false} />,
    );
    // Closed first call: enabled=false
    expect(useActualChangeLog).toHaveBeenLastCalledWith(
      ACTUAL_ID,
      expect.objectContaining({ enabled: false }),
    );
    fireEvent.click(screen.getByTestId('actual-history-toggle'));
    expect(useActualChangeLog).toHaveBeenLastCalledWith(
      ACTUAL_ID,
      expect.objectContaining({ enabled: true }),
    );
  });

  test('when includeSensitive=false, event_payload is NOT rendered', () => {
    useActualChangeLog.mockReturnValue({
      data: {
        items: [{
          id: EVT_ID,
          actual_id: ACTUAL_ID,
          event_type: 'Posted',
          actor_user_id: null,
          event_payload: { secret: 'hide me' },
          occurred_at: '2026-05-15T10:00:00+00:00',
        }],
      },
      isLoading: false,
    });
    renderWithProviders(
      <ActualHistory actualId={ACTUAL_ID} includeSensitive={false} />,
    );
    fireEvent.click(screen.getByTestId('actual-history-toggle'));
    expect(screen.getByTestId(`history-event-${EVT_ID}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`history-payload-${EVT_ID}`)).not.toBeInTheDocument();
    expect(screen.queryByText(/hide me/)).not.toBeInTheDocument();
  });
});
