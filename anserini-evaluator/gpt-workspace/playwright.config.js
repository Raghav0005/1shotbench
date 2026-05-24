// @ts-check
const { defineConfig } = require('@playwright/test');

const PORT = process.env.PORT || '3173';

module.exports = defineConfig({
  testDir: './tests',
  timeout: 240000,
  expect: { timeout: 30000 },
  webServer: {
    command: 'node server.js',
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 120000,
    env: {
      PORT,
      ANSERINI_JAR: process.env.ANSERINI_JAR || require('path').join(__dirname, 'anserini-2.1.1-fatjar.jar')
    }
  },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure'
  }
});
