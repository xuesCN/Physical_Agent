# Session Handoff: C3.1 GUI redesign stabilization + e2e smoke

> 目标：保留用户重设计后的 React dashboard，并将其收口为可构建、可浏览器 smoke 的 C3.1 版本。未 push，未开 PR。

## 已完成范围

- 保留并整理当前 redesign：
  - sidebar navigation：Overview / Actions / World / Robots / Memory / Safety / Events / Settings。
  - 顶部 `StatusBar`：backend、workspace ready、watch、SSE、proposal-only 状态。
  - 主工作区 + 右侧 proposal inspector；窄屏保留移动端 proposal drawer。
  - `ContextTabs`、`RobotsPanel`、`SettingsPanel` 作为正式面板保留。
- 补充 UI 稳定点：
  - 为核心面板和导航加 `data-testid`，方便 e2e 稳定定位。
  - `ActionBoard` 增加固定表格布局、空态文案和横向滚动保护。
  - Chat sender 明确 Enter 提交，并保留 proposal-only chat 行为。
  - Proposal action 的 Params JSON 解析错误会回填表单错误，不再变成不可见异常。
  - 补充长文本换行、Settings/Events/Memory 溢出保护。
- 新增 Playwright e2e：
  - `frontend/playwright.config.ts`
  - `frontend/e2e/dashboard.spec.ts`
  - `frontend/package.json` 新增 `test:e2e`
  - `@playwright/test` 加入 frontend devDependency。
- `.gitignore` 新增：
  - `frontend/playwright-report/`
  - `frontend/test-results/`

## 构建说明

PowerShell 下不要直接用 `npm run build`，使用：

```powershell
cd frontend
npm.cmd install
npm.cmd run build
```

也可以使用：

```powershell
cmd.exe /c npm run build
```

原因：Windows PowerShell 可能优先命中 `npm.ps1` shim，受执行策略或 shell 行为影响；`npm.cmd` / `cmd.exe /c npm ...` 更稳定。

## Vite chunk warning

`vite.config.ts` 已增加轻量 `manualChunks`：

- `react-vendor`
- `antd-vendor`
- `antd-x`
- `markdown-vendor`

最终 build 无 Vite chunk-size warning、无 circular chunk warning。`antd-vendor` 约 1.03 MB minified，因此 `chunkSizeWarningLimit` 设置为 `1100`，这是在 manualChunks 拆出 React/Markdown/AntD X 后对 AntD vendor 实际体量的记录，不是单纯掩盖原始单包输出。

## 启动后端

默认不启动 watch：

```powershell
.\.venv\Scripts\physical-agent.exe api --config physical-agent.yaml --host 127.0.0.1 --port 8766
```

本轮未改变默认行为；不传 `--watch` 时不会启动 watch。

## 前端 e2e

运行：

```powershell
cd frontend
npm.cmd run test:e2e
```

Playwright config 会启动：

- backend: `..\.venv\Scripts\physical-agent.exe api --config ..\physical-agent.yaml --host 127.0.0.1 --port 8766`
- frontend: `npm.cmd run dev -- --port 5173`

覆盖：

- dashboard 首页非空渲染。
- sidebar 切换 Overview / Actions / Memory / Events / Settings。
- `/api/state` 返回 `ready: true` 和 backend。
- Chat 输入发送后显示 assistant 响应。
- Upload 面板存在。
- 未出现 Vite framework error overlay。
- 收集 console error，并断言为空。

## Browser 验证情况

已尝试 Browser 插件路径：

- Browser runtime 可调用，但 `agent.browsers.get("iab")` 返回 `Browser is not available: iab`。
- `agent.browsers.list()` 返回 `[]`。

因此本轮浏览器验证使用本地 Playwright。首次运行 e2e 时本机缺少 Chromium，随后运行：

```powershell
npx.cmd playwright install chromium
```

Chromium headless shell 下载成功；安装命令末尾出现一次 CDN timeout 但退出码为 0。随后真实运行 `npm.cmd run test:e2e` 通过。

## 验证结果

已运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_api_watch_events.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd install
npm.cmd run build
npm.cmd run test:e2e
```

结果：

```text
targeted API/watch/safety pytest: 16 passed, 1 warning
full pytest: 165 passed, 1 warning
npm.cmd install: up to date
npm.cmd run build: passed, no Vite warnings
npm.cmd run test:e2e: 1 passed
```

warning：Python warning 仍是 FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示。

## 安全边界

- 未改 `/api/upload` 安全语义。
- `/api/upload` 仍只写 API 控制的 untrusted uploads / memory / chunks / audit。
- `physical-agent api` 默认不启动 watch。
- 请求 handler 不调用 `WatchRuntime` / `SafetyGate` / `driver.execute`。
- 前端未新增 execute / halt / driver 控制按钮；task/action 仍是 proposal-only。

## 下一步建议

1. C3.2 GUI polish / QA：补移动端截图检查、空 workspace 状态、更多表单校验、SSE reconnect 可视状态。
2. D1 transport：等 GUI QA 稳定后再进入 transport 抽象，不从 GUI 暴露直接硬件执行入口。

