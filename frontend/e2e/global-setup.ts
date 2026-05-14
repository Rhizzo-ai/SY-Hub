// frontend/e2e/global-setup.ts
//
// Runs once before all tests.
//
//  1. Re-seed test users.
//  2. Re-seed demo project + v1 + v2 lineage + empty project + extra appraisal.
//  3. Log in once per role (pm/admin/readonly/site) → 4 storageState files.
//  4. Persist E2E state (project IDs + budget IDs).

import { FullConfig } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';
import { loginAsRole } from './helpers/login';

export default async function globalSetup(_config: FullConfig) {
  const REPO_ROOT = path.resolve(__dirname, '../..');
  const AUTH_DIR = path.resolve(__dirname, '../playwright/.auth');
  const E2E_STATE = path.resolve(__dirname, '../playwright/.auth/state.json');

  const E2E_PROJECT_ID = '8e2e0000-0000-4000-8000-000000000001';
  const E2E_EMPTY_PROJECT_ID = '8e2e0000-0000-4000-8000-000000000002';

  fs.mkdirSync(AUTH_DIR, { recursive: true });

  // 1. Seed test users (idempotent; wipes MFA per row).
  // eslint-disable-next-line no-console
  console.log('[global-setup] seeding test users...');
  execSync('python /app/backend/scripts/seed_test_users.py', {
    cwd: REPO_ROOT, stdio: 'inherit', env: { ...process.env },
  });

  // 2. Seed demo project + v1 + v2 lineage + empty project + extra appraisal.
  // eslint-disable-next-line no-console
  console.log('[global-setup] seeding demo data with extensions...');
  execSync(
    `bash /app/scripts/seed_demo_budget.sh --with-v2-lineage --empty-project --extra-appraisal`,
    {
      cwd: REPO_ROOT, stdio: 'inherit',
      env: { ...process.env, E2E_PROJECT_ID, E2E_EMPTY_PROJECT_ID },
    },
  );

  // Capture seeded IDs.
  const idsRaw = execSync(
    `PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -tA -F\\| -c "SELECT id, version_number, status, is_current FROM budgets WHERE project_id='${E2E_PROJECT_ID}' ORDER BY version_number"`,
    { encoding: 'utf-8' },
  );
  const rows = idsRaw.trim().split('\n').filter(Boolean).map((line) => {
    const [id, version, status, isCurrent] = line.split('|');
    return { id, version: Number(version), status, isCurrent: isCurrent === 't' };
  });
  const v1 = rows.find((b) => b.version === 1);
  const v2 = rows.find((b) => b.version === 2);
  if (!v1 || !v2) {
    throw new Error(`globalSetup expected v1+v2 budgets; got ${JSON.stringify(rows)}`);
  }

  // 3. Login per role (4 storageStates).
  // eslint-disable-next-line no-console
  console.log('[global-setup] caching auth for pm, admin, readonly, site...');
  await loginAsRole('pm', path.join(AUTH_DIR, 'pm.json'));
  await loginAsRole('admin', path.join(AUTH_DIR, 'admin.json'));
  await loginAsRole('readonly', path.join(AUTH_DIR, 'readonly.json'));
  await loginAsRole('site', path.join(AUTH_DIR, 'site.json'));

  // 4. Persist state.
  fs.writeFileSync(
    E2E_STATE,
    JSON.stringify({
      projectId: E2E_PROJECT_ID,
      emptyProjectId: E2E_EMPTY_PROJECT_ID,
      budgets: { v1: v1.id, v2: v2.id },
      seededAt: new Date().toISOString(),
    }, null, 2),
  );

  // eslint-disable-next-line no-console
  console.log('[global-setup] done.');
}
