import { expect, test } from "@playwright/test";

test("dashboard redesign loads and core panels respond", async ({ page, request }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });

  const stateResponse = await request.get("/api/state");
  expect(stateResponse.ok()).toBeTruthy();
  const apiState = (await stateResponse.json()) as { ready: boolean; backend?: string };
  expect(apiState.ready).toBe(true);
  expect(apiState.backend).toBeTruthy();

  await page.goto("/");
  await expect(page.getByTestId("dashboard-shell")).toBeVisible();
  await expect(page.getByTestId("status-bar")).toContainText("Physical Agent");
  await expect(page.getByTestId("status-bar")).toContainText(`backend ${apiState.backend}`);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);

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
  await page.getByPlaceholder("Message the agent").fill("remember that c3.1 e2e smoke is safe");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText(
    "I will remember: c3.1 e2e smoke is safe"
  );

  await page.getByTestId("nav-memory").click();
  await expect(page.getByTestId("upload-panel")).toContainText("Drop text files here");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
