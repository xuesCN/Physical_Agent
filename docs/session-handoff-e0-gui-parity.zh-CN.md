# Session Handoff: E0 GUI 功能对齐（E0.1 + E0.2）

> 范围：E0.1 工作区级重置 + E0.2 硬件接入面板/机器人连接信息。E0.3 配置面板未做（按用户决定留下轮）。
> Brief：`next-session-e0-gui-parity.zh-CN.md` · 计划来源：`plan-e1-gui-ux.zh-CN.md` §E0
> 未 commit，未 push——**工作区仍有大量历史未提交文件，建议本轮连同 docs 一起 commit。**

## 修改范围

### 后端 `physical_agent/api/server.py`
- 新增请求模型：`WorkspaceResetRequest {confirm}`、`IntegrateRequest {source, name?, output?, llm?, model?}`。
- `POST /api/workspace/reset`：`confirm != true` 返回 400；执行 `store.initialize(overwrite=True)` 纯 state 侧 re-init；append_log + `_publish_state("workspace_reset")`。
- `POST /api/integrate`：复用 `HardwareIntegrationAssistant`（脚手架）/ `DriverCodingAgent`（LLM 草稿），行为对齐旧 GUI `integrate_hardware()`；空 source 400；异常归一为 400 + message。

### 前端 `frontend/src/`
- `types.ts`：`WorkspaceResetResponse`、`IntegrateResult/Response/Payload`、`IntegrationSourceProfile`。
- `api.ts`：`resetWorkspace()`（固定发 `confirm: true`，确认交互在 UI 层）、`integrateHardware()`。
- `SidebarNav.tsx`：新增 Hardware 页（`nav-hardware`）。
- `components/HardwarePanel.tsx`（新）：source/name/output/mode(scaffold|llm)/model 表单 + 结果展示（output_path、transport/robot_kind、generated_files、validation checks/errors、next_steps）；顶部固定"Proposal-side only"边界提示。
- `RobotsPanel.tsx`：新增 Health / Endpoint-Port / Mode 列，读 `state.world.robots[id]` 的 `status|endpoint|url|port|serial_port|address|mode|transport` 字段，缺省显示 `-`（mock driver 即此情况）。
- `SettingsPanel.tsx`：底部 Danger Zone——警示 Alert + `Popconfirm` 二次确认 + `reset-workspace-button`；成功/失败反馈 `reset-workspace-feedback`。
- `App.tsx`：hardware 页路由（HardwarePanel + RobotsPanel）；`onWorkspaceReset` 清空本地流式消息后整体换 state。

## 设计决定（偏离 plan 原文，已回写 brief）

plan-a1 §A1.7b 原文是"复用 `setup(force=True)`"，但 `setup_project` 会实例化 `WatchRuntime`，与 C1 冻结的不变量**"API 不实例化 watch/driver"**（`test_api_requests_do_not_instantiate_watch_or_execute_driver` 用 monkeypatch 强制断言）冲突。故改为 `store.initialize(overwrite=True)`，由此：

1. `physical-agent.yaml` **不被覆盖**（旧 GUI Reset 会重写默认配置，覆盖用户 robots 配置——新行为更安全）。
2. capabilities 不在 API 侧重发，等 watch 下轮循环重发（`--watch` 服务或独立 watch 进程）。
3. `workspace/.llm.json` 保留（`initialize` 不删目录，实测确认）。
4. 新增回归测试：reset 期间 `WatchRuntime.__init__` 被 patch 为抛错，验证不变量守住。

## 测试结果

- 后端：`tests/test_api_server.py` 新增 4 用例（reset 缺 confirm 400 / reset 清空且不碰 watch 且保留 yaml / integrate 生成 scaffold / integrate 空 source 400）。全量 **239 用例 235 passed**；4 个失败均为验证环境因素（SOCKS 代理注入 SDK 客户端 ×3、验证沙盒 Python 3.10 被 doctor 正确拒绝 ×1），代理变量清除后相关用例全过（44/44）。
- 前端：`tsc -b` 通过；`vite build` 通过（3246 模块；沙盒内存所限使用 `--minify false`，产物未回写仓库）。
- e2e：现有 `dashboard.spec.ts` 按 testid 点击、不枚举导航全集，新导航项不破坏现有用例；**新面板的 e2e 未补**（见欠账）。

## 验证环境备注（非代码问题）

验证沙盒为 Linux + Python 3.10 + Windows 宿主挂载：需 `datetime.UTC` shim、清除代理变量、Linux 版 esbuild/rollup 原生二进制（与 lock 版本严格一致）。用户本机（Python 3.12 + Windows node）无需任何处理。

## 用户侧待办

1. `cd frontend && npm run build`——FastAPI 托管的是 `frontend/dist`，不重建看不到新 UI（dev 模式 `npm run dev` 也可）。
2. 建议 commit：本轮代码 + docs（含 brief/handoff/矩阵/INDEX）+ 历史未提交文件。

## 留下的欠账

- E0.3 配置面板（A1.8c）：GUI 展示/编辑 `physical-agent.yaml`，本轮未做。
- 新面板 e2e：hardware 页表单流程、danger zone 确认流程。
- RobotsPanel 的 endpoint 对 mock driver 显示 `-` 属预期；接入 xiaozhi/串口 driver 后才有实值，届时可回头核对字段名。
