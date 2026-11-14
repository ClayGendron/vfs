import { defineConfig, devices } from "@playwright/test";

// The browser tests run against the real site, built fresh and served as static files, in Chromium only.
export default defineConfig({
  testDir: "tests",
  testMatch: "layout.spec.ts",
  reporter: "list",
  webServer: {
    command: "bun --bun vite build && bun --bun vite preview --port 4173 --strictPort",
    url: "http://localhost:4173/",
    reuseExistingServer: false,
    timeout: 180_000,
  },
  use: { baseURL: "http://localhost:4173" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
