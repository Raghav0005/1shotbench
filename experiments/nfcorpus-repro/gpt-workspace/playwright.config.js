import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 420000,
  expect: { timeout: 30000 },
  webServer: {
    command: 'npm start',
    url: 'http://127.0.0.1:10000/health',
    reuseExistingServer: !process.env.CI,
    timeout: 360000,
    env: { PORT: '10000', DATA_DIR: './data' }
  },
  use: {
    baseURL: 'http://127.0.0.1:10000',
    trace: 'on-first-retry'
  }
});
