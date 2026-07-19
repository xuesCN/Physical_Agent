# T4 follow-up：MOCE 对话式 transcript、动作记录与终端宽度修复

状态：设计已获用户批准，待实现

日期：2026-07-19

对应账本：`docs/SPEC.zh-CN.md` §4 `T4.1`

## 1. 背景与目标

真实 Windows Terminal 体验暴露了 T4 的宽度回归：finalized chat 把角色前缀与正文拆成 sibling 后，`Static` 仍保持绝对定位的 auto width。正文因此按近似整行宽度换行，没有扣除左右 padding、角色前缀和间隔，Ink 会先产出超过 `stdout.columns` 的行，终端再做第二次硬换行。续行由此丢失悬挂缩进，普通单词也可能在终端边界中间断开。现有场景测试又用 Unicode code point 数代替 display width，未能发现 emoji/CJK 占两列时的超宽。

用户同时希望把 chat 视觉收敛为更接近 Claude Code 的纵向活动流：用户行使用 `>`，MOCE 回复和真实动作记录使用 `⏺`，动作结果使用 `⎿`。`>` 与 `⏺` 必须用不同颜色。待审批动作可显示醒目的只读提示框，但审批仍完全沿用现有 `/approve <action_id>` 与 `/reject <action_id> <reason>` 命令。

本 follow-up 的目标是：

1. finalized 与 streaming chat 使用同一套受终端宽度约束的悬挂缩进布局。
2. 用 `>` / `⏺` / `⎿` 建立可读且无颜色时仍可区分的活动流。
3. 只根据 canonical Action Board 的真实 terminal transition 追加动作结果，不把 draft、Gate pass 或模型正文冒充为执行事实。
4. 用只读审批框提示原有命令，不新增单键审批、session grant、API 或状态语义。
5. 保持 TUI 为纯 HTTP API/SSE 客户端，API、SQLite、watch、driver、SafetyGate 与审批链路零改动。

## 2. 方案选择

评审过三个方向：

- **纯 TUI 活动流（采用）**：修正 Ink 布局，统一消息行，基于现有 Action Board 在本地会话内追加真实 terminal action，并以只读框提示原审批命令。范围集中、事实来源清晰，也符合用户最终确认的“只修改 TUI”。
- **后端补 action 时间与授权会话（放弃）**：可以提供权威完成时间和 standing grant，但会跨 API/state/watch，引入新的授权生命周期，不符合本轮范围。
- **只换 glyph、不修数据和宽度边界（放弃）**：改动最少，但仍会产生终端二次硬换行，也容易把动态 Action Board 与 append-only transcript 混成重复或失实记录。

本轮明确不显示 `done · 12:03:21`：现有 API 没有 action 的权威完成时间，客户端观察时间不能冒充执行完成时间。结果行只显示真实状态，例如 `⎿ done`、`⎿ failed` 或 `⎿ rejected`。

## 3. 视觉与布局契约

### 3.1 Chat 角色轨道

目标输出：

```text
> hello?

⏺ Hello! I'm here and ready to help.
  I can see the arm is idle on the table, with a red block
  and a tray visible nearby.
```

- finalized user marker 为 `>`，使用 `THEME.success`（green）。
- finalized/streaming assistant marker 为 `⏺`，使用 `THEME.brandAccent`（MOCE blue）。
- structured draft 保留 `draft ◇` 与 `THEME.warning`，不得使用 `⏺` 冒充 MOCE 回复或真实动作；system/unknown role 保留带原 role 名的 muted fail-closed fallback。
- marker 后保留一个明确布局间隔，不依赖会被布局覆盖的尾随空格。
- 正文继续使用默认前景色；颜色不是唯一角色载体。
- 所有视觉行都按 terminal display cells 计算，而不是 JavaScript 字符数。
- 续行从正文起始列继续，不能回到第 0 列或 marker 列。
- 普通英文优先按词边界换行；只有单个 token 自身超过正文预算时才允许 hard wrap。

### 3.2 动作活动项

动作只在 TUI 运行期间观察到 canonical Action Board 从非 terminal 进入 terminal 时，作为一个不可变 item 追加到同一个 `Static` 活动流：

```text
⏺ arm_1.move_to(x=120, y=45, z=0)
  ⎿ done
```

