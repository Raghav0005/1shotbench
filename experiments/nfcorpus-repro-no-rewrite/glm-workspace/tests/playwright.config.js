const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  timeout: 360_000,
  retries: 0,
  use: {
    baseURL: process.env.APP_URL || 'http://localhost:10000',
    headless: true,
    actionTimeout: 60_000,
  },
});
