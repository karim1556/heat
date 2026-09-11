import { defineConfig } from "@playwright/test";

// Config for e2e/dashboard.spec.ts. NOT executed as of Prompt 11 (no
// Playwright skill/tool available this session) -- see that spec file's
// header for the fetch-replay verification that ran in its place.
export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  timeout: 30_000,
  fullyParallel: false,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
