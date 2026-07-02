# 追溯矩阵（活文档：里程碑 ↔ 提交 ↔ 测试 ↔ 状态）

> **这是账本，不是快照。** 每轮 session 收尾时更新对应行（新增里程碑加一行，状态变化改一格），代替事后大盘点。
> 基线：`8fa197a`（重构前）· 当前对照 HEAD：`3a807e7` · 最后更新：2026-07-02
> 状态图例：✅ 完成 · 🟡 部分/降级 · ⚪ 未开工 · ⏸ 主动延后

## 维护规则（3 条）

1. 每轮 session 结束：本表加/改一行 → commit → **push**。
2. 里程碑中途拆分（如 A1.7→a/b）：拆成两行，不许一行记两种状态。
3. 状态以"验收测试通过"为准，不以"代码写完"为准。

## 已落地里程碑（按执行顺序）

| 里程碑 | 目标 | 提交 | 关键测试 | handoff | 状态 |
| --- | --- | --- | --- | --- | --- |
| P0/P1/D0 | 冻结安全边界与验收；driver 预留 heartbeat/halt | `8261e93` | test_safety_boundaries, test_driver_contract | session-handoff-p0-p1-d0 | ✅ |
| P1.5 | proposal-only OpenAI 工具循环 | `8261e93` | test_tool_loop | session-handoff-p1.5-tool-loop | ✅ |
| A3 | rolling summary 上下文压缩 | `0a67ebb` | test_chat_protocol, test_chat_runtime | session-handoff-a3 | ✅ |
| B1 | StateStore 抽象 + factory | `b193321` | test_state_store | session-handoff-b1 | ✅ |
| B2 | opt-in SqliteStateStore + 迁移命令 | `f9728e4` | test_state_store | session-handoff-b2 | ✅ |
| B3 | 两 backend 人类可读 audit export | `d3be149` | test_state_store, test_backend_matrix | session-handoff-b3 | ✅ |
| B3.5 | action board 原子契约 | `4698fa0` | test_state_store, test_watch_runtime | session-handoff-b3.5 | ✅ |
| B3.6 | SQLite lease + stale 恢复 | `46f4079` | test_state_store, test_watch_runtime | session-handoff-b3.6 | ✅ |
| B3.7 | backend 矩阵测试 + state-check 诊断 | `1a3c3a4` | test_backend_matrix | session-handoff-b3.7 | ✅ |
| B3.8 | 默认 backend 切 SQLite | `2d33bb4` | test_quickstart_doctor | session-handoff-b3.8 | ✅ |
| B4a | 结构化记忆（kind/tags/importance） | `5192bc8` | test_chat_protocol, test_backend_matrix | session-handoff-b4a | ✅ |
| B4b | 文本文件摄入（ingest-file/upload） | `3c68d94` | test_file_ingestion | session-handoff-b4b | 🟡 仅文本，PDF→A1.5 |
| B4c | 检索地基（关键词，默认关） | `35c0058` | test_retrieval_foundation | session-handoff-b4c | 🟡 向量 RAG 延后 |
| C1 | FastAPI proposal-only 后端 | `3cca4bd` | test_api_server | session-handoff-c1 | ✅ |
| C1.1 | API 测试依赖（httpx）收口 | `c7a366e` | test_api_server | session-handoff-c1.1 | ✅ |
| C2 | 常驻 watch + SSE 事件 | `77d550a` | test_api_watch_events | session-handoff-c2 | ✅ |
| C3 | React+AntD 仪表盘 + 浏览器上传 | `4a496ae` | frontend/e2e/dashboard.spec.ts | session-handoff-c3 | ✅ ⚠️重写丢了旧 GUI reset/硬件面板→A1.7/A1.8 |
| C3.1 | 侧栏重设计稳定 + Playwright e2e | `8c6a5cc` | frontend/e2e/dashboard.spec.ts | session-handoff-c3.1 | ✅ |
| C3.2 | GUI QA/边界硬化 | `0832c0a` | frontend/e2e/dashboard.spec.ts | session-handoff-c3.2 | ✅ |
| D1 | Transport 抽象 + WebSocket | `55addad` | test_transport_websocket, test_xiaozhi_mcp_driver | session-handoff-d1 | ✅ |
| D2 | Serial + Loopback 传输 | `7b1706a` | test_transport_serial, test_transport_loopback | session-handoff-d2 | 🟡 无真实串口 driver |
| D3 | heartbeat/halt 挂入 watch 循环 | `14c9dcb` | test_watch_runtime | session-handoff-d3 | ✅ |
| D3.1 | watchdog 失败阈值策略 | `bc12329` | test_watch_runtime | session-handoff-d3.1 | ✅ |
| 实机回归 | moce 臂 bring-up 回归 | `9cb1978` | （实机手工） | session-handoff-hardware-bringup | ✅ |
| D4 | 实机准备清单文档 | `25c41e1` | — | session-handoff-d4-hardware-docs | ✅ |
| A1.0/A1.1 | 官方 OpenAI SDK 替换 | `9c25e90` | test_openai_compatible, test_tool_loop | session-handoff-a1.0-a1.1 | ✅ |
| A1.6a | LLM settings（.llm.json）+ API chat 桥 | `affbda7` | test_api_server | session-handoff-a1.6a | ✅ |
| A1.2/A1.4 | 流式 chat + abort | `605015c` | test_openai_compatible, test_api_server, test_chat_runtime | session-handoff-a1.2-a1.4 | ✅ |
| B5 | state backend 口径收口 + state-check 语义 | `b5b6071` | test_backend_matrix, test_api_server | session-handoff-b5 | ✅ |
| A1.3a | 默认深度思考（reasoning 参数） | `3a807e7` | test_openai_compatible, test_chat_runtime | session-handoff-a1.3a | ✅ |
| A1.7a | 会话级重置（/api/chat/reset + GUI 按钮） | `605015c` 内含 | test_api_server, e2e reset-chat-button | session-handoff-a1.2-a1.4 | ✅ |
| E0.1 | 工作区级重置（/api/workspace/reset + Danger Zone） | 待 commit | test_api_workspace_reset_* ×2 | session-handoff-e0-gui-parity | ✅ 已实现待提交 |
| E0.2 | 硬件接入面板（/api/integrate + Hardware 页）+ RobotsPanel 连接列 | 待 commit | test_api_integrate_* ×2 | session-handoff-e0-gui-parity | ✅ 已实现待提交（e2e 未补） |
| E0.3-lite | 配置只读视图（/api/config）+ 一键注册 robot（/api/config/robots + ConfigPanel/注册表单） | 待 commit | test_api_get_config_*, test_api_register_robot_* ×3 | session-handoff-e0.3-config-lite | ✅ 已实现待提交（e2e 未补） |

