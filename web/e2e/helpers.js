// Shared E2E helpers: API-based login + session injection.
//
// We authenticate through the API and write the token into localStorage (the same
// keys the app uses: agri_token / agri_user), rather than driving the login UI in
// every spec — that keeps each journey spec focused and stable.
const { expect } = require("@playwright/test");

const API_BASE = process.env.PLAYWRIGHT_API_BASE || "http://localhost:8000/api";
const DEMO_PW = "demo1234";

// Seeded demo accounts (created by app.seed; shared demo password).
const SEEDED = {
  superadmin: "919999999998",
  manager: "919000000001",
  agent: "919000000002",
  transport: "919000000005",
};

async function apiLogin(request, phone, password = DEMO_PW) {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: { phone, password },
  });
  if (!res.ok()) {
    throw new Error(`login failed for ${phone}: ${res.status()} ${await res.text()}`);
  }
  return res.json(); // { token, user }
}

// Log in as a seeded account and land on its dashboard with the session set.
async function loginAs(page, request, role) {
  const phone = SEEDED[role];
  if (!phone) throw new Error(`unknown seeded role: ${role}`);
  const { token, user } = await apiLogin(request, phone);
  // Need a same-origin document before touching localStorage.
  await page.goto("/login");
  await page.evaluate(([t, u]) => {
    localStorage.setItem("agri_token", t);
    localStorage.setItem("agri_user", JSON.stringify(u));
  }, [token, user]);
  return user;
}

module.exports = { API_BASE, DEMO_PW, SEEDED, apiLogin, loginAs, expect };
