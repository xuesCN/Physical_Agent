import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { promises as fs } from "node:fs";
import path from "node:path";

function collectConsoleErrors(page: Page) {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });
  return consoleErrors;
}

async function expectHealthyShell(page: Page) {
  await expect(page.getByTestId("dashboard-shell")).toBeVisible();
  await expect(page.getByTestId("status-bar")).toContainText("Physical Agent");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
}

function expectNoConsoleErrors(consoleErrors: string[]) {
  expect(consoleErrors).toEqual([]);
}

test("desktop dashboard smoke still loads and core panels respond", async ({ page, request }) => {
  const consoleErrors = collectConsoleErrors(page);

  const stateResponse = await request.get("/api/state");
  expect(stateResponse.ok()).toBeTruthy();
  const apiState = (await stateResponse.json()) as { ready: boolean; backend?: string };
  expect(apiState.ready).toBe(true);
  expect(apiState.backend).toBeTruthy();

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("status-bar")).toContainText(`backend ${apiState.backend}`);

  const views = [
    { key: "overview", label: "Overview", panel: "chat-panel" },
    { key: "actions", label: "Actions", panel: "action-board" },
    { key: "memory", label: "Memory", panel: "upload-panel" },
    { key: "events", label: "Events", panel: "events-panel" },
    { key: "settings", label: "Settings", panel: "settings-panel" }
  ];

  for (const view of views) {
    await page.getByTestId(`nav-${view.key}`).click();
    await expect(page.getByTestId(`page-${view.key}`)).toBeVisible();
    await expect(page.getByTestId(view.panel)).toBeVisible();
    await expect(page.getByTestId("status-bar")).toContainText(view.label);
    await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  }

  await page.getByTestId("nav-overview").click();
  await page.getByPlaceholder("Message the agent").fill("remember that c3.2 e2e smoke is safe");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText(
    "I will remember: c3.2 e2e smoke is safe"
  );

  await page.getByTestId("nav-memory").click();
  await expect(page.getByTestId("upload-panel")).toContainText("Drop text files here");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("mobile smoke opens proposal drawer and navigates secondary panels", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("open-proposal-drawer")).toBeVisible();
  await page.getByTestId("open-proposal-drawer").click();
  await expect(page.getByRole("dialog", { name: "Task / Action Proposal" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Task / Action Proposal" })).toBeHidden();

  for (const key of ["memory", "events", "settings"]) {
    await page.getByTestId(`nav-${key}`).click();
    await expect(page.getByTestId(`page-${key}`)).toBeVisible();
    await expect(page.getByTestId("status-bar")).toContainText(
      key.charAt(0).toUpperCase() + key.slice(1)
    );
    await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  }

  expectNoConsoleErrors(consoleErrors);
});

test("browser upload of a markdown file succeeds and updates memory state", async ({
  page,
  request
}, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  const unique = `c3.2-upload-${Date.now()}`;
  const uploadPath = testInfo.outputPath(`${unique}.md`);
  await fs.mkdir(path.dirname(uploadPath), { recursive: true });
  await fs.writeFile(
    uploadPath,
    `# C3.2 Upload\n\nThis real browser upload contains ${unique}.`,
    "utf-8"
  );

  await page.goto("/");
  await page.getByTestId("nav-memory").click();
  await expect(page.getByTestId("upload-panel")).toBeVisible();
  await page
    .getByTestId("upload-panel")
    .locator('input[type="file"]')
    .setInputFiles(uploadPath);

  await expect(page.getByTestId("upload-feedback")).toContainText("uploaded");
  await expect(page.getByTestId("upload-feedback")).toContainText("untrusted proposal context");

  const searchResponse = await request.post("/api/search-memory", {
    data: { query: unique, limit: 5, source_type: "upload" }
  });
  expect(searchResponse.ok()).toBeTruthy();
  const search = (await searchResponse.json()) as {
    results: Array<{ content?: string; trust_level?: string }>;
  };
  expect(search.results.some((item) => item.content?.includes(unique))).toBeTruthy();
  expect(search.results.some((item) => item.trust_level === "untrusted")).toBeTruthy();
  expectNoConsoleErrors(consoleErrors);
});

test("unsupported upload type shows a visible panel error", async ({ page }, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  const pdfPath = testInfo.outputPath("unsupported.pdf");
  await fs.mkdir(path.dirname(pdfPath), { recursive: true });
  await fs.writeFile(pdfPath, "%PDF-1.7\nunsupported", "utf-8");

  await page.goto("/");
  await page.getByTestId("nav-memory").click();
  await page
    .getByTestId("upload-panel")
    .locator('input[type="file"]')
    .setInputFiles(pdfPath);

  await expect(page.getByTestId("upload-feedback")).toContainText("Unsupported upload type");
  await expect(page.getByTestId("upload-feedback")).toContainText(".md");
  expectNoConsoleErrors(consoleErrors);
});

test("oversized upload shows a visible panel error", async ({ page }, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  const oversizedPath = testInfo.outputPath("oversized.md");
  await fs.mkdir(path.dirname(oversizedPath), { recursive: true });
  await fs.writeFile(oversizedPath, "a".repeat(5 * 1024 * 1024 + 1), "utf-8");

  await page.goto("/");
  await page.getByTestId("nav-memory").click();
  await page
    .getByTestId("upload-panel")
    .locator('input[type="file"]')
    .setInputFiles(oversizedPath);

  await expect(page.getByTestId("upload-feedback")).toContainText("exceeds the 5MB limit");
  expectNoConsoleErrors(consoleErrors);
});

test("proposal params validation stays visible in the form", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await expect(page.getByTestId("proposal-panel")).toBeVisible();
  await page.getByTestId("proposal-robot-select").click();
  await page
    .locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content")
    .filter({ hasText: /^arm_1 \(arm\)$/ })
    .click();
  await page.getByTestId("proposal-capability-select").click();
  await page
    .locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content")
    .filter({ hasText: /^observe$/ })
    .click();
  await page.getByTestId("proposal-params-input").fill("{not json");
  await page.getByTestId("propose-action-button").click();

  await expect(page.getByText("Params JSON is invalid")).toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

async function mockReadyApiWithRobot(page: Page) {
  const snapshot = {
    ok: true,
    ready: true,
    message: "Ready.",
    backend: "sqlite",
    config_path: "C:/tmp/physical-agent.yaml",
    workspace_path: "C:/tmp/physical-agent-workspace",
    capabilities: {
      robots: {
        arm_1: {
          kind: "arm",
          driver: "mock_arm",
          status: "connected",
          capabilities: [{ name: "observe", description: "Inspect the workspace." }]
        }
      }
    },
    world: { summary: "Mock world", state: {}, environment: {} },
    actions: { pending: [], completed: [], cancelled: [] },
    feedback: {},
    safety: {},
    chat: { messages: [] },
    plan: {},
    memory: { notes: [] },
    uploads: { uploads: [] },
    chunks: { chunks: [] }
  };

  await mockApiSnapshot(page, snapshot);
}

test("config missing state renders a clear nonblank dashboard", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockNotReadyApi(page, "Config file is missing.", {
    config_exists: false,
    workspace_exists: false
  });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("workspace-notice")).toContainText("Workspace is not ready");
  await expect(page.getByTestId("workspace-notice")).toContainText("Config file is missing.");
  await expect(page.getByTestId("sse-status")).toContainText("SSE disconnected");
  await expect(page.getByTestId("action-board")).toBeVisible();
  expectNoConsoleErrors(consoleErrors);
});

test("workspace not initialized state renders a clear nonblank dashboard", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockNotReadyApi(page, "Workspace is not initialized.", {
    config_exists: true,
    workspace_exists: false,
    backend: "sqlite",
    workspace_path: "C:/tmp/physical-agent-empty-workspace"
  });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("workspace-notice")).toContainText("Workspace is not ready");
  await expect(page.getByTestId("workspace-notice")).toContainText(
    "Workspace is not initialized."
  );
  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("settings-panel")).toContainText("not ready");
  expectNoConsoleErrors(consoleErrors);
});

async function mockNotReadyApi(
  page: Page,
  message: string,
  extras: Record<string, unknown>
) {
  const snapshot = {
    ok: false,
    ready: false,
    message,
    config_path: "C:/tmp/missing-physical-agent.yaml",
    ...extras
  };

  await mockApiSnapshot(page, snapshot);
}

async function mockApiSnapshot(page: Page, snapshot: Record<string, unknown>) {
  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot)
    });
  });
  await page.route("**/api/state", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot)
    });
  });
  await page.route("**/api/events", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        sseEvent(1, "hello", { version: "0.1.0", watch_enabled: false }),
        sseEvent(2, "state", { reason: "connect", state: snapshot })
      ].join("")
    });
  });
}

function sseEvent(id: number, type: string, payload: Record<string, unknown>) {
  return `event: ${type}\ndata: ${JSON.stringify({
    id,
    type,
    ts: "2026-07-01T00:00:00Z",
    payload
  })}\n\n`;
}
