# Next Session Brief: C3.2 GUI QA / edge hardening

> 目标：在已完成的 React dashboard 与 Playwright e2e 基础上，补齐真实使用边界：移动端布局、空/未初始化 workspace 状态、真实浏览器上传、SSE 断线可见状态，以及表单/上传错误的稳定 UI 呈现。不要 push，不开 PR。

## 范围

- 保留 C3 redesign：侧边栏、顶部状态栏、主工作区、右侧 proposal inspector、移动端 proposal drawer。
- 移动端 viewport 下 sidebar、status、action table、chat、upload、proposal drawer 不应重叠或不可用。
- 空 workspace、缺配置、workspace 未初始化时，GUI 显示清晰状态，不无限 loading，不空白。
- SSE disconnected 时状态栏有明确状态；轮询 fallback 继续保持。
- Upload 成功/失败有面板内反馈；unsupported type 和超过 5MB 错误在 UI 可见。
- Proposal action 的 Params JSON 解析错误显示在表单里，并通过 e2e 覆盖。
- 扩展 Playwright e2e：desktop smoke、mobile smoke、真实上传成功、unsupported 上传错误、proposal params 非 JSON、空/缺配置状态。

## 不做

- 不做 D1/D2 transport。
- 不接 Agents SDK。
- 不接 OpenAI embeddings 或 sqlite-vec。
- 不改变 watch 执行边界。
- 不新增 execute / halt / driver 控制按钮；task/action 仍只 proposal-only。
- 不提交 `frontend/playwright-report/` 或 `frontend/test-results/`。

## 安全边界

- `/api/upload` 安全语义不变：只写受 API 控制的 untrusted uploads / memory / chunks / audit。
- `physical-agent api` 默认不启动 watch。
- HTTP request handler 不调用 `WatchRuntime` / `SafetyGate` / `driver.execute`。
- 上传与检索内容只作为 proposal context，不是 safety fact。

## Browser / Playwright 路线

- 如 Browser 插件有可用 in-app Browser 实例，优先用 Browser 插件做渲染检查。
- 如果 Browser runtime 可加载但没有 `iab` 实例，记录失败原因，并继续用本地 Playwright 验证 desktop/mobile/交互路径。
- e2e 继续收集 console error；若需要过滤，必须写明已知 warning 原因。

## 验证命令

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

## 交付文档

- 新增 `docs/session-handoff-c3.2-gui-qa-hardening.zh-CN.md`。
- 写清新增 GUI QA 场景、Browser 插件可用性、Playwright 验证情况、build/e2e 命令、仍未做项，以及下一步是否建议进入 D1 transport。
