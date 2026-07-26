# C7 rAF 攒批回归测试设计

日期：2026-07-26  
范围：`frontend/` 流式聊天渲染调度与对应测试

## 背景

C7 已在 `App.tsx handleChat` 内实现 rAF 攒批：`delta` / `thought` 事件只累加文本，同一动画帧内只安排一个流式 state 刷新；终止事件取消待执行帧，异常提前结束时结算残留内容。

当前逻辑内嵌在 React 组件闭包中，只能依赖完整浏览器流程间接验证。测试需要直接证明调度契约，而不是静态检查源码中是否出现 `requestAnimationFrame`。

## 目标与验收

提取一个只负责帧调度的轻量模块，由 `App.tsx` 注入现有流式刷新回调。

验收契约：

1. 同一帧连续调用 `schedule()` 多次，只注册一个 rAF 回调；帧执行时只调用一次 `flush()`。
2. `settle()` 会取消尚未执行的帧，并立即 flush 一次 pending 内容，防止提前断流丢尾 token；之后旧帧不得再次 flush。
3. `cancel()` 会取消尚未执行的帧并丢弃 pending 刷新，供已有 `done` / `aborted` / `error` 终态路径使用。
4. `App.tsx` 的事件语义、最终消息内容、错误处理与 UI DOM 不变。

## 方案

新增 `frontend/src/streamingFrameBatcher.ts`：

```ts
createStreamingFrameBatcher({
  flush,
  requestFrame = requestAnimationFrame,
  cancelFrame = cancelAnimationFrame
}) => { schedule, settle, cancel }
```

模块仅保存 `frameHandle` 与 `flushPending` 两个状态。生产环境使用浏览器帧 API；测试注入手动帧队列，因此不依赖真实刷新率、计时器或浏览器绘制。

`App.tsx handleChat` 保留 `assistantContent` / `reasoningSummary` 聚合和 `setStreamMessages` 回调，只用 batcher 替换当前内嵌的 schedule / settle / cancel 生命周期。

## 测试

沿用仓库现有 `@playwright/test` runner，新增不使用 `page` fixture 的 TypeScript 测试文件：

- burst 用例：连续三次 `schedule()` 后断言只排一帧、flush 尚未执行；手动执行该帧后断言 flush 恰好一次。
- settle/cancel 生命周期用例：pending 状态下 `settle()` 取消旧帧并同步 flush，`cancel()` 则取消且不 flush；手动尝试执行已取消帧也不能产生第二次刷新。

不新增 Vitest/Jest，不做依赖升级，不通过源码字符串或 mock React setter 来断言实现细节。

## 红—绿与变异验证

由于 rAF 功能已在本轮工作区先行实现，本次属于补回归测试：

1. 先为提取后的公共契约写测试，并确认未实现 API 时测试失败。
2. 实现最小 batcher、接回 `App.tsx`，确认测试通过。
3. 临时移除“已有帧时不重复排队”的保护，确认 burst 用例失败。
4. 恢复实现，再跑专项测试、`tsc -b`、`vite build` 与相关前端回归。

## 范围外

- 不改变 SSE 协议、后端、watch、driver、SafetyGate 或 `SAFETY.md`。
- 不测试浏览器真实 60Hz，也不承诺固定帧率；契约是“每个动画帧至多一次流式 flush”。
- 不把 `streamMessages` 从 Dashboard 下沉，不扩展 C7 的 memo 优化范围。
