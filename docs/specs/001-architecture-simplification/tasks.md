# 001：原子任务与验收账本

状态图例：`[x]` 已完成并有证据；`[ ]` 未完成；`[-]` 经本规格明确有意退役。

原则：勾选“删除”前，必须先勾选同组全部 parity/迁移/双轨门禁。

## R0 第一轮：规格与只读审计

- [x] 对齐 `origin/codex/agent-core-refactor` 的 `46c817e`，把原本地等价提交保存在 `local/agent-core-refactor-ef6e12b`。
- [x] 核验 Claude brief：本轮基线无业务代码增量，远端 commit 为完整恢复后的树。
- [x] 记录用户决定：legacy GUI 全退役；Markdown migration 提前退役；W4/W6.2/F6 等功能扩张暂停。
- [x] 建立 `spec.md`，锁定安全边界、目标架构、范围外与总体验收。
- [x] 建立 `plan.md`，把删除/迁移拆成步骤 1、1.5、2～8 和逐步 Go/No-Go。
- [x] 完成 legacy GUI → React/FastAPI 的端点、用户能力、测试和 wheel parity 审计。
- [x] 完成 migrator/full Workspace → safety/log sidecar 的生产依赖审计。
- [x] 完成 streaming fence、`auto_step`、response duplication、`_append_actions` 审计。
- [x] 在 `SPEC.zh-CN.md` §4 登记 R0-R8，并把功能 backlog 标为 simplification freeze。
- [x] 在 `PLAYBOOK.zh-CN.md` 增加同名条目与本目录链接。
- [x] 在 `REFACTORING.zh-CN.md` 只记录本轮规格/审计完成，不提前宣告删除完成。
- [x] 校验内部路径、关键符号引用、`9072b4e` 历史入口和第一轮文档 diff；`git diff --check` 通过。
- [x] 清理沙盒代理后，在一次性 Python 3.12 venv 全量 `pytest`：393 passed，1 个既有 StarletteDeprecationWarning。
- [x] commit 并 push 第一轮：远端 `e8750ca`（本地等价提交备份 `784b860`）。

第一轮结束条件：本节全部勾选；后续删除项仍保持未勾选。

## R1.5 legacy GUI parity checklist

当前状态：正式栈缺口和 thin-launcher cutover 已实现并经独立 PR 验证。draft PR #1 在 `2d5e909` 上完成真实 Chromium 25/25；Python full、Safety、TUI、frontend build 与 clean-wheel smoke 同轮全绿。R1.5 删除门禁已经通过，R2 已获准执行。

### 端点与用户能力矩阵

