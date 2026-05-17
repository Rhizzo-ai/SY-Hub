// frontend/src/components/ai-capture/__tests__/CaptureActions.test.jsx — Chat 19C §R6.6
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CaptureActions } from '@/components/ai-capture/CaptureActions';
import {
  makeAwaitingReviewJob, makeFailedJob, makeCompletedJob,
} from '@/test/mocks/fixtures';

jest.mock('@/lib/api', () => ({
  api: { get: jest.fn(), post: jest.fn().mockResolvedValue({ data: {} }) },
}));

const admin = { permissions: ['actuals.admin'] };
const readonly = { permissions: ['actuals.view'] };

function wrap(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CaptureActions', () => {
  test('shows Discard for admin on Awaiting_Review job', () => {
    wrap(<CaptureActions job={makeAwaitingReviewJob()} me={admin} />);
    expect(screen.getByTestId('capture-discard-button')).toBeInTheDocument();
    expect(screen.queryByTestId('capture-retry-button')).not.toBeInTheDocument();
  });

  test('shows Retry (only) for admin on Failed job', () => {
    wrap(<CaptureActions job={makeFailedJob()} me={admin} />);
    expect(screen.getByTestId('capture-retry-button')).toBeInTheDocument();
    expect(screen.queryByTestId('capture-discard-button')).not.toBeInTheDocument();
  });

  test('hides all actions on terminal Completed job', () => {
    const { container } = wrap(<CaptureActions job={makeCompletedJob()} me={admin} />);
    expect(container.querySelector('[data-testid="capture-actions"]')).toBeNull();
  });

  test('readonly user sees no actions even on Awaiting_Review', () => {
    const { container } = wrap(<CaptureActions job={makeAwaitingReviewJob()} me={readonly} />);
    expect(container.querySelector('[data-testid="capture-actions"]')).toBeNull();
  });
});
