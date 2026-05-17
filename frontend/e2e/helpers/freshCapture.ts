// frontend/e2e/helpers/freshCapture.ts — Chat 19C §R7.2
//
// Read-only accessors for the AI capture job IDs persisted by globalSetup.
// Mirrors the seed.ts pattern (state.json single source of truth).
import * as fs from 'fs';
import * as path from 'path';

type CaptureSeed = {
  awaitingReviewJobId: string;
  failedJobId: string;
  queuedJobId: string;
};

let cached: CaptureSeed | null = null;

function loadCaptureSeeds(): CaptureSeed {
  if (cached) return cached;
  const statePath = path.resolve(__dirname, '../../playwright/.auth/state.json');
  if (!fs.existsSync(statePath)) {
    throw new Error('[freshCapture] state.json missing — has globalSetup run?');
  }
  const all = JSON.parse(fs.readFileSync(statePath, 'utf-8'));
  if (!all.capture) {
    throw new Error('[freshCapture] state.json.capture is null — backend or webhook unavailable during globalSetup. AI capture E2Es cannot run.');
  }
  cached = all.capture as CaptureSeed;
  return cached;
}

export function getAwaitingReviewJobId(): string {
  return loadCaptureSeeds().awaitingReviewJobId;
}

export function getFailedJobId(): string {
  return loadCaptureSeeds().failedJobId;
}

export function getQueuedJobId(): string {
  return loadCaptureSeeds().queuedJobId;
}
