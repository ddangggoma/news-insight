import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // E2E runs its own dev server beside `next dev` on 8710 (playwright.config.ts)
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  poweredByHeader: false,
};

export default nextConfig;
