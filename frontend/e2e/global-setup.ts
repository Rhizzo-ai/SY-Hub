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
  // 5. Seed AI capture jobs via Postmark webhook (Chat 19C §R7.2).
  //    Approach (c): seed 3 jobs via the webhook, then psql-UPDATE 2 of
  //    them into Failed / Queued status. Cleanest because:
  //      - no test-only knobs leak into the stub provider
  //      - no reliance on stub timing/success-rate
  //      - one-line SQL is auditable in the seed script
  // eslint-disable-next-line no-console
  console.log('[global-setup] seeding AI capture jobs via Postmark webhook...');
  const POSTMARK_SECRET = process.env.POSTMARK_INBOUND_SECRET || 'test-secret-do-not-use';
  const BACKEND_BASE = process.env.E2E_BACKEND_URL || 'http://127.0.0.1:8001';

  async function seedCapture(suffix: string): Promise<string> {
    const body = {
      MessageID: `e2e-cap-${suffix}-${Date.now()}`,
      From: 'supplier@example.com',
      To: 'bills@syhomes.co.uk',
      Subject: `E2E test invoice ${suffix}`,
      Date: new Date().toUTCString(),
      TextBody: 'stub',
      Attachments: [{
        Name: `invoice-${suffix}.pdf`,
        Content: Buffer.from('%PDF-1.4\nstub for E2E capture seed\n%%EOF\n').toString('base64'),
        ContentType: 'application/pdf',
        ContentLength: 32,
      }],
    };
    const res = await fetch(
      `${BACKEND_BASE}/api/v1/inbound/postmark?secret=${POSTMARK_SECRET}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
    if (!res.ok) {
      throw new Error(`Postmark webhook seed failed for ${suffix}: ${res.status} ${await res.text()}`);
    }
    const json: { jobs_enqueued?: string[] } = await res.json();
    if (!json.jobs_enqueued?.length) {
      throw new Error(`Postmark webhook did not enqueue any jobs for ${suffix}`);
    }
    return json.jobs_enqueued[0];
  }

  let captureSeeds: { awaitingReviewJobId: string; failedJobId: string; queuedJobId: string } | null = null;
  try {
    const awaitingReviewJobId = await seedCapture('awaiting');
    const failedJobIdRaw = await seedCapture('failed');
    const queuedJobIdRaw = await seedCapture('queued');

    // psql UPDATE for status overrides (PASS-4 LOCKED approach (c))
    execSync(
      `PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -c "UPDATE ai_capture_jobs SET status='Failed', last_error_message='E2E seed: forced Failed' WHERE id='${failedJobIdRaw}'"`,
    );
    execSync(
      `PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -c "UPDATE ai_capture_jobs SET status='Queued', extracted_data=NULL, confidence_scores=NULL WHERE id='${queuedJobIdRaw}'"`,
    );
    captureSeeds = { awaitingReviewJobId, failedJobId: failedJobIdRaw, queuedJobId: queuedJobIdRaw };
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('[global-setup] AI capture seed skipped:', (e as Error).message);
  }

  // 6. Persist state.
  fs.writeFileSync(
    E2E_STATE,
    JSON.stringify({
      projectId: E2E_PROJECT_ID,
      emptyProjectId: E2E_EMPTY_PROJECT_ID,
      budgets: { v1: v1.id, v2: v2.id },
      capture: captureSeeds,
      seededAt: new Date().toISOString(),
    }, null, 2),
  );

  // eslint-disable-next-line no-console
  console.log('[global-setup] done.');
}
