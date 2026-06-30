# Next Session Brief: C3.1 GUI redesign stabilization + e2e smoke

> 目标：在当前 React dashboard redesign 基础上收口 C3.1，不回退到旧三列布局；补最小浏览器端 e2e/smoke，稳定前端构建和明显 UI/API 集成问题，并提交本地 redesign。不要 push，不开 PR。

## 范围

- 保留当前 redesign：侧边栏导航、顶部状态栏、`ContextTabs`、`RobotsPanel`、`SettingsPanel`、移动端 proposal drawer。
- 修明显的响应式布局、溢出、空状态、按钮文案、TypeScript 或 API 集成问题。
- 前端只允许 proposal-only 交互：chat / task submit / action propose 仍只写 proposal/state/memory，不新增 execute、halt、driver control 按钮。
- 增加最小 e2e/smoke：dashboard 非空渲染、侧边栏切换 Overview / Actions / Memory / Events / Settings、`/api/state` ready/backend、chat 发送后 UI 响应、Upload 面板存在、无明显 framework error overlay。

## 不做

- 不做 D1/D2 transport。
- 不做 Agents SDK。
- 不做 OpenAI embeddings 或 sqlite-vec。
- 不改 watch 执行边界。
- 不改 `/api/upload` 的安全语义。
- 不提交 `frontend/node_modules/` 或 `frontend/dist/`。

## 验证路线

1. Python 依赖和回归：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_api_watch_events.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
```

2. 前端依赖、构建、e2e：

```powershell
cd frontend
npm.cmd install
npm.cmd run build
npm.cmd run test:e2e
```

PowerShell 下优先使用 `npm.cmd` 或 `cmd.exe /c npm ...`，避免 PowerShell 直接调用 `npm.ps1` 时触发执行策略或 shim 行为差异。

3. 后端手动启动命令：

```powershell
.\.venv\Scripts\physical-agent.exe api --config physical-agent.yaml --host 127.0.0.1 --port 8766
```

默认不传 `--watch`，因此不会启动 watch。

## 安全边界检查

- `physical-agent api` 默认不启动 watch。
- HTTP request handler 不调用 `WatchRuntime` / `SafetyGate` / `driver.execute`。
- `/api/upload` 只写受 API 控制的 uploads / memory / chunks / audit，上传内容保持 untrusted proposal context。

