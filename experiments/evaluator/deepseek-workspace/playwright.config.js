const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: 'e2e.spec.js',
  timeout: 300000, // 5 minutes - evaluable discovery + retrieval can take time
  use: {
    headless: true,
    baseURL: 'http://127.0.0.1:8090',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
