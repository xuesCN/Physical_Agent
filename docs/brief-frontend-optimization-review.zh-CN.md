# 评估 brief：React Dashboard 优化审查

> 类型：评估 brief（只审查，未改动任何生产代码）。日期：2026-07-21。
> 口径：R8/R8.1 收口后的 `frontend/` 现状，数字为实测（bundle 为已提交的 `physical_agent/dashboard/dist`）。
> 视觉审查未完成——沙盒无法下载 Chromium，截图脚本已备好待本机执行（见 §5）。

## 0. 结论先行

**不存在紧急问题，但有一个中英混排 bug、一处 i18n 系统性缺口，和一个"一改解决两个问题"的高性价比重构点。**

前端整体工程质量在线：懒加载分包做得细致（连 antd 的 upload/collapse/list 都单独切出去了）、viewmodels 层把格式化逻辑抽离、暗色模式实现干净、响应式在 1024px 下正确降级、状态解释权已在 R2.1 收归服务端。

**优先级速览**（V=视觉审查发现，见 §4.5）

| 级别 | 事项 | 成本 |
| --- | --- | --- |
| P0 | **V1** 动作板「Running」中英混排（`ActionBoard.tsx:73` 硬编码） | 10 分钟 |
| P1 | **A1** 侧栏与页签两套导航打架（世界/安全页状态脱节，见 §4.6） | 半天 |
| P1 | **A2** 主工作流「对话」无导航入口，却被埋在概览页中间列 | 2 小时 |
| P1 | **V2** i18n 缺口：7 个组件零 labels，常驻提案栏 100% 英文 | 半天 |
| P1 | **V3+§2** 提案栏九页常驻 → 挤压布局 **且** 是流式重渲染主因（一改双收） | 半天 |
| P2 | **V4** 空状态占位过大，Overview 页高 2721px（约 3 屏） | 半天 |
| P2 | 无 URL 路由：刷新丢页面、不能深链、后退键退出应用 | 半天 |
| P2 | 无障碍：全仓 `:focus` 样式 0 处、`aria-*` 仅 2 处 | 半天 |
| P3 | **V5-V7** Raw 摘要默认折叠、历史状态徽章降饱和、表格列宽 | 各 1-2 小时 |
| P3 | App.tsx 1014 行上帝组件 | 1-2 天 |
| P3 | antd-vendor 985 KB（本地部署场景，实际影响小） | 不建议动 |

## 1. 体量现状（实测）

```
源码 7251 行 / 17 个文件
  App.tsx            1014   ← 上帝组件
  SettingsPanel       483
  types.ts            480
  HardwarePanel       378
  ChatPanel           329
  api.ts              327
  FeedbackTimeline    317
  ActionBoard         294
  StateOverviewPanel  252
  (其余 < 250)

构建产物（gzip）
  antd-vendor      985 KB → 307 KB   ← 首屏必载，占绝对大头
  react-vendor     140 KB →  45 KB   ← 首屏必载
  markdown-vendor  115 KB →  35 KB
  index             75 KB →  24 KB   ← 首屏必载
  antd-extras       76 KB →  24 KB   ← 已成功延迟到次级页面
  6 个页面 chunk   每个 1-9 KB       ← 懒加载工作正常
  首屏合计 ≈ 335 KB gzip
```

## 2. P1｜流式聊天期间的整树重渲染

**现象**：`App.tsx` 持有 21 个 `useState`，全仓 **0 处 `React.memo`**，且 `renderPageContent({...})` 每次渲染都构造一个新的巨大 props 对象。聊天流式输出时每个 delta 都调 `setStreamMessages`，导致 App 及其所有同屏子组件（StatusBar、WorkspaceNotice、ChatPanel、ProposalPanel）**每个 token 重渲染一次**。

**为什么现在还没炸**：页面是互斥切换的（同一时刻只挂载一个 page content），所以 ActionBoard/FeedbackTimeline 这些重组件在聊天时并不在场——blast radius 被结构性地限制住了。这也是它至今没暴露成 bug 的原因。

**建议改法**（按性价比排序，任选其一即可见效）：

