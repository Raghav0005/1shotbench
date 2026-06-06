import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: 'http://localhost:10000',
  },
  webServer: {
    command: 'node server.js',
    port: 10000,
    reuseExistingServer: true,
  },
});
