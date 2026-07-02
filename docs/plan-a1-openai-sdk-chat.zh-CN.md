# 计划：A1 官方 OpenAI SDK 替换 + Chat 能力增强

> 状态：计划草案
> 锚点里程碑：spec §10 的 **A1**（urllib → 官方 `openai` SDK），把本轮新需求全部挂在它下面。
> 目标模型：火山方舟 Doubao-Seed-2.1-pro（OpenAI 兼容，支持 response_format + 深度思考 + 多模态输入）。
> 本轮范围内需求：接通真实 chat、流式输出、PDF 上传、深度思考、abort/异常处理、工作台内配置用户自己的 API。
> **暂不做**：多模态（图片/视频输入）——留待以后探索。

---

## 0. 为什么以 A1 为锚（我的判断）

这些需求大部分是"换了官方 SDK 就几乎白送"的：

- 官方 `openai` SDK 的 `client.chat.completions.create(stream=True)` 原生**流式**，不用手写 SSE 帧解析。
- **深度思考**参数（Doubao 的 `thinking` / `reasoning_effort`）通过 SDK `extra_body` 直接透传，reasoning 内容单独字段返回。
- SDK 的 `OpenAI(base_url=...)` **自动修掉现在 `/api/v3` 被拼成 `/api/v3/v1/chat/completions` 的坑**。
- **abort**：SDK 支持超时/取消，流式可中断迭代器。

所以把这几项捆进 A1 一起做，比先换 SDK 再各自返工省很多。**唯一不属于 SDK 的是 PDF 上传**（属于摄入层 B4b 的扩展），顺带做。

安全边界全程不变：chat 仍只提案；流式/思考/PDF/配置都是认知侧，watch + SafetyGate 不动。

---

## 1. 分步计划（小步、默认关闭、可回滚）

### A1.0 换官方 SDK（行为不变，先冻结功能面）
- `pyproject.toml`：`[llm]` extra 加 `openai>=1.40`。
- 重写 `OpenAICompatibleClient` 内部改用 `openai.OpenAI(base_url, api_key, timeout)`，**保留现有公开方法签名**（`chat` / `structured_json` / `responses_create` / `test_connection`），调用方零改动。
- 顺带修 base-url：交给 SDK 处理，删掉自制的 `/v1/chat/completions` 拼接。
- 保留 chat_completions / responses 双模式、rule_based 兜底。
- **验收**：mock SDK 的现有 `test_openai_compatible.py` 全绿；`llm-test` 能连火山方舟。

### A1.1 接通并验证真实 chat（本轮第一优先）
- 新增 `.env.example`（火山方舟示例）：
  ```
  GPT_URL=https://ark.cn-beijing.volces.com/api/v3
  GPT_KEY=<ark key>
  GPT_MODEL=doubao-seed-2.1-pro   # 或推理接入点 ep-xxxx
  ```
- 默认 `agent.planner` 由 `rule_based` 改为 `auto`（有 key 走 LLM，无 key 安全回退）。
- `structured_json()` 增加 **strict `json_schema` → `json_object` 自动降级**：豆包若不吃 strict schema 就回退 JSON mode（把 schema 塞进 system prompt 约束）。
- **验收**：`chat --planner llm` 真实返回 LLM 回复，返回体 `mode=llm`。

### A1.2 流式输出
- 客户端新增 `chat_stream()`（SDK `stream=True`，yield 文本 delta）。
- **关键取舍**：流式只用于**对话正文 reply**；**动作提案（structured actions）仍走非流式结构化调用**。即"先流式吐自然语言回答，提案单独结构化返回"，避免流式里解析半截 JSON。
- 接入：复用 C2 的 SSE 基建，新增流式 chat 通道；前端用 Ant Design X `Bubble` 的流式渲染吃 delta。
- 默认可开关：`agent.chat.stream`。

### A1.3 深度思考（reasoning）
- 配置 `agent.reasoning.enabled`（默认关）+ 透传 Doubao `thinking.type` / `reasoning_effort`（SDK `extra_body`）。
- reasoning 内容与最终答案分离：前端用 Ant Design X `ThoughtChain` 单独展示思考链，不混进 reply。
- **验收**：开启后能收到并展示 reasoning，关闭后行为与 A1.1 一致。

