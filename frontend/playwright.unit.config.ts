import { defineConfig } from "@playwright/test";

/**
 * Node-only contract tests (no `page` fixture, no browser, no backend).
 *
 * These live in a separate config so they can run without the API and dev
 * servers that `playwright.config.ts` boots for the real Chromium suite.
 */
export default defineConfig({
  testDir: "./unit",
  timeout: 10_000,
  reporter: [["list"]]
});
