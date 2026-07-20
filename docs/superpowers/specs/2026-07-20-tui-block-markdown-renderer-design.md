# T4.2：TUI finalized assistant 块级 Markdown 渲染器

状态：已实现并通过本地验收

日期：2026-07-20

对应账本：`docs/SPEC.zh-CN.md` §4 `T4.2`

## 1. 背景与问题

T4 已为 finalized assistant 提供无依赖的轻量 Markdown formatter，支持 heading、一级有序/无序列表、`**bold**` 与 inline code；T4.1 又统一了 finalized/streaming 的终端宽度预算和悬挂缩进。真实 Windows Terminal 体验仍暴露一个高频降级问题：LLM 常用如下嵌套列表表达对象详情：

```text
1. **red_block**
   - Type: block
   - Color: red
2. **tray**
   - Type: tray
```

当前 `parseFinalizedText()` 把缩进列表识别为不支持语法，并对整条消息返回 `null`。结果是消息中本来可支持的 `##`、`**`、反引号和顶层列表也全部按原始 Markdown 显示。该行为保证了内容不丢失，却让长回复频繁退回开发者视图，破坏了 MOCE 对话式 transcript 的终端原生阅读体验。

本轮只修正 finalized assistant 的展示模型，不改变模型输出、chat wire、Action Board、审批或执行语义。

## 2. 目标与范围外

### 2.1 目标

1. 将 formatter 从“整条消息全成或全败”改为块级解析与块级保真降级。
2. 支持 heading、paragraph、最多三层的有序/无序混合列表、bold、inline code 和闭合的普通 fenced code block。
3. 列表项和代码行在 24/48/100 列下使用真实 display width，续行悬挂到正文起点，不触发终端二次硬换行。
4. 保持 streaming assistant、user、draft、system/unknown role 的现有 literal 行为。
5. 不支持或畸形的块只在自身范围内原样显示；相邻合法块继续格式化，任何内容不得静默丢失。
6. 保持 `action-draft` fence 为逐字 presentation fallback，绝不恢复或新增正文到动作的协议升级。

### 2.2 范围外

- 不实现完整 CommonMark/GFM、表格布局、链接跳转、图片、HTML、引用块、任务列表或语法高亮。
- 不引入 Markdown runtime dependency。
- 不修改 LLM prompt 来强迫模型输出某一种排版；客户端必须稳健处理真实回复。
- 不改变 chat streaming、API/SSE、SQLite、watch、driver、SafetyGate、SAFETY.md、审批命令或 action/feedback wire。
- 不新增主题、用户配置开关或 terminal hyperlink。

## 3. 方案选择

评估过三个方向：

- **无依赖块级容错渲染器（采用）**：沿用当前受控 inline parser，增加 block scanner、嵌套列表和普通 fence renderer；不支持的内容只让所在块 literal。它能直接解决截图中的真实问题，依赖面和回滚面最小。
- **CommonMark AST dependency（放弃）**：语法覆盖更完整，但会引入新依赖、更多 AST→Ink 映射和宽度边界，也会把本轮体验修复扩成完整 Markdown 子系统。
- **删除标记的输出后处理（放弃）**：实现快，但会误删普通文本中的标点，无法可靠区分代码、列表和畸形输入，也不能提供稳定悬挂缩进。

T4 曾选择“任何 unsupported syntax 使整条消息 literal”。T4.2 显式将该决策收窄为“unsupported block 仅使自身 literal”，原因是已有正反例证明角色/协议边界不依赖整条 fallback，而真实 LLM 回复中一个嵌套列表让全部合法格式失效的体验成本已经可复现。`action-draft` 仍保留更强的逐字例外。

## 4. 输出与视觉契约

目标输出示例：

```text
⏺ Here's a detailed rundown of the current workspace.

  Current Workspace

  Robot state
  • arm_1 is currently idle.
  • Pose: x=0.2, y=0.1, z=0.4

  Visible objects
  1. red_block
     ◦ Type: block
     ◦ Color: red
  2. tray
     ◦ Type: tray
```

