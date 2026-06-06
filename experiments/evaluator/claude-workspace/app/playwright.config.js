import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.PORT || 5174);

export default defineConfig({
  testDir: "./test",
  timeout: 10 * 60 * 1000, // CACM retrieval + eval is fast but allow margin.
  expect: { timeout: 30_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },
  webServer: {
    command: `PORT=${PORT} node server/index.js`,
    url: `http://localhost:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 5 * 60 * 1000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
