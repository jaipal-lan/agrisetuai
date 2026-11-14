// Thin fetch wrapper. Token lives in localStorage; the server is the source of
// truth for everything (prices, status) — the client only displays what it returns.

const BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api";

// URL to display a listing/evidence image by its object_key.
export function mediaUrl(objectKey) {
  if (!objectKey) return null;
  return `${BASE}/media/file/${objectKey}`;
}

// Absolute URL for an API-relative path the server returns (e.g. avatar_url).
export function absUrl(path) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${BASE}${path}`;
}

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

// Upload a single file (image/pdf) as multipart; returns { object_key, ... }.
export async function uploadMedia(file) {
  const token = getToken();
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/media/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(typeof detail === "string" ? detail : "Upload failed");
  }
  return res.json();
}

// POST multipart/form-data (e.g. registration with evidence files). Sends the
// auth token when present but works unauthenticated too (public sign-up).
export async function apiForm(path, formData) {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = (data && data.detail) || res.statusText;
    const err = new Error(typeof detail === "string" ? detail : "Request failed");
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// Fetch an authenticated endpoint and save the response as a file download
// (works for any content type: CSV, PDF, …).
export async function downloadFile(path, filename) {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// Back-compat alias.
export const downloadCsv = downloadFile;

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