1. 把流式消息状态下沉到 ChatPanel 内部，或用 `useRef` + 局部 state 承接 delta，只让聊天区重渲染；
2. 给 StatusBar / ProposalPanel 加 `React.memo`，同时用 `useCallback` 稳定传入的 handler（现在只有 3 个 useCallback，多数 handler 每次都是新函数，加了 memo 也白加——**两件事必须一起做**）；
3. 顺手：SSE 监听里每个 tick 都执行 `JSON.stringify(payload.state)` 做去重比对（500ms 一次），可改为比较服务端提供的 revision/摘要字段，省掉这次序列化。

**注意**：现有的 idle-tick 去重逻辑（`idleWatchTick` 判断）是对的，别动——那是空闲时不刷新快照的关键优化。

## 3. P2｜两个体验欠账

**无 URL 路由**：`activePage` 是纯 React state，仓库无 `react-router`。后果是刷新页面回到 overview、不能把某个页面链接发给同事、浏览器后退键直接退出应用。对"运维要盯着看"的仪表盘来说这是真实痛点。最轻改法是 `useState` + `history.pushState` + `popstate` 监听（不引路由库，约 30 行）；标准改法是引 react-router（+约 15 KB gzip）。

**无障碍**：`:focus` 样式 **0 处**、`aria-*` 仅 2 处。AntD 组件自带部分焦点样式，但自定义区域（侧栏、卡片、inspector）键盘 Tab 过去完全没有视觉反馈。加一条全局 `:focus-visible` 描边规则就能解决大半，成本极低。

## 4. P3｜可延后项

**App.tsx 1014 行**：21 个 state 混杂了 UI 偏好（语言/主题/侧栏折叠）、服务端数据（state/health/executor/config）、交互状态（busy/prefill/tour）三类关注点。建议按类抽三个自定义 hook（`useAppPreferences` / `useAgentSnapshot` / `useProposalDraft`），不需要引状态管理库。这是可维护性投资，不是性能问题——先做 P1，别一上来大重构。

**antd-vendor 985 KB**：看着吓人，但**部署形态是 localhost 本地工具**，不是公网站点，加载成本主要是解析而非传输。真要减，路径是按需引入 antd 组件或换更轻的组件库——两者都是伤筋动骨的改动，**当前收益不值**。除非将来要做远程访问/弱机器部署，否则建议维持现状。已有的分包策略（antd-extras 延迟、6 个页面 chunk）说明这块已经被认真优化过一轮了。

**CSS**：772 行、20 个自定义属性、4 个响应式断点（1360/1080/820/560），结构健康；有 20 处硬编码 hex 色值，暗色模式下可能有零星不适配，需靠截图核实。

## 4.5 视觉审查结果（2026-07-21 已完成）

54 张截图（9 页面 × 亮/暗 × 1440/1280/1024）已在本机产出并逐张审阅。

### 先说做得好的

- **暗色模式实现干净**：抽查 settings/overview 全页，未发现浅色块泄漏；危险区卡片、标签、分隔线都正确适配，20 处硬编码 hex 没有造成可见问题。
- **响应式确实生效**：1024px 下右侧提案栏自动收起为顶部「提案」按钮，布局不挤压——**收起机制已经存在**，这点对下面的 P2 很关键。
- 视觉语言统一：卡片体系、状态色（绿=就绪/蓝=信息/橙=待处理）、字体层级都一致。

### 视觉发现（按优先级）

**V1｜中英混排 bug（精确定位，一行可修）**

动作板状态行实测显示「待处理 0 · **Running** 0 · 已完成 3 · 已取消 0」——四个状态里三个中文一个英文。根因：`ActionBoard.tsx:73` 硬编码了 `` `Running ${...}` ``，而同一组的其他三个走 `labels.actions.*`；`locales/zh.ts` 也缺 `in_progress` 词条。补词条 + 改这一行即可。

**V2｜i18n 系统性缺口（体量比预期大）**

`grep` 复核：**7 个组件完全没有引用 `labels`**——`ProposalPanel`、`FeedbackTimeline`、`CapabilityCard`、`EventsPanel`、`MemorySearchPanel`、`AgentTaskGraphCard`、`FeedbackStatusTag`/`JsonSummary`。约 53 处硬编码英文。