视觉规则：

- heading：隐藏 `#`，使用 `THEME.brandAccent` + bold；原消息中的空行仍决定段间距。
- paragraph：默认前景色；bold 隐藏 `**` 并使用 Ink bold；inline code 隐藏单反引号并使用 cyan。
- unordered list：深度 0/1/2 分别使用 `•`、`◦`、`▪`。
- ordered list：保留源编号；不同层级仍按动态 marker display width 对齐。
- list continuation：在 marker 后使用独立可收缩正文列，物理续行与正文首字符同列。
- fenced code：仅支持顶层闭合三反引号；muted `│` 形成左轨，可选的简单 language label 使用 muted，代码内容保持逐字、默认前景色且不做 inline parsing。
- `action-draft` fence、未闭合 fence、非法 language label 或嵌套 fence：整个 fence block 连标记一起 literal。
- 无颜色终端仍可通过 heading 粗体、列表 glyph、代码左轨和原有角色 marker 区分结构。

## 5. 解析模型

### 5.1 块类型

`FinalizedText` 使用一个纯函数把 normalized message 转为有序 block 列表。概念类型为：

```text
BlankBlock
HeadingBlock
ParagraphBlock
ListBlock<ListItem>
CodeBlock
LiteralBlock
```

解析结果必须覆盖 normalized 输入的全部行。Blank block 显式保留空行；Literal block 保存原始 normalized source，不做二次猜测。

### 5.2 Block scanner

scanner 单调向前消费行：

1. 空行生成 `BlankBlock`。
2. 顶层三反引号尝试读取到匹配 closing fence；只有完整、非保留语言、非嵌套 fence 才生成 `CodeBlock`，否则生成覆盖该 fence 范围的 `LiteralBlock`。
3. 合法 ATX heading 生成 `HeadingBlock`；畸形 heading 行生成单行 `LiteralBlock`。
4. 连续的 list-like candidate 行先形成一个候选 run，再整体校验为 `ListBlock` 或 `LiteralBlock`。candidate 精确定义为 `^[ \t]*(?:[-*]|\d+\.)[ \t]+.*$`，因此带 tab、空正文或其他畸形 item 不会在校验前被拆出 run。
5. 其余相邻非空、非新 block 起始行形成 `ParagraphBlock`；若 inline parser 或 unsupported-pattern 检查失败，仅该 paragraph 变为 `LiteralBlock`。

heading/list/fence 可以在没有空行时成为新 block，避免一个合法结构吞掉后续结构。表格、HTML、link/reference、blockquote、task list、缩进代码和其他未支持结构在其自然段或结构范围内 literal。

合法 heading 的正文同样经过受控 inline parser；若 inline parsing 失败，只把该 heading 单行变为 `LiteralBlock`，不扩大到相邻 paragraph。

Paragraph 的 block grouping 只定义 fallback domain，不采用 CommonMark soft-break：normalized 输入中的每一个源换行继续逐行保留，不能把相邻行拼接成空格。

### 5.3 Fence grammar 与消费范围

只有从 column 0 开始、前三个字符为反引号的行才是 fence candidate。合法 opener 与唯一合法 closer 的 regex 分别为：

```regex
^```([A-Za-z0-9][A-Za-z0-9_+-]{0,31})? *$
^``` *$
```

opener 捕获组缺失表示无 language；closer 只允许尾随 ASCII spaces。其余精确规则如下：

