const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 120000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    actionTimeout: 15000,
  },
  webServer: {
    command: 'node server.js',
    port: 3000,
    reuseExistingServer: !process.env.CI,
    timeout: 10000,
  },
});
