# Physical Agent 接手文档

> 仓库：`https://github.com/sunyuan1111/Physical_Agent.git`  
> 本地路径：`C:\Users\17003\Desktop\Physical_agent`  
> 当前分支：`main`，跟踪 `origin/main`  
> 当前提交：`8fa197a`，`2026-05-25T13:04:01+08:00`，`Merge pull request #3 from sunyuan1111/dev`

## 1. 快速结论

Physical Agent 是一个面向安全物理世界 agent 的本地 agent/runtime 项目。新项目默认使用 SQLite `workspace/state.db` 作为状态真源，同时保留 Markdown backend、Markdown parser / renderer 和可读审计导出。它把“认知侧 agent”和“物理执行侧 watch”拆开：

```text
agent/run/chat  ->  写 pending action proposal
watch           ->  claim action -> safety gate -> driver.execute(action)
watch           ->  写 capabilities / world / feedback / log
```

核心边界是：agent 可以提出动作意图，但不能直接触碰硬件或 driver；只有 watch 进程会加载 driver 并执行动作。当前默认 quickstart 使用内置 `mock_arm` 和 SQLite backend，不需要真实硬件，也不需要 LLM API key。

本次已完成：

- 已拉取仓库并安装依赖到 `.venv/`。
- `py scripts/bootstrap.py` 成功，测试结果 `85 passed in 22.75s`。
- quickstart smoke test 成功：执行 2 个动作，`red_block.location = tray`。
- 已启动 GUI：`http://127.0.0.1:8765`，进程 PID `40228`。
- GUI API 验证通过：`setup -> demo -> chat -> doctor` 均可用。
- 内置浏览器插件当前不可用，未做浏览器截图验证；已做 HTML 获取和内联 JS 语法检查，脚本可解析。

## 2. 环境和启动

### 2.1 Python 入口

当前机器上的 `python.exe` 是 Windows Apps 的占位入口，直接运行会失败：

```text
Program 'python.exe' failed to run: The system cannot find the path specified
```

可用入口是：

```powershell
py --version
# Python 3.12.6
```

因此第一次启动建议使用：

```powershell
py scripts\bootstrap.py
```

bootstrap 会创建 `.venv/`，安装 `.[dev]`，运行全量测试，生成默认 `workspace.backend: sqlite` 的 `physical-agent.yaml` 和 `workspace/`，并执行 mock arm smoke test。

### 2.2 常用命令

```powershell
# GUI
.\.venv\Scripts\physical-agent.exe gui --no-open --port 8765

# 健康检查
.\.venv\Scripts\physical-agent.exe doctor

# 查看当前机器人/world/action 状态
.\.venv\Scripts\physical-agent.exe inspect

# CLI 单轮 chat
.\.venv\Scripts\physical-agent.exe chat --planner rule_based --message "What can you see right now?"

# 双终端核心流程
.\.venv\Scripts\physical-agent.exe watch
.\.venv\Scripts\physical-agent.exe run --task "pick the red block and place it on the tray"
```

### 2.3 本次启动验证记录

bootstrap 输出关键结果：

```text
85 passed in 22.75s
Smoke test passed: executed 2 action(s), red_block location is tray.
```

GUI 后台启动：

```text
URL: http://127.0.0.1:8765
PID: 40228
```

GUI API 顺序验证：

```json
{
  "setup_ok": true,
  "setup_watch_started": true,
  "demo_ok": true,
  "demo_message": "Demo completed.",
  "demo_executed": 2,
  "red_block_location": "tray",
  "latest_feedback": "Placed red_block at tray.",
  "completed_actions": 2,
  "pending_actions": 0
}
```

CLI doctor 也通过，`inspect` 显示：

```text
Robots:
- arm_1: arm via mock_arm (observe, move_to, pick, place)

World summary:
The arm is idle. Visible objects: red_block, tray.

Pending actions:
- none
```

## 3. 目录结构概览

