// Journey 4 — Inspection (field agent).
// Logs in as the seeded agent and confirms the agent surface loads for that role
// (session honoured, not bounced to login). Requires a seeded DEV backend.
const { test } = require("@playwright/test");
const { loginAs, expect } = require("./helpers");

test.describe("Inspection (agent)", () => {
  test("agent reaches their work surface", async ({ page, request }) => {
    await loginAs(page, request, "agent");
    await page.goto("/agent");
    await expect(page).not.toHaveURL(/login/);
    expect(await page.locator("h1, h2, h3").count()).toBeGreaterThan(0);
  });
});
