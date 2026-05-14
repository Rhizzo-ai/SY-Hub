// frontend/e2e/helpers/seed.ts
//
// Read-only accessors for the IDs persisted by globalSetup.

import * as fs from 'fs';
import * as path from 'path';

type State = {
  projectId: string;
  emptyProjectId: string;
  budgets: { v1: string; v2: string };
  seededAt: string;
};

let cached: State | null = null;

function loadState(): State {
  if (cached) return cached;
  const statePath = path.resolve(__dirname, '../../playwright/.auth/state.json');
  if (!fs.existsSync(statePath)) {
    throw new Error(`[seed.ts] state.json not found — has globalSetup run?`);
  }
  cached = JSON.parse(fs.readFileSync(statePath, 'utf-8'));
  return cached!;
}

export function getProjectId(): string { return loadState().projectId; }
export function getEmptyProjectId(): string { return loadState().emptyProjectId; }
export function getBudgetIds(): { v1: string; v2: string } { return loadState().budgets; }
