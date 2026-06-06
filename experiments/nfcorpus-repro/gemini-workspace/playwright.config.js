const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './',
  testMatch: /.*\.spec\.js/,
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:10000',
    headless: true,
  },
  webServer: {
    command: 'node server.js',
    port: 10000,
    reuseExistingServer: !process.env.CI,
  },
});
