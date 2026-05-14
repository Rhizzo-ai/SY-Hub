// frontend/e2e/global-teardown.ts
//
// Runs once after all tests.
//
// Cleanup strategy: exclusion list (since no per-budget PATCH exists
// to tag the `notes` field consistently). Delete every budget on the
// E2E projects EXCEPT the v1 + v2 baselines. Demo project + empty
// project remain (idempotent re-seed on next run).
//
// Safety: only touches projects with the E2E_* UUID prefix.

import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

export default async function globalTeardown(_config: FullConfig) {
  // eslint-disable-next-line no-console
  console.log('[global-teardown] sweeping per-test budgets...');
  const E2E_PROJECT_ID = '8e2e0000-0000-4000-8000-000000000001';
  const E2E_EMPTY_PROJECT_ID = '8e2e0000-0000-4000-8000-000000000002';
  try {
    const statePath = path.resolve(__dirname, '../playwright/.auth/state.json');
    const state = JSON.parse(fs.readFileSync(statePath, 'utf-8'));
    const baseline = [state.budgets.v1, state.budgets.v2].map((id: string) => `'${id}'`).join(',');
    execSync(
      `PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -c "DELETE FROM budgets WHERE project_id IN ('${E2E_PROJECT_ID}','${E2E_EMPTY_PROJECT_ID}') AND id NOT IN (${baseline})"`,
      { stdio: 'inherit' },
    );
  } catch (err) {
    process.stderr.write(`[global-teardown] cleanup warning: ${String(err)}\n`);
  }
  // eslint-disable-next-line no-console
  console.log('[global-teardown] done.');
}
