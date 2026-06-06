const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 180000, // 3 minutes per test
  expect: {
    timeout: 30000,
  },
  retries: 0,
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
    baseURL: 'http://localhost:3000',
  },
  webServer: null, // We manage the server manually in tests
});