- 第一行 marker 使用 `THEME.brandAccent`；结果 marker 使用 `THEME.muted`。
- capability 参数使用稳定的 `name=value` 顺序与紧凑值表示；字段名含 `token`、`secret`、`password` 或 `key` 时必须脱敏。
- draft `AgentOutput`、chat metadata 和模型正文永远不能生成 completed action item。
- terminal bucket truth 只读 `/api/state.actions`，结果文案使用确定映射：`completed` bucket → `done`；`cancelled` bucket 且 `metadata.approval.status=rejected` → `rejected`；其余 `cancelled` 必须等到匹配无 `event`、同 `action_id` 的 action-result feedback 后再追加，并按 feedback `status=failed|cancelled` 显示 `failed|cancelled`。若关联 result 尚未出现则暂缓，始终没有 result 的 cancellation 只保留在 `/view actions`，不向不可变 feed 猜写 fallback。不存在独立的 Action Board `failed` bucket。
- Gate feedback、expectation feedback 与 action result 不得因共享 `action_id` 重复生成多条动作记录。
- 必须支持两阶段 snapshot：先观察到 `cancelled` bucket、后观察到 action-result `failed` 时，第一阶段不 append，第二阶段只 append 一次 `failed`。
- TUI 首次 snapshot 中已经 terminal 的历史动作只留在 `/view actions`，不回灌进本次活动流；本次运行中新观察到的 terminal transition 才追加。
- workspace reset 后清空本地 seen set，允许后续复用 action id；重复 refresh、SSE summary、polling 与 mutation response 不得重复打印。

### 3.3 只读执行审批提示

第一个 `metadata.approval.required=true && metadata.approval.status=pending` 的 canonical pending action 在动态区域显示响应式 Ink `Box`：

```text
╭─ Safety Gate · Execution approval ─╮
│ arm_1.lift() 等待人工批准           │
│ 批准后仍需 watch SafetyGate 校验    │
│ /approve <action_id>               │
│ /reject <action_id> <reason>       │
╰────────────────────────────────────╯
```

- 这是 human execution approval 提示，不是 Gate deny 后的人工 override。
- 不显示 `[y]`、`[n]`、`[a]`，不截获单键，不新增 session grant。
- 不伪造“检测到协作区有人员”等当前系统没有可信传感器证据的文案。
- 多条待审批动作显示 `1/N` 和精确 action id；完整列表继续在 `/view actions` 查看。
- 框使用 `THEME.safety` 和 Ink 自适应 border，不手拼固定长度横线；窄屏时文案自然换行且不得超出终端宽度。

## 4. 组件与数据边界

- 新增小型共享展示组件（名称可在实现时按现有命名调整）：
  - `MessageRow`：固定 marker 区、明确 gap、可收缩正文；不拥有 `Static`，不解析业务状态。
  - `ActionActivityItem`：只格式化已确认 terminal 的 `ActionItem`。
  - `ExecutionApprovalNotice`：只读 canonical pending approval，输出原有命令提示。
- `Transcript` 继续是全局唯一 `Static` owner，但其宽度必须约束为根终端的 `100%`。brand、chat 与本地 terminal action 必须先进入同一个单调追加的 activity feed：只能在尾部 append，已提交给 `Static` 的 item 永不插入、重排、替换或删除；稳定 key 只负责 React identity，不能替代这条 append-only 约束。
- `FinalizedText` 继续只处理已批准的轻量 Markdown 子集；它作为 `MessageRow` 正文，不自行计算终端宽度。
- `ChatPanel` 的 streaming assistant 复用 `MessageRow`，保持 literal 内容，不在 streaming 中启用 finalized Markdown。
- `App` 继续读取 `useStdout().stdout.columns` 供 Banner 选择；活动行的实际可用宽度交给受约束的 Ink flex layout，不手算 prefix/emoji 宽度。
- `App` 从已有 state refresh/SSE/polling 结果观察 Action Board transition，维护仅属于当前 TUI 进程的 terminal seen set，并把 chat/action observation 依次 append 到同一 activity feed；不把两个独立增长数组在 render 时重新拼接，不写 workspace，不改变 action。
- chat 默认视图显示活动流和只读审批提示；`/view actions` 保留现有完整 AgentOutput task、Gate 与 Action Board 信息，避免紧凑活动流隐藏诊断事实。

