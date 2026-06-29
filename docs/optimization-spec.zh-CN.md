# Physical Agent 优化设计 Spec：状态存储 / Agent 工具循环 / 记忆与上下文 / 后端与 GUI / 传输与硬件安全

> 状态：草案 v0.3
> 适用提交：`8fa197a`（main）
> 范围：七条优化主线的统一设计与分阶段实施方案
> 一句话目标：把 v1 的"双终端 + Markdown loop + 手写 HTTP + 朴素记忆 + 各写各的传输"演进为"可常驻服务 + 结构化（JSON/SQLite）状态 + 标准 agent 工具循环 + 分层记忆 + 现代 GUI + 统一传输层 + 硬件级 fail-safe"，**且不破坏现有安全边界**。

本版相对 v0.2 的新增：**Phase D 传输层抽象 + 串口 + 硬件级安全**（§7）。

---

## 0. 不可协商的安全不变量（贯穿全文）

```text
agent 只能提案动作  ->  pending action
watch 是唯一加载 driver、跑 SafetyGate、执行动作的进程
SafetyGate 永远在 watch 侧
driver 不感知存储后端、不调用 agent runtime
```

四条硬约束：

1. **agent 侧（含 LLM 工具循环、记忆检索、上下文压缩、FastAPI 请求处理）永远不导入 driver、不调用硬件 SDK、不直接执行动作**。它只写"提案"。
2. **执行路径唯一**：`提案 -> watch -> SafetyGate.validate() -> driver.execute() -> transport`。无论状态是 JSON/SQLite、记忆来自向量检索、历史被压缩、还是传输是串口，这条链路不变。
3. **新增能力不得绕过安全边界**：记忆检索、上下文压缩、**上传文档**只影响 agent 提案；安全关键事实（SAFETY 规则、approval、pending 依赖、world）一律从结构化 state 实时读取，绝不依赖摘要。**上传文档视为不可信输入（prompt-injection 面），只进提案上下文，由它引出的任何动作仍须过 SafetyGate。**
4. **软件安全 + 硬件安全双层**：`SafetyGate` 是软件侧、执行前的闸门；Phase D 的看门狗/E-stop 是硬件侧 fail-safe——**即使 watch 崩溃或通信中断，硬件也必须能停**。两者互补，缺一不可。

> 验收口径：每阶段后 SafetyGate 拒绝路径测试、端到端 loop 测试全绿；agent 侧 import 图不得出现 `physical_agent.drivers.*`（静态检查守住，见 §9）。

---

## 1. 现状基线与本次范围

当前架构：

- **状态层**：`protocol/workspace.py` 把 10 个 `*.md` 当协议黑板（front-matter + fenced YAML 混合体，靠 `parsers/renderers` 转换）。
- **IPC**：agent 写 `ACTIONS.md`，watch 按 `tick_ms`（默认 500ms）轮询执行，结果写回 `FEEDBACK/WORLD/LOG`。
- **LLM**：`llm/openai_compatible.py` 手写 `urllib`，`LLMPlanner` 一次性吐 JSON，无多轮工具调用。
- **工具预留**：`mcp/server.py` 已有提案专用 `tool_specs()` / `propose_action()`。
- **记忆**：`MEMORY.md` 朴素追加列表，无检索；`CHAT.md` 无压缩。
- **后端/前端**：`gui/server.py` 是 `ThreadingHTTPServer` + 内联 HTML + 单锁，中文 `涓枃` mojibake。
- **传输**：各 driver 各写各的——`xiaozhi_mcp.py` 自带 WebSocket + HTTP/JSON-RPC，mock 进程内，**无串口/BLE/CAN，无硬件级 fail-safe**。
- **依赖**：仅 `pydantic / typer / PyYAML / jsonschema`。

七条主线与耦合关系：