### A1.4 abort + 简单异常处理
- **abort**：流式请求可取消——API 侧提供中断在途 chat 的入口（取消 async 任务 / 关闭流）；前端"停止"按钮。
- **异常分类**：把 SDK 异常（`RateLimitError` / `APITimeoutError` / `APIConnectionError` / `BadRequestError`）映射成清晰的用户可读提示；`auto` 模式失败仍回退 rule_based 并显式说明原因。
- **验收**：拔网/超时/限流/错误模型名分别给出可区分提示，不吞异常、不卡死。

### A1.5 PDF 上传（B4b 摄入扩展）
- `ingest/files.py` 放开 `.pdf`：抽文本（`pdfminer.six` 或 `pypdf`，放进可选 `[ingest]`/`[pdf]` extra）后走**现有 inline/ingest 两档**。
- 扫描件/纯图 PDF（无文本层）明确拒绝并提示"暂不支持 OCR"。
- 仍受大小上限；**上传内容仍是不可信输入，只进提案上下文**（§0 红线）。
- **验收**：文本型 PDF 能摄入并被检索/inline；图片型 PDF 给清晰错误。

### A1.6 工作台 Settings 模块：填 URL + API key（推荐加入）
- **定位（重要）**：本地单用户工具，前端/后端/CLI/watch 全在用户自己机器上，key 不经过任何第三方。所以目标只是"免手改 `.env`"，**不是防外部泄露**——不用堆重防护。
- 前端复用已有 `SettingsPanel`：填 `base_url`（或完整 endpoint）/ `api_key` / `model`，加流式、深度思考开关，和"测试连接"按钮。
- 后端：
  - **单一来源** `workspace/.llm.json`（gitignore），**CLI / GUI / watch 共用同一份**；CLI 仍兼容读 `.env`。
  - `GET /api/settings/llm`：回 url / model + key 状态（打码尾号，纯属体面，不是防谁）。
  - `POST /api/settings/llm`：写入；`POST /api/settings/llm/test`：复用 `llm-test`。
  - **为什么走本地后端而非浏览器直连 LLM**：厂商 CORS 通常挡浏览器跨域调用 + CLI/watch 也要用同一 key。工程原因，非第三方安全。
- **卫生就两条**：别提交进 git、别打进日志。
- **验收**：工作台填好 URL+key 即用，无需手改 `.env`；CLI/GUI/watch 共享同一份；重启后仍在。

### A1.7 重置能力（会话级 + 工作区级，二者解耦）
- **背景**：新 React GUI 在重构里**丢了重置入口**（`api/server.py` 无任何 reset 端点）；旧 GUI 的 Reset 是"核平整个 workspace"，把对话和世界/动作/记忆一起清。本轮拆成两个**解耦**入口，**先不引入多会话**。
- **A1.7a 会话级重置（新对话 / 清空对话）**：
  - StateStore 新增 `reset_conversation()`：只清 chat 消息 + `running_summary`；**保留** WORLD / CAPABILITIES / SAFETY / ACTIONS / FEEDBACK / MEMORY / PLAN。markdown / sqlite 两 backend 都实现。
  - API：`POST /api/conversation/reset`。
  - 前端：对话面板顶部加"新对话 / 清空对话"按钮。
  - 现在对"当前单条会话"操作；将来多会话落地时改成按 `conversation_id` 即可（前向兼容）。
- **A1.7b 工作区级重置（全量，二次确认）**：
  - 等价旧 `setup(force=True)` 的 full re-init（overwrite）。
  - API：`POST /api/workspace/reset`（需显式 `confirm=true`）。
  - 前端：放 Settings/Overview，带确认弹窗，文案明确"会清空世界/动作/记忆/对话"。
  - 复用现有 `setup(force=True)`，不新造逻辑。
- **边界**：重置全在认知/状态侧，**不触碰 watch/driver/硬件执行**；会话级重置尤其不得牵连 world/硬件状态。
- **验收**：会话重置后 chat 空、summary 清，但 world/actions/memory 仍在；工作区重置与旧 Reset 一致且需确认；新 React GUI 两个入口都可用（恢复并超越旧 GUI 的重置能力）。

