/**
 * UI 审查截图脚本（本机运行，不属于 e2e 套件，不影响 CI 用例数）。
 *
 * 用途：把 Dashboard 每个页面在 亮/暗 × 多个视口下截图，
 * 输出到 .tmp/ui-review/（已 gitignore），用于视觉走查或交给 AI 做视觉审查。
 *
 * 前置：先把后端和前端跑起来（两个终端）
 *   1) .\.venv\Scripts\physical-agent.exe api --watch
 *   2) cd frontend && npm run dev
 *
 * 然后：
 *   cd frontend
 *   node tools/ui-screenshots.mjs                      # 默认 http://127.0.0.1:5173
 *   node tools/ui-screenshots.mjs http://127.0.0.1:8766  # 或直接打包后的 Dashboard
 *
 * 只截图，不点任何提交/审批按钮，不产生任何 action。
 */

import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const BASE_URL = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT_DIR = path.resolve("../.tmp/ui-review");

const PAGES = [
  "overview",
  "actions",
  "world",
  "robots",
  "hardware",
  "memory",
  "safety",
  "events",
  "settings"
];

const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "laptop-1280", width: 1280, height: 800 },
  { name: "narrow-1024", width: 1024, height: 768 }
];

const THEMES = ["light", "dark"];

// localStorage keys — 与 src/locales/index.ts 保持一致
const KEY_THEME = "physical-agent-theme";
const KEY_TOUR = "physical-agent-tour-dismissed";

async function shoot(browser, viewport, theme) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 2 // 二倍图，文字更清晰便于审查
  });

  // 预置 localStorage：关掉首次引导 Tour，设定主题
  await context.addInitScript(
    ([keyTheme, keyTour, themeValue]) => {
      localStorage.setItem(keyTheme, themeValue);
      localStorage.setItem(keyTour, "1");
    },
    [KEY_THEME, KEY_TOUR, theme]
  );

  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="dashboard-shell"]', { timeout: 15000 });

  for (const key of PAGES) {
    const nav = page.locator(`[data-testid="nav-${key}"]`);
    if ((await nav.count()) === 0) {
      console.log(`  ! 跳过 ${key}（导航项未找到）`);
      continue;
    }
    await nav.click();
    await page.waitForSelector(`[data-testid="page-${key}"]`, { timeout: 10000 });
    await page.waitForTimeout(600); // 等懒加载页面和动画稳定

    const file = path.join(OUT_DIR, `${viewport.name}_${theme}_${key}.png`);
    await page.screenshot({ path: file, fullPage: true });
    console.log(`  ✓ ${path.basename(file)}`);
  }

  await context.close();
  return consoleErrors;
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log(`目标: ${BASE_URL}`);
  console.log(`输出: ${OUT_DIR}\n`);

  const browser = await chromium.launch();
  const allErrors = [];

  try {
    for (const viewport of VIEWPORTS) {
      for (const theme of THEMES) {
        console.log(`[${viewport.name} / ${theme}]`);
        const errors = await shoot(browser, viewport, theme);
        allErrors.push(...errors);
      }
    }
  } finally {
    await browser.close();
  }

  const unique = [...new Set(allErrors)];
  if (unique.length) {
    console.log(`\n控制台错误 ${unique.length} 条:`);
    unique.slice(0, 10).forEach((e) => console.log(`  - ${e.slice(0, 160)}`));
  } else {
    console.log("\n控制台无错误。");
  }
  console.log(`\n完成，共 ${VIEWPORTS.length * THEMES.length * PAGES.length} 张图。`);
}

main().catch((err) => {
  console.error("失败:", err.message);
  console.error("提示: 确认后端(8766)和前端(5173)都在运行；首次使用需 npx playwright install chromium");
  process.exit(1);
});
