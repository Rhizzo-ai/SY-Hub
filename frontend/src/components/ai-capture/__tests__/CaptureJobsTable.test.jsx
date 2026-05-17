// frontend/src/components/ai-capture/__tests__/CaptureJobsTable.test.jsx — Chat 19C §R6.4
import { render, screen, fireEvent } from '@testing-library/react';
import { CaptureJobsTable } from '@/components/ai-capture/CaptureJobsTable';
import {
  makeAwaitingReviewJob, makeFailedJob,
} from '@/test/mocks/fixtures';

describe('CaptureJobsTable', () => {
  test('renders rows with supplier guess and fmtGBP-formatted net amount', () => {
    const jobs = [makeAwaitingReviewJob()];
    render(<CaptureJobsTable jobs={jobs} total={1} onRowClick={() => {}} />);
    expect(screen.getByTestId('capture-jobs-table')).toBeInTheDocument();
    expect(screen.getByText('Acme Supplies Ltd')).toBeInTheDocument();
    // fmtGBP("100.00") -> "£100.00"
    expect(screen.getByText(/\u00a3100\.00/)).toBeInTheDocument();
  });

  test('renders empty state when jobs array is empty', () => {
    render(<CaptureJobsTable jobs={[]} total={0} onRowClick={() => {}} />);
    expect(screen.getByTestId('capture-jobs-empty')).toBeInTheDocument();
  });

  test('row click fires onRowClick with the full job object', () => {
    const onRowClick = jest.fn();
    const job = makeFailedJob();
    render(<CaptureJobsTable jobs={[job]} total={1} onRowClick={onRowClick} />);
    fireEvent.click(screen.getByTestId(`capture-row-${job.id}`));
    expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({ id: job.id }));
  });
});
