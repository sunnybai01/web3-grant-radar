import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      beforeFiles: [],
      afterFiles: [],
      // Fallback only: plain-array rewrites run before dynamic route handlers,
      // so /api/dashboard/opportunities/[eventId] (detail, delete, triage)
      // bypassed its proxy and went straight to this backend without the
      // internal key.
      fallback: [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/api/v1/:path*",
        },
      ],
    };
  },
};

export default nextConfig;
