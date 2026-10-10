import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Vitest does not read tsconfig `paths` on its own, so the `@/*` alias used by
 * the app and its API routes (for example `@/lib/api`) failed to resolve and the
 * route tests could not even be loaded. Mirror the tsconfig mapping here.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