| Legacy surface | 用户能力 | 正式栈现状 | 决定 | 删除前证据 |
| --- | --- | --- | --- | --- |
| `GET /`, `/static/*` | 打开本地 GUI | FastAPI `/` 从 package resource 托管 React build | 保留并补齐 | [x] clean wheel `/` + hashed assets；[x] thin `gui` launcher |
| `GET /api/state` | 状态、world、actions、feedback、safety、chat、plan、memory | FastAPI 同名 API 字段更多 | 保留 | [x] API state + Dashboard contracts；[x] 当前提交浏览器全套 |
| `GET /api/doctor` | Python/config/workspace/driver 诊断 | `/api/state-check` 只覆盖 state backend | 有意退役 browser doctor | [x] README/UI 指向 `physical-agent doctor`；[x] doctor 回归 |
| `POST /api/setup` | 首次建 config/workspace、发布能力、连接 watch | 新 `/api/project/initialize` 只初始化，不连接 watch | 补安全初始化；不连接 watch | [x] missing/empty/invalid/并发 API；[x] Playwright case；[x] 浏览器实跑 |
| `POST /api/setup {force:true}` | 覆写 YAML、清 state、重连 watch | `/api/workspace/reset` 清 state、保留 YAML、active lease 拒绝 | 用安全 reset 替代 | [x] UI 文案；[x] 409 lease；[x] `setup --force` 指针 |
| `POST /api/watch/start` | GUI 启动 watch | 正式进程生命周期 + executor projection | 有意退役 UI 控制 | [x] operator 命令；[x] embedded/external/none/waiting health |
| `POST /api/watch/stop` | GUI 停止 watch（旧页面无按钮） | 停止正式 watch/API 进程 | 有意退役 UI 控制 | [x] operator 命令/停止语义 |
| `POST /api/watch/step` | 手动执行一轮 | 无 | 有意退役 | [x] legacy routes 404 负用例；[x] watch 回归 |
| `POST /api/task` | task → pending proposal | `/api/tasks/submit` + ProposalPanel | 已覆盖 | [x] canonical `agent_output.actions` API/UI contracts |
| `POST /api/chat` | chat | `/api/chat` + `/api/chat/stream` | 已覆盖；步骤 5 才新增结构化通道 | [x] fence stream → card → real propose/state Playwright case；[x] 浏览器实跑 |
| chat planner selector | 每条消息选 auto/llm/rules | React 固定 auto | 有意退役 UI selector | [x] Settings 仅配 provider/model；[x] CLI `chat --planner` 文档 |
| chat auto-step | reply 后推进 watch | Dashboard/API 不提供；CLI 兼容残余留到 R4 | Dashboard 侧退役 | [-] 正式 Dashboard 负用例；R4 仍按原顺序单独退役 CLI 形状 |
| browser code skill | chat 改本地代码并展示 `code_result` | FastAPI 显式关闭 | 有意退役 | [x] `chat --show-code-result` 指针；[x] API-safe runtime 测试 |
| `POST /api/integrate` | scaffold/LLM driver 生成、model override | FastAPI + HardwarePanel 已覆盖并增强 | 保留 | [x] FastAPI LLM/model override/生成结果测试 |
| `POST /api/demo` | hard-coded mock pick/place + 两步执行 | 无；CLI smoke-test 替代 | 有意退役 | [x] `setup --smoke-test` 文案和回归；[x] `/api/demo` 404 |
| language toggle | 中英文 | React i18n + AntD locale | 已覆盖 | [x] 既有 i18n Playwright contract；[x] 当前提交浏览器全套 |
| runtime mode | mock/hardware/confirmation/driver mode | config + executor/capability 分层展示 | 补 config mode + health | [x] watch 未运行时 hardware/simulation API + Playwright case |
| world/timeline/system | world、robots、objects、actions/feedback、raw details | React 已产品化，信息架构不同 | 已覆盖/增强 | [x] 既有 Overview/Actions/Events/Safety cases；[x] 当前提交浏览器全套 |
| hardware result | generated files、validation、next steps | React 展示更多且可注册 robot | 已覆盖/增强 | [x] scaffold/register API/e2e contract；[x] LLM generation API |
| refresh | 重读当前状态 | SSE + executor heartbeat + refresh/fallback | 已覆盖/增强 | [x] SSE EOF/fallback/TUI tests；[x] lease heartbeat event test |
| `/api/config`, `/api/config/robots` | 查看有效配置、注册 robot | ConfigPanel/HardwarePanel 正式能力 | 正式栈保留 | [x] read/register/duplicate/invalid API + e2e contracts |
| `/api/upload`, `/api/search-memory` | 上传不可信文本、检索 memory | UploadPanel/MemorySearchPanel 正式能力 | 正式栈保留 | [x] limits/trust/search API + e2e contracts |
| `/api/export-audit`, `/api/state-check` | 审计导出、SQLite 诊断 | Settings/状态面板正式能力 | 正式栈保留 | [x] export/state-check API + UI contracts |
| `/api/settings/llm*` | 保存 provider/model/key、连接测试 | Settings 正式能力 | 正式栈保留 | [x] secret redaction/save/test API + e2e contracts |
| `/api/actions/{id}/approve|reject` | 执行审批/拒绝 | ActionBoard 正式能力 | 正式栈保留 | [x] approval/reject/Gate 不绕过 API/e2e contracts |

### R1.5 原子任务