后果在截图里非常直观：**每页常驻的右侧面板是 100% 英文**（Task / Submit Task / Robot / Capability / Action ID / Params JSON / Reason / Depends on），Overview 的卡片标题也全英（System status / Agent output tasks / Robots / Capabilities），而导航是中文。中文用户看到的是一个半汉化界面。C4 条目当初记的是"高频文案已抽取"，实测覆盖率没到位。

**V3｜提案栏常驻挤压主内容（布局主因）**

`Task / Action Proposal` 面板在 ≥1080px 时**九个页面全部常驻**约 370px，包括「设置」「记忆」「安全」这些和提案无关的页面。可见后果：设置页主卡片被压到约 400px 宽，导致路径在词中间断行——截图实测 `...\Physical_agent\physic` / `al-agent.yaml`；同时右侧「原始调试」卡占满一列却只有一行折叠内容。

**建议**：把提案栏改成非提案页面默认收起（1024px 下的抽屉机制已经能用，等于复用现成逻辑）。这一改同时消掉 §2 的 P1 性能问题——流式聊天时 ProposalPanel 不再挂载就不会跟着重渲染。**一次改动解决两个问题，这是本轮性价比最高的一项。**

**V4｜空状态占位过大，页面过长**

Overview 页实测高 **2721 CSS px**（1440 视口下约 3 屏）。主因是空状态按满尺寸卡片渲染：「Agent output tasks」空态占约 180px 显示"No compiled AgentOutput"，位置还在首屏黄金位。记忆/机器人/安全三页则是内容只占上方 1/3、下方大片空白。建议空态卡片收缩为单行提示或折叠。

**V5｜反馈条目被 Raw 摘要淹没**

每条 feedback 下方的 `Raw: approval=required=true, status=pending, metadata=source=planner, proposed_by=api, original_task=..., planner_reason=...` 灰色等宽长串，视觉权重超过上方给人读的标题。它是 F2.5 有意做的 `JsonSummaryLine`（不是遗留裸 JSON），但建议默认折叠、点击展开。

**V6｜历史状态与当前状态视觉混淆**

动作板显示「待处理 0」，下方反馈时间线同时并排三个橙色 `pending` 徽章——两者都对（时间线是历史事件），但同屏看容易误读成"有 3 个待处理"。建议历史条目的状态徽章降低饱和度，或显式标注为事件时刻状态。

**V7｜表格列宽分配不均**

动作板表头「ID / 目标 / 参数 / 依赖 复核」——前三列吃掉绝大部分宽度，「依赖」「复核」被挤到右缘几乎贴在一起。给后两列设最小宽度即可。

## 4.6 页面组件排布 / 信息架构审查

把 `renderPageContent()` 的实际组装摊开看：

| 侧栏页面 | 实际渲染的组件 |
| --- | --- |
| 概览 | StateOverviewPanel + [ActionBoard + **ChatPanel**] + [ContextTabs + RobotsPanel] |
| 动作 | ActionBoard + ContextTabs(默认 feedback) |
| 世界 | **仅** ContextTabs(默认 world) |
| 机器人 | **仅** RobotsPanel |
| 硬件 | HardwarePanel + ConfigPanel + RobotsPanel |
| 记忆 | UploadPanel + MemorySearchPanel |
| 安全 | **仅** ContextTabs(默认 safety) |
| 事件 | EventsPanel + RawDebug |
| 设置 | SettingsPanel + RawDebug |

九个导航项，实际只有约九个独立组件，且严重复用。由此暴露四个结构问题：

**A1｜侧栏与页签是两套打架的导航（最严重）**

「世界」和「安全」两个侧栏页，渲染的是**同一个 `ContextTabs` 组件**，只是 `defaultActiveKey` 不同——而这个组件永远把「世界 / 反馈 / 安全 / 能力」四个页签**全部渲染出来**。

后果：用户在「世界」页点一下页签里的「安全」，内容变成安全规则，但侧栏高亮仍停在「世界」——**导航状态与内容脱节**。同一份内容有两条到达路径，且互不同步。截图可验证：动作页、世界页、安全页顶部是同一条四页签栏，只是激活项不同。

**建议**：二选一。要么把「世界/安全」从侧栏撤掉，合并为一个「状态」页内部用页签切换；要么保留侧栏项、让 ContextTabs 在这些页只渲染单个面板（不显示页签栏）。前者信息架构更干净，后者改动更小。

