import { defineConfig } from '@playwright/test';

// The runner tool (e2e_agent/tools/runner.py) sets E2E_RUN_DIR per run;
// video, trace, and the JSON report land there so the verifier agent can
// audit the execution.
const runDir = process.env.E2E_RUN_DIR ?? 'runs/adhoc';
const actionTimeoutMs = Number(process.env.E2E_ACTION_TIMEOUT_MS ?? 10_000);

export default defineConfig({
  testDir: '.',
  testMatch: 'test_generated.spec.ts',
  outputDir: `${runDir}/artifacts`,
  timeout: Number(process.env.E2E_TEST_TIMEOUT_MS ?? 120_000),
  use: {
    video: 'on',
    trace: 'on',
    screenshot: 'only-on-failure',
    actionTimeout: actionTimeoutMs,
    viewport: { width: 1280, height: 720 },
    headless: process.env.E2E_HEADLESS !== '0',
  },
  expect: { timeout: actionTimeoutMs },
  reporter: [['list'], ['json', { outputFile: `${runDir}/report.json` }]],
});