- language 不做 Unicode 归一化，只对捕获的 ASCII token 调用 `toLowerCase()`；结果等于 `action-draft` 时是保留 fence。
- scanner 遇到 candidate opener 后，消费到第一个合法 closer（包含 closer）；若不存在 closer，则消费到消息 EOF。
- opener 不匹配 grammar、language 为保留 token、或 opener 与 closer 之间出现任何另一个从 column 0 以三个反引号开头但不是合法 closer 的行时，整个已消费范围生成一个 `LiteralBlock`。
- 合法 opener + 首个合法 closer + 中间无 nested candidate 才生成 `CodeBlock`。代码正文逐行原样保留，不做 inline parsing。

因此 invalid/reserved fence 在存在 closer 时只影响自身范围；unclosed fence 按 Markdown 的开放范围影响到 EOF，但仍逐字显示且不吞掉字符。带前导空格的 fence 不属于顶层 candidate，按所在 paragraph/unsupported block literal。

### 5.4 列表缩进

candidate run 建立后，每一行必须再匹配严格 item grammar `^( *)([-*]|\d+\.) +(.+)$`：缩进和 marker 后分隔只允许 ASCII spaces，正文非空。任一行含 tab、空正文或不满足严格 grammar，整个 candidate run 生成一个 `LiteralBlock`。空行和非 list-like 行结束 run；本轮不把无 marker 的缩进续行猜成 list item。

每个连续 list block 建立 indentation stack：

- 第一项的 leading-space column 是 depth 0 基线。
- 相同 column 保持当前层；任何更大的新 column 都只推进一个逻辑 depth，与差值无关，所以 `0 → 8` 明确定义为合法的单级推进。
- 回退必须精确命中当前 stack 中已有 column，并截断其后的 deeper columns；随后再次增加 column 可重新推进一级。
- stack 最多包含三个 distinct columns，对应 depth 0..2。尝试加入第四个更深 column，或回退到未知/小于基线的 column 时，整个 list block literal。
- mixed ordered/unordered marker 合法；每项正文继续使用受控 inline parser。

该规则按同一回复实际使用的 2/3/4-space 风格建立层级，不把固定空格数硬编码成全局 Markdown 语义。

### 5.5 Inline parser

沿用并收紧当前有限子集：

- plain text；
- 非空、配对、非嵌套的 `**bold**`；
- 非空、配对、非嵌套的单反引号 inline code。

未配对 delimiter、嵌套 delimiter、unsupported emphasis/link/HTML 等使当前 paragraph 或当前 list block literal。scanner 和 inline parser 均不得抛出到 React render；任何内部拒绝都转换为对应 block 的保真 fallback。

## 6. Ink 组件边界与宽度

- `Transcript` 和全局唯一 `Static` owner 不变。
- `MessageRow` 继续拥有角色 marker 与正文总宽度；Markdown renderer 不自行读取全局 terminal columns。
- `FinalizedText` 从单个嵌套 `<Text>` 调整为纵向 block renderer。
- heading/paragraph/literal 使用普通可收缩 Text 行。
- list item 与 code line 使用共享的内部 hanging-row primitive：固定 display-width prefix 列 + 一个 gap + `flexGrow=1/flexShrink=1/flexBasis=0` 正文列。
- prefix 宽度必须用 `string-width` 或 Ink 已验证等价布局计算；不能用 JS string length/code point count。
- 空行由显式空 Text 行产生，不能通过 margin 猜测，因为 `Static` 的物理输出和窄屏快照需要确定性。

## 7. 数据流与生命周期

```text
assistant stream chunk
  → ChatPanel literal MessageRow（不解析）
assistant done / persisted chat entry
  → Transcript append-only Static item
  → MessageRow
  → parseFinalizedBlocks(normalized content)
  → block renderer
```

formatter 只消费已经属于 assistant finalized entry 的字符串，不读取 metadata、Action Board、feedback 或 driver 状态。它的输出不能创建 proposal、action、approval 或 Gate evidence。

## 8. 安全与兼容边界