## 未落地里程碑（backlog）

| 里程碑 | 目标 | 归属计划 | 状态 |
| --- | --- | --- | --- |
| A1.5 | PDF 摄入（抽文本，扫描件明确拒绝） | plan-a1 §A1.5 / plan-e1 §E4 | ⚪ |
| A1.8c-full | 通用配置编辑器（改已有 robot / watch/agent 段） | 有真实使用需求再排 | ⏸ E0.3-lite 已覆盖注册场景 |
| E0-e2e | Hardware 注册流程 + ConfigPanel + Danger Zone 的 Playwright 用例 | plan-e1 §E0 验收补遗 | ⚪ |
| C4 | 前端 zh/EN i18n（核实确认未做） | plan-e1 §E3.1 | ⚪ |
| E1.x | 聊天体验（markdown/提案卡片/重试） | plan-e1 §E1 | ⚪ |
| E2.x | 仪表盘实时化 + Actions 看板增强 | plan-e1 §E2 | ⚪ |
| B4-vec | 真实向量 RAG（sqlite-vec + embedding） | optimization-spec §4 | ⏸ |
| D2b | ServoBus 舵机协议层（Feetech/Dynamixel） | optimization-spec §7.3 | ⏸ |
| 多模态 | 图像等多模态输入 | 待定 | ⏸ |

## 工程基建欠账（非功能，影响流程可信度）

| 项 | 现状（2026-07-02） | 建议 |
| --- | --- | --- |
| CI | 无 `.github/`，无任何 CI | pytest(3.11/3.12) + 前端 build + e2e smoke |
| 分支 | `codex/openai-tool-loop-foundation` 领先 main 29 提交，未 push 未 PR | 合并或 push 打 tag |
| 未提交文件 | 工作区 128 个改动/未跟踪（含本 docs 数份） | 纳入版本控制 |
| 测试环境耦合 | 测试读宿主 env（代理变量）、doctor 断言 Python 版本 | env-scrub fixture |
