// frontend/playwright.config.ts
//
// Playwright config for SY-Hub Budgets E2E (Prompt 2.4B-ii).
//
// Decisions baked in:
//  - Single worker (D1) — shared per-suite project, parallel workers race.
//  - Headless by default.
//  - retries: 0 locally — flakiness is a bug.
//  - trace: retain-on-failure; screenshot: only-on-failure; video: off.
//  - storageState per role via 4 named projects + an anon project.
//  - baseURL via REACT_APP_PREVIEW_URL env.

import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

const PREVIEW_URL =
  process.env.REACT_APP_PREVIEW_URL
  || process.env.REACT_APP_BACKEND_URL
  || 'https://sdlt-audit-fix.preview.emergentagent.com';

const AUTH_DIR = path.resolve(__dirname, 'playwright/.auth');

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],
  globalSetup: require.resolve('./e2e/global-setup'),
  globalTeardown: require.resolve('./e2e/global-teardown'),
  outputDir: 'test-results/',
  use: {
    baseURL: PREVIEW_URL,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    headless: true,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: false,
  },
  projects: [
    {
      name: 'chromium-pm',
      use: { ...devices['Desktop Chrome'], storageState: path.join(AUTH_DIR, 'pm.json') },
      testMatch: /(.+)\.(pm|shared)\.spec\.ts/,
    },
    {
      name: 'chromium-admin',
      use: { ...devices['Desktop Chrome'], storageState: path.join(AUTH_DIR, 'admin.json') },
      testMatch: /(.+)\.(admin|shared)\.spec\.ts/,
    },
    {
      name: 'chromium-readonly',
      use: { ...devices['Desktop Chrome'], storageState: path.join(AUTH_DIR, 'readonly.json') },
      testMatch: /(.+)\.readonly\.spec\.ts/,
    },
    {
      name: 'chromium-site',
      use: { ...devices['Desktop Chrome'], storageState: path.join(AUTH_DIR, 'site.json') },
      testMatch: /(.+)\.site\.spec\.ts/,
    },
    {
      name: 'chromium-anon',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /(.+)\.anon\.spec\.ts/,
    },
  ],
});
