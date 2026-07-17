# T4：MOCE TUI 品牌与终端视觉刷新设计

状态：书面规格已于 2026-07-17 获用户批准，进入实施计划

日期：2026-07-17

对应账本：`docs/SPEC.zh-CN.md` §4 `T4`

## 1. 背景与目标

现有 Ink TUI 以 append-only transcript 为核心，视觉层只有零散的 cyan/gray/green/yellow/red 文本：没有启动品牌、统一主题 token、分区标题或输入框边界；最终 assistant 消息中的 `##`、`**` 和反引号也按原始纯文本显示。用户在 Windows Terminal 实际体验后明确要求：加入 Claude Code 风格的打印式品牌，主品牌为暗蓝色 `MOCE`，并提高整体信息层级。

本条目是 R8.1 完成后的独立、显式 SPEC 决策，只重启 TUI 展示层，不恢复其他冻结功能。目标是：

1. 启动时打印一次大型暗蓝色 `MOCE` Logo；进入交互后保留紧凑 `MOCE` 标题栏。
2. 保持纵向、append-only 的 Claude Code 式 transcript，不退回多栏 dashboard。
3. 为状态、分区、角色和输入框建立克制但明确的视觉层级。
4. 对 finalized transcript 做轻量 Markdown 呈现，隐藏最常见的原始标记；streaming 中间态保持稳定纯文本。
5. 不改变任何 API、命令、状态、审批、SafetyGate、watch 或 driver 行为。

## 2. 方案选择

评审过三种方向：

- **克制品牌化（采用）**：Logo、紧凑标题栏、分区标题、角色轨道、输入框轮廓和轻量 Markdown。既有信息密度不变，窄终端仍可用。
- **全边框驾驶舱（放弃）**：视觉更强，但会占用终端高度、导致窄屏折行，并与 append-only transcript 冲突。
- **仅 Logo（放弃）**：风险最低，但不能解决正文层级和输入区过于单薄的问题。

用户选择品牌展示方式 C：启动大 Logo + 常驻紧凑标题栏。

## 3. 视觉契约

### 3.1 品牌与颜色

- 主品牌：`MOCE`。
- Logo 主色：暗蓝 `#1D4ED8`，用于大号块字，保留用户批准的暗蓝品牌观感。
- 小字号品牌强调色：`#3B82F6`，用于紧凑 wordmark、分区标题、输入框边界和 assistant 角色轨道；暗蓝不直接承担黑底小字可读性。
- 语义色保持既有含义：green=成功/在线，yellow=等待/降级，red=错误/拒绝，magenta=SafetyGate，gray=次级信息。
- 颜色永远不是唯一状态载体；所有状态继续保留文字标签，`NO_COLOR` 或低色深终端仍可理解。

宽终端启动输出：

```text
███╗   ███╗  ██████╗   ██████╗ ███████╗
████╗ ████║ ██╔═══██╗ ██╔════╝ ██╔════╝
██╔████╔██║ ██║   ██║ ██║      █████╗
██║╚██╔╝██║ ██║   ██║ ██║      ██╔══╝
██║ ╚═╝ ██║ ╚██████╔╝ ╚██████╗ ███████╗
╚═╝     ╚═╝  ╚═════╝   ╚═════╝ ╚══════╝

PHYSICAL AGENT · SAFE CONTROL PLANE
type /help to explore
```

终端可用宽度小于 58 列或宽度未知时，不打印可能折断的块字，降级为：

```text
MOCE · PHYSICAL AGENT
type /help to explore
```

### 3.2 常驻布局

Ink 输出只允许一个持续挂载的 `Static` feed：大 Logo 是该 feed 的首个稳定 item，后续 finalized transcript 也追加到同一个 feed；不得为 Banner 和 Transcript 分别创建两个 `Static`，也不得因 view 切换卸载并重建 feed。这样 Logo 只打印一次，不随 health/SSE 刷新或视图切换重复。动态区域保持：紧凑标题栏 → 当前视图 → notice → 输入框。标题栏示意：

```text
MOCE  ● connected  SSE  executor embedded  LLM connected
─────────────────────────────────────────────────────────
```

状态过长时允许 Ink `flexWrap`，不硬编码列宽；API URL、backend、last refresh 等次级字段放在第二行并使用 gray。divider 由布局伸缩，不拼接固定长度字符。

### 3.3 Transcript 与输入

