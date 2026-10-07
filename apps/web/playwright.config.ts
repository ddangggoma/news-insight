import { defineConfig, devices } from "@playwright/test";

// E2E against a seeded throwaway database (news_insight_e2e): API on 8712, web on 8713.
// The seed (apps/api/scripts/e2e_seed.py) resets that database on every run.
const DB = process.env.E2E_DATABASE_URL ?? "postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight_e2e";
const KEY = "e2e-console-key";
const PUBLIC_KEY = "e2e-public-key";
const WEB = "http://127.0.0.1:8713";
// System Chrome by default; E2E_BROWSER_CHANNEL="" uses Playwright's bundled Chromium (containers).
const CHANNEL = process.env.E2E_BROWSER_CHANNEL ?? "chrome";
const browser = CHANNEL ? { channel: CHANNEL } : {};

export const E2E_ENV = { DATABASE_URL: DB, CONSOLE_API_KEY: KEY, PUBLIC_API_KEY: PUBLIC_KEY, PUBLIC_BASE_URL: WEB, SMTP_HOST: "" };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: WEB, trace: "retain-on-failure", locale: "ko-KR", timezoneId: "Asia/Seoul" },
  // Every page needs a login (plan 14): setup logs the seeded accounts in once, and the
  // reader specs start from the saved reader session (e2e/accounts.ts).
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/, use: { ...browser } },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], ...browser, storageState: "e2e/.auth/reader.json" },
      dependencies: ["setup"],
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], ...browser, storageState: "e2e/.auth/reader.json" },
      grep: /@mobile/,
      dependencies: ["setup"],
    },
  ],
  webServer: [
    {
      command: "uv run python scripts/e2e_seed.py && uv run uvicorn news_insight.main:app --host 127.0.0.1 --port 8712",
      cwd: "../api",
      url: "http://127.0.0.1:8712/api/health",
      env: E2E_ENV,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npx next dev --port 8713 --hostname 127.0.0.1",
      url: WEB,
      env: { API_INTERNAL_URL: "http://127.0.0.1:8712", CONSOLE_API_KEY: KEY, PUBLIC_API_KEY: PUBLIC_KEY, NEXT_DIST_DIR: ".next-e2e" },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