- [x] 新增 proposal-only 的安全初始化 use case/API；handler 不 import watch/driver，已有 config 原子 fail-safe 保留，重复调用幂等，invalid config fail closed。
- [x] Dashboard 对 config missing/workspace missing 提供初始化按钮、处理中与错误态；成功后并行刷新 state/config。
- [x] 定义 executor status schema：聚合进程内 ApiWatchService phase/error 与 SQLite active `watch-executor` lease/expiry，区分 waiting_for_init/embedded/external/none；硬件/driver health 仍单独表达。
- [x] SSE hello/state/周期 executor event、React StatusBar 与 TUI status 使用新 schema；`watch_enabled` 只作配置兼容。
- [x] Config/Robots 在 watch 未启动时从 YAML 展示 `execution_mode`。
- [x] Reset 文案固定“清 workspace、保留 YAML、恢复默认 SAFETY”；active lease 409 可读。
- [x] README/GUI 提供 `physical-agent setup --force` factory-reset 指针。
- [x] React build 固定到 `physical_agent/dashboard/dist` package resource；build hook 清除增量 wheel 的旧 hash 资产。
- [x] `pyproject.toml` package-data 同时覆盖正式 Dashboard；legacy static 条目仅为 R2 前回退保留，R2 随实现一起删除。
- [x] base wheel 缺 `[server]` 时给出可执行提示；clean venv 的 wheel + server extra 已验证 `gui`、`api`、`/`、hashed assets 与 `/api/health`。
- [x] `physical-agent gui` 已切正式 app factory；默认 embedded、支持 `--no-watch`，不 import/call legacy controller。
- [x] missing config/workspace 时显示 waiting-for-init；初始化后 service 自行接管；external lease 时安静 standby；driver setup 失败 degraded fail-stop。
- [x] thin launcher 覆盖 embedded/`--no-watch`/host/port/no-open/readiness browser opener/missing server extra contracts。
- [x] FastAPI LLM integrate 覆盖 model override 与生成结果。
- [x] hardware/simulation mode 覆盖 config/API 与无 executor 的 Dashboard case。
- [x] 增加 streaming fence draft → card → real Add to Actions → pending state Playwright case。
- [x] 所有有意退役项已有可执行替代命令和 canonical routes 负用例。
- [x] Dashboard planner 固定 auto；Settings 只配置 provider/model；README 使用 `physical-agent chat --planner ...` 调试。
- [x] browser code skill 替代为 `physical-agent chat --show-code-result`，不暗示 Settings 能启用。
- [x] Python 全量、frontend build、TUI typecheck/test、wheel content/clean-venv smoke 已通过。
- [x] Playwright 当前提交可发现 25 个用例。
- [x] draft PR #1 / CI run `29139972352` 在 `2d5e909` 上真实运行 Chromium：25/25。
- [x] parity 表最终全绿，R2 删除门禁通过。

## R2 验证 cutover 后删除 legacy GUI

当前状态：实现删除与本地全量回归完成；等待 R2 pushed commit 在 draft PR #1 上再次运行真实 Chromium，绿后才进入 R3。

- [x] R1.5 thin launcher 已成为默认入口并经过独立提交/验证；删除前 legacy 实现仍可回退但不再被 CLI 使用。
- [x] launcher 与 wheel/API/核心 e2e 的 cutover 证据全绿后才开始删除。
- [x] 更新安全 allowlist，删除 `physical_agent/gui/controller.py` 例外。
- [x] 删除 `physical_agent/gui/__init__.py`、`controller.py`、`server.py`、`static/*`。
- [x] 删除 `tests/test_gui_server.py`；有价值用例已先迁到正式栈。
- [x] 删除 `tests/test_gui_static_contract.py`；正式 React contract/e2e 已覆盖。
- [x] 删除 legacy package-data，并确认 README/guide 只描述正式 Dashboard。
- [x] `rg "GuiController|make_server|physical_agent\.gui|gui/static"` 仅允许历史记录。
- [x] 本地 Python 405 passed、Safety/API/docs 定向 66 passed、frontend build、TUI 59 tests/typecheck/build、clean-wheel smoke 全绿。
- [ ] R2 pushed commit 的 draft PR #1 真实 Chromium 25/25。

## R3 Markdown migration / full Workspace 退役

### R3-A 先锁现有 sidecar 行为

