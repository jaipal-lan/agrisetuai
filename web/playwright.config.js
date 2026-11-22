// Playwright E2E config for the KissanSetu web app.
//
// Runs the 6 critical-journey specs in web/e2e against a running stack. Point it
// at a stack with:
//   PLAYWRIGHT_BASE_URL  — the web app      (default http://localhost:3000)
//   PLAYWRIGHT_API_BASE  — the API          (default http://localhost:8000/api)
// The backend must run in DEV_MODE with the demo seed (app.seed), so the seeded
// staff accounts (demo password "demo1234") exist for the role journeys.
//
// Locally:  npm run build && npm start   (web)   +   uvicorn app.main:app   (api, seeded)
//           then  npm run e2e
// CI boots both — see .github/workflows/e2e.yml.
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    actionTimeout: 10000,
    navigationTimeout: 20000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