```text
A  OpenAI 官方 SDK + 工具调用循环          agent 侧内聚，最低风险，先做
A3 最简上下文压缩（rolling summary）         随 A，轻量
B  JSON 为准的 StateStore + SQLite + 人类视图 地基：定下 GUI/记忆的数据契约
B4 记忆分层 + sqlite-vec 检索               建在 B 的 SQLite 之上
C  FastAPI 后端 + 常驻 watch + AntD GUI      依赖 B 的 JSON 契约稳定后再做
D  传输层抽象 + 串口 + 硬件级安全            仅动 drivers/ + watch/，与 A/B/C 解耦
```

排序原则：A 内聚先行；B 是数据地基；记忆建在 B 上；GUI 等 B 契约定型；**D 与 A/B/C 解耦，默认排最后（看门狗正好挂进 C 的常驻循环），可随真硬件随时前移**。

---

## 2. 阶段 B：JSON 为准的 StateStore + SQLite + 人类可读视图

### 2.1 设计原则

- **SQLite 为唯一真源，payload 用 JSON**（不再用 Markdown 当存储格式），可**直接删掉** `parsers/renderers` Markdown 混合解析层，schema 用 pydantic 校验。
- **人类可读文本是从 JSON 生成的视图，不是存储格式**（见 2.4）。
- `StateStore` 抽象把"读写状态"与"后端"解耦；driver 与 SafetyGate 继续只与 `Action`/`Observation`/`Capability` 交互，不感知后端。

### 2.2 StateStore 接口

`physical_agent/state/base.py`，方法名与现有 `Workspace` 对齐，新增原子操作：

```python
class StateStore(Protocol):
    def write_task(...); def read_task() -> dict: ...
    def write_capabilities(...); def read_capabilities() -> dict: ...
    def write_world(...); def read_world() -> dict: ...
    def read_actions() -> dict: ...                      # 组装 {pending, completed, cancelled}
    def append_pending_action(self, action: Action) -> None: ...   # 原子追加
    def claim_next_ready_action(self) -> Action | None: ...        # watch 侧原子领取
    def write_feedback(...); def read_feedback() -> dict: ...
    def read_safety() -> dict: ...                       # 仍读文件
    def append_chat_message(...); def read_chat() -> dict: ...
    def append_memory_note(...); def read_memory() -> dict: ...
    def append_log(...): ...
    def export_human_view(self, out_dir: Path) -> None: ...        # JSON -> 人类视图
```

### 2.3 SQLite schema

`workspace/state.db`，`PRAGMA journal_mode=WAL`：

```sql
CREATE TABLE doc_state (name TEXT PRIMARY KEY, revision INTEGER DEFAULT 1, payload TEXT, updated_at TEXT);
CREATE TABLE actions (id TEXT PRIMARY KEY, robot TEXT, capability TEXT, params TEXT, reason TEXT,
                      depends_on TEXT, status TEXT, result TEXT, seq INTEGER, created_at TEXT, updated_at TEXT);
CREATE INDEX idx_actions_status ON actions(status, seq);
CREATE TABLE log_entries   (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, message TEXT);
CREATE TABLE chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, created_at TEXT, metadata TEXT);
CREATE TABLE memory_notes  (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, source TEXT, created_at TEXT);
```

`read_actions()` 由 `SELECT ... WHERE status=?` 组装，调用方零改动；`SAFETY.md` 保持文件真源；`doc_state.revision` 保留自增。

### 2.4 人类可读视图（取代 Markdown 审计）

- **结构化数据 + summary 字段并存**：每类状态 JSON 带 `summary` 人话句子（`Observation.summary` 已有先例）。
- `export_human_view()`：渲染 pretty-print JSON + 可选自然语言摘要到 `workspace/audit/`，保留 git 可 diff 审计。
- dashboard 不展示 raw JSON，而是字段映射成 AntD 组件 + summary（§6）。

### 2.5 配置、迁移、风险

```yaml
workspace: { path: ./workspace, backend: sqlite, format: json, audit_export: true }
```

