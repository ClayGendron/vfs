import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "./gap", reporter: "line", workers: 4, timeout: 45000, use: { browserName: "chromium" } });