- [ ] 把 `tests/test_workspace.py` 中 LOG mirror 行为迁到聚焦的 sidecar behavior tests。
- [ ] 把 `tests/test_markdown_protocol.py` 中 SAFETY/front-matter 必要行为迁到 sidecar tests；task/action/capabilities/feedback roundtrip 暂不删。
- [ ] 锁定 SAFETY 默认值/覆盖值/front matter/revision/malformed 行为。
- [ ] 锁定 LOG 初始化/actor/timestamp/revision/进程内并发 append/SQLite 双写行为。
- [ ] 锁定 doctor 的逻辑文档检查和 LOG front-matter 校验。
- [ ] 锁定 audit export：复制 SAFETY；LOG JSON 只来自 SQLite。

### R3-B sidecar 接管生产路径

- [ ] 新 `state/sidecars.py`（最终命名可调整）只负责 safety policy + log mirror。
- [ ] `SqliteStateStore` 不再 import/reference/instantiate `protocol.workspace.Workspace`。
- [ ] 把 `SqliteStateStore.filenames = Workspace.filenames` 改成 state 层自己的逻辑文档名常量。
- [ ] sidecar 只持有 `SAFETY.md`/`LOG.md` 文件名，不缩减 SQLite 的 task/capabilities/world/actions/feedback/chat/plan/memory 逻辑文档集合。
- [ ] doctor 继续检查 task/capabilities/world/actions/feedback/chat/plan/memory，并只对 LOG 做 front-matter 文件校验。
- [ ] `SqliteStateStore`、doctor、audit export 全部切到新 adapter。
- [ ] `rg "from physical_agent.protocol.workspace import Workspace|Workspace\.filenames|_file_workspace" physical_agent/state physical_agent/doctor.py` 为零。

### R3-C 先固化 legacy 防护与真实救援 smoke

- [ ] 保留 `RETIRED_MARKDOWN_BACKEND_GUIDANCE`。
- [ ] 保留 `LEGACY_MARKDOWN_WORKSPACE_FILES`。
- [ ] 保留 `_looks_like_legacy_markdown_workspace()`。
- [ ] 显式 `workspace.backend: markdown` 继续拒绝。
- [ ] 省略 backend + 完整旧文件集合继续拒绝，不能静默叠加 `state.db`。
- [ ] 保留并更新 `test_open_state_store_rejects_explicit_markdown_backend`。
- [ ] 保留并更新 `test_load_config_rejects_legacy_markdown_workspace_when_backend_omitted`。
- [ ] 错误文案指向独立 worktree checkout `9072b4e`（完整 commit `9072b4e9fb600e505668aeb6076eb6cb85e5ff82`）。
- [ ] 在临时目录/独立 worktree checkout `9072b4e9fb600e505668aeb6076eb6cb85e5ff82`，安装并调用该 checkout 的旧 Python package，构造完整 legacy workspace 并运行历史 migrator；不得误用当前 executable。
- [ ] rescue smoke 确认历史命令不会自动改 config；手动改为 sqlite 后回当前版本，运行不带 `--force` 的 `physical-agent init`，随后运行 `physical-agent state-check`。
- [ ] rescue smoke 验证迁移后的 task/actions/chat/memory/log 可读。
- [ ] 明示已有 `state.db` 时不要轻率使用历史 `--overwrite`。

### R3-D 删除一次性迁移入口

- [ ] `physical_agent/cli.py`: migrator import 与 `migrate-md-to-sqlite` command。
- [ ] `physical_agent/state/legacy_markdown.py`: `LegacyMarkdownWorkspaceReader` 全文件。
- [ ] `physical_agent/state/sqlite.py`: `migrate_markdown_workspace_to_sqlite()` 与迁移专用 imports。
- [ ] `physical_agent/state/audit.py`: `read_markdown_log_document/entries()` 与专属 imports。
- [ ] `physical_agent/config.py`: `allow_retired_markdown=True` 开关。
- [ ] 删除 `tests/test_state_store.py::test_legacy_markdown_reader_is_migration_only_not_state_store`。
- [ ] 删除 `tests/test_state_store.py::test_migrate_markdown_to_sqlite_cli_does_not_switch_backend`。
- [ ] 删除 `tests/test_state_store.py::test_migrated_sqlite_export_contains_action_board_chat_memory_and_log`。
- [ ] 删除 `tests/test_backend_matrix.py::test_markdown_to_sqlite_migration_preserves_readiness_state_and_audit`。
- [ ] 删除 `tests/test_backend_matrix.py::test_markdown_to_sqlite_migration_reads_legacy_workspace_when_backend_omitted`。
- [ ] CLI help 不再出现 migrate；legacy backend 负用例仍通过。

