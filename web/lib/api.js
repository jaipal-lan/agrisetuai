// Thin fetch wrapper. Token lives in localStorage; the server is the source of
// truth for everything (prices, status) — the client only displays what it returns.

const BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api";

// URL to display a listing/evidence image by its object_key. Cloudinary uploads
// are stored as full https URLs (served from their CDN); local keys go through
// the backend's /media/file route.
export function mediaUrl(objectKey) {
  if (!objectKey) return null;
  if (objectKey.startsWith("http")) return objectKey;
  return `${BASE}/media/file/${objectKey}`;
}

// Absolute URL for an API-relative path the server returns (e.g. avatar_url).
export function absUrl(path) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${BASE}${path}`;
}

// Temporary demo produce photos (royalty-free, in web/public/produce/). Shown
// only for seeded "sample/..." listings that have no real photo yet; a real
// seller upload (any non-sample object_key) always wins. Remove this map (and
// the files) once the catalogue has real seller photos.
const DEMO_PRODUCE = [
  "milled-rice", "black-pepper", "coriander-seed", "cumin-seed", "dry-ginger",
  "green-gram", "bengal-gram", "toor-dal", "red-chilli", "groundnut",
  "turmeric", "tamarind", "mustard", "maize", "paddy",
].sort((a, b) => b.length - a.length); // longest first for prefix matching

// Resolve a listing/product image key to a display URL, preferring a real
// upload, then a bundled demo photo, then the neutral SVG placeholder.
export function productImage(objectKey) {
  if (!objectKey) return null;
  if (!objectKey.startsWith("sample/")) return mediaUrl(objectKey); // real upload
  const slug = objectKey.slice("sample/".length).replace(/\.svg$/, "");
  const match = DEMO_PRODUCE.find((d) => slug === d || slug.startsWith(d + "-"));
  return match ? `/produce/${match}.jpg` : mediaUrl(objectKey);
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

// Pull a human message out of an error body. FastAPI 422 returns `detail` as an
// array of {msg,...} — surface the first message (minus Pydantic's "Value error,"
// prefix) so a user sees "Tare cannot exceed gross", not a generic failure.
function errMessage(data, res) {
  const d = data && data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const msg = d[0] && (d[0].msg || d[0].message);
    if (msg) return String(msg).replace(/^Value error,\s*/i, "");
  }
  return res.statusText || "Request failed";
}

// A stale/expired token should return the user to login rather than surfacing a
// raw 401 on every panel. Clears the session and redirects once (no loop).
function handleUnauthorized(res) {
  if (res.status !== 401 || typeof window === "undefined") return;
  const had = getToken();
  logout();
  if (had && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

// fetch with an abort-based timeout so a hung request on a weak field network
// fails fast instead of leaving the UI spinning. Uploads pass a longer budget.
async function fetchT(url, opts = {}, ms = 20000) {
  if (typeof AbortController === "undefined") return fetch(url, opts);
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } catch (e) {
    if (e.name === "AbortError") throw new Error("Request timed out — check your connection.");
    throw e;
  } finally {
    clearTimeout(id);
  }
}

// Upload a single file (image/pdf) as multipart; returns { object_key, ... }.
// Pass { private: true } for KYC / ID docs so the file is stored privately and
// is only reachable through a signed view-link (never the public media route).
export async function uploadMedia(file, { private: isPrivate = false } = {}) {
  const token = getToken();
  const fd = new FormData();
  fd.append("file", file);
  if (isPrivate) fd.append("private", "true");
  // Media (photos, packing videos) can be large on a slow link — allow 2 min.
  const res = await fetchT(`${BASE}/media/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  }, 120000);
  if (!res.ok) {
    handleUnauthorized(res);
    let data = null;
    try { data = await res.json(); } catch {}
    throw new Error(errMessage(data, res));
  }
  return res.json();
}

// POST multipart/form-data (e.g. registration with evidence files). Sends the
// auth token when present but works unauthenticated too (public sign-up).
export async function apiForm(path, formData) {
  const token = getToken();
  const res = await fetchT(`${BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  }, 120000);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    handleUnauthorized(res);
    const err = new Error(errMessage(data, res));
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
  const res = await fetchT(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }, 60000);
  if (!res.ok) { handleUnauthorized(res); throw new Error("Download failed"); }
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
  const res = await fetchT(`${BASE}${path}`, {
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
    handleUnauthorized(res);
    const err = new Error(errMessage(data, res));
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}
