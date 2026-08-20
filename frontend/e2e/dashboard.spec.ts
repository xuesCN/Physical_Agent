import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TOUR_STORAGE_KEY = "physical-agent-tour-dismissed";
const LANGUAGE_STORAGE_KEY = "physical-agent-language";
const THEME_STORAGE_KEY = "physical-agent-theme";
const PROPOSAL_PAGES_STORAGE_KEY = "physical-agent-proposal-pages:v1";
const ACTION_BOARD_COLLAPSED_STORAGE_KEY = "physical-agent-action-board-collapsed:v1";

function collectConsoleErrors(page: Page, expected404Urls: string[] = []) {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      const location = message.location();
      const ignored404Urls = ["/api/chat/stream", ...expected404Urls];
      if (
        message.text().includes("404") &&
        ignored404Urls.some((url) => location.url.includes(url))
      ) {
        return;
      }
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });
  return consoleErrors;
}

async function tourTargets(page: Page, testId: string): Promise<boolean> {
  return page.evaluate((id) => {
    const nav = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    const placeholder = document.querySelector<HTMLElement>(".ant-tour-target-placeholder");
    if (!nav || !placeholder) {
      return false;
    }
    const navBox = nav.getBoundingClientRect();
    const targetBox = placeholder.getBoundingClientRect();
    const centerDistance = Math.hypot(
      navBox.left + navBox.width / 2 - (targetBox.left + targetBox.width / 2),
      navBox.top + navBox.height / 2 - (targetBox.top + targetBox.height / 2),
    );
    return centerDistance < 24 && targetBox.width < 100;
  }, testId);
}

async function expectHealthyShell(page: Page) {
  await expect(page.getByTestId("dashboard-shell")).toBeVisible();
  await expect(page.getByTestId("status-bar")).toContainText("Physical Agent");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
}

function expectNoConsoleErrors(consoleErrors: string[]) {
  expect(consoleErrors).toEqual([]);
}

test.beforeEach(async ({ page }, testInfo) => {
  await page.addInitScript(
    ({ languageKey, themeKey, tourKey, showTour }) => {
      localStorage.setItem(languageKey, "en");
      localStorage.setItem(themeKey, "light");
      if (showTour) {
        localStorage.removeItem(tourKey);
      } else {
        localStorage.setItem(tourKey, "1");
      }
    },
    {
      languageKey: LANGUAGE_STORAGE_KEY,
      themeKey: THEME_STORAGE_KEY,
      tourKey: TOUR_STORAGE_KEY,
      showTour: testInfo.title.includes("tour opens on first visit"),
    },
  );
});

test("desktop dashboard smoke still loads and core panels respond", async ({
  page,
  request,
}) => {
  const consoleErrors = collectConsoleErrors(page);

  const stateResponse = await request.get("/api/state");
  expect(stateResponse.ok()).toBeTruthy();
  const apiState = (await stateResponse.json()) as {
    ready: boolean;
    backend?: string;
  };
  expect(apiState.ready).toBe(true);
  expect(apiState.backend).toBeTruthy();
  await installMockChatStream(page, [
    sseEvent(3, "start", { stream_id: "desktop-smoke", request_id: "desktop-smoke" }),
    sseEvent(4, "delta", {
      stream_id: "desktop-smoke",
      request_id: "desktop-smoke",
      delta: "I will remember: c3.2 e2e smoke is safe",
    }),
    sseEvent(5, "done", {
      stream_id: "desktop-smoke",
      request_id: "desktop-smoke",
      reply: "I will remember: c3.2 e2e smoke is safe",
      mode: "rule_based",
    }),
  ]);

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("status-bar")).toContainText(
    `backend ${apiState.backend}`,
  );

  const views = [
    { key: "chat", label: "Chat", panel: "chat-panel" },
    { key: "overview", label: "Overview", panel: "state-overview-panel" },
    { key: "actions", label: "Actions", panel: "action-board" },
    { key: "state", label: "State", panel: "context-tabs" },
    { key: "hardware", label: "Hardware", panel: "hardware-panel" },
    { key: "memory", label: "Memory", panel: "upload-panel" },
    { key: "events", label: "Events", panel: "events-panel" },
    { key: "settings", label: "Settings", panel: "settings-panel" },
  ];

  for (const view of views) {
    await page.getByTestId(`nav-${view.key}`).click();
    await expect(page.getByTestId(`page-${view.key}`)).toBeVisible();
    await expect(page.getByTestId(view.panel)).toBeVisible();
    await expect(page.getByTestId("status-bar")).toContainText(view.label);
    await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  }

  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "Recommended backend",
  );
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "state.db is source of truth",
  );
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "SAFETY.md remains file source",
  );

  await page.getByTestId("nav-chat").click();
  await page
    .getByPlaceholder("Message the agent")
    .fill("remember that c3.2 e2e smoke is safe");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText(
    "I will remember: c3.2 e2e smoke is safe",
  );

  await page.getByTestId("nav-memory").click();
  await expect(page.getByTestId("upload-panel")).toContainText(
    "Drop text files here",
  );
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("mobile smoke opens proposal drawer and navigates secondary panels", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("open-proposal-drawer")).toBeVisible();
  await page.getByTestId("open-proposal-drawer").click();
  await expect(
    page.getByRole("dialog", { name: "Task / Action Proposal" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("dialog", { name: "Task / Action Proposal" }),
  ).toBeHidden();

  await page.getByTestId("nav-actions").click();
  await expect(
    page.getByRole("dialog", { name: "Task / Action Proposal" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("dialog", { name: "Task / Action Proposal" }),
  ).toBeHidden();

  for (const key of ["memory", "events", "settings"]) {
    await page.getByTestId(`nav-${key}`).click();
    await expect(page.getByTestId(`page-${key}`)).toBeVisible();
    await expect(page.getByTestId("status-bar")).toContainText(
      key.charAt(0).toUpperCase() + key.slice(1),
    );
    await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  }

  expectNoConsoleErrors(consoleErrors);
});

test("C6 navigation and page composition retire duplicate page keys without losing content", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page, {
    world: {
      summary: "C6 world is visible",
      state: {
        objects: {
          c6_block: { type: "block", status: "available" },
        },
      },
      environment: {},
    },
    safety: {
      rules: { require_known_robot: true },
    },
  });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect
    .poll(() =>
      page.locator('[data-testid^="nav-"]').evaluateAll((elements) =>
        elements.map((element) => element.getAttribute("data-testid")),
      ),
    )
    .toEqual([
      "nav-chat",
      "nav-overview",
      "nav-actions",
      "nav-state",
      "nav-hardware",
      "nav-memory",
      "nav-events",
      "nav-settings",
    ]);
  await expect(page.getByTestId("nav-world")).toHaveCount(0);
  await expect(page.getByTestId("nav-safety")).toHaveCount(0);
  await expect(page.getByTestId("nav-robots")).toHaveCount(0);

  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("page-chat")).toBeVisible();
  await expect(page.getByTestId("chat-panel")).toBeVisible();
  await expect(page.getByTestId("nav-chat").locator("xpath=ancestor::li")).toHaveClass(
    /ant-menu-item-selected/,
  );

  await page.getByTestId("nav-overview").click();
  await expect(page.getByTestId("state-overview-panel")).toBeVisible();
  await expect(page.getByTestId("robots-panel")).toBeVisible();
  await expect(page.getByTestId("chat-panel")).toHaveCount(0);
  await expect(page.getByTestId("action-board")).toHaveCount(0);
  await expect(page.getByTestId("context-tabs")).toHaveCount(0);

  await page.getByTestId("nav-state").click();
  const stateContext = page.getByTestId("context-tabs");
  await expect(page.getByTestId("page-state")).toBeVisible();
  await expect(stateContext.getByRole("tab")).toHaveCount(4);
  await expect(stateContext.getByRole("tab", { name: /World/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(stateContext).toContainText("c6_block");
  await stateContext.getByRole("tab", { name: /Safety/ }).click();
  await expect(stateContext).toContainText("require_known_robot");
  await expect(page.getByTestId("nav-state").locator("xpath=ancestor::li")).toHaveClass(
    /ant-menu-item-selected/,
  );

  await page.getByTestId("nav-actions").click();
  await expect(page.getByTestId("action-board")).toBeVisible();
  await expect(page.getByTestId("context-tabs").getByRole("tab")).toHaveCount(0);
  await expect(page.getByTestId("context-tabs")).toContainText("No feedback");

  await page.getByTestId("nav-hardware").click();
  await expect(page.getByTestId("robots-panel")).toContainText("arm_1");
  expectNoConsoleErrors(consoleErrors);
});

test("C6.1 page query opens and reloads the requested dashboard page", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);

  await page.goto("/?page=actions");
  await expect(page.getByTestId("page-actions")).toBeVisible();
  await expect(page.getByTestId("nav-actions").locator("xpath=ancestor::li")).toHaveClass(
    /ant-menu-item-selected/,
  );

  await page.reload();
  await expect(page.getByTestId("page-actions")).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.get("page")).toBe("actions");
  expectNoConsoleErrors(consoleErrors);
});