```text
physical_agent/
  cli.py                 Typer CLI 入口
  config.py              项目配置模型、默认配置写入/读取
  quickstart.py          setup/smoke test 编排
  doctor.py              健康检查
  agent/                 agent、chat、planner、代码技能、硬件接入助手
  watch/                 watch runtime、safety gate、action dependency 工具
  drivers/               driver contract、loader、内置 driver、driver 模板
  protocol/              Markdown 协议 schema/parser/renderer/workspace（兼容与审计路径仍保留）
  gui/                   依赖最少的本地 Web GUI
  llm/                   OpenAI-compatible Chat Completions 客户端
  mcp/                   轻量 MCP-shaped facade
examples/                quickstart、moce_arm、xiaozhi_mcp_hardware 示例
skills/                  repo-local skill manifest，目前有 code skill
tests/                   单元/集成测试，覆盖 runtime、GUI、chat、safety 等
```

`.gitignore` 已忽略 `.venv/`、`workspace/`、`.physical-agent/`、`physical-agent.yaml` 和 `.env`，所以本次启动生成物没有污染 Git 状态。

## 4. 核心模块说明

### 4.1 `physical_agent/cli.py`

CLI 使用 Typer，主命令包括：

- `init`：写默认 `physical-agent.yaml` 并初始化 workspace；新项目默认 `workspace.backend: sqlite`。
- `setup`：调用 quickstart，支持 `--smoke-test`。
- `doctor`：运行健康检查。
- `gui`：启动本地 Web 控制台。
- `watch`：启动物理侧 watch 循环。
- `run`：提交一次任务，写入 action intent，可等待 feedback。
- `chat`：日常交互入口，支持普通聊天、动作提案、代码技能和 SDK 接入。
- `llm-test`：测试 OpenAI-compatible endpoint。
- `inspect`：打印 robots/world/pending actions。
- `integrate`：从 SDK/repo/package 生成 driver scaffold，可加 `--llm`。
- `driver new`：生成空 driver 模板。
- `skill list`：列出 repo-local skills。

### 4.2 `physical_agent/config.py` 和 `quickstart.py`

默认配置会生成一个 `mock_arm`，并把新项目 backend 设为 SQLite：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
robots:
  arm_1:
    driver: mock_arm
    config:
      objects:
        red_block:
          location: table
        tray:
          location: table
