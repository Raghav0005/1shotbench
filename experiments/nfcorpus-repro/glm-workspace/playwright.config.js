import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'browser-test.spec.js',
  timeout: 180_000,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:10000',
    headless: true,
  },
});