test("C6.1 navigation preserves other query parameters and follows browser history", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);

  await page.goto("/?source=operator");
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("page-chat")).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.get("page")).toBe("chat");
  await expect.poll(() => new URL(page.url()).searchParams.get("source")).toBe("operator");

  await page.getByTestId("nav-state").click();
  await expect(page.getByTestId("page-state")).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.get("page")).toBe("state");

  await page.goBack();
  await expect(page.getByTestId("page-chat")).toBeVisible();
  await expect(page.getByTestId("nav-chat").locator("xpath=ancestor::li")).toHaveClass(
    /ant-menu-item-selected/,
  );

  await page.goForward();
  await expect(page.getByTestId("page-state")).toBeVisible();
  await expect(page.getByTestId("nav-state").locator("xpath=ancestor::li")).toHaveClass(
    /ant-menu-item-selected/,
  );
  expectNoConsoleErrors(consoleErrors);
});

test("C6.1 invalid and retired page keys normalize to overview", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);

  for (const pageKey of ["world", "not-a-dashboard-page"]) {
    await page.goto(`/?page=${pageKey}`);
    await expect(page.getByTestId("page-overview")).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get("page")).toBe("overview");
  }
  expectNoConsoleErrors(consoleErrors);
});

test("C6 proposal panel mounts on demand and remembers each page", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await expect(page.getByTestId("page-overview")).toBeVisible();
  await expect(page.getByTestId("proposal-panel")).toHaveCount(0);
  for (const pageKey of ["chat", "state", "hardware", "memory", "events", "settings"]) {
    await page.getByTestId(`nav-${pageKey}`).click();
    await expect(page.getByTestId("proposal-panel")).toHaveCount(0);
  }
  await page.getByTestId("nav-overview").click();
  const proposalToggle = page.getByTestId("proposal-panel-toggle");
  await expect(proposalToggle).toHaveAccessibleName("Open proposal panel");
  await proposalToggle.click();
  await expect(page.getByTestId("proposal-panel")).toBeVisible();

  await page.getByTestId("nav-actions").click();
  await expect(page.getByTestId("proposal-panel")).toBeVisible();
  await expect(proposalToggle).toHaveAccessibleName("Collapse proposal panel");
  await proposalToggle.click();
  await expect(page.getByTestId("proposal-panel")).toHaveCount(0);

  await page.getByTestId("nav-state").click();
  await expect(page.getByTestId("proposal-panel")).toHaveCount(0);
  await page.getByTestId("nav-overview").click();
  await expect(page.getByTestId("proposal-panel")).toBeVisible();
  await page.getByTestId("nav-actions").click();
  await expect(page.getByTestId("proposal-panel")).toHaveCount(0);

  const stored = await page.evaluate((key) => localStorage.getItem(key), PROPOSAL_PAGES_STORAGE_KEY);
  expect(JSON.parse(stored ?? "{}")).toEqual({ overview: true, actions: false });
  expectNoConsoleErrors(consoleErrors);
});

test("C6 chat fills the desktop workspace and keeps the proposal rail centered", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(
    ({ languageKey }) => localStorage.setItem(languageKey, "zh"),
    { languageKey: LANGUAGE_STORAGE_KEY },
  );
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await page.getByTestId("nav-chat").click();

  const chatPanel = page.getByTestId("chat-panel");
  const proposalToggle = page.getByTestId("proposal-panel-toggle");
  const proposalText = page.getByTestId("proposal-rail-text");
  await expect(chatPanel).toBeVisible();
  await expect(proposalText).toHaveText("提案");

  const layout = await page.evaluate(() => {
    const chat = document.querySelector<HTMLElement>('[data-testid="chat-panel"]');
    const toggle = document.querySelector<HTMLElement>(
      '[data-testid="proposal-panel-toggle"]',
    );
    const text = document.querySelector<HTMLElement>('[data-testid="proposal-rail-text"]');
    if (!chat || !toggle || !text) {
      throw new Error("chat layout targets are missing");
    }
    const chatBox = chat.getBoundingClientRect();
    const toggleBox = toggle.getBoundingClientRect();
    const textBox = text.getBoundingClientRect();
    const textStyle = window.getComputedStyle(text);
    return {
      chatHeight: chatBox.height,
      chatBottomGap: window.innerHeight - chatBox.bottom,
      railCenterDelta: Math.abs(
        toggleBox.left + toggleBox.width / 2 - (textBox.left + textBox.width / 2),
      ),
      railTextWidth: textBox.width,
      railTextHeight: textBox.height,
      railWritingMode: textStyle.writingMode,
      railTextOrientation: textStyle.textOrientation,
      railTextInside:
        textBox.top >= toggleBox.top &&
        textBox.bottom <= toggleBox.bottom &&
        textBox.left >= toggleBox.left &&
        textBox.right <= toggleBox.right,
    };
  });

  expect(layout.chatHeight).toBeGreaterThan(760);
  expect(layout.chatBottomGap).toBeGreaterThanOrEqual(10);
  expect(layout.chatBottomGap).toBeLessThanOrEqual(14);
  expect(layout.railCenterDelta).toBeLessThanOrEqual(1);
  expect(layout).toMatchObject({
    railWritingMode: "vertical-rl",
    railTextOrientation: "upright",
  });
  expect(layout.railTextWidth).toBeGreaterThan(0);
  expect(layout.railTextHeight).toBeGreaterThan(0);
  expect(layout.railTextInside).toBeTruthy();

  await proposalToggle.click();
  await expect(page.getByTestId("proposal-panel")).toBeVisible();
});

test("C6 ActionBoard collapses an empty board to one informative line", async ({ page }) => {
  await mockReadyApiWithRobot(page);
  await page.goto("/");
  await page.getByTestId("nav-actions").click();

  const board = page.getByTestId("action-board");
  await expect(board.getByTestId("action-board-summary")).toContainText("No pending actions");
  await expect(board.getByTestId("action-board-summary").locator(".ant-tag")).toHaveCount(0);
  await expect(board.getByTestId("action-board-toggle")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await expect(board.getByTestId("action-board-body")).toHaveCount(0);
  await board.getByTestId("action-board-toggle").click();
  await expect(board.getByTestId("action-board-body")).toBeVisible();
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), ACTION_BOARD_COLLAPSED_STORAGE_KEY))
    .toBe("false");
  await page.reload();
  await page.getByTestId("nav-actions").click();
  await expect(page.getByTestId("action-board-body")).toBeVisible();
});

test("C6 ActionBoard keeps counts visible when ordinary pending actions are collapsed", async ({
  page,
}) => {
  await mockReadyApiWithRobot(page, {
    actions: {
      pending: [
        {
          id: "act-no-approval",
          robot: "arm_1",
          capability: "observe",
          params: {},
          metadata: { approval: { required: false, status: "not_required" } },
        },
      ],
      in_progress: [],
      completed: [
        {
          id: "act-completed",
          robot: "arm_1",
          capability: "observe",
          params: {},
        },
      ],
      cancelled: [],
    },
  });
  await page.goto("/");
  await page.getByTestId("nav-actions").click();

  const board = page.getByTestId("action-board");
  await expect(board.getByTestId("action-board-summary")).toContainText("Pending 1");
  await expect(board.getByTestId("action-board-summary")).toContainText("Completed 1");
  await expect(board.getByTestId("action-board-toggle")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await expect(board.getByTestId("action-board-body")).toHaveCount(0);
});

test("C6 ActionBoard forces approval-required pending actions open and cannot collapse", async ({
  page,
}) => {
  await page.addInitScript((key) => localStorage.setItem(key, "true"), ACTION_BOARD_COLLAPSED_STORAGE_KEY);
  await mockReadyApiWithRobot(page, {
    actions: {
      pending: [
        {
          id: "act-awaiting-human",
          robot: "arm_1",
          capability: "observe",
          params: {},
          metadata: { approval: { required: true, status: "pending" } },
        },
        {
          id: "act-approved-but-still-pending",
          robot: "arm_1",
          capability: "observe",
          params: {},
          metadata: { approval: { required: true, status: "approved" } },
        },
      ],
      in_progress: [],
      completed: [],
      cancelled: [],
    },
  });
  await page.goto("/");
  await page.getByTestId("nav-actions").click();

  const board = page.getByTestId("action-board");
  await expect(board).toHaveClass(/action-board-approval-required/);
  await expect(board.getByTestId("action-board-summary")).toContainText(
    "2 actions waiting for your approval",
  );
  await expect(board.getByTestId("action-board-toggle")).toHaveCount(0);
  await expect(board.getByTestId("action-board-body")).toBeVisible();
  await expect(board.getByRole("button", { name: "Approve execution" })).toBeVisible();
  await expect(board.getByRole("button", { name: "Reject" }).first()).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("open-proposal-drawer")).toBeDisabled();
  await expect(page.getByRole("dialog", { name: "Task / Action Proposal" })).toHaveCount(0);
  await expect(board.getByTestId("action-board-summary")).toBeVisible();
  await expect(board.getByRole("button", { name: "Approve execution" })).toBeVisible();
  await expect(board.getByRole("button", { name: "Reject" }).first()).toBeVisible();
});

