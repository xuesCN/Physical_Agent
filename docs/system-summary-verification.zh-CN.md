# system-summary 核实报告 + 重新总结（2026-07-02）

> 核实对象：`docs/system-summary.zh-CN.md`（写于 2026-07-01，对照 HEAD `25c41e1`）
> 核实基准：当前 HEAD `3a807e7` + 源码实扫 + 测试实跑
> **关键发现：summary 写完后又落了 5 个提交（A1.0/A1.1、A1.6a、A1.2/A1.4、B5、A1.3a），原欠账表 10 条中 4 条已还清。**
> 状态图例：✅ 属实 · 🔄 已过时（后续提交已解决） · ⚠️ 属实且仍欠

---

## 1. 逐节核实结论

| summary 章节 | 核实结果 | 证据 |
| --- | --- | --- |
| §1 入口层 | ✅ 属实，但"缺口"半过时 | cli.py 16 命令 + `driver new`；api/server.py 18 端点；旧 GUI reset/硬件面板在；frontend 8 面板全在；mcp 5 工具全在 |
| §1 缺口"新 GUI 缺 reset" | 🔄 **已解决**（A1.7a） | `POST /api/chat/reset` + ChatPanel `reset-chat-button`（带确认）；但 A1.7b 工作区级重置（`/api/workspace/reset`）**仍缺** |
| §1 缺口"缺硬件接入面板" | ⚠️ 属实仍欠 | api/server.py 无 `/api/integrate`；frontend 无 Hardware 面板；RobotsPanel 无 endpoint/port/health |
| §2 认知侧 Agent | ✅ 属实 | 13 个模块文件全部存在，职责与描述一致 |
| §3 LLM"仍 urllib 未换 SDK" | 🔄 **已过时** | `9c25e90` 已换官方 `openai` SDK（`import openai`，pyproject `llm=["openai>=1.40"]`）；错误归一 + key 脱敏 |
| §3 缺口"流式/深思考/abort" | 🔄 **已解决** | `stream_chat_text()`、`respond_stream()`、`/api/chat/stream`(SSE) + `/api/chat/abort/{id}`（`605015c`）；reasoning 默认开启（`3a807e7`） |
| §4 状态·协议层 | ✅ 属实（且增强） | state/ 6 文件 + protocol/ 8 文件全在；B5 后 `state-check` 增 backend 语义字段 + `GET /api/state-check` |
| §5 "PDF 未做" | ⚠️ 属实仍欠 | `ingest/files.py` 仅 `ALLOWED_TEXT_SUFFIXES`，PDF 明确拒绝 |
| §5 "sqlite-vec/embedding 未做" | ⚠️ 属实仍欠 | 全源码 `vec0/sqlite-vec/embedding` 零命中；仅确定性关键词检索，默认关 |
| §6 执行侧 Watch | ✅ 属实 | heartbeat 失败计数、watchdog 阈值触发 halt、关停收尾均在 runtime.py |
| §7 "ServoBus 未做" | ⚠️ 属实仍欠 | 全源码 `ServoBus/feetech/dynamixel` 零命中；transport 4 文件在 |
| §8 配置 | ✅ 属实 | `physical-agent.yaml` 已 `backend: sqlite`；GUI 未暴露（A1.8c 未做） |
| §9 "35 个测试文件" | ✅ 属实 | 实数 35；实跑 235 个测试 **231 通过**，4 个失败全为验证环境因素（SOCKS 代理 ×3、Python 3.10 被 doctor 正确拒绝 ×1），Python≥3.11 无代理环境应全绿 |

## 2. 欠账总表（更新版，对照当前 HEAD）

| # | 原欠账 | 现状 | 说明 |
| --- | --- | --- | --- |
| 1 | 官方 OpenAI SDK | ✅ **已还** | `9c25e90`；base-url 拼接坑同步修复（root 原样传 SDK） |
| 2 | 流式/深思考/abort/异常分类 | ✅ **已还** | `605015c` + `3a807e7`；SDK 异常归一 + 脱敏 |
| 3 | PDF 摄入 | ⚠️ 仍欠 | A1.5，独立可随时插 |
| 4 | 工作台 LLM 配置 | ✅ **已还** | `affbda7`：`workspace/.llm.json` + SettingsPanel 表单 + 测试连接 |
| 5 | 会话/工作区重置 | 🟡 **半还** | A1.7a 会话级已做；A1.7b 工作区级重置未做 |
| 6 | 硬件接入面板 + 连接信息 + 配置面板 | ⚠️ 仍欠 | A1.8a/b/c 全未做（后端能力在，纯接线） |
| 7 | 真实向量 RAG | ⚠️ 仍欠 | 主动延后，契约已就位 |
| 8 | ServoBus 舵机协议层 | ⚠️ 仍欠 | 主动延后（Phase D2b） |
| 9 | 多模态输入 | ⚠️ 仍欠 | 延后探索 |
| 10 | C4 zh/EN 切换核实 | ❌ **核实：未实现** | frontend 无任何 i18n 机制（仅 ActionBoard 一处 emptyText locale）；mojibake 已随 React 重写消除 |

## 3. 重新总结（一句话版）

**主干全部落地且可信**：安全边界（认知只提案 / watch 唯一执行 / SafetyGate 不可绕）全程冻结；SQLite 默认状态存储 + 原子动作/lease/恢复、官方 SDK + 流式 + 深思考 + abort、FastAPI proposal-only 后端、React 仪表盘（含流式聊天、LLM 设置、会话重置）、传输层 + 心跳看门狗——均有测试背书（231/235 实测通过）。

**剩余欠账收敛为两类**：
- **纯接线类**（后端在、前端没接）：A1.7b 工作区重置、A1.8 硬件面板/连接信息/配置面板、C4 i18n——正好是 GUI 优化的主料。
- **主动延后的重活**：PDF 摄入、向量 RAG、ServoBus、多模态。

建议 `system-summary.zh-CN.md` §3 的 🟡 与 §10 的 #1/#2/#4/#5 按本报告更新，避免误导下一轮排期。

---

*核实方法：模块清单 diff、端点/命令 grep 实扫、关键特性代码定位、pytest 全量实跑（Linux 沙盒 Python 3.10 + utc shim）。下一步计划见 `plan-e1-gui-ux.zh-CN.md`。*