- finalized user：`you  ›`，绿色或默认前景；finalized assistant：`moce │`，品牌蓝；draft：`draft ◇`，yellow/gray。
- finalized assistant 文本使用无新依赖的轻量 formatter：识别行首 heading、无序/有序列表、`**bold**` 与 inline code；不实现完整 CommonMark、表格、链接交互或代码语法高亮。
- formatter 以内容保真优先：fenced code、未配对 `**`/反引号、嵌套或其他不支持语法整段原样保留；不得吞字、重排机器文本，也不得把历史 `action-draft` fence 当作可执行协议。
- streaming partial 继续走现有稳定纯文本路径，避免未闭合 Markdown token 造成闪烁；done 后进入 finalized formatter。
- `CommandInput` 使用 round border、品牌蓝边界与 `›` prompt；disabled 状态保留 `Working...`，输入行为和快捷命令不变。
- 各 view 复用统一 `SectionTitle`，只改标题层级，不给每个面板增加重型边框。

## 4. 组件边界

- 新增 `tui/src/theme.ts`：品牌与语义色 token，不承载状态逻辑。
- 新增 `tui/src/components/BrandBanner.tsx`：纯展示；根据 stdout columns 选择 full/compact wordmark，并提供可单测的宽度选择函数；组件本身不拥有第二个 `Static`。
- 新增 `tui/src/components/SectionTitle.tsx`：统一分区标题和轻量 divider。
- 新增或扩展 transcript formatter：只负责 finalized terminal text tokenization/render，不解析动作或机器协议。
- `Transcript.tsx`（或等价 feed 组件）成为唯一且持续挂载的 `Static` owner，以稳定 key 顺序输出 Banner 和 finalized entries。
- `App.tsx` 只负责把一次性 Banner item 接入同一 feed 并沿用既有布局；不改变 refresh、SSE、command 或 chat data flow。
- `StatusBar.tsx`、`CommandInput.tsx` 与各 panel 只消费主题/展示组件。

每个新增组件都必须可在不知道 API internals 的情况下独立渲染和测试。

## 5. 数据流与安全边界

数据流保持原样：

```text
FastAPI health/state/config/events/chat
  -> existing TuiClient/App state
  -> existing canonical projection
  -> presentation-only MOCE components
```

不新增 API 调用，不读取 workspace/SQLite，不 import Python/watch/driver，不新增 Add/execute/hardware-control 能力。TUI 继续只展示 structured draft；Action Board、approval、SafetyGate 与 watch 唯一执行权完全不变。

截图顶部的 PowerShell `WindowTitle` 红字来自本轮外部启动命令的字符串展开错误，不属于 TUI。体验重启时改用正确转义的可见 PowerShell 命令；不为此向 TUI 引入 shell 管理代码。

## 6. 错误与兼容策略

- 宽度未知、非 TTY 或窄终端：使用 compact Banner；完整 App 在 48 列不得产生已知超宽固定行，标题栏与输入框仍须可用。
- Unicode 块字不可用时仍有可读的 `MOCE · PHYSICAL AGENT` 文本；不把 Logo 成功渲染作为启动条件。
- API offline、SSE degraded、LLM failure 与 SafetyGate 状态沿用现有文字和语义色。
- formatter 遇到未支持或不完整 Markdown 时退回原文，不吞内容、不截断长回复。
- 不新增 runtime dependency；继续使用 Ink 5/React 18 现有能力。

## 7. 测试与验收

实现必须按 TDD 逐项落地：

1. `BrandBanner` 在 100 列打印完整 `MOCE`，在 48 列及 `columns` 未定义时打印 compact fallback；App rerender、health/SSE 更新和 view 切换均不重复输出大 Logo，并证明全局只有一个 `Static` feed。
2. 紧凑标题栏仍显示 connection/mode/executor/LLM 的可读文字。
3. Transcript 显示 `you ›`、`moce │`、`draft ◇`；finalized 常见 Markdown 不再暴露 `##`/`**`/inline-code 反引号；fenced code、未配对标记、嵌套/不支持语法和旧 `action-draft` fence 用负例证明逐字保留且绝不触发协议行为。
4. 输入框有品牌边界但提交、disabled 和 `/help` 行为不变。
5. 既有七个 scenario、API/SSE、命令与 safety 测试全部通过；测试 stdout 增加 48/100/未定义列宽覆盖，并断言 48 列完整 App 无固定超宽行、标题栏和输入框可用。
6. `npm run typecheck`、`npm test`、scenario matrix、`npm run build` 全绿，并在真实 Windows Terminal 手工确认颜色、折行和一次性 Banner；使用文档化启动命令时额外确认外部 PowerShell 不再产生 `WindowTitle` 红字，但该检查不作为 TUI 代码可自动保证的行为。
7. TUI 安全扫描继续证明无 `driver.execute`、无 Python watch/driver import、无 SQLite 直接访问。

## 8. 范围外

- 不改 React Dashboard、后端、协议或业务状态。
- 不实现完整 Markdown/CommonMark、终端超链接、代码语法高亮、主题切换或用户自定义配色。
- 不引入双栏 dashboard、鼠标交互、动画 Logo 或启动等待页。
- 不借本条目恢复 VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan。