test("browser upload of a markdown file succeeds and updates memory state", async ({
  page,
  request,
}, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  const unique = `c3.2-upload-${Date.now()}`;
  const uploadPath = testInfo.outputPath(`${unique}.md`);
  await fs.mkdir(path.dirname(uploadPath), { recursive: true });
  await fs.writeFile(
    uploadPath,
    `# C3.2 Upload\n\nThis real browser upload contains ${unique}.`,
    "utf-8",
  );

  await page.goto("/");
  await page.getByTestId("nav-memory").click();
  await expect(page.getByTestId("upload-panel")).toBeVisible();
  await page
    .getByTestId("upload-panel")
    .locator('input[type="file"]')
    .setInputFiles(uploadPath);

  await expect(page.getByTestId("upload-feedback")).toContainText("uploaded");
  await expect(page.getByTestId("upload-feedback")).toContainText(
    "untrusted proposal context",
  );

  const searchResponse = await request.post("/api/search-memory", {
    data: { query: unique, limit: 5, source_type: "upload" },
  });
  expect(searchResponse.ok()).toBeTruthy();
  const search = (await searchResponse.json()) as {
    results: Array<{ content?: string; trust_level?: string }>;
  };
  expect(
    search.results.some((item) => item.content?.includes(unique)),
  ).toBeTruthy();
  expect(
    search.results.some((item) => item.trust_level === "untrusted"),
  ).toBeTruthy();
  expectNoConsoleErrors(consoleErrors);
});

test("unsupported upload type shows a visible panel error", async ({
  page,
}, testInfo) => {
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

  await expect(page.getByTestId("upload-feedback")).toContainText(
    "Unsupported upload type",
  );
  await expect(page.getByTestId("upload-feedback")).toContainText(".md");
  expectNoConsoleErrors(consoleErrors);
});

test("oversized upload shows a visible panel error", async ({
  page,
}, testInfo) => {
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

  await expect(page.getByTestId("upload-feedback")).toContainText(
    "exceeds the 5MB limit",
  );
  expectNoConsoleErrors(consoleErrors);
});

test("proposal params validation stays visible in the form", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await page.getByTestId("proposal-panel-toggle").click();
  await expect(page.getByTestId("proposal-panel")).toBeVisible();
  await page.getByTestId("proposal-robot-select").click();
  await page
    .locator(
      ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content",
    )
    .filter({ hasText: /^arm_1 \(arm\)$/ })
    .click();
  await page.getByTestId("proposal-capability-select").click();
  await page
    .locator(
      ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content",
    )
    .filter({ hasText: /^observe$/ })
    .click();
  await page.getByTestId("proposal-params-input").fill("{not json");
  await page.getByTestId("propose-action-button").click();

  await expect(page.getByText("Params JSON is invalid")).toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("F2 readable context shows feedback world and capabilities without raw debug", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page, {
    capabilities: {
      robots: {
        arm_1: {
          kind: "arm",
          driver: "mock_arm",
          status: "connected",
          capabilities: [
            {
              name: "pick",
              description: "Pick up a known object.",
              params_schema: {
                type: "object",
                properties: { object_id: { type: "string" } },
                required: ["object_id"],
              },
              constraints: { object_must_exist: true },
              requires_approval: true,
            },
          ],
        },
      },
    },
    world: {
      summary: "The arm is idle. Visible objects: red_block, tray.",
      state: {
        objects: {
          red_block: {
            type: "block",
            location: "table",
            pose: { x: 0.2, y: 0.1, z: 0.0 },
            status: "available",
            container: "workspace",
            color: "red",
          },
          tray: {
            type: "tray",
            location: "bench",
            pose: { x: 0.5, y: 0.2, z: 0.0 },
          },
        },
        environment: {
          bounds: { x_min: 0, x_max: 1, y_min: 0, y_max: 1 },
        },
        raw: { driver_note: "mock-arm snapshot" },
      },
    },
    actions: {
      pending: [
        {
          id: "act_pick_1",
          robot: "arm_1",
          capability: "pick",
          params: { object_id: "red_block" },
          reason: "Pick the red block.",
          metadata: {
            source: "chat_draft",
            user_message: "pick the red block",
            approval: {
              required: true,
              status: "approved",
              by: "gui",
              at: "2026-07-07T00:00:00Z",
              reason: "Approved from Actions board.",
            },
          },
        },
      ],
      completed: [],
      cancelled: [],
    },
    feedback: {
      latest: {
        action_id: "act_pick_1",
        status: "failed",
        robot: "arm_1",
        capability: "pick",
        message: "SafetyGate rejected the action: object is outside bounds.",
        result: { error_type: "SafetyViolation", error_message: "outside bounds" },
      },
      history: [
        {
          action_id: "act_pick_1",
          status: "failed",
          robot: "arm_1",
          capability: "pick",
          message: "SafetyGate rejected the action: object is outside bounds.",
          result: { error_type: "SafetyViolation", error_message: "outside bounds" },
        },
      ],
    },
    chat: {
      messages: [
        {
          role: "assistant",
          content: "I cannot draft that action.",
          created_at: "2026-07-07T00:01:00Z",
          metadata: {
            refusal_reason: "No listed capability can pour coffee.",
          },
        },
      ],
    },
  });

  await page.goto("/");
  await expectHealthyShell(page);
  await page.getByTestId("nav-actions").click();
  await expect(page.getByTestId("action-board")).toContainText("Params: object_id=red_block");
  await expect(page.getByTestId("action-board").locator(".raw-json-collapse")).toHaveCount(0);
  await expect(page.getByTestId("context-tabs")).toContainText(
    "SafetyGate rejected the action",
  );
  await expect(page.getByTestId("context-tabs")).toContainText(
    "Execution approved",
  );
  await expect(page.getByTestId("context-tabs")).toContainText(
    "No listed capability can pour coffee",
  );
  await expect(page.getByTestId("context-tabs")).toContainText("Raw:");
  await expect(page.getByTestId("context-tabs").locator(".raw-json-collapse")).toHaveCount(0);
  await page.getByRole("button", { name: /action act_pick_1/ }).first().click();
  await expect(page.getByTestId("page-actions")).toBeVisible();

  await page.getByTestId("nav-state").click();
  await expect(page.getByTestId("context-tabs")).toContainText("red_block");
  await expect(page.getByTestId("context-tabs")).toContainText("x=0.2");
  await expect(page.getByTestId("context-tabs")).toContainText("workspace");
  await page.getByRole("tab", { name: /Capabilities/ }).click();
  await expect(page.getByTestId("context-tabs")).toContainText("pick");
  await expect(page.getByTestId("context-tabs")).toContainText("Params: object_id*: string");
  await expect(page.getByTestId("context-tabs")).toContainText("approval required");
  await expect(page.getByTestId("context-tabs").locator(".raw-json-collapse")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("F2.5 state overview uses productized schema components with collapsed raw debug", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page, {
    backend_private_snapshot: { revision: 7 },
    capabilities: {
      robots: {
        arm_1: {
          kind: "arm",
          driver: "mock_arm",
          mode: "simulation",
          status: "connected",
          custom_driver_note: "hidden in raw debug",
          capabilities: [
            {
              name: "pick",
              description: "Pick up a known object.",
              params_schema: {
                type: "object",
                properties: { object_id: { type: "string" } },
                required: ["object_id"],
              },
              requires_approval: true,
            },
            {
              name: "place",
              description: "Place a held object at a named target.",
              params_schema: {
                type: "object",
                properties: { target_id: { type: "string" } },
                required: ["target_id"],
              },
              requires_approval: false,
            },
          ],
        },
      },
    },
    world: {
      summary: "The arm is idle. Visible objects: red_block, tray.",
      state: {
        robots: {
          arm_1: { health: "ok", mode: "simulation" },
        },
        objects: {
          red_block: {
            type: "block",
            location: "table",
            pose: { x: 0.2, y: 0.1, z: 0.0 },
            status: "available",
            color: "red",
          },
          tray: {
            type: "tray",
            location: "bench",
            pose: { x: 0.5, y: 0.2, z: 0.0 },
            status: "ready",
          },
        },
        environment: {
          bounds: { x_min: -1, x_max: 1, y_min: -0.5, y_max: 0.5, z_min: 0, z_max: 1 },
          calibration_note: "hidden in raw debug",
        },
        raw: { driver_note: "mock-arm snapshot" },
      },
    },
  });

  await page.goto("/");
  await expectHealthyShell(page);

  await expect(page.getByTestId("system-status-card")).toContainText("Ready");
  await expect(page.getByTestId("system-status-card")).toContainText("sqlite");
  await expect(page.getByTestId("system-status-card")).toContainText(
    "C:/tmp/physical-agent-workspace",
  );
  await expect(page.getByTestId("robots-table")).toContainText("arm_1");
  await expect(page.getByTestId("robots-table")).toContainText("mock_arm");
  await expect(page.getByTestId("robots-table")).toContainText("simulation");
  await expect(page.getByTestId("robots-table")).toContainText("2");
  await expect(page.getByTestId("capability-cards")).toContainText("pick");
  await expect(page.getByTestId("capability-cards")).toContainText("place");
  await expect(page.getByTestId("capability-cards")).toContainText("object_id*: string");
  await expect(page.getByTestId("capability-cards")).toContainText("approval required");
  await expect(page.getByTestId("environment-descriptions")).toContainText("x bounds");
  await expect(page.getByTestId("environment-descriptions")).toContainText("-1 to 1");
  await expect(page.getByTestId("environment-descriptions")).toContainText("-0.5 to 0.5");
  await expect(page.getByTestId("world-objects-table")).toContainText("red_block");
  await expect(page.getByTestId("world-objects-table")).toContainText("tray");
  await expect(page.getByTestId("world-objects-table")).toContainText("available");
  await expect(page.getByTestId("raw-debug-panel")).toContainText("Unknown/raw fields");
  await expect(page.getByTestId("raw-debug-collapse").locator(".ant-collapse-content-active"))
    .toHaveCount(0);
  await expect(page.getByTestId("raw-debug-panel").locator(".ant-tree")).toHaveCount(0);
  await expect(page.getByTestId("raw-debug-panel").locator(".json-tree")).toHaveCount(0);
  await expect(page.getByTestId("raw-debug-panel")).not.toContainText("driver_note");
  await page.getByTestId("raw-debug-collapse").getByText("Unknown/raw fields").click();
  await expect(page.getByTestId("raw-debug-panel").locator(".ant-tree")).toBeVisible();
  await expect(page.getByTestId("raw-debug-panel")).toContainText("world_raw");
  await expect(page.getByTestId("raw-debug-panel")).toContainText("driver_note");
  await expect(page.getByText("Full state JSON")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("settings panel saves and tests LLM settings with mocked API", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "Recommended backend",
  );
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "state.db is source of truth",
  );
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "SAFETY.md remains file source",
  );
  await expect(page.getByTestId("settings-panel")).toContainText(
    "key ****7890",
  );

  await page.getByLabel("Base URL").fill("http://local-llm.test/v1");
  await page.getByLabel("API key").fill("sk-local-00007890");
  await page.getByLabel("Model").fill("local-model");
  await page.getByTestId("save-llm-settings").click();

  await expect(page.getByTestId("llm-settings-feedback")).toContainText(
    "LLM settings saved",
  );
  await expect(page.getByTestId("settings-panel")).toContainText(
    "key ****7890",
  );

  await page.getByTestId("test-llm-settings").click();
  await expect(page.getByTestId("llm-settings-feedback")).toContainText(
    "LLM connection test passed",
  );

  await page.getByTestId("export-audit-button").click();
  await expect(page.getByTestId("export-audit-feedback")).toContainText(
    "Exported audit view",
  );
  expectNoConsoleErrors(consoleErrors);
});

