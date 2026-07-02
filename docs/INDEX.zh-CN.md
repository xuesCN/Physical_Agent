# docs 索引（导航页）

> 60+ 份文档的检索入口。**新增文档时在此登记一行。** 最后更新：2026-07-02
> 状态/进度查询请直接看 [traceability-matrix.zh-CN.md](traceability-matrix.zh-CN.md)（账本），本页只管"文件在哪"。

## 1. 先读这几份（总览/评估）

| 文档 | 内容 |
| --- | --- |
| [optimization-spec.zh-CN.md](optimization-spec.zh-CN.md) | 重构总 spec v0.3：安全不变量 + A/B/C/D 阶段设计 + §10 里程碑 |
| [traceability-matrix.zh-CN.md](traceability-matrix.zh-CN.md) | **活账本**：里程碑↔提交↔测试↔状态（每轮更新） |
| [REFACTOR-LOG.zh-CN.md](REFACTOR-LOG.zh-CN.md) | 重构日志快照（对照 `25c41e1`，A1 部分已过时） |
| [system-summary.zh-CN.md](system-summary.zh-CN.md) | 按子系统的职责/现状/欠账汇总（对照 `25c41e1`，§3/§10 部分已过时） |
| [system-summary-verification.zh-CN.md](system-summary-verification.zh-CN.md) | 上表的逐条核实报告（对照 `3a807e7`，含测试实跑结论） |
| [architecture-boundaries.zh-CN.md](architecture-boundaries.zh-CN.md) | 认知/执行安全边界说明 |
| [current-architecture-overview.svg](current-architecture-overview.svg) | 架构总览图 |
| [readme-compat-audit.zh-CN.md](readme-compat-audit.zh-CN.md) | README 声称 vs 实际行为审计 |

## 2. 计划（未来工作从这里领）

| 文档 | 范围 |
| --- | --- |
| [plan-a1-openai-sdk-chat.zh-CN.md](plan-a1-openai-sdk-chat.zh-CN.md) | A1.0–A1.8：SDK/流式/设置/重置/硬件面板（A1.0–A1.4/A1.6a/A1.7a 已完成） |
| [plan-e1-gui-ux.zh-CN.md](plan-e1-gui-ux.zh-CN.md) | Phase E：GUI/UX 优化主计划（E0 接线欠账 → E1 聊天 → E2 仪表盘 → E3 视觉/i18n） |

## 3. 参考/操作手册

| 文档 | 内容 |
| --- | --- |
| [state-backends.zh-CN.md](state-backends.zh-CN.md) | SQLite/Markdown 后端语义与切换 |
| [sqlite-readiness.zh-CN.md](sqlite-readiness.zh-CN.md) | SQLite 后端就绪矩阵 |
| [hardware-bringup-checklist.zh-CN.md](hardware-bringup-checklist.zh-CN.md) | 实机接入准备清单 |
| [xiaozhi-driver-tutorial.zh-CN.md](xiaozhi-driver-tutorial.zh-CN.md) | 小智 MCP 设备接入教程 |
| `../HANDOFF.zh-CN.md`（仓库根） | 项目级交接总文档 |

## 4. 每轮记录（brief = 开工前 next-session-\*；handoff = 收工后 session-handoff-\*）

命名规律：`next-session-<里程碑>.zh-CN.md` / `session-handoff-<里程碑>.zh-CN.md`，一一对应。

| 阶段 | 里程碑（brief + handoff 成对，除标注外） |
| --- | --- |
| P（地基） | p0-p1-d0（仅 handoff）· p1.5-tool-loop |
| A（LLM/上下文） | a3-rolling-summary · a1.0-a1.1-openai-sdk-chat（仅 handoff，brief 见 plan-a1）· a1.2-a1.4-streaming-abort（仅 handoff）· a1.3a-default-deep-thinking（仅 handoff）· a1.6a-llm-settings-api-chat（仅 handoff） |
| B（状态存储） | b1-state-store-abstraction · b2-sqlite-state-store · b3-audit-export · b3.5-atomic-actions · b3.6-action-lease-recovery · b3.7-sqlite-readiness · b3.8-default-sqlite · b4a-structured-memory · b4b-file-ingestion · b4c-retrieval-foundation · b5-state-backend-realignment（仅 handoff） |
| C（API/GUI） | c1-fastapi-backend · c1.1-api-test-deps · c2-watch-events · c3-gui-foundation · c3.1-gui-e2e · c3.2-gui-qa-hardening |
| D（传输/硬件） | d1-transport-websocket · d2-serial-loopback-transport · d3-watch-heartbeat-halt · d3.1-watchdog-policy · d4-hardware-docs（仅 handoff）· hardware-bringup（仅 handoff） |
| E（GUI/UX） | e0-gui-parity · e0.3-config-lite |

## 5. 登记规则

1. 新 brief/handoff 按命名规律放 docs/，并在 §4 对应阶段行补上里程碑名。
2. 新计划/参考文档在 §2/§3 加一行。
3. 快照类评估文档（如 REFACTOR-LOG）写明"对照 HEAD"，过时后在本页标注。
