import type { NextConfig } from "next";

// Query keys of the triage view (lib/triage-state.ts).
const TRIAGE_QUERY_KEYS = ["status", "type", "trust", "chain", "q", "sort", "closing", "id"];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Triage used to live at "/". Links shared from that era carry the view in
  // the query, so they still open the board instead of the landing page; the
  // query is passed through unchanged.
  async redirects() {
    return TRIAGE_QUERY_KEYS.map((key) => ({
      source: "/",
      has: [{ type: "query" as const, key }],
      destination: "/triage",
      permanent: false,
    }));
  },
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
