/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Don't advertise the framework/version to the browser (fingerprinting).
  poweredByHeader: false,

  // Never ship readable source maps to the browser in production — keeps the
  // app code from being reconstructed in dev tools.
  productionBrowserSourceMaps: false,

  // Browser-level security headers on every response. These close off framing/
  // clickjacking, MIME-sniffing and referrer-leak vectors at the browser.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
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
        ],
      },
    ];
  },
};

module.exports = nextConfig;
