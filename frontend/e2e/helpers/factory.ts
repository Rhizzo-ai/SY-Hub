// frontend/e2e/helpers/factory.ts
//
// API-first budget factory. Creates a fresh Draft budget per test by
// re-seeding an `--extra-appraisal`, then calling
// POST /api/v1/projects/{projectId}/budgets/from-appraisal.
//
// Why re-seed each time: the from-appraisal endpoint consumes an
// un-linked Approved appraisal and marks it linked. Re-running the
// `--extra-appraisal` flag uniquely-names a new appraisal so multiple
// fixture uses don't exhaust the pool.

import { APIRequestContext } from '@playwright/test';
import { execSync } from 'child_process';
import { activateBudget, lockBudget } from './api';

const SEED_SH = '/app/scripts/seed_demo_budget.sh';
const PG_CMD_BASE = `PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -tA`;

export interface FreshBudget {
  id: string;
  version_number: number;
  status: string;
}

/**
 * Re-seed an un-linked Approved appraisal, then POST from-appraisal
 * via the supplied API context. Returns the created budget summary.
 */
export async function createFreshBudget(
  ctx: APIRequestContext,
  projectId: string,
): Promise<FreshBudget> {
  // Re-seed --extra-appraisal so we always have a usable un-linked one.
  execSync(`bash ${SEED_SH} --extra-appraisal`, {
    env: { ...process.env, E2E_PROJECT_ID: projectId },
    stdio: 'pipe',
  });

  // Pick the most recently-created un-linked Approved appraisal on this project.
  const sql = `SELECT a.id FROM appraisals a WHERE a.project_id='${projectId}' AND a.status='Approved' AND NOT EXISTS (SELECT 1 FROM budgets b WHERE b.source_appraisal_id=a.id) ORDER BY a.created_at DESC LIMIT 1`;
  const out = execSync(`${PG_CMD_BASE} -c "${sql}"`, { encoding: 'utf-8' }).trim();
  if (!out) {
    throw new Error('createFreshBudget: no un-linked appraisal found after re-seed');
  }
  const appraisalId = out.split('\n')[0].trim();

  const resp = await ctx.post(`/api/v1/projects/${projectId}/budgets/from-appraisal`, {
    data: { appraisal_id: appraisalId },
  });
  if (!resp.ok()) {
    throw new Error(`from-appraisal failed ${resp.status()}: ${await resp.text()}`);
  }
  const body = await resp.json();
  return { id: body.id, version_number: body.version_number, status: body.status };
}

/** Create a fresh Draft, then advance to Active. */
export async function createActiveBudget(
  ctx: APIRequestContext,
  projectId: string,
): Promise<FreshBudget> {
  const b = await createFreshBudget(ctx, projectId);
  await activateBudget(ctx, b.id);
  return { ...b, status: 'Active' };
}

/** Create a fresh Draft, advance Draft → Active → Locked. */
export async function createLockedBudget(
  ctx: APIRequestContext,
  projectId: string,
): Promise<FreshBudget> {
  const b = await createActiveBudget(ctx, projectId);
  await lockBudget(ctx, b.id);
  return { ...b, status: 'Locked' };
}
