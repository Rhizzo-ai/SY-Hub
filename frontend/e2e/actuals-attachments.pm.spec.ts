// frontend/e2e/actuals-attachments.pm.spec.ts — Chat 19B §R7.3
import { test, expect } from './helpers/freshActual';
import { getProjectId } from './helpers/seed';

test('Drag-drop a PDF: upload completes, attachment appears in list', async ({ page, freshDraftActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshDraftActual.id}`);
  await expect(page.getByTestId('actual-attachments')).toBeVisible({ timeout: 15_000 });
  // react-dropzone exposes its hidden <input type="file"> — drive it directly.
  const fileInput = page.locator('[data-testid="actual-attachments"] input[type="file"]');
  await fileInput.setInputFiles({
    name: 'invoice.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 test'),
  });
  await expect(page.getByText('invoice.pdf')).toBeVisible({ timeout: 15_000 });
});

test('Upload >25MB: rejected with error', async ({ page, freshDraftActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshDraftActual.id}`);
  await expect(page.getByTestId('actual-attachments')).toBeVisible({ timeout: 15_000 });
  const huge = Buffer.alloc(26 * 1024 * 1024, 0); // 26 MB
  const fileInput = page.locator('[data-testid="actual-attachments"] input[type="file"]');
  await fileInput.setInputFiles({
    name: 'huge.pdf',
    mimeType: 'application/pdf',
    buffer: huge,
  });
  // The dropzone or the toast surface the rejection — file must NOT appear in the list.
  await expect(page.getByText('huge.pdf')).toHaveCount(0, { timeout: 5_000 });
});

test('Delete attachment: ConfirmDialog → confirm → row removed', async ({ page, freshDraftActual }) => {
  // Chat-19C §R0.6.4: B36 (POST-attachment vs GET-list regression) is no
  // longer reproducible at HEAD per the chat-19c-closing.md walkthrough.
  // Backend regression test test_actuals_attachments.py::
  // test_post_attachment_immediately_visible_in_list locks the read-after-
  // write invariant. Re-enabled here so the full delete flow is back under
  // E2E coverage.
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshDraftActual.id}`);
  const fileInput = page.locator('[data-testid="actual-attachments"] input[type="file"]');
  await fileInput.setInputFiles({
    name: 'receipt.pdf',
    mimeType: 'application/pdf',
    // Use a longer buffer + valid-ish PDF prefix so any backend magic-byte
    // / min-size sniffing accepts it.
    buffer: Buffer.concat([
      Buffer.from('%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'),
      Buffer.alloc(2048, 0x20),
    ]),
  });
  // Wait for the LIST row (not just the dropzone preview) to render — the
  // delete trigger only mounts inside `attachment-row-{id}`.
  await page.locator('[data-testid^="attachment-row-"]').first().waitFor({ timeout: 20_000 });
  // Click the first Delete button (trigger that opens the ConfirmDialog).
  const deleteBtn = page.locator(
    '[data-testid="actual-attachments"] [data-testid^="attachment-delete-"]',
  ).first();
  await deleteBtn.click();
  // ConfirmDialog confirm button (test pattern from chat-17).
  await page.getByRole('button', { name: 'Delete', exact: true }).last().click();
  await expect(page.locator('[data-testid^="attachment-row-"]'))
    .toHaveCount(0, { timeout: 10_000 });
});
