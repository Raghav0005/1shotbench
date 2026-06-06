const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 300000, // 5 minutes - Anserini retrieval can be slow
  expect: {
    timeout: 120000
  },
  use: {
    baseURL: 'http://localhost:3456',
    headless: true,
  },
  webServer: {
    command: 'node server.js',
    port: 3456,
    timeout: 30000,
    reuseExistingServer: false,
  },
});
