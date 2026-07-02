# Next Session Brief: E0 GUI 功能对齐（E0.1 + E0.2）

> 目标：还清 C3 重写丢失的两项旧 GUI 能力——工作区级重置、硬件接入面板 + 机器人连接信息。
> 来源：plan-e1-gui-ux §E0.1/§E0.2（原 plan-a1 §A1.7b/§A1.8a/§A1.8b）。
> 范围外：E0.3 配置面板、i18n、聊天体验（E1）。

## 修改范围

### E0.1 工作区级重置（A1.7b）
- 后端 `api/server.py`：
  - `POST /api/workspace/reset`，请求体 `{confirm: true}`；`confirm` 非 true 时 400。
  - **偏离 plan 原文的设计决定**：不走 `setup_project(force=True)`——它会实例化 `WatchRuntime`，与 C1 冻结的不变量"API 不实例化 watch/driver"（`test_api_requests_do_not_instantiate_watch_or_execute_driver`）冲突。改为纯 state 侧 re-init：`store.initialize(overwrite=True)`。
  - 由此的两个语义差异（均更安全）：① `physical-agent.yaml` 不被覆盖（用户机器人配置保留）；② capabilities 不在 API 侧重发，等 watch 下轮循环重发。`.llm.json` 不受影响（initialize 不删目录）。
  - 成功后 append_log + `_publish_state("workspace_reset")`。
- 前端 `SettingsPanel`：Danger Zone 区块，按钮 + 确认弹窗，文案明确"清空世界/动作/记忆/对话，SAFETY 重置为默认"。

### E0.2 硬件接入面板 + 连接信息（A1.8a/b）
- 后端 `api/server.py`：
  - `POST /api/integrate`，请求体 `{source, name?, output?, llm?: bool, model?}`。
  - 复用 `HardwareIntegrationAssistant`（脚手架）/ `DriverCodingAgent`（LLM 草稿），对齐旧 GUI `integrate_hardware()` 行为。
  - 生成仍是"写文件 + mock 验证"，不执行硬件。
- 前端：
  - SidebarNav 新增 Hardware 页；表单（source/name/mode/model）+ 结果展示（output_path、transport/robot_kind、generated_files、next_steps、LLM validation）。
  - `RobotsPanel` 补连接信息列：endpoint/port/mode/health（读自 `state.world.robots`，driver `observe()` 已提供的字段，缺省显示 `-`）。

## 安全边界（不可破）

- 两个新端点都在认知/状态侧：reset 不触碰 watch 执行；integrate 只写文件 + mock 验证。
- SafetyGate 与 watch 的唯一执行权不受影响；`SAFETY.md` 重置为默认属 `setup(force)` 既有语义。

## 验收

1. `POST /api/workspace/reset`（confirm=true）后：chat/actions/memory 清空、workspace 重新初始化、`/api/state` ready；缺 confirm 返回 400。
2. `POST /api/integrate` 用示例 SDK 目录能生成 scaffold，返回 output_path 与 profile；`llm=true` 且无 LLM 时降级或明确报错（对齐 CLI/旧 GUI 行为）。
3. RobotsPanel 显示 mock 机器人 endpoint/mode 信息（mock 无 endpoint 时显示占位）。
4. pytest 新增用例通过；`tsc -b && vite build` 通过。
