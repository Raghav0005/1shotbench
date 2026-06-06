// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 15 * 60 * 1000,
  expect: { timeout: 180 * 1000 },
  use: {
    browserName: 'chromium',
    trace: 'retain-on-failure',
  },
  workers: 1,
});
