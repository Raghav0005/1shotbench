const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60000,
  use: {
    browserName: 'chromium',
    headless: true,
  },
  webServer: {
    command: 'node server.js',
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
});
