// The backend origin the client talks to (XHR + media images). Derived from the
// baked API base so the CSP stays in sync with wherever the app is deployed.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api";
let API_ORIGIN = "http://127.0.0.1:8000";
try {
  API_ORIGIN = new URL(API_BASE).origin;
} catch {
  // keep the fallback
}

// Content-Security-Policy, scoped to exactly what the app loads:
//  - self for scripts/styles/pages; 'unsafe-inline' is required because the app
//    uses inline style={{…}} attributes and Next's inline bootstrap (no nonce).
//  - images from self + data:/blob: (agent photos) + the API origin (media).
//  - XHR/fetch to self + the API origin + OpenStreetMap Nominatim (reverse
//    geocoding at sign-up, to turn the device's GPS fix into a street address).
//  - the live courier map is an openstreetmap.org iframe (frame-src).
// No external scripts, fonts or CDNs are used, so everything else is denied.
// When the app is served over HTTPS (staging/prod), force all subresources to
// HTTPS and send HSTS. On plain-HTTP localhost/LAN dev these are omitted so the
// HTTP API keeps working.
const IS_HTTPS = API_ORIGIN.startsWith("https:");

const csp = [
  "default-src 'self'",
  ...(IS_HTTPS ? ["upgrade-insecure-requests"] : []),
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  // cdnjs serves the barcode/QR scanner (html5-qrcode) + QR label generator.
  "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
  // cdnjs also serves the Leaflet stylesheet (map pin picker).
  "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
  // OpenStreetMap raster tiles + Leaflet marker images for the map pin.
  `img-src 'self' data: blob: ${API_ORIGIN} https://*.tile.openstreetmap.org https://cdnjs.cloudflare.com https://res.cloudinary.com`,
  // Uploaded videos (product/packing clips) are served from the Cloudinary CDN.
  "media-src 'self' blob: https://res.cloudinary.com",
  // api.data.gov.in: the superadmin "import from this device" button fetches the
  // mandi feed from the browser (an Indian IP) because the backend's datacenter is
  // geo-blocked (connection refused) by data.gov.in.
  `connect-src 'self' ${API_ORIGIN} https://nominatim.openstreetmap.org https://api.data.gov.in`,
  "frame-src 'self' https://www.openstreetmap.org",
  "font-src 'self' data:",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Don't advertise the framework/version to the browser (fingerprinting).
  poweredByHeader: false,

  // Never ship readable source maps to the browser in production — keeps the
  // app code from being reconstructed in dev tools.
  productionBrowserSourceMaps: false,

  // Browser-level security headers on every response. These close off framing/
  // clickjacking, MIME-sniffing, injection and referrer-leak vectors.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          // Block other sites from framing the app (clickjacking).
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          // Don't let the browser guess content types.
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Don't leak full URLs to third parties.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Only this app may use the camera (agent photos) and location
          // (courier GPS); everything else is denied.
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=(), geolocation=(self), interest-cohort=()",
          },
          // Force HTTPS for a year (incl. subdomains) once served over TLS. Only
          // sent when the deployment is HTTPS, so http localhost dev is untouched.
          ...(IS_HTTPS ? [{ key: "Strict-Transport-Security",
                            value: "max-age=31536000; includeSubDomains" }] : []),
        ],
      },
    ];
  },
};

module.exports = nextConfig;
