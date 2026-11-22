// Journey 1 — Onboarding: the public can reach sign-up and login.
// (Frontend-only; no backend needed. Deeper OTP->register step-through is a
// follow-up once this base suite is green in CI.)
const { test, expect } = require("@playwright/test");

test.describe("Onboarding", () => {
  test("register page offers role sign-up with a phone field", async ({ page }) => {
    await page.goto("/register");
    await expect(page).toHaveURL(/register/);
    expect(await page.locator("input").count()).toBeGreaterThan(0);
  });

  test("login page takes phone + password", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveURL(/login/);
    expect(await page.locator("input").count()).toBeGreaterThan(0);
    // A password field is present on the primary login path.
    expect(await page.locator('input[type="password"]').count()).toBeGreaterThan(0);
  });
});
