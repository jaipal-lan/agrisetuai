// Thin fetch wrapper. Token lives in localStorage; the server is the source of
// truth for everything (prices, status) — the client only displays what it returns.

const BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api";

export function getToken() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("agri_token");
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  try {
    if (token) window.localStorage.setItem("agri_token", token);
    if (user) window.localStorage.setItem("agri_user", JSON.stringify(user));
  } catch {}
}

export function getUser() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("agri_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function logout() {
  try {
    window.localStorage.removeItem("agri_token");
    window.localStorage.removeItem("agri_user");
  } catch {}
}

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  const token = getToken();
  const h = { "Content-Type": "application/json", ...headers };
  if (token) h["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: h,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = (data && data.detail) || res.statusText;
    const err = new Error(typeof detail === "string" ? detail : "Request failed");
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}
