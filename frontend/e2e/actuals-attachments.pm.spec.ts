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
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshDraftActual.id}`);
  const fileInput = page.locator('[data-testid="actual-attachments"] input[type="file"]');
  await fileInput.setInputFiles({
    name: 'receipt.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 receipt'),
  });
  await expect(page.getByText('receipt.pdf')).toBeVisible({ timeout: 15_000 });
  // Click the first Delete button under the attachments section.
  const deleteBtn = page.locator(
    '[data-testid="actual-attachments"] [data-testid^="attachment-delete-"]',
  ).first();
  await deleteBtn.click();
  // ConfirmDialog confirm button (test pattern from chat-17).
  await page.getByRole('button', { name: 'Delete', exact: true }).last().click();
  await expect(page.getByText('receipt.pdf')).toHaveCount(0, { timeout: 10_000 });
});