## 5. 宽字符与测试计数

产品实现不新增手写 wcwidth 算法。当前锁定的 Ink 5.2.1 / `wrap-ansi` 9.0.2 / `string-width` 7.2.0 链路用于处理 ANSI 与测试中明确列出的 emoji、CJK、combining mark 和 ZWJ 样例；本轮不对所有 Unicode grapheme 作超出该版本行为的通用保证。修复重点是让 Ink 得到正确的正文预算。

测试侧将 `string-width` 声明为直接 dev dependency，并用它替换 `[...line].length`。这样测试不依赖 Ink 的传递依赖，也不会把 emoji/CJK 错算成一列。ANSI 清理后，每个物理输出行都必须满足 `stringWidth(line) <= stdout.columns`。

## 6. 状态变化、错误与兼容策略

- terminal transition 去重只影响 TUI 本地展示；重启 TUI 不尝试重建历史时序。
- Action Board 暂时不可用时不生成 action item；原有 API offline/degraded 文案继续工作。
- 参数格式化遇到循环外的 unknown object、长数组或长字符串时使用有界、可读且脱敏的摘要，不让单项无限扩大 transcript。
- approval mutation、busy、streaming 与 CommandInput 行为保持原样；只读提示框不参与焦点竞争。
- terminal 宽度未知时 Banner 仍使用 compact fallback；验收只断言组件不写固定数值 `width/minWidth`、根布局保持可收缩且内容不丢失，不复用需要具体上限的 `lineWidth <= columns` 断言，也不声称非 TTY 有一个并不存在的物理终端列数。
- 旧 `you ›`、`moce │` 文本只属于视觉输出，不是 wire/API；场景和文档同步切换为新 glyph。
- `NO_COLOR` 下仍可用 `>`、`⏺`、`⎿` 和文字状态识别角色与结果。

## 7. TDD 与验收

实现必须逐项 RED → GREEN：

1. 48 列 finalized assistant 长英文先证明当前输出超过 48 列，再修到每行 display width 不超界、首行 marker/gap 正确、续行保持悬挂缩进、正文重组无丢字。
2. streaming assistant 使用同样的 48 列断言，并保持未闭合 Markdown literal。
3. emoji、CJK、组合字符与 ZWJ emoji 用 `string-width` 验证；旧 code-point helper 必须由测试证明会低估后再替换。
4. `>` 使用 success green、`⏺` 使用 brand blue、`⎿` 使用 muted，`draft ◇` 保持 warning；system/unknown role 不得升级成 `⏺`。无颜色时 glyph/role 文字仍不同。
5. canonical action 从 pending/in-progress 进入 completed/cancelled 后只追加一次，并按 §3.2 的 action-result feedback 规则把 eligible cancelled 确定映射为 `rejected`、`failed` 或 `cancelled`；测试必须先给无 result 的 cancelled snapshot（不追加），再给 failed result snapshot（只追加一次）。重复 snapshot、Gate/expectation feedback、polling 与 SSE 不重复。
6. draft output、历史 terminal action和非 terminal action不生成假的 `done`；reset 后相同 action id 可再次生成新活动项。
7. pending required approval 显示只读响应式框、action id、原 `/approve`/`/reject` 命令和“仍需 SafetyGate”说明；无 pending 时不显示。
8. 24/48/100 列下用 display width 证明 chat、action 与审批框不超宽；未知列宽只验 compact Banner、无固定数值宽度与内容不丢失。普通输入、所有既有命令、完整 `/view actions` 信息不变。
9. 完成 `npm run typecheck`、定向 render/scenario/physical stdout、完整 `npm test` 与 `npm run build`；按仓库纪律再跑 Python 全量与安全边界回归。

## 8. 范围外

- 不改 FastAPI、SQLite schema、Action/feedback wire、watch、driver、SafetyGate、SAFETY.md 或审批状态机。
- 不新增 y/n/a 单键审批、standing grant、授权 TTL、后台自动 approve 或 Gate override。
- 不显示非权威 action 完成时间，不把客户端观察时间标成执行时间。
- 不实现完整 shell/tool-call transcript、实时 running spinner、历史 Run/Event ledger 或跨进程活动流恢复。
- 不恢复 Phase F、VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan。
