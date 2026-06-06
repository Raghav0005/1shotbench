const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 300_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    actionTimeout: 30_000,
  },
  webServer: {
    command: 'node server.js',
    port: 3000,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
