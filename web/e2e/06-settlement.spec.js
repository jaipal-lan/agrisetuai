// Journey 6 — Settlement / finance (superadmin).
// Logs in as the seeded superadmin and confirms the admin console loads with its
// finance/pricing sections. The ledger-balanced settlement itself is asserted at
// the API layer (smoke + volume); this guards the console UI entry.
const { test } = require("@playwright/test");
const { loginAs, expect } = require("./helpers");

test.describe("Settlement / admin (superadmin)", () => {
  test("superadmin reaches the admin console", async ({ page, request }) => {
    await loginAs(page, request, "superadmin");
    await page.goto("/admin");
    await expect(page).not.toHaveURL(/login/);
    // The console has multiple sections (pricing, service areas, KYC, …).
    expect(await page.locator("h1, h2").count()).toBeGreaterThan(1);
  });
});
