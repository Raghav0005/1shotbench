// Playwright config for the end-to-end test.
//
// The webServer entry starts the app under test on a dedicated port. Because
// the catalog build spawns ~17 JVMs and CACM retrieval downloads a small
// prebuilt index on first run, we give the workflow generous timeouts.
const { defineConfig } = require('@playwright/test');

const PORT = 4318;

module.exports = defineConfig({
  testDir: './tests',
  timeout: 5 * 60 * 1000,
  expect: { timeout: 30 * 1000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    actionTimeout: 30 * 1000,
    navigationTimeout: 60 * 1000,
    headless: true,
  },
  webServer: {
    command: `node server.js`,
    env: { PORT: String(PORT) },
    url: `http://localhost:${PORT}/api/health`,
    timeout: 120 * 1000,
    reuseExistingServer: !process.env.CI,
    stdout: 'pipe',
    stderr: 'pipe',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
