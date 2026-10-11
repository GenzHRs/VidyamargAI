import type { NextConfig } from "next";

// Build-time Security Guard: Reject unauthorized auth bypass on public production Vercel builds
const isProdVercelBuild = process.env.VERCEL_ENV === "production";
const isBypassActiveBuild =
  process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true" || process.env.NEXT_PUBLIC_DEV_MODE === "true";
const isAuthorizedTestingBuild =
  process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS_DEPLOYMENT === "authorized_testing";

if (isProdVercelBuild && isBypassActiveBuild && !isAuthorizedTestingBuild) {
  throw new Error(
    "CRITICAL BUILD SECURITY ERROR: NEXT_PUBLIC_DEV_AUTH_BYPASS is active on a public production Vercel deployment without authorization! " +
    "To protect candidate data, set NEXT_PUBLIC_DEV_AUTH_BYPASS=false, or for an authorized test deployment specify NEXT_PUBLIC_DEV_AUTH_BYPASS_DEPLOYMENT=authorized_testing."
  );
}

const nextConfig: NextConfig = {
  /* config options here */
  allowedDevOrigins: ["localhost", "127.0.0.1", "192.168.1.7"],
  env: {
    // Public values are embedded at build time.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "https://vidyamargai-production-2c1f.up.railway.app/api/v1",
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || "wss://vidyamargai-production-2c1f.up.railway.app/ws",
  },
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      {
        // MinIO / local object storage
        protocol: "http",
        hostname: "localhost",
        port: "9000",
        pathname: "/**",
      },
    ],
    minimumCacheTTL: 86400,  // 24h browser cache for optimized images
  },
  async redirects() {
    return [
      ...(isBypassActiveBuild
        ? [
            {
              source: "/",
              destination: "/candidate/dashboard",
              permanent: false,
            },
            {
              source: "/login",
              destination: "/candidate/dashboard",
              permanent: false,
            },
            {
              source: "/signup",
              destination: "/candidate/dashboard",
              permanent: false,
            },
            {
              source: "/candidate",
              destination: "/candidate/dashboard",
              permanent: false,
            },
            {
              source: "/auth/login",
              destination: "/candidate/dashboard",
              permanent: false,
            },
            {
              source: "/auth/signup",
              destination: "/candidate/dashboard",
              permanent: false,
            },
            {
              source: "/auth/register",
              destination: "/candidate/dashboard",
              permanent: false,
            },
          ]
        : [
            {
              source: "/auth/login",
              destination: "/login",
              permanent: false,
            },
            {
              source: "/auth/signup",
              destination: "/signup",
              permanent: false,
            },
            {
              source: "/auth/register",
              destination: "/signup",
              permanent: false,
            },
            {
              source: "/candidate",
              destination: "/candidate/dashboard",
              permanent: false,
            },
          ]),
      {
        source: "/candidate/learning",
        destination: "/candidate/skill-lab",
        permanent: true,
      },
    ];
  },
};

// Enable bundle analyzer if ANALYZE env is true
const bundleAnalyzed = process.env.ANALYZE === "true"
  ? require("@next/bundle-analyzer")({ enabled: true })(nextConfig)
  : nextConfig;

// Sentry Next.js plugin — wraps config to upload source maps and inject SDK auto-wiring
// https://docs.sentry.io/platforms/javascript/guides/nextjs/
let config: NextConfig = bundleAnalyzed;
try {
  const { withSentryConfig } = require("@sentry/nextjs");
  config = withSentryConfig(bundleAnalyzed, {
    // Org and project are picked up from SENTRY_ORG / SENTRY_PROJECT env vars
    silent: true,                // Suppress build-time noise
    disableClientWebpackPlugin: !process.env.SENTRY_DSN, // Skip upload if no DSN
    disableServerWebpackPlugin: !process.env.SENTRY_DSN,
    widenClientFileUpload: true, // Upload additional client files
    transpileClientSDK: true,
    hideSourceMaps: true,        // Do not ship source maps to browser
    dryRun: !process.env.SENTRY_DSN,
  });
} catch {
  // @sentry/nextjs not installed — that's fine, skip wrapping
}

export default config;

