# Codex prompt（C5：Dashboard 可读性与 i18n 收口）

> 第一轮 / 共两轮。复制分隔线之间的内容粘贴进新 session。

---

在 Physical_agent 仓库执行 **C5：Dashboard 可读性与 i18n 收口**。

先读 `AGENTS.md` 走完开工流程。本轮的诊断与规格：`docs/brief-frontend-optimization-review.zh-CN.md`（§4.5 视觉发现）与 `docs/design/ui-redesign-spec.zh-CN.md` 的 **A.6 节**。

**范围**：纯前端可读性收口——补齐 i18n、修中英混排、空状态收缩、raw 摘要默认折叠、历史徽章与当前状态的视觉区分、表格列宽、焦点样式。不动导航结构、不改 page key、不改任何 Python 文件。规格 A.1–A.5 属于下一轮 C6，本轮不要碰。

## 坑（这几条你查代码查不出来，务必注意）

1. **安全信号只能变清楚，不能变模糊。** 本轮多处"默认折叠"，但折叠对象仅限 raw 元数据摘要和**历史**状态徽章。当前待审批状态、Gate 结果、拒绝原因一律不得折叠或弱化——这是 human-in-the-loop 的核心信号，藏起来等于让 operator 不知道系统在等他。

2. **别碰 `ChatPanel` 里的推理摘要折叠块**（`data-testid="reasoning-summary"`）。上一轮 `832519e` 刚落地，含免责文案与专项 e2e，必须继续通过。

3. **i18n 要自己扫，别信任何现成清单。** 已知有多个组件完全没接 `labels`，但具体是哪些、共多少处，以你 grep 的结果为准。沿用现有轻量字典模式（`locales/zh.ts` / `en.ts` + 传 `labels` prop），不要引入 i18n 框架；两个语言文件的键必须一一对应。

4. **视觉判断类的三项——空状态高度、徽章饱和度、表格列宽——做保守版本即可**，后续会有人工轮次拿截图微调。不要在这三项上反复纠结或自创设计语言。

## 验收

按 `AGENTS.md` 收工要求走。额外要求：中英文两种模式各通读一遍全部页面（无残留英文，专有名词除外）；键盘 Tab 走一遍主路径，亮/暗模式下焦点均可见。`frontend/tools/ui-screenshots.mjs` 可用于自查（需本机 Chromium）。

有分歧或发现规格与代码实际不符，先停下来说明，不要自行改设计。

---