test("settings panel explains sqlite backend without live switching", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page, {
    backend: "sqlite",
    workspace_path: "C:/tmp/physical-agent-sqlite-workspace",
  });

  await page.goto("/");
  await page.getByTestId("nav-settings").click();

  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "Recommended backend",
  );
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "state.db is source of truth",
  );
  await expect(page.getByTestId("state-backend-summary")).toContainText(
    "no GUI live backend switch",
  );
  await expect(page.getByTestId("state-backend-summary")).not.toContainText(
    "JSON backend",
  );
  expectNoConsoleErrors(consoleErrors);
});

test("settings danger zone keeps explicit reset confirmation path", async ({
  page,
  request,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  const wrongConfirm = await request.post("/api/workspace/reset", {
    data: {},
  });
  expect(wrongConfirm.status()).toBe(400);
  expect((await wrongConfirm.json()).message).toContain("confirm");

  await page.goto("/");
  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("reset-workspace-button")).toBeVisible();
  await page.getByTestId("reset-workspace-button").click();
  await page.getByRole("button", { name: "Reset workspace", exact: true }).last().click();
  await expect(page.getByTestId("reset-workspace-feedback")).toContainText(
    "Workspace reset",
  );
  expectNoConsoleErrors(consoleErrors);
});

test("hardware scaffold can register a robot and config panel refreshes", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await page.getByTestId("nav-hardware").click();
  await page.getByTestId("integrate-source-input").fill("C:/tmp/mock-sdk");
  await page.getByTestId("integrate-name-input").fill("bench_arm");
  await page.getByTestId("integrate-submit-button").click();
  await expect(page.getByTestId("integrate-result")).toContainText("bench_arm");

  await page.getByTestId("register-robot-id").fill("bench_arm_1");
  await page.getByTestId("register-robot-button").click();
  await expect(page.getByTestId("register-robot-feedback")).toContainText(
    "Registered bench_arm_1",
  );
  await expect(page.getByTestId("config-panel")).toContainText("bench_arm_1");
  await expect(page.getByTestId("config-panel")).toContainText("Execution mode");
  await expect(page.getByTestId("config-panel")).toContainText("hardware");
  expectNoConsoleErrors(consoleErrors);
});

test("language and dark mode switches persist", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await page.getByTestId("nav-settings").click();
  await page.getByTestId("language-switch").getByText("中文").click();
  await expect(page.getByTestId("status-bar")).toContainText("工作台");
  await expect(page.evaluate(() => localStorage.getItem("physical-agent-language"))).resolves.toBe("zh");

  await page.getByTestId("theme-switch").getByText("深色").click();
  await expect(page.locator("body")).toHaveAttribute("data-theme", "dark");
  await expect(page.evaluate(() => localStorage.getItem("physical-agent-theme"))).resolves.toBe("dark");
  expectNoConsoleErrors(consoleErrors);
});

test("tour opens on first visit closes and can be reopened from settings", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.addInitScript(() => {
    localStorage.setItem("physical-agent-language", "en");
    localStorage.setItem("physical-agent-theme", "light");
    localStorage.removeItem("physical-agent-tour-dismissed");
  });
  await mockReadyApiWithRobot(page);

  await page.goto("/");
  await expect(page.getByText("Set up first")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Approve next")).toBeVisible();
  expect(await tourTargets(page, "nav-actions")).toBe(true);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Observe feedback")).toBeVisible();
  expect(await tourTargets(page, "nav-chat")).toBe(true);
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.evaluate(() => localStorage.getItem("physical-agent-tour-dismissed"))).resolves.toBe("1");

  await page.getByTestId("nav-settings").click();
  await page.getByTestId("show-tour-button").click();
  await expect(page.getByText("Set up first")).toBeVisible();
  expectNoConsoleErrors(consoleErrors);
});

test("chat panel streams text incrementally and can stop", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  const snapshot = await mockReadyApiWithRobot(page);
  const finalState = {
    ...snapshot,
    chat: {
      messages: [
        {
          role: "user",
          content: "stream a greeting",
          created_at: "2026-07-01T00:00:00Z",
        },
        {
          role: "assistant",
          content: "Hello stream",
          created_at: "2026-07-01T00:00:01Z",
        },
      ],
    },
  };
  await installControlledChatStream(
    page,
    [
      sseEvent(10, "start", { stream_id: "stream-e2e", request_id: "req-e2e" }),
      sseEvent(11, "delta", {
        stream_id: "stream-e2e",
        request_id: "req-e2e",
        delta: "Hello",
      }),
      sseEvent(12, "delta", {
        stream_id: "stream-e2e",
        request_id: "req-e2e",
        delta: " stream",
      }),
      sseEvent(13, "done", {
        stream_id: "stream-e2e",
        request_id: "req-e2e",
        reply: "Hello stream",
        mode: "llm",
        state: finalState,
      }),
    ],
    2,
  );

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await page.getByPlaceholder("Message the agent").fill("stream a greeting");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("stop-chat-stream")).toBeEnabled();
  await expect(page.getByTestId("chat-panel")).toContainText("Hello");
  await expect(page.getByTestId("chat-panel")).not.toContainText(
    "Hello stream",
    { timeout: 150 },
  );
  await page.evaluate(() => {
    (
      window as typeof window & { __releaseChatStream?: () => void }
    ).__releaseChatStream?.();
  });
  await expect(page.getByTestId("chat-panel")).toContainText("Hello stream");
  await expect(page.getByTestId("reasoning-summary")).toHaveCount(0);
  await expect(page.getByTestId("stop-chat-stream")).toBeDisabled();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("chat reasoning summary is a collapsed non-decision disclosure", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.addInitScript(() => {
    localStorage.setItem("physical-agent-language", "zh");
    localStorage.setItem("physical-agent-theme", "light");
    localStorage.setItem("physical-agent-tour-dismissed", "1");
  });
  const snapshot = await mockReadyApiWithRobot(page);
  const reasoningSummary = "Checked the constraints. No action was executed.";
  const finalState = {
    ...snapshot,
    chat: {
      messages: [
        {
          role: "user",
          content: "解释你的结论",
          created_at: "2026-07-21T00:00:00Z",
        },
        {
          role: "assistant",
          content: "这是最终答复。",
          created_at: "2026-07-21T00:00:01Z",
          metadata: { reasoning_summary: reasoningSummary },
        },
      ],
    },
  };
  await installControlledChatStream(
    page,
    [
      sseEvent(14, "start", { stream_id: "thought-e2e", request_id: "thought-e2e" }),
      sseEvent(15, "thought", {
        stream_id: "thought-e2e",
        request_id: "thought-e2e",
        delta: "Checked the constraints. ",
      }),
      sseEvent(16, "thought", {
        stream_id: "thought-e2e",
        request_id: "thought-e2e",
        delta: "No action was executed.",
      }),
      sseEvent(17, "delta", {
        stream_id: "thought-e2e",
        request_id: "thought-e2e",
        delta: "这是最终答复。",
      }),
      sseEvent(18, "done", {
        stream_id: "thought-e2e",
        request_id: "thought-e2e",
        reply: "这是最终答复。",
        mode: "llm",
        state: finalState,
      }),
    ],
    4,
  );

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await page.getByPlaceholder("给 agent 发消息").fill("解释你的结论");
  await page.getByPlaceholder("给 agent 发消息").press("Enter");
  const liveDisclosure = page.getByTestId("reasoning-summary");
  await expect(liveDisclosure).toContainText("模型推理摘要");
  await expect(liveDisclosure).toContainText("仅供参考，不是决策依据");
  await expect(page.getByTestId("reasoning-summary-body")).not.toBeVisible();
  await liveDisclosure.locator("summary").click();
  await expect(page.getByTestId("reasoning-summary-body")).toHaveText(reasoningSummary);

  await page.evaluate(() => {
    (
      window as typeof window & { __releaseChatStream?: () => void }
    ).__releaseChatStream?.();
  });
  await expect(page.getByTestId("stop-chat-stream")).toBeDisabled();
  await expect(page.getByTestId("reasoning-summary-body")).not.toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("chat stop aborts the active stream and leaves a visible status", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);
  await installMockChatStream(
    page,
    [
      sseEvent(20, "start", {
        stream_id: "stream-stop",
        request_id: "req-stop",
      }),
      sseEvent(21, "delta", {
        stream_id: "stream-stop",
        request_id: "req-stop",
        delta: "Partial",
      }),
      sseEvent(22, "delta", {
        stream_id: "stream-stop",
        request_id: "req-stop",
        delta: " ignored",
      }),
    ],
    900,
  );

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await page.getByPlaceholder("Message the agent").fill("stream slowly");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText("Partial");
  await page.getByTestId("stop-chat-stream").click();
  await expect(page.getByTestId("chat-stream-error")).toContainText("stopped");
  await expect(page.getByTestId("stop-chat-stream")).toBeDisabled();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("chat stream unavailable falls back to regular chat", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);
  await installUnavailableChatStream(page);

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await page.getByPlaceholder("Message the agent").fill("fallback please");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText(
    "Fallback reply: fallback please",
  );
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("overview exposes the compiled SafetyGate task in AgentOutput", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page, {
    plan: {
      status: "needs_watch",
      agent_output: {
        schema: "physical-agent/agent-output/v1",
        status: "waiting_execution",
        decision: "propose",
        lifecycle: "submitted",
        message: "Move the arm after the execution-time safety check.",
        proposal_id: "proposal-42",
        tasks: [
          {
            id: "task:safety_gate:move-1",
            kind: "safety_gate",
            owner: "watch",
            status: "queued",
            label: "Safety gate for move-1",
            action_id: "move-1",
            depends_on: [],
            origin: "plan_compiler",
            mandatory: true,
            policy_source: "SAFETY.md",
            checks: [
              { code: "safety.robot.known", description: "Robot must exist." },
              {
                code: "safety.approval.satisfied",
                description: "Approval must be satisfied.",
              },
            ],
            details: {},
          },
          {
            id: "task:physical_action:move-1",
            kind: "physical_action",
            owner: "watch",
            status: "waiting",
            label: "Execute move-1",
            action_id: "move-1",
            depends_on: ["task:safety_gate:move-1"],
            origin: "plan_compiler",
            mandatory: false,
            policy_source: null,
            checks: [],
            details: {},
          },
        ],
        actions: [
          {
            id: "move-1",
            robot: "arm_1",
            capability: "move",
            params: { x: 0.1 },
          },
        ],
      },
    },
  });

  await page.goto("/");
  await expectHealthyShell(page);

  const graph = page.getByTestId("agent-task-graph");
  await expect(graph).toContainText("Agent output tasks");
  await expect(graph).toContainText("proposal-42");
  await expect(graph).toContainText(
    "Safety gates are mandatory execution tasks compiled by the system and owned by watch.",
  );

  const safetyGate = graph.locator("tr.agent-task-row-safety");
  await expect(safetyGate).toContainText("Safety gate for move-1");
  await expect(safetyGate).toContainText("mandatory");
  await expect(safetyGate).toContainText("watch");
  await expect(safetyGate).toContainText("queued");
  await expect(safetyGate).toContainText("SAFETY.md");
  await expect(safetyGate).toContainText("2 checks");

  const physicalAction = graph.locator("tr.agent-task-row-physical_action");
  await expect(physicalAction).toContainText("task:safety_gate:move-1");
  expectNoConsoleErrors(consoleErrors);
});