1. `driver.execute`、driver import、watch import 与 SQLite import 继续禁止出现在 TUI。
2. generic fenced code 只是 presentation；语言名和内容都不触发 parser/proposal/tool。
3. `action-draft`（大小写归一后）作为保留 language，整个 fence 逐字显示，锁住 R7 后“正文永不升级为 Draft”的边界。
4. user、draft、system/unknown role 不进入 formatter，避免把非 assistant 内容重新解释。
5. normalized 文本中的控制字符继续由现有 `normalizeTerminalText()` 处理；本轮不改变其规则。
6. 任何 unsupported/malformed 输入都以可读原文结束，不得返回空块、吞字符或中断整个 transcript render。

## 9. 测试与验收

### 9.1 TDD 关键 RED

1. 以用户截图等价的 heading + bold + ordered list + 三空格 nested bullets 构造 finalized assistant；当前实现会整条 literal，RED 必须证明新契约要求隐藏合法标记。
2. 合法 heading/bold 与 unsupported table/link 分属相邻 block；RED 必须证明旧 whole-message fallback 错误拖累合法块。
3. 48 列嵌套列表和 code block 的物理 stdout；RED 必须证明续行若复用普通 Text 会丢失内部 prefix 悬挂缩进或超宽。

### 9.2 正反矩阵

- heading、paragraph、bold、inline code；
- 0/1/2 depth unordered、ordered、mixed list，2/3/4-space 风格分别覆盖；
- 重复编号、两位数编号和 emoji/CJK/combining/ZWJ 正文；
- 24/48/100 列下每个 ANSI-stripped physical line 的 display width 不超过 columns；
- 普通闭合 fence、language label、空代码行和长代码行；
- `action-draft`、nested fence、tab/depth>2/bad-dedent list、table、link、HTML、blockquote、task list、畸形 inline literal；
- closed invalid/reserved fence 只让 opener→首个 closer 范围 literal；unclosed fence 明确消费到 EOF，后续形似 heading/list 的行仍属于该 literal fence；
- unsupported block 两侧的合法 block 仍格式化；
- streaming assistant、user、draft 与 unknown role literal；
- semantic content 不丢失，Static/Logo/terminal action once-only 契约不回归。

### 9.3 完成门禁

- `npm.cmd run typecheck`
- formatter/render/physical-width/scenario 定向测试
- `npm.cmd test`
- `npm.cmd run build`
- TUI 禁止 backend/watch/driver/sqlite import 扫描
- Python safety boundary 与 full pytest
- `git diff --check`
- 独立 spec/quality review，Critical=0、Important=0 后方可闭环
- Push 与 draft-PR exact-head CI 均成功；PR 保持 OPEN + draft，不解冻其他功能

## 10. 关键文件与提交边界

预计修改：

- `tui/src/components/FinalizedText.tsx`
- 可选新增一个仅服务 Markdown block 的 hanging-row component；不得复制 `MessageRow` 的角色语义
- `tui/src/components/render.test.tsx`
- `tui/tests/scenario-runner.test.tsx`
- 必要时更新 chat scenario fixture
- `docs/SPEC.zh-CN.md`、`docs/PLAYBOOK.zh-CN.md`、`docs/REFACTORING.zh-CN.md`

实现按 parser/model、Ink renderer/width、integration/closure 拆成可独立回滚的小提交。该变化对 wire 和持久化完全兼容，不需要 feature flag；回滚展示提交即可恢复 T4.1 行为。

## 11. 明确决策

- 采用块级 fallback，不采用 item-level 或 token-level 猜测；列表中的一个畸形 item 使该连续 list block literal，但不影响相邻 heading/paragraph。
- 最多支持三层列表；更深内容优先保真，不为视觉效果无限压缩正文宽度。
- 普通 fenced code 从 T4 的全量 literal 边界中解冻为纯 presentation 能力；`action-draft` 继续逐字保留。
- 不依靠 prompt 约束替代客户端渲染健壮性。
- 本轮完成不解冻任何 backend、approval、SafetyGate、feature-freeze 或自动 replan 条目。
