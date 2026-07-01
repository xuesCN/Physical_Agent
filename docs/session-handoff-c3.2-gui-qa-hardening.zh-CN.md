# Session Handoff: C3.2 GUI QA / edge hardening

> 目标：在 React dashboard 与 Playwright e2e 基础上补齐真实使用边界：移动端布局、空/未初始化 workspace、真实浏览器上传、SSE 断线可见状态，以及上传/表单错误的稳定 UI 呈现。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`8c6a5cc Stabilize redesigned React dashboard`
- 开始前 `git status --short` 无输出，工作区干净。

## 已完成范围

- 新增 brief：
  - `docs/next-session-c3.2-gui-qa-hardening.zh-CN.md`
- GUI 状态硬化：
  - `GET /api/health` / `GET /api/state` 的 `ok:false` body 现在会进入 UI 快照流，不再被前端当作普通异常吞掉。
  - 主工作区新增 `workspace-notice`，缺配置、workspace 未初始化、API snapshot 不可用、初始加载都有清晰状态，不空白。
  - 状态栏 SSE 文案改为可定位的 `SSE disconnected; polling fallback active`；原有轮询 fallback 保持。
  - 移动端 proposal drawer 入口增加稳定测试锚点，折叠 sidebar 下导航图标仍可被 e2e 真实点击。
- Upload 体验硬化：
  - 成功上传在 Upload 面板内显示 filename、size、untrusted proposal context。
  - unsupported type 与超过 5MB 在 Upload 面板内显示可见错误。
  - 成功路径仍调用真实 `/api/upload`；本轮未改变后端上传安全语义。
- Proposal 表单硬化：
  - Params JSON 语法错误使用稳定表单错误文案：`Params JSON is invalid...`
  - 机器人、能力、params、submit 增加稳定 e2e 定位点。

## Playwright e2e 覆盖

`frontend/e2e/dashboard.spec.ts` 扩展为 8 个 Chromium 测试：

- desktop dashboard smoke：首屏、核心面板切换、chat、Upload 面板、console error 为空。
- mobile smoke：390x844 viewport，打开 proposal drawer，切到 Memory / Events / Settings。
- 真实浏览器上传一个小 `.md` 文件，并通过 `/api/search-memory` 断言 untrusted upload chunk 可检索。
- unsupported `.pdf` 上传显示面板错误。
- 超过 5MB 的 `.md` 上传显示面板错误。
- proposal params 非 JSON 显示表单校验错误。
- mock config missing 状态：dashboard 非空白，workspace notice 可见，SSE disconnected 可见。
- mock workspace not initialized 状态：dashboard 非空白，Settings 显示 not ready。

所有 e2e 都收集 `console.error` 与 `pageerror`，当前没有需要过滤的已知 warning。

## Browser 验证情况

Browser skill / runtime 可加载，但当前没有 in-app Browser 实例：

- `agent.browsers.get("iab")` 返回：`Browser is not available: iab`
- 读取 `bootstrap-troubleshooting` 后执行 `agent.browsers.list()`，结果为 `[]`

因此本轮渲染验证继续使用本地 Playwright。未使用 Chrome 或其它浏览器控制面绕过 Browser 插件。

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
cd ..
git diff --check
```

结果：

```text
pip install -e .[dev,server]: passed
targeted API/watch/safety pytest: 16 passed, 1 warning
full pytest: 165 passed, 1 warning
npm.cmd install: up to date
npm.cmd run build: passed, no Vite warnings
npm.cmd run test:e2e: 8 passed
git diff --check: passed
```

warning：

- Python warning 仍是 FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示。
- `git diff --check` 只有 Windows 换行提示，退出码为 0。

## 安全边界

- `/api/upload` 安全语义未改变：只写受 API 控制的 untrusted uploads / memory / chunks / audit。
- `physical-agent api` 默认不启动 watch。
- 请求 handler 不调用 `WatchRuntime` / `SafetyGate` / `driver.execute`。
- 前端未新增 execute / halt / driver 控制按钮；task/action 仍只 proposal-only。
- 本轮未修改 `physical_agent/api/server.py` 的执行边界。

## 未完成 / 下一步建议

- 未做 D1/D2 transport。
- 未接 Agents SDK。
- 未接 OpenAI embeddings 或 sqlite-vec。
- 未做跨浏览器矩阵；当前 e2e 为 Chromium。
- C3.2 GUI QA 已稳定，可以进入 D1 transport 设计/实现；进入 D1 时仍应保持 GUI 不暴露直接硬件执行入口，执行路径继续是 proposal -> watch -> SafetyGate -> driver。