test("AgentOutput task statuses trust the server projection over raw feedback", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  const completedAction = {
    ...mockAction("move-success"),
    metadata: {
      approval: { required: true, status: "approved" },
    },
  };
  const projectedTasks = [
    { ...mockApprovalTask(completedAction.id), status: "completed" },
    ...mockCompiledTaskPair(completedAction.id).map((task) => ({
      ...task,
      status: task.kind === "safety_gate" ? "failed" : "completed",
    })),
  ];
  await mockReadyApiWithRobot(page, {
    plan: {
      metadata: { revision: 7 },
      plan: {
        status: "needs_watch",
        agent_output: {
          schema: "physical-agent/agent-output/v1",
          status: "failed",
          decision: "propose",
          lifecycle: "submitted",
          message: "The server rejected non-authoritative Gate evidence.",
          proposal_id: "proposal-runtime-status",
          tasks: projectedTasks,
          actions: [completedAction],
        },
      },
    },
    feedback: {
      history: [
        {
          event: "safety_gate",
          task_id: `task:safety_gate:${completedAction.id}`,
          action_id: completedAction.id,
          status: "passed",
          decision: "allow",
          actor: "agent",
        },
      ],
    },
    actions: {
      pending: [],
      completed: [completedAction],
      cancelled: [],
    },
  });

  await page.goto("/");
  await expectHealthyShell(page);

  const graph = page.getByTestId("agent-task-graph");
  await expect(graph).toContainText("proposal-runtime-status");

  const completedApproval = graph
    .locator("tr.agent-task-row-approval")
    .filter({ hasText: completedAction.id });
  await expect(completedApproval).toContainText("completed");

  const completedGate = graph
    .locator("tr.agent-task-row-safety")
    .filter({ hasText: completedAction.id });
  await expect(completedGate).toContainText("failed");
  await expect(completedGate).not.toContainText("passed");
  const completedTask = graph
    .locator("tr.agent-task-row-physical_action")
    .filter({ hasText: completedAction.id });
  await expect(completedTask).toContainText("completed");
  expectNoConsoleErrors(consoleErrors);
});

function mockAction(id: string) {
  return {
    id,
    robot: "arm_1",
    capability: "move",
    params: { x: 0.1 },
  };
}

function mockApprovalTask(actionId: string) {
  return {
    id: `task:approval:${actionId}`,
    kind: "approval",
    owner: "human",
    status: "requested",
    label: `Approve ${actionId}`,
    action_id: actionId,
    depends_on: [],
    origin: "plan_compiler",
    mandatory: true,
    policy_source: null,
    checks: [],
    details: {},
  };
}

function mockCompiledTaskPair(actionId: string) {
  return [
    {
      id: `task:safety_gate:${actionId}`,
      kind: "safety_gate",
      owner: "watch",
      status: "queued",
      label: `Safety gate for ${actionId}`,
      action_id: actionId,
      depends_on: [],
      origin: "plan_compiler",
      mandatory: true,
      policy_source: "SAFETY.md",
      checks: [],
      details: {},
    },
    {
      id: `task:physical_action:${actionId}`,
      kind: "physical_action",
      owner: "watch",
      status: "waiting",
      label: `Execute ${actionId}`,
      action_id: actionId,
      depends_on: [`task:safety_gate:${actionId}`],
      origin: "plan_compiler",
      mandatory: true,
      policy_source: null,
      checks: [],
      details: {},
    },
  ];
}

function draftAgentOutput(actions: Array<Record<string, unknown>>) {
  return {
    schema: "physical-agent/agent-output/v1",
    status: "draft",
    decision: "propose",
    lifecycle: "draft",
    message: "Review the structured draft.",
    proposal_id: null,
    tasks: [],
    actions,
    refusal_reason: null,
  };
}

async function mockReadyApiWithRobot(
  page: Page,
  overrides: Record<string, unknown> = {},
) {
  const snapshot = {
    ok: true,
    ready: true,
    message: "Ready.",
    backend: "sqlite",
    config_path: "C:/tmp/physical-agent.yaml",
    workspace_path: "C:/tmp/physical-agent-workspace",
    executor: {
      mode: "embedded",
      status: "active",
      embedded_enabled: true,
      lease: { active: true, expires_at: "2026-07-10T00:00:00Z" },
      last_error: null,
    },
    capabilities: {
      robots: {
        arm_1: {
          kind: "arm",
          driver: "mock_arm",
          status: "connected",
          capabilities: [
            { name: "observe", description: "Inspect the workspace." },
          ],
        },
      },
    },
    world: { summary: "Mock world", state: {}, environment: {} },
    actions: { pending: [], completed: [], cancelled: [] },
    feedback: {},
    safety: {},
    chat: { messages: [] },
    plan: {},
    memory: { notes: [] },
    uploads: { uploads: [] },
    chunks: { chunks: [] },
    ...overrides,
  };

  await mockApiSnapshot(page, snapshot);
  return snapshot;
}

test("config missing state renders a clear nonblank dashboard", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page, ["/api/config"]);
  await mockNotReadyApi(page, "Config file is missing.", {
    config_exists: false,
    workspace_exists: false,
  });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("workspace-notice")).toContainText(
    "Workspace is not ready",
  );
  await expect(page.getByTestId("workspace-notice")).toContainText(
    "Config file is missing.",
  );
  await expect(page.getByTestId("executor-status")).toContainText(
    "waiting for initialization",
  );
  await expect(page.getByTestId("initialize-project-button")).toBeVisible();
  await expect(page.getByTestId("sse-status")).toContainText(
    "SSE disconnected",
  );
  await expect(page.getByTestId("state-overview-panel")).toBeVisible();
  expectNoConsoleErrors(consoleErrors);
});