工厂 `open_state_store(config)` 取代直接 `Workspace(path)`；`physical-agent migrate-md-to-sqlite` 迁移；风险缓解：审计靠 `audit_export`、回归靠后端矩阵测试（§9）、并发靠 WAL + 行级原子、安全入口靠 `SAFETY.md` 保持文件。

---

## 3. 阶段 A：OpenAI 官方 SDK + 工具调用循环

### 3.1 SDK 接入

- `openai>=1.x` 放进 `[llm]` extra（核心 + rule_based 仍零重依赖）；复用现有 env 变量；用 `OpenAI(api_key, base_url)` 构造。
- 保留 `structured_json()` 签名。拆两步：**A1 仅换客户端（行为不变）**，**A2 加工具循环**。

### 3.2 工具调用循环（`agent/tool_loop.py`）

```text
loop (<= agent.max_steps):
  resp = client.<chat|responses>.create(model, input=messages, tools=TOOL_SPECS)
  if 无 tool_call: 收尾返回文本
  for call in tool_calls: messages += tool_result(dispatch(call))   # 仅白名单
```

- 白名单 = `tool_specs()`，dispatch 只路由 `submit_task` / `propose_action`——只写 pending action，绝不执行硬件。
- **禁止**注册任何 import driver / 调 `driver.execute` 的工具（§9 静态检查）。
- `params` 走 `Action.model_validate` + watch 侧 `SafetyGate` 双层兜底。

### 3.3 与现有 planner 的关系

`agent.planner` 新增 `tool_loop`；`auto` 升级为优先 `tool_loop`、失败回退 `rule_based`；`ChatRuntime` 优先级链不变。

---

## 4. 记忆分层与检索（sqlite-vec）

### 4.1 分层

| 记忆类型 | 现状 | 方案 |
| --- | --- | --- |
| 工作/状态（world、pending） | 状态层 | SQLite，**不需要 RAG** |
| 情景（任务、结果） | `LOG`/feedback | 结构化查询；相似历史再加向量 |
| 语义（事实、偏好、lessons） | `MEMORY`/`LESSONS` | 量小=行；量大=embedding |
| **文档接地（真正的 RAG 收益）** | 无 | SDK 文档 / driver 手册 / 安全策略 → 切块嵌入，给 planner 与 `DriverCodingAgent` 接地 |

### 4.2 sqlite-vec：一套存储加向量表

```sql
CREATE TABLE memory_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, content TEXT, source TEXT, created_at TEXT);
CREATE VIRTUAL TABLE memory_vec USING vec0(chunk_id INTEGER, embedding FLOAT[768]);  -- dim 取决于 embedding 模型
```

### 4.3 策略与安全

- **结构化召回优先，向量召回用于相似历史与文档接地**；最该上 RAG 的是 `DriverCodingAgent`。
- 渐进：先结构化上线，语料够再开 `memory.embedding.enabled`。别过早堆重 RAG。
- 安全：检索只进 agent 提案上下文，**不进 watch 执行路径**（§0）。

### 4.4 输入摄入：文件上传（不单列主线，作为 §4 的入口）

输入端现状很机械：agent 只读十个固定协议文件，全量 dump + 末尾切片（`chat[-12:]`/`memory[-20:]`），且**无法摄入用户主动提供的外部文档**。补一个**普通文件上传**入口即可，UI 用 AntD `Upload`（拖拽），后端 `POST /api/upload`（multipart）。

**上传只是前门，处理按大小/用途分两档**（不要建花哨流水线）：

- **小文档**（笔记、任务简报、短手册）→ 抽文本后 **inline 进本轮 context**。
- **大文档 / 需长期留存**（整本手册、SDK 文档）→ 切块嵌入进 `memory_chunks`（§4.2），后续**检索接地**，不整篇入 prompt。

约束：

- 存 `workspace/uploads/`（仿 `artifacts/`），元数据进 state 可审计；v1 只收**可抽文本类型**（txt/md/code/PDF→抽文本），图片留待 vision；加大小上限。
- **安全（§0 第 3 条）**：上传内容是**不可信输入**，只进提案上下文；由它引出的动作仍须过 `SafetyGate`，绝不自动执行。

