import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": import.meta.dirname } },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"],
  },
});
