import type { NextConfig } from "next";

// Query keys of the triage view (lib/triage-state.ts).
const TRIAGE_QUERY_KEYS = ["status", "type", "trust", "chain", "q", "sort", "closing", "id"];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle for the Docker image (see Dockerfile).
  // Vercel ignores this setting.
  output: "standalone",
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
};

export default nextConfig;