---

## 5. 上下文管理（最简压缩）

### 5.1 最简方案：rolling summary buffer

```text
保留最近 K 条消息 verbatim；更旧的滚动摘要成 running_summary，存进 state；条数/token 超阈值触发压缩
工具循环每轮喂：能力清单 + 当前 world + running_summary + 最近 K 条
```

```yaml
agent: { context: { max_recent: 12, summarize_threshold: 24, summary_mode: simple } }  # simple | llm
```

### 5.2 安全红线

压缩**只作用于"对话叙事"**；**安全关键事实（SAFETY、approval、pending 依赖、world）一律从结构化 state 实时读取，绝不依赖 running_summary**。

### 5.3 范式呼应与演进

会话内压缩 + 跨阶段开新 session（spec/state 落盘做记忆载体）互补。首版只做 `simple` 阈值 + 拼接裁剪；后续可升级 token 计数 / LLM 摘要 / importance 加权。

---

## 6. 阶段 C：FastAPI 后端 + 常驻 watch + AntD GUI

### 6.1 API 与常驻 watch

- FastAPI + pydantic 暴露等价端点（自动 OpenAPI + 校验）；新增 `GET /api/events`（WS/SSE）watch step 后推送增量状态。
- FastAPI lifespan 后台任务跑常驻 `WatchRuntime`（按 `tick_ms`）；单锁职责下沉状态层（WAL + `claim_next_ready_action`）。**只有 watch 后台任务能 import driver / 跑 SafetyGate / execute；HTTP 请求处理器一律只提案**（建议 watch 独立任务/进程）。

### 6.2 前端栈

```text
React + Vite + TypeScript
antd v5                 核心组件（CSS-in-JS，Vite 自动 tree-shaking）
@ant-design/x           AI 对话组件（Bubble/Sender/Conversations/ThoughtChain）
react-markdown (+ 高亮)  渲染协议文件正文（AntD 不带 markdown/代码查看器）
```

FastAPI `StaticFiles` 托管 `dist/`；开发期 Vite 代理 `/api`→FastAPI；前端独立 `frontend/`。

### 6.3 组件 ↔ 面板/协议映射

| 面板 / 数据 | AntD 组件 |
| --- | --- |
| Actions（pending/completed/cancelled） | `Table` / `Timeline` / `Tag` |
| World & robots | `Descriptions` / `Card` / `Badge` |
| Chat 对话 | `@ant-design/x` `Bubble.List` + `Sender` + `Conversations`，流式渲染 |
| Agent 计划/工具步骤 | `@ant-design/x` `ThoughtChain` |
| Hardware integration 表单 | `Form` / `Select` |
| Feedback | `notification` / `Alert` |
| 协议文件正文 | `Layout`(Sider+Content) + `Tree`/`Menu` + `react-markdown` |
| 文件上传（§4.4 摄入入口） | `Upload`（拖拽）→ `POST /api/upload` |
| Raw / debug 原始状态 | JSON 树查看器（`react-json-view`） |

### 6.4 JSON 渲染、顺序、i18n

- 状态是 JSON，dashboard"渲染"=字段映射到上表 AntD 组件，**不需要特殊库**。
- **不采用** Vercel `json-render`（生成式 UI、用途错位、基于 shadcn 会与 AntD 撞设计系统）。
- **GUI 正式改造排在 §2 JSON 契约稳定之后**；现 GUI 的 `涓枃` mojibake 可先止血当临时观测工具。
- `ConfigProvider` locale + 自有 zh/en，修 mojibake 与 `tests/test_gui_server.py` 中 `涓枃` 断言。

---

## 7. 阶段 D：传输层抽象 + 串口 + 硬件级安全

### 7.1 现有硬件接入现状盘点（代码实测）

设计 Phase D 前，先记录代码里实际存在的硬件接入，作为基线：

