import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 10_000
  },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: [
    {
      command:
        "cmd.exe /c ..\\.venv\\Scripts\\physical-agent.exe api --config ..\\physical-agent.yaml --host 127.0.0.1 --port 8766",
      url: "http://127.0.0.1:8766/api/health",
      reuseExistingServer: !isCI,
      timeout: 30_000
    },
    {
      command: "cmd.exe /c npm.cmd run dev -- --port 5173",
      url: "http://127.0.0.1:5173/",
      reuseExistingServer: !isCI,
      timeout: 30_000
    }
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