test("safe initialization creates the project then refreshes executor state", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page, ["/api/config"]);
  await mockNotReadyApi(page, "Config file is missing.", {
    config_exists: false,
    workspace_exists: false,
  });

  await page.goto("/");
  await page.getByTestId("initialize-project-button").click();
  await expect(page.getByTestId("workspace-notice")).toHaveCount(0);
  await expect(page.getByTestId("executor-status")).toContainText("embedded");
  await expect(page.getByTestId("status-bar")).toContainText("workspace ready");
  await page.getByTestId("nav-hardware").click();
  await expect(page.getByTestId("config-panel")).toContainText(
    "C:/tmp/physical-agent.yaml",
  );
  await expect(page.getByTestId("config-panel")).not.toContainText("Config unavailable");
  expectNoConsoleErrors(consoleErrors);
});

test("executor status distinguishes an external lease from embedded configuration", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page, {
    executor: {
      mode: "none",
      status: "stopped",
      embedded_enabled: false,
      lease: null,
      last_error: null,
    },
  });
  await page.route("**/api/events", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        sseEvent(1, "hello", {
          version: "0.1.0",
          watch_enabled: false,
          executor: {
            mode: "none",
            status: "stopped",
            embedded_enabled: false,
            lease: null,
            last_error: null,
          },
        }),
        sseEvent(2, "executor", {
          executor: {
            mode: "external",
            status: "active",
            embedded_enabled: false,
            lease: { active: true, expires_at: "2026-07-10T12:00:00Z" },
            last_error: { message: "previous lease contention", phase: "acquire_lease" },
          },
        }),
      ].join(""),
    });
  });

  await page.goto("/");
  await expect(page.getByTestId("executor-status")).toContainText(
    "executor external · active",
  );
  await expect(page.getByTestId("executor-status")).toHaveAttribute(
    "title",
    /Lease active until 2026-07-10T12:00:00Z/,
  );
  await expect(page.getByTestId("executor-status")).toHaveAttribute(
    "title",
    /Last error: previous lease contention/,
  );
  expectNoConsoleErrors(consoleErrors);
});

test("real streaming AgentOutput and ChatPlan can be persisted to pending Actions", async ({
  page,
  request,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  publishE2eCapabilities();
  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  const streamResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/chat/stream") &&
      response.request().method() === "POST",
  );
  await page.getByPlaceholder("Message the agent").fill("observe the workspace");
  await page.getByPlaceholder("Message the agent").press("Enter");
  const streamResponse = await streamResponsePromise;
  expect(streamResponse.ok()).toBeTruthy();
  const streamEvents = parseSseEvents(await streamResponse.text());
  expect(streamEvents.filter((event) => event.type === "delta").length).toBeGreaterThan(1);
  const done = streamEvents.find((event) => event.type === "done");
  expect(done).toBeTruthy();
  const agentOutput = done?.payload.agent_output as {
    schema?: string;
    message?: string;
    actions?: Array<{ id?: string }>;
    tasks?: Array<Record<string, unknown>>;
  };
  const chatPlan = done?.payload.plan as {
    agent_output?: unknown;
    needs_watch?: boolean;
  };
  expect(done?.payload).not.toHaveProperty("actions");
  expect(done?.payload).not.toHaveProperty("draft_actions");
  expect(done?.payload).not.toHaveProperty("chat_contract");
  expect(done?.payload).not.toHaveProperty("has_structured_draft");
  expect(agentOutput.schema).toBe("physical-agent/agent-output/v1");
  expect(agentOutput.message).not.toContain("```action-draft");
  expect(done?.payload.reply).toBe(agentOutput.message);
  expect(done?.payload.reply).not.toContain("```action-draft");
  expect(chatPlan.agent_output).toEqual(agentOutput);
  expect(chatPlan).not.toHaveProperty("actions");
  expect(chatPlan.needs_watch).toBe(false);
  expect(
    agentOutput.tasks?.some(
      (task) =>
        task.kind === "safety_gate" &&
        task.owner === "watch" &&
        task.mandatory === true &&
        task.policy_source === "SAFETY.md",
    ),
  ).toBe(true);
  const actionId = agentOutput.actions?.[0]?.id;
  expect(actionId).toBeTruthy();

  const cards = page.getByTestId("draft-action-card");
  await expect(cards).toHaveCount(1);
  await expect(cards).toContainText("arm_1.observe");
  await page.getByTestId("add-draft-to-actions").click();
  await page.getByTestId("nav-actions").click();
  await page.getByTestId("action-board-toggle").click();
  await expect(page.getByTestId("action-board")).toContainText(actionId);
  await expect(page.getByTestId("action-board")).toContainText("observe");
  await expect
    .poll(async () => {
      const response = await request.get("/api/state");
      const state = (await response.json()) as {
        actions?: { pending?: Array<{ id?: string }> };
      };
      return state.actions?.pending?.map((action) => action.id) ?? [];
    })
    .toContain(actionId);

  const stateResponse = await request.get("/api/state");
  expect(stateResponse.ok()).toBeTruthy();
  const state = (await stateResponse.json()) as {
    actions?: {
      pending?: Array<{
        id?: string;
        metadata?: {
          source?: string;
          approval?: { status?: string };
        };
      }>;
      completed?: Array<{ id?: string }>;
      cancelled?: Array<{ id?: string }>;
    };
    plan?: {
      plan?: {
        agent_output?: {
          actions?: Array<{ id?: string }>;
          tasks?: Array<{
            kind?: string;
            action_id?: string;
            owner?: string;
            status?: string;
            mandatory?: boolean;
            policy_source?: string | null;
          }>;
        };
      };
    };
  };
  const pending = state.actions?.pending?.filter((action) => action.id === actionId) ?? [];
  expect(pending).toHaveLength(1);
  expect(pending[0]?.metadata?.source).toBe("chat_draft");
  expect(pending[0]?.metadata?.approval?.status).not.toBe("approved");
  expect(state.actions?.completed?.some((action) => action.id === actionId)).toBe(false);
  expect(state.actions?.cancelled?.some((action) => action.id === actionId)).toBe(false);

  const formalOutput = state.plan?.plan?.agent_output;
  expect(formalOutput?.actions?.map((action) => action.id)).toContain(actionId);
  const gate = formalOutput?.tasks?.find(
    (task) => task.kind === "safety_gate" && task.action_id === actionId,
  );
  expect(gate).toMatchObject({
    owner: "watch",
    mandatory: true,
    policy_source: "SAFETY.md",
  });
  expect(gate?.status).not.toBe("passed");
  const physicalAction = formalOutput?.tasks?.find(
    (task) => task.kind === "physical_action" && task.action_id === actionId,
  );
  expect(physicalAction?.status).not.toBe("completed");
  expectNoConsoleErrors(consoleErrors);
});

test("streaming fence-like text stays inert until structured AgentOutput arrives", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockReadyApiWithRobot(page);
  const action = {
    id: "draft-incremental-dual-track",
    robot: "arm_1",
    capability: "observe",
    params: {},
    reason: "Legacy text must stay inert.",
    depends_on: [],
  };
  const structuredAction = {
    ...action,
    reason: "Structured terminal draft.",
  };
  const structuredOutput = draftAgentOutput([structuredAction]);
  const replyPrefix = "Historical action draft text follows.";
  const partialFence = `\n\n\`\`\`action-draft\n${JSON.stringify(action).slice(0, -2)}`;
  const completedFence = `${JSON.stringify(action).slice(-2)}\n\`\`\``;
  const reply = `${replyPrefix}${partialFence}${completedFence}`;
  await installGatedChatStream(
    page,
    [
      sseEvent(40, "start", { stream_id: "draft-incremental", request_id: "draft-incremental" }),
      sseEvent(41, "delta", {
        stream_id: "draft-incremental",
        request_id: "draft-incremental",
        delta: replyPrefix,
      }),
      sseEvent(42, "delta", {
        stream_id: "draft-incremental",
        request_id: "draft-incremental",
        delta: partialFence,
      }),
      sseEvent(43, "delta", {
        stream_id: "draft-incremental",
        request_id: "draft-incremental",
        delta: completedFence,
      }),
      sseEvent(44, "done", {
        stream_id: "draft-incremental",
        request_id: "draft-incremental",
        reply,
        mode: "llm",
        agent_output: structuredOutput,
        plan: {
          status: "proposed_actions",
          intent: "act",
          summary: replyPrefix,
          steps: [],
          needs_watch: false,
          agent_output: structuredOutput,
        },
      }),
    ],
    [3, 4],
  );

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await page.getByPlaceholder("Message the agent").fill("observe incrementally");
  await page.getByPlaceholder("Message the agent").press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText(replyPrefix);
  const cards = page.getByTestId("draft-action-card");
  await expect(cards).toHaveCount(0);
  await expect(page.getByTestId("chat-stream-error")).toHaveCount(0);

  await releaseNextChatChunk(page);
  await expect(cards).toHaveCount(0);
  await expect(page.getByTestId("chat-panel")).toContainText(action.id);
  await expect(page.getByTestId("stop-chat-stream")).toBeEnabled();
  await expect(page.getByTestId("chat-stream-error")).toHaveCount(0);

  await releaseNextChatChunk(page);
  await expect(page.getByTestId("stop-chat-stream")).toBeDisabled();
  await expect(cards).toHaveCount(1);
  await expect(cards).toContainText("Structured terminal draft.");
  await expect(cards).not.toContainText("Legacy text must stay inert.");
  await expect(page.getByTestId("chat-stream-error")).toHaveCount(0);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expectNoConsoleErrors(consoleErrors);
});