| driver | robot kind | 来源 | 连接方式 | 能力 |
| --- | --- | --- | --- | --- |
| `mock_arm` / `mock_rover` | arm / rover | 内置 | 进程内仿真，无硬件 | pick/place/move_to / move_to |
| `xiaozhi_mcp` | mcp_device | **内置（唯一内置真硬件）** | **网络协议**：driver 作为客户端调"**设备自己的 MCP server**"，走 WebSocket/HTTP JSON-RPC（`tools/list`、`tools/call`） | observe / set_volume / otto_action / home / stop |
| `momoagent_driver`（moce_arm） | arm | **example（唯一真串口）** | **串口**：通过**厂商 SDK** `soarmmoce_sdk` 的 `make_bus(port, motors)` 驱动**串口舵机**（非自写串口） | 全臂 / 单关节+夹爪，modes mock/full/partial |

**两种连接哲学并存**：

- **设备暴露高层工具**（driver 当 MCP/JSON-RPC 客户端）——xiaozhi，内置一等公民。
- **设备是串口哑舵机**（厂商 SDK 封装协议）——moce，仅 example。

**两个不同的"MCP"务必区分**（避免混淆）：

- `physical_agent/mcp/server.py` = `PhysicalAgentMCP`：**认知侧**、提案专用（`propose_action`/`tool_specs`）、**不碰硬件**，且只是 "MCP-shaped facade"，还不是真 MCP server。
- `xiaozhi_mcp.py` 里的 MCP：**设备侧协议**，driver 是客户端。把 `Action` 翻成真指令永远在 **driver（watch 侧）**，不在 `mcp/server.py`。

**现状缺口（Phase D 要补）**：核心**无共享传输层**；真串口只在 example 且**绑死厂商 SDK**；**无通用的串口/舵机总线/CAN/GPIO** 接入路径——每接一种串口设备都要各背一套 bespoke SDK。

### 7.2 目标与定位

补齐真实硬件最常见的连法（串口/舵机总线），并加硬件级 fail-safe。**只动 `drivers/` 与 `watch/`，与 A/B/C 解耦**：driver contract 收发 `Action`/`Observation` schema 对象，和存储格式（B）、agent（A）、GUI（C）无关。默认排最后，**可随真硬件随时前移**。

### 7.3 Transport / Driver 分离 + 舵机总线层

针对盘点出的两种哲学，分三层（不是两层）：

```text
Driver         = Action -> 设备语义动作的映射
ServoBus（可选） = 舵机协议：motor id、寄存器读写(Goal_Position)、包帧+校验（Feetech/Dynamixel 风格）
Transport      = 字节传输 + 连接管理（机制）
```

`physical_agent/drivers/transport/base.py`：

```python
class Transport(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def write(self, data: bytes) -> None: ...
    async def read(self, *, timeout_s: float) -> bytes: ...
    async def health(self) -> HealthStatus: ...
```

- **Transport 实现**：`SerialTransport`(pyserial)、`TcpTransport`、`WebSocketTransport`、（未来）`BleTransport`/`CanTransport`。统一处理**重连退避、帧切分（换行/定长/COBS）、超时、写 flush、线程/async 安全**。把 `xiaozhi_mcp.py` 重构为复用 `WebSocketTransport`，验证抽象成立。
- **ServoBus 薄层（参照 moce 的 `make_bus`/motors 模型）**：声明 motor 列表与 id，提供 `read/write register`、`sync write`、checksum/packet framing。这样新接一个 **Feetech/Dynamixel 风格的舵机臂**，**不必像 moce 那样背一整个厂商 SDK，也不必各写各的包协议**。
- **复杂/专有臂仍可走"driver 直接调厂商 SDK"**（moce 模式保留为合法选项）；ServoBus 只是覆盖最常见的标准舵机总线，不强制。

### 7.4 串口 / 舵机 driver 骨架

`physical_driver.yaml` 声明传输（两种典型）：

