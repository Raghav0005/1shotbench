const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 600000, // 10 minutes for evaluation runs
  retries: 0,
  use: {
    baseURL: 'http://localhost:3456',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'node src/server.js',
    port: 3456,
    timeout: 30000,
    reuseExistingServer: !process.env.CI,
  },
});
