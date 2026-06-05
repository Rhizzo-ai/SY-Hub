// frontend/e2e/helpers/login.ts
//
// Cookies-only login helper. Logs in via the live backend, completes
// the MFA enrolment dance for `test-admin` (super_admin role), and
// persists the resulting storageState to disk.

import { request } from '@playwright/test';
import { authenticator } from 'otplib';

const PREVIEW_URL =
  process.env.REACT_APP_PREVIEW_URL
  || process.env.REACT_APP_BACKEND_URL
  || 'https://sy-hub-ops.preview.emergentagent.com';

const PASSWORD = process.env.TEST_USER_PASSWORD || 'TestUser-Dev-2026!';

const ROLE_EMAILS = {
  pm: 'test-pm@example.test',
  admin: 'test-admin@example.test',
  readonly: 'test-readonly@example.test',
  site: 'test-site@example.test',
} as const;

export type Role = keyof typeof ROLE_EMAILS;

export async function loginAsRole(role: Role, storageStatePath: string) {
  const email = ROLE_EMAILS[role];
  const ctx = await request.newContext({ baseURL: PREVIEW_URL });

  // 1. Initial login.
  const loginResp = await ctx.post('/api/auth/login', {
    data: { email, password: PASSWORD, remember_me: false },
  });
  if (!loginResp.ok()) {
    throw new Error(
      `loginAsRole(${role}): login failed ${loginResp.status()} ${await loginResp.text()}`,
    );
  }
  const loginBody = await loginResp.json();

  // 2. MFA enrolment dance (test-admin only).
  if (loginBody.mfa_enrollment_required) {
    if (role !== 'admin') {
      throw new Error(
        `loginAsRole(${role}): unexpected MFA enrolment required — check seed_test_users.py`,
      );
    }
    const startResp = await ctx.post('/api/auth/mfa/enroll/start');
    if (!startResp.ok()) throw new Error(`mfa/enroll/start failed ${startResp.status()}`);
    const { secret } = await startResp.json();
    const code = authenticator.generate(secret);
    const confirmResp = await ctx.post('/api/auth/mfa/enroll/confirm', {
      data: { secret, code },
    });
    if (!confirmResp.ok()) {
      throw new Error(`mfa/enroll/confirm failed ${confirmResp.status()} ${await confirmResp.text()}`);
    }
  } else if (loginBody.mfa_required) {
    throw new Error(
      `loginAsRole(${role}): mfa_required (already enrolled). Run seed_test_users.py to wipe MFA state.`,
    );
  }

  // 3. Save state.
  await ctx.storageState({ path: storageStatePath });
  await ctx.dispose();
}