```yaml
# 通用串口（换行分帧的简单设备）
transport: { kind: serial, port: /dev/ttyUSB0, baudrate: 115200, framing: newline }

# 舵机总线臂
transport: { kind: serial, port: /dev/ttyUSB0, baudrate: 1000000, framing: servo_packet }
servo_bus:
  protocol: feetech            # feetech | dynamixel
  motors: [{ name: wrist_roll, id: 5 }, { name: gripper, id: 6 }]
```

`driver.py` 只负责：把 `Action` 编码成寄存器写入/设备帧 → 经 ServoBus/Transport 发送 → 解析回 `Observation`。连接/重连/缓冲交给 transport。

### 7.5 硬件级安全（physical 专属，§0 第 4 条）

- **driver contract 预留两个可选方法，默认 no-op**（现有 mock + 85 测试不受影响）：

```python
async def heartbeat(self) -> None: ...   # 默认 no-op
async def halt(self) -> None: ...        # 默认 no-op；E-stop
```

- **看门狗 / deadman**：watch 常驻循环周期性调 `driver.heartbeat()`；固件/舵机侧约定"心跳超时即停机"——**watch 崩了/串口断了，硬件自动停**。
- **E-stop 通路 + 指令限速**：GUI/CLI 触发 `halt()` 立即下发停止；对舵机臂 `halt()` 可实现为**失能力矩/抱闸释放或保持当前位**（moce 配置已有 `release_torque_on_disconnect` 先例可参照）。watch 对高频指令限速。与软件侧 `SafetyGate`（执行前校验）互补。
- **位置**：心跳挂进 Phase C 的常驻 async watch loop——这正是 D 排在 C 之后更顺的原因。

### 7.6 可测试性

`LoopbackTransport` / 录制回放 transport（含舵机总线帧回放）：串口/舵机 driver **不接真设备也能跑测试**；mock driver 继续保留。

### 7.7 安全边界

不变量不变：传输层与 ServoBus 都只在 watch 侧；driver 仍不解析协议状态、不调 agent。新增的 `heartbeat/halt` 是 **watch → 硬件**方向的安全增强，**不向 agent 暴露任何执行能力**。

---

## 8. 依赖与配置汇总

```toml
[project.optional-dependencies]
dev    = ["pytest>=8.0", "pytest-asyncio>=0.23"]
llm    = ["openai>=1.40"]                       # A
server = ["fastapi>=0.110", "uvicorn>=0.29"]    # C
memory = ["sqlite-vec>=0.1"]                    # B4，核心仍标准库 sqlite3
serial = ["pyserial>=3.5"]                      # D，串口传输
# 前端在独立 frontend/，npm 管理：react / vite / antd / @ant-design/x / react-markdown
```

`physical-agent.yaml` 新增（均有默认值）：`workspace.{backend,format,audit_export}`、`agent.planner=auto`、`agent.context.*`（§5）、`memory.embedding.*`（§4，默认关闭）、robot 级 `transport.*`（§7）。

---

## 9. 测试与验收策略

1. **后端矩阵**：依赖 `Workspace` 的用例参数化跑 `markdown`/`sqlite` 两遍；衍生 `test_e2e_sqlite_loop`。
2. **安全边界静态检查**：扫描 `agent/`、`llm/`、FastAPI 请求模块，断言 import 图无 `physical_agent.drivers.*` 与 `driver.execute`。
3. **SafetyGate 拒绝路径**：现有全部拒绝用例在所有阶段后保持绿。
4. **工具循环**：mock SDK 返回 tool_call，断言只调白名单提案工具、只产 pending action、不触发任何 driver 调用。
5. **记忆**：固定 fixture 下结构化 + 向量召回确定性；检索结果不进执行路径。
6. **上下文压缩**：超阈值触发、最近 K 条保留；**断言安全关键事实读自 state 而非摘要**。
7. **传输/硬件安全（D）**：用 `LoopbackTransport` 测串口 driver 编解码与重连；测**心跳超时→halt** 路径；`heartbeat/halt` 默认 no-op 不影响现有 mock 与 85 测试。
8. **GUI**：FastAPI 端点与旧 server 对等；最小 e2e——加载 dashboard、渲染 Bubble、读取 workspace 文件。
9. **验收测试先写后冻结**：每阶段验收测试实现前写好、人审、冻结，防 reward hacking（尤其 §2 迁移）。
10. 每阶段跑全量 `pytest -q`（基线 85 passed）。

