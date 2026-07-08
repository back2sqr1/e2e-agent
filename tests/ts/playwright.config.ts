import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  // Match the Python harness: record video + trace for every run,
  // screenshot on failure. Artifacts land in test-results/.
  use: {
    video: 'on',
    trace: 'on',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
    viewport: { width: 1280, height: 720 },
  },
  expect: { timeout: 10_000 },
  reporter: [['list'], ['json', { outputFile: 'test-results/report.json' }]],
});
