// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 420000,
  expect: { timeout: 120000 },
  use: { baseURL: 'http://127.0.0.1:10173' },
  webServer: {
    command: 'PORT=10173 APP_CACHE_DIR=.cache node server.js',
    url: 'http://127.0.0.1:10173/health',
    reuseExistingServer: false,
    timeout: 420000
  }
});
