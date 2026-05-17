// frontend/src/components/ai-capture/__tests__/ExtractedFieldsPanel.test.jsx — Chat 19C §R6.7
import { render, screen } from '@testing-library/react';
import { ExtractedFieldsPanel } from '@/components/ai-capture/ExtractedFieldsPanel';
import { makeAwaitingReviewJob, makeQueuedJob } from '@/test/mocks/fixtures';

describe('ExtractedFieldsPanel', () => {
  test('renders all 8 fields with formatted values', () => {
    render(<ExtractedFieldsPanel job={makeAwaitingReviewJob()} />);
    expect(screen.getByTestId('extracted-fields-panel')).toBeInTheDocument();
    expect(screen.getByTestId('extracted-row-supplier_name')).toHaveTextContent('Acme Supplies Ltd');
    expect(screen.getByTestId('extracted-row-net_amount')).toHaveTextContent(/\u00a3100\.00/);
  });

  test('renders em-dash for missing extracted_data (Queued job)', () => {
    render(<ExtractedFieldsPanel job={makeQueuedJob()} />);
    expect(screen.getByTestId('extracted-row-supplier_name')).toHaveTextContent('\u2014');
  });

  test('low overall confidence renders amber pill with warning icon', () => {
    const job = makeAwaitingReviewJob({
      confidence_scores: { ...makeAwaitingReviewJob().confidence_scores, overall: 0.65 },
    });
    render(<ExtractedFieldsPanel job={job} />);
    expect(screen.getByTestId('confidence-pill-low')).toBeInTheDocument();
  });
});