```

`setup_project()` 的流程：

1. 写入默认配置。
2. 初始化 `workspace/`；默认创建 `workspace/state.db`，并保留 `SAFETY.md` 文件真源。
3. 可选启动 `WatchRuntime.setup()` 发布 capabilities/world。
4. 可选 smoke test：`AgentRuntime.run_task()` 写 action，`WatchRuntime.step()` 执行。
5. 跑 `doctor` 并返回结果。

### 4.3 `physical_agent/protocol/*` 与 StateStore

协议层仍保留 Markdown 文件的 schema/parser/renderer/workspace，用于显式 Markdown backend、迁移和审计兼容。默认运行态通过 `StateStore` 工厂打开 SQLite backend；`SAFETY.md` 仍由文件读取。

核心 schema：

- `Action`：`id`、`robot`、`capability`、`params`、`reason`、`depends_on`。
- `ActionResult`：`completed|failed|cancelled`、message、result、artifacts。
- `Observation`：summary、robots、objects、environment、artifacts、raw。
- `Capability`：name、description、params_schema、constraints、approval、timeout。
- `ChatMessage`、`ChatPlan`、`CodeTaskResult` 等。

`Workspace` 是协议文件的主要读写入口：

```text
TASK.md
CAPABILITIES.md
WORLD.md
ACTIONS.md
FEEDBACK.md
SAFETY.md
LOG.md
CHAT.md
PLAN.md
MEMORY.md
artifacts/
```

每次写文件会通过 `_next_revision()` 自动递增 front matter 里的 `revision`。renderer 负责写 YAML front matter 和 fenced YAML block，parser 从固定 heading 下提取 YAML。

### 4.4 `physical_agent/agent/runtime.py`

`AgentRuntime.run_task()` 是 CLI `run` 的核心：

1. 初始化 workspace。
2. 写 `TASK.md`。
3. 读取 `CAPABILITIES.md` 和 `WORLD.md`。
4. 根据配置选择 planner。
5. planner 生成 `Action` 列表。
6. 对 action id 做去重/续号。
7. 写入当前 StateStore 的 pending action；显式 Markdown backend 下对应 `ACTIONS.md`。
8. 如需等待，则轮询 `FEEDBACK.md` 直到 action 完成/失败/取消或超时。

重要点：`AgentRuntime` 不加载 driver，也不调用硬件 SDK。

### 4.5 `physical_agent/agent/rule_based.py`

本地规则 planner，主要靠关键词把任务转成动作：

- observe/look/scan -> `observe`
- move/go -> `move_to`
- pick/grasp -> `pick`
- place/drop -> `place`
- 也扩展了 gripper、say、set_light、set_volume、otto_action、home、stop 等能力匹配。

它会根据 `CAPABILITIES.md` 选择第一个满足能力名的 robot，再从 `WORLD.md` 推断 object/target。默认 pick/place demo 会生成：

```text
act_001 arm_1.pick(object_id=red_block)
act_002 arm_1.place(target=tray), depends_on=[act_001]
```

### 4.6 `physical_agent/agent/llm_planner.py`

LLM planner 使用 OpenAI-compatible Chat Completions。系统提示要求模型只返回 JSON action intent，且只能使用当前 capabilities 里列出的 robot/capability。随后代码会解析 JSON、规范化 id 和 depends_on，生成 `Action`。

`.env` 支持：

```text
GPT_URL / OPENAI_BASE_URL
GPT_KEY / OPENAI_API_KEY
GPT_MODEL / OPENAI_MODEL
```

### 4.7 `physical_agent/agent/chat_runtime.py`

`ChatRuntime.respond()` 是 GUI chat 和 CLI chat 的核心，优先级如下：

1. 先 append 用户消息到 `CHAT.md`。
2. 如果 `SkillRouter` 判断是代码/SDK 接入请求，走 code/integration skill。
3. 如果是硬件接入语义，走 `HardwareIntegrationAssistant` 或 `DriverCodingAgent`。
4. 普通聊天按 `planner_name`：
   - `llm`：严格走 LLM。
   - `auto`：能初始化 LLM 就走 LLM，否则 fallback 到规则。
   - `rule_based`：直接规则聊天。
5. 有动作时 `_append_actions()` 追加到 `ACTIONS.md`，并写 `PLAN.md`。
6. 如果 `auto_step=True`，会临时启动 `WatchRuntime` 执行一轮。

规则聊天支持：

- `remember that ...`：写 `MEMORY.md`。
- 有物理动作关键词：写 action proposal。
- 包含 status/world/see：读取 world 和 latest feedback 回答。
- memory 查询：读取最近 memory notes。

### 4.8 `physical_agent/watch/runtime.py`

`WatchRuntime` 是唯一会加载 driver 并执行 action 的运行时。

`setup()`：

1. 读取 config。
2. 初始化 workspace。
3. 对每个 robot 调用 `load_driver()`。
4. `driver.connect()`。
5. 收集 `driver.capabilities()`，写 `CAPABILITIES.md`。
6. `driver.observe()`，写 `WORLD.md`。

`step()`：

1. 读取 `ACTIONS.md` 的 pending/completed/cancelled。
2. 读取 `SAFETY.md`。
3. 对 pending action 逐个跑 `SafetyGate.validate()`。
4. 通过后调用 `loaded.driver.execute(action)`。
5. 按结果移动到 completed/cancelled。
6. 写 `FEEDBACK.md`、`LOG.md`，并更新 `WORLD.md`。

### 4.9 `physical_agent/watch/safety.py`

Safety gate 会拒绝：

- 重复 action id。
- 依赖未完成。
- 未知 robot。
- robot 不暴露该 capability。
- `SAFETY.md` 禁用 autonomous execution。
- capability 或 robot 需要人工审批。
- params 不符合 capability 的 JSON schema。
- 参数超出 constraints bounds。
- capability timeout 超过 safety max。

这层是物理执行安全边界，必须在 watch 侧执行。

### 4.10 `physical_agent/drivers/*`

driver contract 在 `base.py`：

```python
async def connect()
async def disconnect()
async def health()
async def observe()
def capabilities()
async def execute(action)
```

`loader.py` 支持两类 driver：

- 内置 driver：`mock_arm`、`mock_rover`、`xiaozhi_mcp`。
- 本地 driver 目录：需要 `physical_driver.yaml` 和 `driver.py`，driver class 必须继承 `PhysicalDriver`。

`mock_arm.py` 是 quickstart 默认模拟器，维护 pose、holding、objects，支持 `observe/move_to/pick/place`。`place` 会把 held object 的 location 设置为 target；如果 target 有 pose，会同步 pose。

`xiaozhi_mcp.py` 是更复杂的硬件桥示例，包含 WebSocket client、HTTP/JSON-RPC 调用、remote tool refresh，以及 `XiaozhiMcpDriver`。

### 4.11 `physical_agent/agent/onboarding.py` 和 `driver_coder.py`

硬件接入有两档：

- `HardwareIntegrationAssistant`：确定性扫描 SDK/repo/package，推断 source kind、transport、robot kind、capabilities、config schema，然后生成 driver scaffold、README 和 integration report。
- `DriverCodingAgent`：先生成安全 scaffold，再收集 SDK 上下文，调用 LLM 生成有限 allowlist 文件，放到临时 candidate 中验证。验证通过才写回输出目录；失败则保留安全 scaffold 并写 `llm-coding-report.md`。

允许 LLM 更新的文件范围很窄：`driver.py`、`physical_driver.yaml`、README、report、聚焦测试文件。生成 driver 必须仍然遵守 watch-side 边界。

### 4.12 `physical_agent/agent/code_runtime.py`

代码技能用于 chat 中处理“改文件/写测试/运行脚本/SDK 接入”类请求：

- `CodeIntentRouter` 识别 code_run、code_edit、sdk_integration。
- code_run 会定位脚本，用当前 Python 执行，产物放到 `.physical-agent/code/artifacts/`。
- code_edit 会调用 LLM 生成 JSON patch，限制在 repo root 内写文件，随后运行测试。
- 内置 deterministic 示例：识别画正方形任务时直接写 `test/draw_square.py` 和测试。
- lessons 写入 `.physical-agent/code/LESSONS.md`。

## 5. GUI / 前端交互详细说明

这个项目没有独立 `frontend/`、`package.json` 或构建链路。GUI 是 `physical_agent/gui/server.py` 里的 dependency-free 本地 Web 控制台：

- 后端：`ThreadingHTTPServer` + `BaseHTTPRequestHandler`。
- 前端：一个 `INDEX_HTML` raw string，内含 HTML、CSS、JS。
- 数据：全部通过 `/api/*` JSON 端点读取/写入 workspace。

### 5.1 GUI 后端 controller

`GuiController` 持有：

```python
self.config_path
self.lock
self.watch_runtime
```

所有会改状态的操作都在 `with self.lock:` 中执行，避免并发请求同时改 workspace/watch_runtime。

主要方法：

- `state()`：读取 config/workspace，返回页面渲染所需完整状态。
- `setup(force=False)`：停止旧 watch，调用 `setup_project()`，然后创建并 setup 新 `WatchRuntime`。
- `start_watch()`：确保 watch 已连接。
- `stop_watch()`：关闭 watch 并清空 runtime。
- `step_watch()`：执行一轮 watch step。
- `submit_task(task)`：调用 `AgentRuntime.run_task(..., wait_for_feedback=False)`。
- `chat_message(message, planner, auto_step)`：调用 `ChatRuntime.respond(..., auto_step=False)`，如果 UI 勾选 auto-step，再复用 GUI 持有的 watch runtime 执行一步。
- `integrate_hardware(...)`：调用 scaffold 或 LLM driver coding。
- `run_demo()`：提交固定 pick/place 任务，然后 watch step。
- `doctor()`：返回健康检查。

### 5.2 HTTP API

GET：

```text
/             返回 INDEX_HTML
/api/state    返回完整 GUI state
/api/doctor   返回 doctor checks
```

POST：

```text
/api/setup          body: {force?: boolean}
/api/watch/start
/api/watch/stop
/api/watch/step
/api/task           body: {task: string}
/api/chat           body: {message: string, planner?: auto|llm|rule_based, auto_step?: boolean}
/api/integrate      body: {source: string, output?: string, name?: string, llm?: boolean, model?: string}
/api/demo
```

错误处理：`do_POST` 外层捕获异常并返回 HTTP 500 + `{ok:false,message}`；空 task/chat/source 会返回 400。

### 5.3 `/api/state` 数据结构

前端主要依赖这些字段：

```text
ready
watch_started
message
config_path
workspace_path
task
capabilities
world
code_result
actions.pending/completed/cancelled
feedback
chat
plan
memory
doctor
```

其中 `code_result` 会从 `CHAT.md` 最新带有 `metadata.code_result` 的消息中提取，用于显示代码技能结果面板。

### 5.4 前端布局

页面分两列：

左列：

- Chat 面板：planner 选择、聊天记录、输入框、发送按钮、auto-step checkbox、code result details。
- Quick actions：Setup、Reset、Start watch、Run step、Pick/place demo、Refresh。
- Hardware integration：source/name/model/mode 输入与 Generate driver。

右列：

- World：world summary 和 robots。
- Actions：pending/completed/cancelled。
- Feedback：latest feedback。
- System：config/workspace/message 和 details JSON（plan/memory/doctor）。

响应式断点：`max-width: 900px` 时改成单列。

### 5.5 前端 JS 流程

关键函数：

- `setLanguage(next)`：更新 localStorage、`documentElement.lang`、所有 `data-i18n` 和 placeholder。
- `api(path, options)`：fetch JSON，非 2xx 抛错。
- `post(path, payload)`：JSON POST。
- `render(state)`：统一更新 status、chat、code result、world、actions、feedback、system。
- `renderChat(state)`：展示最近 16 条消息。
- `renderWorld(state)`：展示 summary 和 robot capabilities。
- `renderActions(state)`：展示 action board。
- `renderFeedback(state)`：展示 latest feedback。
- `run(labelKey, fn)`：按钮通用 loading/error/render 包装。

事件绑定：

```text
Setup          -> POST /api/setup
Reset          -> POST /api/setup {force:true}
Start watch    -> POST /api/watch/start
Run step       -> POST /api/watch/step
Demo           -> POST /api/demo
Refresh        -> GET  /api/state
Send chat      -> POST /api/chat
Generate driver-> POST /api/integrate
```

### 5.6 GUI 交互链路示例

#### Pick/place demo

```text
button#demo
  -> post("/api/demo")
  -> GuiController.run_demo()
  -> AgentRuntime.run_task(wait_for_feedback=False)
  -> write TASK.md + ACTIONS.md
  -> WatchRuntime.step()
  -> SafetyGate.validate()
  -> MockArmDriver.execute(pick/place)
  -> write FEEDBACK.md + WORLD.md + ACTIONS.md
  -> JSON state
  -> renderWorld/renderActions/renderFeedback
```

#### Chat with auto-step

```text
button#send-chat
  -> post("/api/chat", {message, planner, auto_step})
  -> GuiController.chat_message()
  -> ChatRuntime.respond(auto_step=False)
  -> maybe append actions to ACTIONS.md
  -> if UI auto_step and actions: existing WatchRuntime.step()
  -> JSON state
  -> renderChat/renderActions/renderFeedback/renderWorld
```

这里 GUI 特意让 `ChatRuntime.respond()` 不自己启动临时 watch，而是复用 GUI controller 内持有的 watch runtime。这个设计避免 chat auto-step 和 GUI watch 状态分叉。

#### Hardware integration

```text
Generate driver
  -> post("/api/integrate", {source,name,model,llm})
  -> GuiController.integrate_hardware()
  -> llm=false: HardwareIntegrationAssistant.generate()
  -> llm=true:  DriverCodingAgent.generate()
  -> result + refreshed state
```

### 5.7 前端已知问题

中文 i18n 文案在源码和测试里已经是乱码形态，例如按钮显示文本为 `涓枃`，英文状态中的分隔符也出现 `Ready 路 watch connected`。这不是启动阻断，JS 语法检查通过，但中文 UI 实际会显示乱码。相关位置：

- `README.zh-CN.md`
- `physical_agent/gui/server.py` 的 `I18N.zh`
- `physical_agent/agent/rule_based.py` / `chat_runtime.py` / `code_router.py` 中部分中文触发词和中文回复
- `tests/test_gui_server.py` 当前还显式断言 `涓枃`

建议后续单独做一次编码修复：确认原始预期中文文案，修复源码和测试断言，并加一个 UTF-8 中文 smoke test。

### 5.8 前端验证边界

本次尝试使用 Codex 内置 Browser 插件时返回：

```text
Browser is not available: iab
```

所以没有截图级视觉验证。替代验证包括：

- `GET /` 返回 HTML。
- 内联 JS 提取后 `node --check` 通过。
- `/api/state`、`/api/doctor` 可用。
- `/api/setup -> /api/demo` 跑通。
- `/api/chat` rule-based 模式可用。

项目自己的 `tests/test_gui_server.py` 主要覆盖 HTTP endpoint，不覆盖真实浏览器 DOM/点击/控制台。

## 6. 测试覆盖

本次 bootstrap 跑了全量测试：`85 passed`。主要覆盖：

- Markdown front matter 和 fenced YAML parser/renderer。
- Workspace 初始化、revision、log append。
- Driver manifest/config schema/loader。
- mock arm、mock rover、Xiaozhi MCP driver。
- rule-based planner。
- watch runtime step 和 safety gate。
- agent/run 到 watch 的端到端 Markdown loop。
- quickstart doctor/smoke test。
- GUI HTTP endpoint，包括 setup/demo/chat/integrate。
- Chat runtime 的 memory/action/auto-step/LLM fallback。
- Code skill、SDK integration、driver coding validation。

GUI 相关测试重点文件：

- `tests/test_gui_server.py`
- `tests/test_chat_runtime.py`
- `tests/test_e2e_markdown_loop.py`
- `tests/test_watch_runtime.py`

## 7. 重要接手注意事项

1. `python` 命令在当前 Windows 环境不可用，优先用 `py` 或 `.venv\Scripts\python.exe`。
2. `workspace/`、`workspace/state.db` 和 `physical-agent.yaml` 是运行态文件，默认被 gitignore，不要把它们当源码改动提交。
3. 新项目默认 backend 是 SQLite；已有 Markdown 项目只要显式保留 `workspace.backend: markdown`，仍走 Markdown backend。单项目回滚也是把该配置改回 `markdown`。
4. agent/watch 的安全边界不要打破：任何真实硬件执行都必须经过 `action board -> watch -> SafetyGate -> driver.execute()`。
5. GUI 是单文件内联前端，改起来方便但可维护性一般；如果继续扩展 UI，建议拆出模板/static assets 或引入轻量前端结构。
6. LLM 相关功能需要 `.env`，默认没有 key 时 rule-based 路径仍然能跑。
7. PowerShell 下用 `curl.exe -d '{"force":true}'` 可能吞掉 JSON 双引号；调试 API 建议用 `Invoke-RestMethod`。
8. 中文文案/触发词疑似 mojibake，需要专项修复。

## 8. 建议下一步

优先级较高：

- 修复 UTF-8 中文文案和相关测试断言。
- 给 GUI 增加浏览器级 E2E smoke test：页面加载、点击 setup/demo、发送 chat、检查 DOM 状态。
- 把 GUI 的 HTML/CSS/JS 从 Python raw string 中拆出来，至少分成模板和静态 JS，便于维护。
- 为 `/api/setup`、`/api/demo` 等长操作增加前端禁用按钮/防重复点击状态。

中期：

- 明确真实硬件 approval 流程，在 GUI 中显示“需要人工批准”的状态和操作入口。
- 为 driver integration 的输出目录和覆盖行为增加更明显的 UI 提示。
- 给 LLM planner/chat 增加更细的错误分类展示。

长期：

- 如果 MCP 要变成正式服务，需要从当前 dependency-free facade 接入具体 MCP server library。
- 如果多 robot/多用户并发需求变强，需要重新设计 workspace 文件锁、watch 生命周期和 UI 状态同步。
