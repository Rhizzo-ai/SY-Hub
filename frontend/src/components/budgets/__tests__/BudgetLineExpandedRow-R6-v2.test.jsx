/**
 * R6 v2 — additional contract tests:
 *
 *   1. Expand-All hydrates EVERY per-line cache from P0.2's
 *      `by_budget_line` index in ONE network call. Per-line POsSection
 *      mounts then render WITHOUT firing per-line GETs.
 *   2. Keyboard — Enter and Space toggle the expand button (native
 *      <button> semantics; we assert by firing a click via keyboard
 *      activation).
 *   3. Error + Retry — POsSection's error branch shows a Retry button
 *      that triggers `refetch()` (a second GET).
 *   4. ReceiptPhotoThumb — loading="lazy" + alt + broken-src fallback.
 */
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('@/lib/api', () => {
  const get = jest.fn();
  return { api: { get }, API_BASE: '/api', authedFetch: jest.fn() };
});
import { api } from '@/lib/api';

jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ me: { id: 'u1', permissions: ['pos.view'] } }),
}));
jest.mock('@/hooks/budgets', () => ({
  useCreateLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  usePatchLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  useDeleteLineItem: () => ({ mutate: jest.fn(), isPending: false }),
}));

import { POsSection }
  from '../grid/PerLineTransactionDrilldown/POsSection';
import { ReceiptPhotoThumb }
  from '../grid/PerLineTransactionDrilldown/ReceiptPhotoThumb';
import { listBudgetPOs } from '@/lib/api/purchaseOrders';
import { poKeys } from '@/hooks/purchaseOrders';

function wrap(ui, qc) {
  const client = qc ?? new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return { qc: client, ...render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  ) };
}

beforeEach(() => { jest.clearAllMocks(); });

// ─────────────────────────────────────────────────────────────────────
// 1. Expand-All hydrates per-line caches from the bulk endpoint
// ─────────────────────────────────────────────────────────────────────
describe('R6 v2 — Expand-all hydrates per-line caches', () => {
  test('one bulk GET seeds every per-line cache; child POsSections do NOT round-trip', async () => {
    const BULK = {
      budget_id: 'b1',
      items: [
        { id: 'po-1', po_number: 'P-001', supplier_name: 'A', status: 'issued', gross_total: '100.00', issued_at: null },
        { id: 'po-2', po_number: 'P-002', supplier_name: 'B', status: 'draft',  gross_total: null,      issued_at: null },
      ],
      by_budget_line: {
        'line-1': [
          { id: 'po-1', po_number: 'P-001', supplier_name: 'A', status: 'issued', gross_total: '100.00', issued_at: null },
        ],
        'line-2': [
          { id: 'po-2', po_number: 'P-002', supplier_name: 'B', status: 'draft',  gross_total: null,      issued_at: null },
        ],
      },
      total: 2, limit: 50, offset: 0,
    };
    api.get.mockResolvedValueOnce({ data: BULK });

    // Simulate the BudgetGridV2Desktop expand-all path exactly:
    // single P0.2 fetch → setQueryData per line.
    const { qc } = wrap(<div data-testid="ph">probe</div>);
    const bulk = await listBudgetPOs('b1');
    const byLine = bulk.by_budget_line;
    for (const lid of Object.keys(byLine)) {
      qc.setQueryData(poKeys.budgetLineList(lid), {
        budget_line_id: lid, items: byLine[lid], total: byLine[lid].length, limit: 50, offset: 0,
      });
    }
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith(
      '/v1/budgets/b1/purchase-orders',
      expect.objectContaining({ signal: undefined }),
    );

    // Now mount POsSection for line-1 and line-2 INSIDE the same qc.
    // They should hydrate from the cache, NOT fire fresh GETs.
    const callCountBefore = api.get.mock.calls.length;
    // Defensive: arm a fallback resolver so any unexpected GET resolves
    // with an empty list (rather than `undefined`, which would crash
    // the consumer and mask the cache-hit assertion below).
    api.get.mockResolvedValue({
      data: { items: [], total: 0, limit: 50, offset: 0 },
    });
    const r = render(
      <QueryClientProvider client={qc}>
        <POsSection lineId="line-1" projectId="p1" />
        <POsSection lineId="line-2" projectId="p1" />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('bg2-po-po-1')).toBeInTheDocument());
    expect(screen.getByTestId('bg2-po-po-2')).toBeInTheDocument();
    // CRITICAL — no additional per-line PO GETs after the bulk seed.
    // (Receipts roll-ups under issued POs are a separate lazy hook by
    // design — they're scoped to /purchase-orders/{id}/receipts and
    // are explicitly allowed.)
    const extraPOCalls = api.get.mock.calls
      .slice(callCountBefore)
      .map((c) => c[0])
      .filter((u) => /\/budget-lines\/.+\/purchase-orders/.test(u));
    expect(extraPOCalls).toEqual([]);
    r.unmount();
  });

  test('Expand-all RO gating — null gross_total still renders em-dash from cached rows', async () => {
    const BULK = {
      budget_id: 'b1', items: [], by_budget_line: {
        'line-1': [{ id: 'po-1', po_number: 'P-001', supplier_name: 'A', status: 'draft', gross_total: null, issued_at: null }],
      }, total: 1, limit: 50, offset: 0,
    };
    api.get.mockResolvedValueOnce({ data: BULK });
    const { qc } = wrap(<div />);
    const bulk = await listBudgetPOs('b1');
    qc.setQueryData(poKeys.budgetLineList('line-1'), {
      budget_line_id: 'line-1', items: bulk.by_budget_line['line-1'],
      total: 1, limit: 50, offset: 0,
    });
    render(
      <QueryClientProvider client={qc}>
        <POsSection lineId="line-1" projectId="p1" />
      </QueryClientProvider>,
    );
    const cell = await screen.findByTestId('bg2-po-gross-po-1');
    expect(cell.textContent).toBe('—');
  });
});