### R3-E 退役 full Workspace helper/protocol

- [ ] `tests/test_driver_loader.py`、`tests/test_hardware_onboarding.py`、`tests/test_xiaozhi_mcp_driver.py` 先改成 SQLite/专用 path fixture。
- [ ] `tests/test_chat_protocol.py::test_chat_summary_trim_respects_tiny_budget` 保留；只删 full Workspace roundtrip。
- [ ] `WorkspaceDocument` 若仍作为最小 front-matter 返回类型则保留，不因名称相似误删。
- [ ] `physical_agent/protocol/markdown.py` 只缩到 sidecar 所需 front matter/YAML fence/safety/log 最小函数（或内收 sidecar）；不得按文件名机械全删。
- [ ] 删除 `physical_agent/protocol/workspace.py` full Workspace helper。
- [ ] 删除 task/action/chat/capabilities/feedback/memory 的退役 Markdown parser/renderer。
- [ ] 删除 `physical_agent/protocol/__init__.py` 的 `Workspace` public export。
- [ ] 永久保留 `export-audit` 命令与 SQLite audit export。
- [ ] 只有 R3-A 行为已迁移后，才删除旧 `tests/test_workspace.py` 与 `tests/test_markdown_protocol.py` 中退役 full-document roundtrip tests。

### R3-F 文档与最终验证

- [ ] 清 `README.md`、`README.zh-CN.md`、`docs/state-backends.zh-CN.md`、`docs/system-summary.zh-CN.md`、`docs/hardware-bringup-checklist.zh-CN.md`。
- [ ] 清 `docs/current-architecture-audit.md/html`、`docs/current-architecture-overview.svg`、`examples/xiaozhi_mcp_hardware/README.md`；若改 audit Markdown，同步 HTML hash 测试。
- [ ] 同步 `docs/SPEC.zh-CN.md`、`docs/PLAYBOOK.zh-CN.md`、`docs/REFACTORING.zh-CN.md`；B6 历史事实保留，只追加提前退役。
- [ ] `rg "LegacyMarkdownWorkspaceReader|migrate_markdown_workspace_to_sqlite|physical_agent\.protocol\.workspace"` 为零（历史说明逐条审阅）。
- [ ] sidecar、legacy negative、rescue smoke、全量 pytest 与 safety boundary 全绿。

## R4 `auto_step` 退役

- [ ] 删除 legacy GUI auto-step surface（随 R2）。
- [ ] 删除 `physical-agent chat --auto-step` option。
- [ ] 删除 `physical_agent/cli.py::_run_chat_auto_step()` 与调用/输出。
- [ ] 删除 `ChatRuntime.respond(... auto_step=...)`。
- [ ] 删除 `ChatRuntime.respond_stream(... auto_step=...)`。
- [ ] 删除 `ChatRequest.auto_step`。
- [ ] 删除 API 的显式 `auto_step=False` 兼容传参。
- [ ] 更新 README/README.zh-CN/CI/current architecture 口径。
- [ ] 将兼容测试改为“request/proposal handler 不加载 WatchRuntime/driver”的直接边界测试。
- [ ] 保留正式 `watch` command 和 `api --watch`；验证没有误删所需 import。
- [ ] `rg "auto_step|auto-step"` 仅剩历史 REFACTORING。

## R5 structured Chat Turn + 双轨

### Producer/API