**A2｜主要工作流「对话」没有导航入口**

`ChatPanel` **只出现在概览页**的中间列，侧栏九项里没有「对话」。但按 SPEC 的档位模型，档位1（Chat 起草→人批）是主力工作流。现状是：档位0 的手动提案表单（ProposalPanel）**九页常驻**占着右栏，而档位1 的聊天却被埋在最忙页面的中间列里，且随概览页一起被撑到 2721px 高。**信息架构与实际使用频次是倒挂的。**

**建议**：给「对话」一个独立侧栏页（工作量小，组件现成），概览页则回归"一屏看完系统状态"的定位。

**A3｜单组件页面过薄，导航颗粒度不一致**

「世界」「机器人」「安全」三页各自只有一个组件——截图里这三页内容只占上方约三分之一，下方大片空白（V4 提到的现象，根因在这）。而「硬件」页塞了三个组件、「概览」页塞了五个。同一个侧栏里，页面权重差了 3-5 倍。

**A4｜组件跨页重复，用户容易迷路**

ActionBoard 出现在 2 页、RobotsPanel 出现在 3 页、ContextTabs 出现在 4 页、RawDebug 出现在 2 页。复用本身没错（组件设计得好），但在导航上会让人搞不清"我刚才那张动作表是在哪一页看到的"。尤其 RobotsPanel 同时出现在「机器人」和「硬件」两个语义邻近的页面，更容易混淆。

### 建议的重排（需要你做产品判断，不是直接开工）

```
现状 9 项：概览 动作 世界 机器人 硬件 记忆 安全 事件 设置

建议 8 项：
  对话      ← 新增，ChatPanel 独立成页（主工作流应有入口）
  概览      ← 瘦身：只留 状态 + 机器人 + 任务图，删掉 ActionBoard/ChatPanel/ContextTabs
  动作      ← ActionBoard + 反馈时间线（保持）
  状态      ← ContextTabs 四页签（吸收原「世界」「安全」，消除 A1 冲突）
  硬件      ← HardwarePanel + ConfigPanel + RobotsPanel（吸收原「机器人」）
  记忆 / 事件 / 设置  ← 不变
```

配合 V3（提案栏改为按需展开），布局问题基本可以一次性解决。

**改动量评估**：`renderPageContent` 是纯组装函数，改排布本身很轻（约半天）；但会动到 Playwright 用例里的 `data-testid="nav-*"` 和 `page-*` 断言，需要同步更新 e2e——按 `AGENTS.md` 这属于"改动必须带测试"的范畴，建议立 SPEC 条目再动。

## 5. 截图脚本用法（可复跑）

沙盒无法安装 Chromium（Playwright CDN 下载得到 0 字节，与 R1.5 时的沙盒限制一致），故本轮**未做视觉审查**。已提供 `frontend/tools/ui-screenshots.mjs`：

```powershell
# 终端 1
.\.venv\Scripts\physical-agent.exe api --watch
# 终端 2
cd frontend; npm run dev
# 终端 3
cd frontend; node tools/ui-screenshots.mjs
```

输出到 `.tmp/ui-review/`（已 gitignore），9 个页面 × 亮/暗 × 3 个视口 = 54 张二倍图，并汇总控制台错误。脚本只做导航和截图，不触发任何提案或审批。

截出来后把图贴进对话，可做的视觉审查包括：暗色模式下硬编码色值的对比度问题、窄视口下的布局挤压、信息密度与视觉层级、空状态表现、卡片间距一致性。

## 6. 与项目纪律的关系

R8/R8.1 已收口，冻结清单针对的是 VNext-3/4、W4/W5/W6.2、F0/F5/F6 等**后端功能扩张**，前端体验优化不在其中。但按 `AGENTS.md`：动工前应在 SPEC §4 建条目（可挂在 C 系列或新开 UI 条目）、出轮次 brief、改动带测试（此处即 Playwright 用例）、收工回写 SPEC/REFACTORING。

**建议排期**：P1 + P2 三项合并成一轮（约一天），P3 单独立项。

## 范围外

- 本轮未改任何生产代码；未引入新依赖。
- 不建议在未做视觉审查前改动视觉设计。