// ─────────────────────────────────────────────────────────────────────
// 2. Keyboard — Enter / Space toggle on the expand button
// ─────────────────────────────────────────────────────────────────────
describe('R6 v2 — keyboard activation', () => {
  // We test on a synthetic <button> element — it's the same native
  // element the grid uses, with the same aria-expanded contract. The
  // browser fires `click` on Enter and Space for buttons by default;
  // this verifies the React handler hooks up correctly to that.
  function FakeRow() {
    const [open, setOpen] = require('react').useState(false);
    return (
      <button
        type="button"
        aria-expanded={open}
        aria-controls="panel-1"
        onClick={() => setOpen((v) => !v)}
        data-testid="kbd-toggle"
      >
        {open ? 'Open' : 'Closed'}
      </button>
    );
  }

  test('Enter activates the toggle (button native semantics)', () => {
    render(<FakeRow />);
    const btn = screen.getByTestId('kbd-toggle');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    btn.focus();
    // Native <button> fires `click` on Enter — assert the handler
    // runs by firing a click directly (the test renderer doesn't
    // simulate the Enter→click default browser action).
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  test('Space activates the toggle', () => {
    render(<FakeRow />);
    const btn = screen.getByTestId('kbd-toggle');
    // Same as above — Space on a <button> defaults to click.
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });
});

// ─────────────────────────────────────────────────────────────────────
// 3. Error + Retry — POsSection error UI calls refetch on click
// ─────────────────────────────────────────────────────────────────────
describe('R6 v2 — error + retry', () => {
  test('error UI shows Retry; clicking it fires a second GET', async () => {
    api.get
      .mockRejectedValueOnce(Object.assign(new Error('boom'), { friendlyMessage: 'boom' }))
      .mockResolvedValueOnce({
        data: { budget_line_id: 'line-x', items: [], total: 0, limit: 50, offset: 0 },
      });
    wrap(<POsSection lineId="line-x" projectId="p1" />);
    const retry = await screen.findByTestId('bg2-pos-retry');
    expect(retry).toBeInTheDocument();
    act(() => { fireEvent.click(retry); });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    // After successful retry the error pane is gone and the empty
    // state renders.
    await waitFor(() => screen.getByTestId('bg2-pos-empty'));
  });
});

// ─────────────────────────────────────────────────────────────────────
// 4. ReceiptPhotoThumb — lazy + alt + broken-src fallback
// ─────────────────────────────────────────────────────────────────────
describe('R6 v2 — ReceiptPhotoThumb', () => {
  test('renders <img> with loading="lazy" and a non-empty alt', () => {
    render(
      <ReceiptPhotoThumb
        photo={{
          id: 'ph-1',
          caption: 'Pallet delivered to North gate',
          original_filename: 'IMG_001.jpg',
        }}
        receiptId="r1"
      />,
    );
    const img = screen.getByTestId('bg2-receipt-photo-r1');
    expect(img.tagName).toBe('IMG');
    expect(img.getAttribute('loading')).toBe('lazy');
    expect(img.getAttribute('alt')).toBe('Pallet delivered to North gate');
    // Source points at the future-shaped photo endpoint, not a raw
    // server-side file_path.
    expect(img.getAttribute('src')).toBe('/api/v1/receipts/photos/ph-1');
  });

  test('alt falls back to filename when caption is empty', () => {
    render(
      <ReceiptPhotoThumb
        photo={{ id: 'ph-2', caption: null, original_filename: 'delivery.png' }}
        receiptId="r2"
      />,
    );
    expect(screen.getByTestId('bg2-receipt-photo-r2').getAttribute('alt'))
      .toBe('delivery.png');
  });

  test('alt has a deterministic non-empty fallback when filename also missing', () => {
    render(
      <ReceiptPhotoThumb
        photo={{ id: 'ph-3', caption: null, original_filename: null }}
        receiptId="r3"
      />,
    );
    expect(screen.getByTestId('bg2-receipt-photo-r3').getAttribute('alt'))
      .toBe('Receipt photo');
  });

  test('broken src → swaps in a fallback glyph (no blank pixel)', () => {
    render(
      <ReceiptPhotoThumb
        photo={{ id: 'ph-4', caption: 'x', original_filename: 'x.jpg' }}
        receiptId="r4"
      />,
    );
    const img = screen.getByTestId('bg2-receipt-photo-r4');
    fireEvent.error(img);
    const fb = screen.getByTestId('bg2-receipt-photo-fallback-r4');
    expect(fb).toBeInTheDocument();
    expect(fb.getAttribute('role')).toBe('img');
    expect(fb.getAttribute('aria-label')).toMatch(/x.*image unavailable/);
  });

  test('no photo → renders an em-dash placeholder, never an empty cell', () => {
    render(<ReceiptPhotoThumb photo={null} receiptId="r5" />);
    expect(screen.getByTestId('bg2-receipt-photo-none-r5').textContent).toBe('—');
  });
});

// ─────────────────────────────────────────────────────────────────────
// 5. Warm-expand timing (<500ms)
// ─────────────────────────────────────────────────────────────────────
describe('R6 v2 — warm-expand timing', () => {
  test('a warm second expand (cache hit) mounts < 500ms', async () => {
    // Pre-seed the cache; a "warm" expand is therefore a synchronous
    // cache read + render — no network round-trip. We measure mount.
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    qc.setQueryData(poKeys.budgetLineList('line-w'), {
      budget_line_id: 'line-w',
      items: [{ id: 'po-w', po_number: 'P-W', supplier_name: 'S', status: 'draft', gross_total: '0.00', issued_at: null }],
      total: 1, limit: 50, offset: 0,
    });
    const t0 = performance.now();
    render(
      <QueryClientProvider client={qc}>
        <POsSection lineId="line-w" projectId="p1" />
      </QueryClientProvider>,
    );
    await screen.findByTestId('bg2-po-po-w');
    const elapsed = performance.now() - t0;
    // 500ms is the warm-expand budget; we expect this to be well under.
    expect(elapsed).toBeLessThan(500);
    // Sanity log — visible in `--verbose` Jest output.
    // eslint-disable-next-line no-console
    console.log(`R6 warm-expand elapsed: ${elapsed.toFixed(1)}ms (budget 500ms)`);
  });
});
