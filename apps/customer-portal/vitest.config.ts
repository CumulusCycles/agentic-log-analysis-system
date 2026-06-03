import { defineConfig } from "vitest/config";

// Backend Vitest runs in Node. Frontend has its own vitest config under
// frontend/. Playwright owns e2e/ in the frontend tree.
export default defineConfig({
  test: {
    environment: "node",
    globals: false,
    include: ["tests/**/*.test.ts"],
    exclude: ["node_modules", "dist", "frontend"],
  },
});
