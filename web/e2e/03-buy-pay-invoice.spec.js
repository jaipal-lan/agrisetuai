// Journey 3 — Buy / pay / invoice (entry).
// A buyer-only surface (invoices) must gate an anonymous visitor to login rather
// than exposing data. The full buy->pay->KS/LAN invoice money flow is covered end
// to end at the API layer by smoke_test.py / volume_test.py; this guards the UI
// entry point. Driving the full purchase through the UI is a follow-up.
const { test, expect } = require("@playwright/test");

test.describe("Buy / invoice", () => {
  test("invoices page is gated for anonymous users", async ({ page }) => {
    await page.goto("/invoices");
    // Either redirected to login, or an in-page gate prompts sign-in.
    await page.waitForLoadState("networkidle").catch(() => {});
    const onLogin = /login/.test(page.url());
    const hasLoginLink = (await page.locator('a[href*="login"]').count()) > 0;
    const hasPassword = (await page.locator('input[type="password"]').count()) > 0;
    expect(onLogin || hasLoginLink || hasPassword).toBeTruthy();
  });
});
