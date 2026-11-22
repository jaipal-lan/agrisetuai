// Journey 5 — Delivery (transport partner).
// Logs in as the seeded transport partner and confirms the transport surface
// loads for that role. Requires a seeded DEV backend.
const { test } = require("@playwright/test");
const { loginAs, expect } = require("./helpers");

test.describe("Delivery (transport)", () => {
  test("transport partner reaches their trips surface", async ({ page, request }) => {
    await loginAs(page, request, "transport");
    await page.goto("/transport");
    await expect(page).not.toHaveURL(/login/);
    expect(await page.locator("h1, h2, h3").count()).toBeGreaterThan(0);
  });
});
