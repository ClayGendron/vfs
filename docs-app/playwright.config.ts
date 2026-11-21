import { defineConfig, devices } from "@playwright/test";

// The browser tests run against the real site, built fresh and served as static files, in Chromium only.
// scripts/docs.sh check sets VFS_DOCS_PORT to a free port, so a server already on 4173 cannot stop the gate.
const port = Number(process.env.VFS_DOCS_PORT ?? 4173);

export default defineConfig({
  testDir: "tests",
  testMatch: "layout.spec.ts",
  reporter: "list",
  webServer: {
    command: `bun --bun vite build && bun --bun vite preview --port ${port} --strictPort`,
    url: `http://localhost:${port}/`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
  use: { baseURL: `http://localhost:${port}` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