---

## 10. 里程碑（建议落地顺序）

```text
A1  openai SDK 替换 urllib（行为不变）                  低风险，可独立合并
A2  tool_loop 工具循环 + import 静态检查                 agent 侧内聚
A3  最简上下文压缩（rolling summary）                   轻量，随 A
B1  StateStore 抽象，Workspace 改造为接口实现            纯重构
B2  SqliteStateStore（JSON 为准）+ 矩阵测试 + 迁移命令    切真源，删 md 解析层
B3  export_human_view 人类视图 + audit_export            补回可读审计
B4  sqlite-vec 记忆分层 + 检索（先结构化，后 embedding）  建在 B 之上
B4b 文件上传摄入入口（小→inline / 大→ingest，§4.4）       Upload + /api/upload，不可信输入
C1  FastAPI 端点与旧 server 对等                         后端迁移
C2  常驻 watch + WS/SSE 增量推送 + 并发测试               服务化
C3  React + AntD + @ant-design/x 仪表盘（等 B 契约稳定）  GUI 正式改造
C4  前端 i18n / mojibake 修复                            体验收尾
D0  driver contract 预留 heartbeat/halt no-op           零成本保险，可现在就做
D1  Transport 抽象 + 重构 xiaozhi 复用 WebSocketTransport drivers/ 内聚
D2  SerialTransport(pyserial) + 串口 driver 骨架 + Loopback 测试
D2b ServoBus 薄层（Feetech/Dynamixel）+ 舵机臂 driver（参照 moce）   可选，覆盖标准舵机总线
D3  看门狗/心跳 + E-stop（挂进 C 的常驻循环）            硬件级 fail-safe
```

依赖：A/B/C 内部如前；**D 与 A/B/C 解耦**，默认最后；`D3` 最好在 `C2`（常驻循环）之后；`D0` 零成本可立即做，避免将来破坏性改 contract；**真硬件提前到达时 D 可整体前移**。

---

## 11. 待确认的开放问题

1. **工具循环走 Responses 还是 Chat Completions tool_calls？** 若第三方网关对 Responses 不稳，默认 Chat tool_calls。
2. **Embedding 来源**：本地 vs API；维度决定 `vec0` 表；是否首版就开（建议默认关闭）。
3. **上下文压缩阈值**：消息条数还是 token；`simple` vs `llm` 摘要。
4. **是否引入 Dify 作为外部认知层**：把 `mcp/server.py` 升为 HTTP-based MCP server，只暴露提案档工具；Dify 负责对话 + RAG + workflow，watch + SafetyGate + driver 仍是唯一执行层。可选，需评估外部依赖成本。
5. **常驻 watch 与 FastAPI 是否同进程**：推荐独立进程（隔离执行与请求）。
6. **审计人类视图是否纳入 git**：纳入则约定导出频率与目录。
7. **串口帧协议与固件契约**：framing 方式（换行/定长/COBS）、心跳超时阈值、E-stop 是软件指令还是独立硬件线（高安全场景建议独立硬件 E-stop）。
8. **ServoBus 覆盖范围**：先支持哪种舵机协议（Feetech 还是 Dynamixel）；标准舵机臂走自研 ServoBus 薄层，还是沿用 moce 那样直接调厂商 SDK——两条路如何在配置里共存。
9. **上传摄入细节**：inline 与 ingest 的大小阈值；支持的文件类型与抽文本方式（尤其 PDF）；上传文档是"本轮对话"临时还是"项目长期知识"。

---

*本 spec 是设计蓝本，不含实现代码。确认方向后可按 §10 里程碑逐项落地。保持精简、可验证、按需演进——避免 spec 膨胀成"表演"。*