- [ ] R5 开工先做受限 spike；正式方案必须同时保留一个 authoritative action set、真实首 token/delta 和中途 abort，不能用完整 reply 的本地分块冒充 streaming；无法同时满足则暂停并请求产品取舍。
- [ ] 定义 typed/discriminated Chat result：普通 reply 的 `agent_output` 可选，proposal 为 draft output，tool-loop 为 submitted variant；R5 只收口 API 使用的 rule/LLM reply/proposal，不删除 CLI code/integration/tool-loop variants。
- [ ] raw model actions 只分配一次稳定 draft IDs，再直接编译 draft `AgentOutput`；不从 fence 反向解析。
- [ ] 同一个 result 写 ChatPlan 与 assistant metadata；done/plan/metadata/fence 的 action IDs/dependencies 完全一致。
- [ ] `respond_stream()` 的 done item 携带同一个 `agent_output`/plan。
- [ ] `ApiController.chat_stream()` 转发 `agent_output`/plan，不再只保留 reply/mode/state。
- [ ] `/api/chat` 与 SSE done 的结构化字段语义一致。
- [ ] draft lifecycle 不写 pending Action Board。
- [ ] 浏览器/abort endpoint 中止客户端 transport；上游 provider iterator/request 按既有可取消能力释放，不能静默降级 Stop 语义。
- [ ] compile/persist/done 前再次检查 cancellation；abort/error/partial stream 不产生可提交 structured draft 或 assistant draft metadata。
- [ ] 增加“structured producer 仍在进行时 abort”的专项测试，验证无 done/draft persistence 与资源释放。
- [ ] 每个 draft action 有唯一 mandatory、watch-owned Gate task。

### 双轨 consumer

- [ ] 兼容 fence 由 structured actions 生成；禁止 fence → canonical output。
- [ ] React 增加 type guard，至少验证 `schema=physical-agent/agent-output/v1`、`lifecycle=draft`、`decision=propose` 和合法 action 数组。
- [ ] type guard 通过后，React 优先 `message.metadata.agent_output.actions` / SSE `payload.agent_output.actions`。
- [ ] structured 缺失时才 fallback `parseActionDrafts()`。
- [ ] structured + fence 只显示一组；冲突时 structured 胜出。
- [ ] refresh 后从 assistant metadata 恢复 Draft 卡片。
- [ ] Add to Actions 提交 structured action，并补 `source=chat_draft` provenance。
- [ ] structured turn 只分配一次稳定 draft IDs；现有逐卡 Add 语义下，prerequisite 先添加、dependent 后添加时 dependency 保持。
- [ ] dependent-first 返回 422 且不产生部分写入；本轮不新增 Add All/batch UI 或新 batch endpoint。
- [ ] TUI `AgentOutput` 类型增加 `actions`，draft 与 board truth 分开展示。

### 双轨验收

- [ ] backend：done/ChatPlan/assistant metadata/compat fence 四者 actions IDs/dependencies 相等。
- [ ] React：structured-only。
- [ ] React：fence-only 历史 fallback。
- [ ] React：structured + fence 一致。
- [ ] React：structured + fence 冲突，structured 胜出。
- [ ] React：Add → pending，未隐式 approve/execute。
- [ ] e2e：stream → structured card → Add → pending board。
- [ ] TUI：done/state 不丢 output，不把 draft 当 pending。
- [ ] fake provider 延迟测试证明首个 delta 在最终 structured output 前到达；中途 abort 停止后续 transport/持久化。
- [ ] 安全扫描：API/chat request path 不实例化 watch/driver。
- [ ] 双轨以独立提交/CI 轮次运行并记录证据；R5 完成后只能进入 R6，R7 还必须等待 R6 consumer migration。

## R6 职责/read-model 去重（含点名死代码）

