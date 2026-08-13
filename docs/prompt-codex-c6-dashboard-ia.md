# Codex prompt（C6：Dashboard 信息架构重排）

> 第二轮 / 共两轮。**必须在 C5 完成并推送后执行。** 复制分隔线之间的内容粘贴进新 session。

---

在 Physical_agent 仓库执行 **C6：Dashboard 信息架构重排**。

先读 `AGENTS.md` 走完开工流程。本轮规格已定稿：`docs/design/ui-redesign-spec.zh-CN.md` 的 **A.1–A.5 节**，配套可点击原型 `docs/design/dashboard-ia-redesign.html`（浏览器打开或直接读源码）。诊断依据见 `docs/brief-frontend-optimization-review.zh-CN.md` §4.6。规格已经过讨论定稿，按它执行，不要重新设计。

**范围**：导航 9→8、页面组件重组、ContextTabs 行为收敛、提案栏按需展开、ActionBoard 三态折叠。改动集中在 `renderPageContent()` 与 `SidebarNav`，组件本身基本是"搬家 + 加开关"，不需要重写。不改任何 Python 文件、不碰后端契约、不引入路由库或状态管理库。

## 坑（查代码查不出来的，务必注意）

1. **ActionBoard 的折叠是安全语义，不是样式偏好。** 它是审批入口——`requires_approval` 的动作卡在 pending 等人点批准。规格 A.5 的第三态"待审批时强制展开且不可折叠"是硬要求，优先级高于用户的 localStorage 偏好。做完必须有正向 e2e 断言。

2. **上一轮的推理摘要 e2e 会失败，这是预期内的。** `832519e` 新增的用例里有 `page.goto("/")` 后直接找 `data-testid="reasoning-summary"`，隐含"默认落地页有 chat"的假设。ChatPanel 迁出 overview 后必然失败，加一步导航到「对话」页即可——**不是回归 bug，更不要因此放弃迁移**。

3. **提案栏要真的按需挂载，不能只改宽度。** 附带收益是 ProposalPanel 在多数页面不再挂载，聊天流式输出时的整树重渲染随之消失（诊断 brief §2 的 P1 性能问题）。只把宽度改成 0 而组件仍挂载，等于白做。`<1080px` 已有收起机制，复用它，别另写一套。

4. **退役 page key 前逐项确认内容已被新页覆盖。** `world`/`safety`/`robots` 三个 key 要退役，按 R0-R8 的老规矩：删除要有证据，不能推定"应该没人用"。

5. **ContextTabs 的收敛是本轮核心价值。** 现状是侧栏和页签两套导航打架（在「世界」页点页签切到「安全」，内容变了但侧栏高亮不变）。改完后任何页面都不得出现"侧栏说 A、内容显示 B"。

## 验收

按 `AGENTS.md` 收工要求走。额外要求：ActionBoard 三态可复现且待审批时无法折叠；提案栏的展开/收起选择被记住；推理摘要 e2e 已适配新导航并通过。`frontend/tools/ui-screenshots.mjs` 可用于自查。

有分歧或发现规格与代码实际不符（比如某组件强依赖当前所在页面的 props、或按需挂载破坏了既有 e2e 前置条件），先停下来说明，不要自行改设计。

---
