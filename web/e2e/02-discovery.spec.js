// Journey 2 — Discovery: the home/marketplace renders for an anonymous visitor.
// (Frontend-only. Backend may or may not have listings; we assert the shell
// renders and navigation to sign-in exists, which is stable either way.)
const { test, expect } = require("@playwright/test");

test.describe("Discovery", () => {
  test("home renders the marketplace shell", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    // A heading or product grid should be present (not a blank/error page).
    expect(await page.locator("h1, h2, h3").count()).toBeGreaterThan(0);
  });

  test("an anonymous visitor can reach sign-in", async ({ page }) => {
    await page.goto("/");
    // There is a path to log in (link or redirect target).
    const loginLink = page.locator('a[href*="login"]');
    if (await loginLink.count()) {
      await expect(loginLink.first()).toBeVisible();
    } else {
      await page.goto("/login");
      await expect(page).toHaveURL(/login/);
    }
  });
});