### A1.8 恢复硬件接入面板 + 机器人连接信息展示
- **背景**：C3 重写 React GUI 时没把旧 GUI 的"硬件接入/生成 driver"面板搬过来——新 `api/server.py` **无 `/api/integrate` 端点**、未 import `HardwareIntegrationAssistant`/`DriverCodingAgent`；新 `RobotsPanel` 只读且**不显示连接端点/port/health**；`physical-agent.yaml`（robots[].config 里藏着 `serial_port`/`endpoint`）也未在 GUI 暴露。**后端能力都在，纯属没接线。**
- **A1.8a 硬件接入面板（恢复旧能力）**：
  - 新 API 加 `POST /api/integrate`，**直接复用现有** `HardwareIntegrationAssistant`（脚手架）/ `DriverCodingAgent`（LLM 草稿）。
  - React 加 Hardware 面板：`source` / `name` / `model` / `mode`（脚手架 vs LLM 草稿）+ 结果展示（生成路径、检测到的 transport/robot_kind、验证状态）。
  - 边界：生成 driver 仍是"写文件 + mock 验证"，**不执行硬件**。
- **A1.8b 机器人连接信息展示**：
  - `RobotsPanel` 补列：**transport endpoint / port / health**——读自 `world.robots`（driver `observe()` 提供的 `endpoint`/`mode`）+ `driver.health()`。
  - 让用户在界面上看得到"连到哪、连没连上"，补回旧 GUI world 视图里的连接明细。
- **A1.8c（可选）项目配置面板**：
  - 展示/编辑 `physical-agent.yaml` 的 `robots`（driver + config，含 `serial_port`/`endpoint`）、`watch`、`agent` 段；用 `physical_driver.yaml` 的 `config_schema` 驱动表单校验。
  - **保存 = 写回 yaml + 触发 re-setup**（watch 重载重连），不热更；审批/bounds 等安全字段编辑需显眼。
  - 这一项同时解决"新 GUI 看不到 port"——因为 port 就在 robots[].config 里。
- **边界**：接入生成/配置编辑全在认知/配置侧，不碰 watch 执行；配置改动经 re-setup 生效；不绕过 SafetyGate。
- **验收**：新 GUI 能像旧 GUI 一样从 source 生成 driver；RobotsPanel 显示 endpoint/port/health；（可选）能在 GUI 改 `serial_port` 并 re-setup 生效。

---

## 2. 顺序与依赖

```text
A1.0 换 SDK（含修 base-url）          先做，行为不变
A1.1 接通 + json 降级 + 默认 auto     A1.0 后立刻，拿到"能对话"
────────── 以上跑通再叠加 ──────────
A1.2 流式    ┐
A1.3 深度思考 ├ 三者相对独立，可并行；都默认关闭
A1.4 abort/异常 ┘
A1.5 PDF 上传（摄入层，独立，可随时插）
A1.6 Settings 面板（依赖 A1.0 的客户端 + 现有 FastAPI/React）
A1.7 重置能力（会话级/工作区级，与 SDK 无关，独立，可随时插）
A1.8 硬件接入面板 + 机器人连接信息（后端已在，纯接线，独立，可随时插）
```

建议：**A1.0 + A1.1 单独一轮先合并**，确认真实 chat 通了，再排后面的增强。

---

## 3. 关键取舍与开放问题

1. **流式 vs 结构化**：本计划采用"对话正文流式、动作提案非流式结构化"。若要连提案也流式，需要增量 JSON 解析，复杂度高——建议首版不做。
2. **豆包是否支持 strict `json_schema`**：截图不确定。A1.1 内置 `json_object` 降级即可兜底；实测后确定默认走哪个。
3. **深度思考的成本/延迟**：reasoning 会增加 token 与时延，默认关闭，按需开。
4. **key 存储形态**：`workspace/.llm.json`（结构化、易打码）还是写 `.env`（与 CLI 一致）？倾向前者，CLI 仍读 `.env` 兼容。
5. **多用户**：当前单用户本地工具，key 存 workspace 本地即可；若将来多用户/多项目需重新设计隔离。

---

## 4. 与 spec / 重构日志的关系

- 本计划把重构日志里 **A1（未做）** 正式补上，并把它从"仅换客户端"扩展为"换 SDK + chat 能力增强"。
- 顺带偿还两笔欠账：base-url 兼容、**PDF 摄入**（原 B4b 只做了文本）。
- **多模态**仍留欠账，但 A1.0 换 SDK 后，多模态从"客户端不支持"变成"加 content-block 即可"，为以后铺好路。

---

*本文件是实施计划，不含实现代码。建议按 §2 顺序、每步附测试与 handoff 落地，保持安全边界与"默认关闭"纪律。*