test("historical action-draft fences remain text and only structured output is actionable", async ({
  page,
  request,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  const structuredOnly = {
    id: "draft-structured-only",
    robot: "arm_1",
    capability: "observe",
    params: {},
    reason: "Structured only.",
    depends_on: [],
  };
  const fenceOnly = {
    id: "draft-fence-only",
    robot: "arm_1",
    capability: "pick",
    params: { object: "red_block" },
    reason: "Historical text only.",
    depends_on: [],
  };
  const structuredConflict = {
    id: "draft-structured-wins",
    robot: "arm_1",
    capability: "observe",
    params: {},
    reason: "Structured output is authoritative.",
    depends_on: [],
  };
  const fenceConflict = {
    id: "draft-fence-loses",
    robot: "arm_1",
    capability: "pick",
    params: { object: "wrong_block" },
    reason: "Historical conflict text.",
    depends_on: [],
  };
  const fence = (action: Record<string, unknown>) =>
    `\n\n\`\`\`action-draft\n${JSON.stringify(action)}\n\`\`\``;

  await mockReadyApiWithRobot(page, {
    chat: {
      messages: [
        { role: "user", content: "structured only", created_at: "2026-07-01T01:00:00Z" },
        {
          role: "assistant",
          content: "Structured-only reply.",
          created_at: "2026-07-01T01:00:01Z",
          metadata: {
            agent_output: draftAgentOutput([structuredOnly]),
          },
        },
        { role: "user", content: "historical fence", created_at: "2026-07-01T01:00:02Z" },
        {
          role: "assistant",
          content: `Fence-only reply.${fence(fenceOnly)}`,
          created_at: "2026-07-01T01:00:03Z",
        },
        { role: "user", content: "conflicting tracks", created_at: "2026-07-01T01:00:04Z" },
        {
          role: "assistant",
          content: `Conflict reply.${fence(fenceConflict)}`,
          created_at: "2026-07-01T01:00:05Z",
          metadata: { agent_output: draftAgentOutput([structuredConflict]) },
        },
        { role: "user", content: "old-schema metadata", created_at: "2026-07-01T01:00:06Z" },
        {
          role: "assistant",
          content: `Old schema is not canonical.${fence(fenceOnly)}`,
          created_at: "2026-07-01T01:00:07Z",
          metadata: {
            agent_output: {
              ...draftAgentOutput([structuredConflict]),
              schema: "physical-agent/agent-output/v0",
            },
          },
        },
      ],
    },
  });

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  const cards = page.getByTestId("draft-action-card");
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText("arm_1.observe");
  await expect(cards.nth(1)).toContainText("Structured output is authoritative.");
  await expect(cards.nth(0)).not.toContainText("Historical text only.");
  await expect(cards.nth(1)).not.toContainText("Historical text only.");
  await expect(cards.nth(0)).not.toContainText("Historical conflict text.");
  await expect(cards.nth(1)).not.toContainText("Historical conflict text.");
  await expect(page.getByTestId("add-draft-to-actions")).toHaveCount(2);
  await expect(page.getByTestId("chat-panel")).toContainText(fenceOnly.id);
  await expect(page.getByTestId("chat-panel")).toContainText(fenceConflict.id);

  await cards.nth(0).getByTestId("add-draft-to-actions").click();
  await page.getByTestId("nav-actions").click();
  await page.getByTestId("action-board-toggle").click();
  await expect(page.getByTestId("action-board")).toContainText(structuredOnly.id);
  await expect(page.getByTestId("action-board")).not.toContainText(fenceOnly.id);
  await expect(page.getByTestId("action-board")).not.toContainText(fenceConflict.id);
  const scenarioIds = new Set([structuredOnly.id, fenceOnly.id, fenceConflict.id]);
  await expect
    .poll(async () => {
      const response = await request.get("/api/state");
      const state = (await response.json()) as {
        actions?: {
          pending?: Array<{ id?: string }>;
        };
      };
      return (state.actions?.pending ?? []).flatMap((action) =>
        action.id && scenarioIds.has(action.id) ? [action.id] : [],
      );
    })
    .toEqual([structuredOnly.id]);
  expectNoConsoleErrors(consoleErrors);
});

test("Robots reads YAML execution mode while no executor is running", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockNotReadyApi(page, "Workspace is not initialized.", {
    config_exists: true,
    workspace_exists: false,
    executor: {
      mode: "none",
      status: "stopped",
      embedded_enabled: false,
      lease: null,
      last_error: null,
    },
  });
  await page.route("**/api/config", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: "Config loaded.",
        config_path: "C:/tmp/physical-agent.yaml",
        config: {
          workspace: { path: "C:/tmp/physical-agent-workspace", backend: "sqlite" },
          robots: {
            yaml_arm: {
              driver: "vendor_arm",
              execution_mode: "hardware",
              config: { port: "COM7" },
            },
          },
        },
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByTestId("executor-status")).toContainText("not running");
  await page.getByTestId("nav-hardware").click();
  await expect(page.getByTestId("robots-panel")).toContainText("yaml_arm");
  await expect(page.getByTestId("robots-panel")).toContainText("vendor_arm");
  await expect(page.getByTestId("robots-panel")).toContainText("hardware");
  await expect(page.getByTestId("robots-panel")).toContainText("configured");
  expectNoConsoleErrors(consoleErrors);
});

test("workspace not initialized state renders a clear nonblank dashboard", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockNotReadyApi(page, "Workspace is not initialized.", {
    config_exists: true,
    workspace_exists: false,
    backend: "sqlite",
    workspace_path: "C:/tmp/physical-agent-empty-workspace",
  });

  await page.goto("/");
  await expectHealthyShell(page);
  await expect(page.getByTestId("workspace-notice")).toContainText(
    "Workspace is not ready",
  );
  await expect(page.getByTestId("workspace-notice")).toContainText(
    "Workspace is not initialized.",
  );
  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("settings-panel")).toContainText("not ready");
  expectNoConsoleErrors(consoleErrors);
});

async function mockNotReadyApi(
  page: Page,
  message: string,
  extras: Record<string, unknown>,
) {
  const snapshot = {
    ok: false,
    ready: false,
    message,
    config_path: "C:/tmp/missing-physical-agent.yaml",
    executor: {
      mode: "waiting_for_init",
      status: "waiting",
      embedded_enabled: true,
      lease: null,
      last_error: null,
    },
    ...extras,
  };

  await mockApiSnapshot(page, snapshot);
}