- [ ] 删除 `physical_agent/agent/chat_runtime.py::_append_actions`（当前确认零调用）。
- [ ] 删除其专属 `from physical_agent.agent.llm_planner import _normalize_depends_on`。
- [ ] 删除其专属 `_max_action_number()`。
- [ ] `rg "_append_actions|_max_action_number" physical_agent/agent/chat_runtime.py` 为零；保留 `application/proposals.py` 的 canonical 编号 helper。
- [ ] `tests/test_proposal_service.py` 通过。
- [ ] `tests/test_chat_runtime.py` 通过。
- [ ] action batch all-or-nothing 与 dependency remap tests 通过。
- [ ] React `submitTask/proposeAction` types/tests 改读 `agent_output.actions`。
- [ ] TUI/MCP/CLI `run/chat`/AgentRuntime/tool-loop 正式消费者改读 `agent_output.actions`。
- [ ] 保留 `ProposalResult.actions` 等 application 内部 typed command result，不强迫内部代码序列化后再反读 AgentOutput。
- [ ] 此阶段暂留 API 顶层 proposal compatibility 字段，只用于旧 consumer 验证。
- [ ] API/MCP current status/task graph 统一经 application projection/query。
- [ ] ChatPlan 可以保留最后一次 `agent_output` snapshot，但不重复 materialize Gate/status；current status 只来自 application projection。
- [ ] 删除无消费者的 projection/compat wrapper；每项删除前有 `rg` 证据。
- [ ] React/TUI formatter 继续各自保留；后端 owner/status 语义一致性测试通过。

## R7 wire compatibility 切断

- [ ] R5 双轨验证证据已完成。
- [ ] R6 官方 consumer migration 已完成。
- [ ] 停止后端 prompt/rule path 产生 `action-draft` fence。
- [ ] 删除 `_extract_action_drafts_from_reply()` 及 fence formatter/parser。
- [ ] 删除 React `actionDraft.ts` 与 fence 专用 tests/fixtures；保留 structured Draft 卡片组件、交互测试和 `.draft-action-card` 样式。
- [ ] 旧 chat fence 作为普通可读文本保留，不再承诺历史可点击 draft；upgrade note 已写。
- [ ] 删除 `POST /api/tasks/submit` 顶层 `actions`。
- [ ] 删除 `POST /api/actions/propose` 顶层 `action`。
- [ ] 删除 `POST /api/chat` 顶层 proposal `actions`。
- [ ] 删除 ChatRuntime result/assistant metadata 的顶层 `draft_actions`。
- [ ] 删除 MCP submit_task、AgentRuntime/tool-loop 等对等公开 action convenience fields；保留 envelope/status/correlation 和内部 `ProposalResult.actions`。
- [ ] 保留 approve/reject mutation response 的 `action`。
- [ ] 永久保留 `/api/state.actions` 和 SQLite Action Board。
- [ ] 更新 README/API 示例、breaking-change note、OpenAPI/schema/types。
- [ ] 更新 frontend Playwright mocked responses、TUI scenario mocks、MCP tool tests、CLI output tests。
- [ ] 全仓旧字段 consumer grep 经逐项审阅，API/official clients/positive-negative tests 全绿。

## R8 收口

- [ ] current architecture 文档只描述当前实现；过期 snapshot/HTML 删除或重新生成。
- [ ] `agent-architecture-vnext` 改为 current architecture/历史决策口径，冻结项不再写成默认下一步。
- [ ] SPEC、PLAYBOOK、REFACTORING、README 双语、state/backend/hardware/example/CLI help 一致。
- [ ] Python 全量 pytest。
- [ ] frontend `tsc -b && vite build`。
- [ ] Playwright 完整主路径与负用例。
- [ ] TUI build/test/scenario matrix。
- [ ] wheel build + clean install + `gui`/`api`/assets smoke。
- [ ] safety AST/grep 边界扫描。
- [ ] R0-R8 每个删除项有对应替代/负用例证据。
- [ ] SPEC R0-R8 标记完成，REFACTORING 追加实现、决策和教训。
- [ ] commit/push；不创建独立 handoff。

## 暂停项（本规格期间不实施）

- [ ] VNext-3 persistent obligation/task table（暂停，不是本规格任务）。
- [ ] VNext-4 Run/Turn/Event ledger（暂停）。
- [ ] W4 world freshness/多机器人并行执行（暂停）。
- [ ] W5 driver 模板扩展（暂停；仅现有安全回归可改）。
- [ ] W6.2 hardware fencing token（暂停）。
- [ ] F0 继续实验、F5 硬件生态、F6 Demo/BYO simulator（暂停）。
- [ ] B4-vec、registry/read-model 新能力、自动 replan/Level 3（暂停）。

这些 checkbox 表示明确不执行，不应在 R8 时误勾为“已实现”；R8 后重新评审是否继续挂起。
