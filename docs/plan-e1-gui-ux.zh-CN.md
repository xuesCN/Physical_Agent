# Phase E 计划：GUI 前端优化与用户体验增强（草案 v0.1）

> 时间：2026-07-02 · 基线 HEAD `3a807e7`
> 前提：主干已稳（见 `system-summary-verification.zh-CN.md`）；本阶段以 GUI/UX 为主轴，穿插还清"纯接线类"欠账。
> 纪律沿用 optimization-spec §0/§9：小步可回滚、默认关闭/向后兼容、**安全边界冻结**（前端一切操作仍是提案侧，不碰 watch/driver 执行）。

---

## E0 先还"纯接线"欠账（1–2 轮，风险低收益高）

这些后端能力全在，只差前端/API 接线，做完 GUI 才算功能对齐旧版：

### E0.1 工作区级重置（= 原 A1.7b）
- API：`POST /api/workspace/reset`（需 `confirm=true`），复用 `setup(force=True)`。
- 前端：Settings 页危险区（Danger Zone），确认弹窗文案明确"清空世界/动作/记忆/对话"。
- 验收：与旧 GUI Reset 等价；会话级/工作区级两入口解耦并存。

### E0.2 硬件接入面板 + 机器人连接信息（= 原 A1.8a/b）
- API：`POST /api/integrate`，复用 `HardwareIntegrationAssistant` / `DriverCodingAgent`。
- 前端：新增 Hardware 页（source/name/model/mode 表单 + 生成结果展示）；RobotsPanel 补 endpoint/port/health 列 + 心跳状态点。
- 边界：生成 driver 仍是"写文件 + mock 验证"，不执行硬件。
- 验收：新 GUI 能像旧 GUI 一样从 source 生成 driver；机器人"连到哪、连没连上"可见。

### E0.3 项目配置面板（= 原 A1.8c，可选）
- 展示/编辑 `physical-agent.yaml` robots/watch/agent 段，`config_schema` 驱动表单校验；保存 = 写回 yaml + re-setup。
- 验收：GUI 可改 `serial_port` 并 re-setup 生效。

## E1 聊天体验升级（GUI 核心场景）

流式/abort/重置已具备，聚焦"用起来舒服"：

- **E1.1 消息渲染**：~~markdown 渲染 + 代码块高亮~~ **已按用户决定搁置（2026-07-02）**——本产品 chat 是提案操作台而非内容阅读器，优先级低；仅保留一键复制/长消息折叠作为可选小项。
- **E1.2 提案内联卡片**：chat 中产生 action proposal 时渲染结构化卡片（robot/action/args/状态），点击跳转 Actions 页对应条目——把"提案→执行→反馈"闭环在界面上讲清楚。
- **E1.3 状态反馈**：发送中/思考中指示、流式中断后"重试"按钮、错误分类提示（key 无效/超时/限流分开说人话）。
- **E1.4 会话滚动**：自动跟随流式输出、向上翻阅时暂停跟随。
- 验收：Playwright e2e 覆盖 markdown 渲染、提案卡片跳转、错误重试。

## E2 仪表盘信息架构与实时性

- **E2.1 Overview 仪表盘化**：关键指标卡片（backend/watch 状态/pending actions 数/最近事件/LLM 连接状态），替代纯文本摘要。
- **E2.2 SSE 全面接入**：各面板统一订阅 `/api/events` 增量刷新（现有 SSE 基建复用），断线重连提示保留。
- **E2.3 Actions 看板增强**：状态流转可视化（pending→in_progress→completed/failed/cancelled）、lease 持有与 stale 恢复标记、失败原因直接展开。
- **E2.4 安全可见性**：SAFETY 约束/审批要求只读展示强化，watchdog 触发 halt 时全局横幅警示。（只展示，不提供绕过入口——边界冻结）
- 验收：mock 双机器人跑 demo 时，全程不手动刷新即可看到状态流转。

## E3 视觉与国际化

- **E3.1 i18n（还清 C4）**：zh/EN 切换，antd `ConfigProvider` locale + 文案抽取；默认跟浏览器语言。
- **E3.2 主题**：暗色模式（antd token 级切换），持久化到 localStorage。
- **E3.3 首次引导**：空 workspace 时向导化（setup → watch 启动 → quick demo），对齐旧 GUI 的 quick demo 心智。
- 验收：语言/主题切换持久；新用户零文档跑通 demo。

## E4 延后大项（非 GUI，另行排期）

| 项 | 归属 | 备注 |
| --- | --- | --- |
| PDF 摄入（A1.5） | 摄入层 | 独立可随时插，`pdfminer.six`/`pypdf` 进可选 extra |
| 真实向量 RAG（sqlite-vec + embedding） | 记忆检索 | 契约已就位，"填实现"而非"改架构" |
| ServoBus 舵机协议层（D2b） | 驱动传输 | 依赖真实舵机硬件到位再做 |
| 多模态输入 | LLM+摄入 | 待场景明确 |

---

## 排期与纪律

- **顺序**：E0 → E1 → E2 → E3（E0 是功能对齐，E1/E2 是体验主菜，E3 是打磨）；E4 独立穿插。
- **每轮照旧**：先写 brief/验收 → 实现 → 测试（前端补 Playwright e2e）→ session-handoff 文档。
- **不可破的四条**：agent/llm/gui 只提案；watch 唯一执行；SafetyGate 不被绕过；新能力默认关闭或向后兼容。

*本计划为草案，E1–E3 内部条目可按实际使用痛点重排；建议每完成一轮更新 REFACTOR-LOG。*