async function mockApiSnapshot(page: Page, snapshot: Record<string, unknown>) {
  let currentSnapshot = snapshot;
  let llmSettings = {
    base_url: "http://mock-llm.test/v1",
    model: "mock-model",
    api_mode: "chat_completions",
    has_api_key: true,
    masked_api_key: "****7890",
    settings_path: "C:/tmp/workspace/.llm.json",
  };
  const configRobots: Record<
    string,
    { driver: string; execution_mode: "simulation" | "hardware"; config: Record<string, unknown> }
  > = {};

  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentSnapshot),
    });
  });
  await page.route("**/api/state", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentSnapshot),
    });
  });
  await page.route("**/api/project/initialize", async (route) => {
    currentSnapshot = {
      ...currentSnapshot,
      ok: true,
      ready: true,
      message: "Ready.",
      config_exists: true,
      workspace_exists: true,
      backend: currentSnapshot.backend ?? "sqlite",
      workspace_path:
        currentSnapshot.workspace_path ?? "C:/tmp/physical-agent-workspace",
      executor: {
        mode: "embedded",
        status: "starting",
        embedded_enabled: true,
        lease: null,
        last_error: null,
      },
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: "Project initialized.",
        config_created: true,
        workspace_created: true,
        state: currentSnapshot,
      }),
    });
  });
  await page.route("**/api/state-check", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(stateCheckForSnapshot(snapshot)),
    });
  });
  await page.route("**/api/export-audit", async (route) => {
    const backend = String(snapshot.backend ?? "sqlite");
    const workspacePath = String(
      snapshot.workspace_path ?? "C:/tmp/physical-agent-workspace",
    );
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: "Exported audit view.",
        backend,
        workspace_path: workspacePath,
        out_dir: `${workspacePath}/audit`,
        manifest: `${workspacePath}/audit/manifest.json`,
        result: {
          backend,
          workspace_path: workspacePath,
          out_dir: `${workspacePath}/audit`,
          manifest: `${workspacePath}/audit/manifest.json`,
        },
      }),
    });
  });
  await page.route("**/api/workspace/reset", async (route) => {
    const body = route.request().postDataJSON() as { confirm?: boolean };
    if (!body.confirm) {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          message: "Workspace reset requires explicit confirmation.",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: "Workspace reset complete.",
        state: {
          ...snapshot,
          actions: { pending: [], completed: [], cancelled: [] },
          chat: { messages: [] },
          memory: { notes: [] },
        },
      }),
    });
  });
  await page.route("**/api/integrate", async (route) => {
    const body = route.request().postDataJSON() as { name?: string; output?: string };
    const name = body.name || "mock_driver";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: `Generated ${name}.`,
        state: snapshot,
        result: {
          output_path: body.output || `my_hardware/${name}`,
          generated_files: ["driver.py", "physical_driver.yaml"],
          llm_used: false,
          source: {
            name,
            title: name,
            robot_kind: "arm",
            transport: "mock",
            config_schema: {
              type: "object",
              properties: {
                port: { type: "string", default: "COM1" },
              },
            },
            capabilities: [
              {
                name: "observe",
                description: "Inspect workspace.",
                params_schema: { type: "object", properties: {} },
              },
            ],
          },
          validation: { ok: true, checks: ["scaffold"], errors: [] },
          next_steps: ["Register robot"],
        },
      }),
    });
  });
  await page.route("**/api/config/robots", async (route) => {
    const body = route.request().postDataJSON() as {
      robot_id: string;
      driver: string;
      config?: Record<string, unknown>;
    };
    configRobots[body.robot_id] = {
      driver: body.driver,
      execution_mode:
        (body as { execution_mode?: "simulation" | "hardware" }).execution_mode ?? "simulation",
      config: body.config ?? {},
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: `Registered ${body.robot_id}.`,
      }),
    });
  });
  await page.route("**/api/config", async (route) => {
    if (currentSnapshot.config_exists === false) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ ok: false, message: "Config file is missing." }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        config_path: "C:/tmp/physical-agent.yaml",
        config: {
          workspace: { path: "C:/tmp/physical-agent-workspace", backend: "sqlite" },
          watch: { tick_ms: 500, require_human_approval: true },
          robots: configRobots,
        },
      }),
    });
  });
  await page.route("**/api/events", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        sseEvent(1, "hello", {
          version: "0.1.0",
          executor: currentSnapshot.executor,
          watch_enabled: false,
        }),
        sseEvent(2, "state", { reason: "connect", state: currentSnapshot }),
      ].join(""),
    });
  });
  await page.route("**/api/settings/llm", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as {
        base_url?: string;
        api_key?: string;
        model?: string;
        api_mode?: string;
      };
      llmSettings = {
        ...llmSettings,
        base_url: body.base_url ?? llmSettings.base_url,
        model: body.model ?? llmSettings.model,
        api_mode: body.api_mode ?? llmSettings.api_mode,
        has_api_key: Boolean(body.api_key) || llmSettings.has_api_key,
        masked_api_key: body.api_key
          ? `****${body.api_key.slice(-4)}`
          : llmSettings.masked_api_key,
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          message: "LLM settings saved.",
          ...llmSettings,
          settings: llmSettings,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, ...llmSettings, settings: llmSettings }),
    });
  });
  await page.route("**/api/settings/llm/test", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: "LLM connection test passed.",
        ...llmSettings,
        settings: llmSettings,
      }),
    });
  });
  await page.route("**/api/chat", async (route) => {
    const body = route.request().postDataJSON() as { message?: string };
    const nextSnapshot = {
      ...snapshot,
      chat: {
        messages: [
          {
            role: "user",
            content: body.message ?? "",
            created_at: "2026-07-01T00:00:00Z",
          },
          {
            role: "assistant",
            content: `Fallback reply: ${body.message ?? ""}`,
            created_at: "2026-07-01T00:00:01Z",
          },
        ],
      },
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        mode: "rule_based",
        reply: `Fallback reply: ${body.message ?? ""}`,
        state: nextSnapshot,
      }),
    });
  });
  await page.route("**/api/chat/abort/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        stream_id: "mock-stream",
        aborted: true,
      }),
    });
  });
}

function stateCheckForSnapshot(snapshot: Record<string, unknown>) {
  const workspacePath = String(
    snapshot.workspace_path ?? "C:/tmp/physical-agent-workspace",
  );
  return {
    ok: true,
    ready: Boolean(snapshot.ready ?? true),
    message: "State backend is ready.",
    backend: "sqlite",
    backend_role: "recommended",
    backend_label: "SQLite recommended backend",
    source_of_truth: `${workspacePath}/state.db`,
    payload_format: "JSON payloads inside SQLite tables",
    human_view: "export-audit creates a read-only audit view",
    safety_source: `${workspacePath}/SAFETY.md`,
    runtime_switch_supported: false,
    switching_model:
      "Change workspace.backend in config and restart the process; there is no GUI live backend switch.",
    recommendation:
      "Use workspace/state.db as the state source of truth; SAFETY.md remains the file source for safety rules.",
    workspace_path: workspacePath,
    workspace_initialized: Boolean(snapshot.ready ?? true),
    audit_dir: `${workspacePath}/audit`,
    audit_export_writable: true,
    sqlite_schema_complete: true,
    sqlite_chunk_schema_complete: true,
    sqlite_missing_tables: [],
    sqlite_missing_action_columns: [],
    sqlite_missing_memory_columns: [],
    sqlite_missing_upload_columns: [],
    sqlite_missing_chunk_columns: [],
  };
}

function sseEvent(id: number, type: string, payload: Record<string, unknown>) {
  return `event: ${type}\ndata: ${JSON.stringify({
    id,
    type,
    ts: "2026-07-01T00:00:00Z",
    payload,
  })}\n\n`;
}

function parseSseEvents(body: string): Array<{
  type: string;
  payload: Record<string, unknown>;
}> {
  const events: Array<{ type: string; payload: Record<string, unknown> }> = [];
  for (const block of body.split(/\r?\n\r?\n/)) {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) {
      continue;
    }
    const parsed = JSON.parse(data) as {
      type?: unknown;
      payload?: unknown;
    };
    if (
      typeof parsed.type === "string" &&
      parsed.payload !== null &&
      typeof parsed.payload === "object" &&
      !Array.isArray(parsed.payload)
    ) {
      events.push({
        type: parsed.type,
        payload: parsed.payload as Record<string, unknown>,
      });
    }
  }
  return events;
}

function publishE2eCapabilities() {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
  const configPath = path.join(projectRoot, ".tmp", "e2e", "physical-agent.yaml");
  const executable =
    process.env.PA_E2E_CLI ??
    (process.platform === "win32"
      ? path.join(projectRoot, ".venv", "Scripts", "physical-agent.exe")
      : "physical-agent");
  execFileSync(executable, ["setup", "--config", configPath], {
    cwd: projectRoot,
    encoding: "utf8",
    stdio: "pipe",
  });
}

async function installMockChatStream(
  page: Page,
  chunks: string[],
  delayMs = 250,
) {
  await page.addInitScript(
    ({ chunks, delayMs }) => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (!url.includes("/api/chat/stream")) {
          return originalFetch(input, init);
        }
        const encoder = new TextEncoder();
        const signal = init?.signal;
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            let aborted = false;
            signal?.addEventListener("abort", () => {
              aborted = true;
              controller.error(new DOMException("Aborted", "AbortError"));
            });
            const push = (index: number) => {
              if (aborted) {
                return;
              }
              if (index >= chunks.length) {
                controller.close();
                return;
              }
              controller.enqueue(encoder.encode(chunks[index]));
              window.setTimeout(() => push(index + 1), delayMs);
            };
            push(0);
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      };
    },
    { chunks, delayMs },
  );
}

async function installControlledChatStream(
  page: Page,
  chunks: string[],
  releaseAfter: number,
) {
  await page.addInitScript(
    ({ chunks, releaseAfter }) => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (!url.includes("/api/chat/stream")) {
          return originalFetch(input, init);
        }
        const encoder = new TextEncoder();
        let release: (() => void) | null = null;
        const releasePromise = new Promise<void>((resolve) => {
          release = resolve;
        });
        (
          window as typeof window & { __releaseChatStream?: () => void }
        ).__releaseChatStream = () => release?.();
        const stream = new ReadableStream<Uint8Array>({
          async start(controller) {
            init?.signal?.addEventListener("abort", () => {
              controller.error(new DOMException("Aborted", "AbortError"));
            });
            for (let index = 0; index < chunks.length; index += 1) {
              if (index === releaseAfter) {
                await releasePromise;
              }
              controller.enqueue(encoder.encode(chunks[index]));
            }
            controller.close();
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      };
    },
    { chunks, releaseAfter },
  );
}

async function installGatedChatStream(
  page: Page,
  chunks: string[],
  gatedBefore: number[],
) {
  await page.addInitScript(
    ({ chunks, gatedBefore }) => {
      const originalFetch = window.fetch.bind(window);
      let release: (() => void) | null = null;
      (
        window as typeof window & { __releaseNextChatChunk?: () => void }
      ).__releaseNextChatChunk = () => {
        const current = release;
        release = null;
        current?.();
      };
      window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (!url.includes("/api/chat/stream")) {
          return originalFetch(input, init);
        }
        const encoder = new TextEncoder();
        const gatedIndexes = new Set(gatedBefore);
        const stream = new ReadableStream<Uint8Array>({
          async start(controller) {
            init?.signal?.addEventListener("abort", () => {
              controller.error(new DOMException("Aborted", "AbortError"));
            });
            for (let index = 0; index < chunks.length; index += 1) {
              if (gatedIndexes.has(index)) {
                await new Promise<void>((resolve) => {
                  release = resolve;
                });
              }
              controller.enqueue(encoder.encode(chunks[index]));
            }
            controller.close();
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      };
    },
    { chunks, gatedBefore },
  );
}

async function releaseNextChatChunk(page: Page) {
  await page.evaluate(() => {
    (
      window as typeof window & { __releaseNextChatChunk?: () => void }
    ).__releaseNextChatChunk?.();
  });
}

async function installUnavailableChatStream(page: Page) {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (url.includes("/api/chat/stream")) {
        return Promise.resolve(new Response("{}", { status: 404 }));
      }
      return originalFetch(input, init);
    };
  });
}
