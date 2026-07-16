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

当前状态：完成。R2 pushed commit `5764bac` 在 draft PR #1 / CI run `29140290422` 上通过 Python full、Safety、TUI、frontend、packaged-wheel 与真实 Chromium 25/25；可以进入 R3。

- [x] R1.5 thin launcher 已成为默认入口并经过独立提交/验证；删除前 legacy 实现仍可回退但不再被 CLI 使用。
- [x] launcher 与 wheel/API/核心 e2e 的 cutover 证据全绿后才开始删除。
- [x] 更新安全 allowlist，删除 `physical_agent/gui/controller.py` 例外。
- [x] 删除 `physical_agent/gui/__init__.py`、`controller.py`、`server.py`、`static/*`。
- [x] 删除 `tests/test_gui_server.py`；有价值用例已先迁到正式栈。
- [x] 删除 `tests/test_gui_static_contract.py`；正式 React contract/e2e 已覆盖。
- [x] 删除 legacy package-data，并确认 README/guide 只描述正式 Dashboard。
- [x] `rg "GuiController|make_server|physical_agent\.gui|gui/static"` 仅允许历史记录。
- [x] 本地 Python 405 passed、Safety/API/docs 定向 66 passed、frontend build、TUI 59 tests/typecheck/build、clean-wheel smoke 全绿。
- [x] R2 pushed commit `5764bac` 的 draft PR #1 真实 Chromium 25/25。

## R2.1 canonical projection 与门禁 review fix

- [x] React 删除从 raw feedback/Action Board 二次推断 AgentTask status 的逻辑，只呈现服务端 canonical projection。
- [x] TUI 删除同类二次推断逻辑，只呈现服务端 canonical projection。
- [x] React/TUI 增加 forged/incomplete Gate feedback 负例：后端 task=`failed` 时不得显示成 `passed`。
- [x] backend projection 对重新处于 `pending` 的 action 忽略旧 canonical `passed/allow` Gate 事件；invalid/forged evidence 仍 fail closed。
- [x] 不新增 attempt/task persistence；watch claim/validate/record/execute 顺序与唯一执行权保持不变。
- [x] PR Playwright 移除 `continue-on-error`，R0-R8 期间作为阻塞门禁。
- [x] clean-wheel smoke 直接断言 archive 不含 `physical_agent/gui/`。
- [x] 用户指定的 `current-architecture-audit.md/html` 与 `system-summary.zh-CN.md` 保持阶段快照，不在本轮改写。
- [x] frontend build/e2e、TUI test/typecheck/build、Python projection/safety tests、wheel smoke 全绿（PR #1 CI run `29146358558`）。

## R3 Markdown migration / full Workspace 退役

### R3-A 先锁现有 sidecar 行为

- [x] 把 `tests/test_workspace.py` 中 LOG mirror 行为迁到聚焦的 sidecar behavior tests。
- [x] 把 `tests/test_markdown_protocol.py` 中 SAFETY/front-matter 必要行为迁到 sidecar tests；task/action/capabilities/feedback roundtrip 暂不删。
- [x] 锁定 SAFETY 默认值/覆盖值/front matter/revision/malformed 行为。
- [x] 锁定 LOG 初始化/actor/timestamp/revision/进程内并发 append/SQLite 双写行为。
- [x] 锁定普通 init 不覆盖人工 SAFETY/现有 LOG；overwrite/reset 恢复默认 SAFETY 并清 LOG。
- [x] 定义并锁定 LOG mirror 写失败或 malformed 时的契约：SQLite log 真源不得回滚/丢失，doctor 必须给出可诊断失败。
- [x] 锁定 doctor 的逻辑文档检查和 LOG front-matter 校验。
- [x] 锁定 audit export：复制 SAFETY；LOG JSON 只来自 SQLite。

### R3-B sidecar 接管生产路径

- [x] 新 `state/sidecars.py` 只负责 safety policy + log mirror。
- [x] `SqliteStateStore` 不再 import/reference/instantiate `protocol.workspace.Workspace`。
- [x] 把 `SqliteStateStore.filenames = Workspace.filenames` 改成 state 层自己的逻辑文档名常量。
- [x] sidecar 只持有 `SAFETY.md`/`LOG.md` 文件名，不缩减 SQLite 的 task/capabilities/world/actions/feedback/chat/plan/memory 逻辑文档集合。
- [x] doctor 继续检查 task/capabilities/world/actions/feedback/chat/plan/memory，并只对 LOG 做 front-matter/revision 文件校验。
- [x] `SqliteStateStore`、doctor、audit export 全部切到新 adapter。
- [x] `rg "from physical_agent.protocol.workspace import Workspace|Workspace\.filenames|_file_workspace" physical_agent/state/sqlite.py physical_agent/doctor.py` 为零。
- [x] 更宽的 `physical_agent/state` grep 曾只命中 migration-only `legacy_markdown.py` 两处；R3-C rescue gate 通过后已随 R3-D 删除，未用间接 import 隐藏依赖。

### R3-C 先固化 legacy 防护与真实救援 smoke

- [x] 保留 `RETIRED_MARKDOWN_BACKEND_GUIDANCE`。
- [x] 保留 `LEGACY_MARKDOWN_WORKSPACE_FILES`。
- [x] 保留 `_looks_like_legacy_markdown_workspace()`。
- [x] 显式 `workspace.backend: markdown` 继续拒绝。
- [x] 省略 backend + 完整旧文件集合继续拒绝，不能静默叠加 `state.db`；不完整文件集合不误判。
- [x] 保留并更新 `test_open_state_store_rejects_explicit_markdown_backend`。
- [x] 保留并更新 `test_load_config_rejects_legacy_markdown_workspace_when_backend_omitted`。
- [x] 错误文案指向独立 worktree checkout `9072b4e`（完整 commit `9072b4e9fb600e505668aeb6076eb6cb85e5ff82`）。
- [x] `scripts/smoke_legacy_workspace_rescue.py` 在临时目录/独立 worktree checkout 完整历史 commit，以独立 venv interpreter 调用旧 package/CLI migrator；不使用当前 executable 充当旧 migrator。
- [x] smoke 显式记录 old/current 两个解释器的 `physical_agent.__file__`，并断言分别来自旧 worktree/current checkout。
- [x] rescue smoke 确认历史命令不会自动改 config；手动改为 sqlite 后回当前版本，运行不带 `--force` 的 `physical-agent init`，随后运行 `physical-agent state-check`。
- [x] rescue smoke 逐项验证迁移后的 task/capabilities/world/actions/feedback/SAFETY/chat/plan/memory/uploads/log 可读，并确认 current init 前后 SAFETY/LOG 内容不被意外覆盖。
- [x] 已有 `state.db` 时历史命令无 `--overwrite` 会拒绝；错误指引明示先备份且不要轻率覆盖。

### R3-D 删除一次性迁移入口

- [x] `physical_agent/cli.py`: migrator import 与 `migrate-md-to-sqlite` command。
- [x] `physical_agent/state/legacy_markdown.py`: `LegacyMarkdownWorkspaceReader` 全文件。
- [x] `physical_agent/state/sqlite.py`: `migrate_markdown_workspace_to_sqlite()` 与迁移专用 imports。
- [x] `physical_agent/state/sqlite.py`: 删除只由 migrator 调用的 `_replace_actions_with_revision`、`_replace_chat_with_revision`、`_replace_memory_with_revision`、`_replace_uploads_with_revision`、`_replace_log_entries`、`_payload_revision`、`_metadata_revision`。
- [x] `physical_agent/state/audit.py`: `read_markdown_log_document/entries()` 与专属 imports。
- [x] `physical_agent/config.py`: `allow_retired_markdown=True` 开关。
- [x] 删除 `tests/test_state_store.py::test_legacy_markdown_reader_is_migration_only_not_state_store`。
- [x] 删除 `tests/test_state_store.py::test_migrate_markdown_to_sqlite_cli_does_not_switch_backend`。
- [x] 删除 `tests/test_state_store.py::test_migrated_sqlite_export_contains_action_board_chat_memory_and_log`。
- [x] 删除 `tests/test_backend_matrix.py::test_markdown_to_sqlite_migration_preserves_readiness_state_and_audit`。
- [x] 删除 `tests/test_backend_matrix.py::test_markdown_to_sqlite_migration_reads_legacy_workspace_when_backend_omitted`。
- [x] CLI help 不再出现 migrate；显式/隐式 legacy backend 负用例仍通过。
- [x] 删除后重新执行真实 `9072b4e` 独立 worktree 救援 smoke，十一类数据面与 current 非 force init/state-check 全部通过。
- [x] production/tests 中 migrator/reader/bypass/迁移专用 helper 符号为零；清除沙盒代理影响后全量 Python `415 passed, 1 warning`。

### R3-E 退役 full Workspace helper/protocol

- [x] `tests/test_driver_loader.py`、`tests/test_hardware_onboarding.py`、`tests/test_xiaozhi_mcp_driver.py` 先改成只创建实际所需目录的专用 path fixture。
- [x] `tests/test_chat_protocol.py::test_chat_summary_trim_respects_tiny_budget` 保留；只删 full Workspace roundtrip。
- [x] `WorkspaceDocument` 仍作为最小 front-matter 返回类型保留，没有因名称相似误删。
- [x] `physical_agent/protocol/markdown.py` 已缩到 sidecar 所需 front matter/YAML fence/safety/log 最小函数。
- [x] 删除 `physical_agent/protocol/workspace.py` full Workspace helper。
- [x] 删除 task/action/chat/capabilities/world/feedback/plan/memory 的退役 Markdown parser/renderer。
- [x] 删除 `physical_agent/protocol/__init__.py` 的 `Workspace` public export。
- [x] 永久保留 `export-audit` 命令与 SQLite audit export。
- [x] R3-A 行为迁移已完成后，删除 `tests/test_workspace.py` 与 `tests/test_markdown_protocol.py` 中退役 full-document roundtrip tests；最小 front-matter contract 保留。
- [x] legacy detection 测试改为显式构造旧文件集合，不用退役 helper 伪装 runtime 初始化。
- [x] production/tests 的 full Workspace/parser/renderer imports 与调用为零；定向 39 tests、全量 Python `404 passed, 1 warning`。
- [x] 删除后再次运行真实 `9072b4e` rescue smoke，十一类数据面、SAFETY/LOG 与 current init/state-check 全绿。

### R3-F 文档与最终验证

- [x] 清 `README.md`、`README.zh-CN.md`、`docs/state-backends.zh-CN.md`、`docs/hardware-bringup-checklist.zh-CN.md`；当前版本只描述 SQLite + SAFETY/LOG sidecar，旧 workspace 只保留 `9072b4e9fb600e505668aeb6076eb6cb85e5ff82` 独立 worktree 救援入口。
- [-] `docs/current-architecture-audit.md/html` 与 `docs/system-summary.zh-CN.md` 是用户保留的阶段快照，不纳入 R3 current-doc 收口，也不据此阻塞 R3。
- [x] 清 `docs/current-architecture-overview.svg`、xiaozhi/moce hardware examples；不再把退役 Markdown 文件或 legacy GUI 操作写成当前入口。
- [x] 同步 `docs/SPEC.zh-CN.md`、`docs/PLAYBOOK.zh-CN.md`、`docs/REFACTORING.zh-CN.md`；B6 历史事实保留，只追加提前退役。
- [x] production/tests 中 `rg "LegacyMarkdownWorkspaceReader|migrate_markdown_workspace_to_sqlite|physical_agent\.protocol\.workspace"` 为零；历史/救援文档仅保留逐条审阅后的白名单引用。
- [x] 修复增量 wheel 的陈旧 `build/lib/physical_agent` 泄漏，并在 wheel smoke/unit test 断言不包含 legacy GUI、migrator 与 full Workspace 模块。
- [x] sidecar、legacy negative、真实 rescue smoke、全量 Python `404 passed, 1 warning`、Safety smoke、frontend build、TUI 59 tests/typecheck/build 与 clean-wheel smoke 全绿；本地 Playwright 因无 Chromium 未执行，以本轮 PR CI 为最终门禁。
- [x] R3-F 实现提交 `9698b3e`；R3 全部完成，下一阶段 R4 退役 `auto_step`，不启动冻结功能。

## R4 `auto_step` 退役

- [x] 删除 legacy GUI auto-step surface（已随 R2 完成；CLI/API/ChatRuntime 兼容形状仍按本节后续任务退役）。
- [x] 删除 `physical-agent chat --auto-step` option。
- [x] 删除 `physical_agent/cli.py::_run_chat_auto_step()` 与调用/输出。
- [x] 删除 `ChatRuntime.respond(... auto_step=...)`。
- [x] 删除 `ChatRuntime.respond_stream(... auto_step=...)`。
- [x] 删除 `ChatRequest.auto_step`。
- [x] 删除 API 的显式 `auto_step=False` 兼容传参。
- [x] 更新 README/README.zh-CN/CI/current architecture 口径。
- [x] 将兼容测试改为 CLI chat 与 HTTP proposal/request handlers 不实例化 WatchRuntime、不调用 driver 的直接边界测试。
- [x] 保留正式 `watch` command 和 `api --watch`；CLI help 与 watch runtime smoke 证明所需 import 未误删。
- [x] production/tests/frontend/TUI/README/CI 的 `rg "auto_step|auto-step|_run_chat_auto_step"` 为零；只在规格顺序与历史 REFACTORING 保留经审阅记录。
- [x] 定向 68 tests、最终树全量 Python `403 passed, 1 warning`、Safety 32 tests、frontend build、TUI 59 tests/typecheck/build 与 clean-wheel smoke 全绿。
- [x] R4 实现提交 `da14064` 的远端 CI run `29234488489` 五个实际门禁全绿，包含真实 Chromium Playwright；下一阶段进入 R5，不提前删除 fence。

## R5 structured Chat Turn + 双轨

### Producer/API

- [x] R5 开工先做受限 spike；单调用 structured stream 同时保留 authoritative action set、真实 provider reply delta 和中途 abort，没有用完整 reply 的本地分块冒充 LLM streaming。
- [x] 定义 typed/discriminated Chat result：普通 reply、draft proposal 与 tool-loop submitted proposal 分 variant；CLI code/integration 路径保持独立。
- [x] raw model actions 只分配一次稳定 draft IDs，再直接编译 draft `AgentOutput`；不从 fence 反向解析。
- [x] 同一个 result 写 ChatPlan 与 assistant metadata；done/plan/metadata/fence 的 action IDs/dependencies 完全一致。
- [x] `respond_stream()` 的 done item 携带同一个 `agent_output`/plan。
- [x] `ApiController.chat_stream()` 转发 `agent_output`/plan/draft compatibility envelope，不再只保留 reply/mode/state。
- [x] `/api/chat` 与 SSE done 的结构化字段语义一致。
- [x] draft lifecycle 不写 pending Action Board。
- [x] 浏览器/abort endpoint 中止客户端 transport；ChatRuntime 与 provider iterator 均显式 close。
- [x] compile/persist/done 前再次检查 cancellation；abort/error/partial stream 不产生可提交 structured draft 或 assistant draft metadata。
- [x] 增加“structured producer 仍在进行时 abort”的专项测试，验证无 done/draft persistence 与资源释放。
- [x] 每个 draft action 有唯一 mandatory、watch-owned Gate task。

### Review-fix

- [x] terminal persistence exactly-once：收到 `done` 后关闭 iterator 不追加 cancelled assistant，不覆盖 answered plan。
- [x] canonical `AgentOutput.message` 只含 base reply；兼容 `action-draft` fence 只写 wire reply。
- [x] structured stream 首选 JSON mode + 本地 schema 校验；只在零 byte 且 format unsupported 时退回 plain JSON prompt。
- [x] API stream state 注册实际 SDK transport closer；abort endpoint 除置位外会 best-effort close provider transport。
- [x] 新消息写 `chat_contract=structured_v1` 与 `has_structured_draft`；reply-only structured turn 不把模型 fence 变成卡片。
- [x] 历史无版本消息仍可 fence fallback；声明存在 structured draft 但 envelope 丢失/损坏时，R5 双轨 fallback 仍可用。
- [x] review-fix 定向门禁：backend/API/provider `97 passed`；frontend production build 通过。
- [x] review-fix 本地门禁：Python `413 passed`、Safety `32 passed`、TUI typecheck/build + `60 passed`、frontend production build、clean-wheel smoke 全绿；Playwright 26 cases 发现通过。
- [x] review-fix 真实 Chromium 证据完成：2026-07-14 本机 Playwright 1.61.1 / Chrome for Testing 149.0.7827.55（revision 1228）实际启动，最终完整套件 27/27 通过。
- [x] review-fix 独立远端 CI 证据：`d1ca53c3`，fork Push run `29321294713`、PR run `29321297674` 均成功。

### 双轨 consumer

- [x] 兼容 fence 由 structured actions 生成；禁止 fence → canonical output。
- [x] React 增加 type guard，验证 schema/lifecycle/decision 和合法 action 数组。
- [x] type guard 通过后，React 优先 `message.metadata.agent_output.actions` / SSE `payload.agent_output.actions`。
- [x] 历史消息在 structured 缺失/不合法时 fallback；新 structured 消息只有 compiler 声明存在 draft 时才允许兼容 fence fallback。
- [x] structured + fence 只显示一组；冲突时 structured 胜出。
- [x] refresh 后从 assistant metadata 恢复 Draft 卡片。
- [x] Add to Actions 提交 structured action，并补 `source=chat_draft` provenance。
- [x] structured turn 只分配一次稳定 draft IDs；prerequisite-first 后 dependent dependency 保持。
- [x] dependent-first 返回 422 且不产生部分写入；未新增 Add All/batch UI 或新 batch endpoint。
- [x] TUI `AgentOutput` 类型增加 `actions`，draft 以独立 transcript role 明示不属于 Action Board。

### 双轨验收

- [x] backend：done/ChatPlan/assistant metadata/compat fence 四者 actions IDs/dependencies 相等。
- [x] React：structured-only；真实 Chromium 从 assistant metadata 的 canonical `agent_output.actions` 恢复一张 Draft 卡片。
- [x] React：fence-only 历史 fallback；真实 Chromium 渲染卡片并实际点击 Add，Action Board/API 均只出现一条 pending action。
- [x] React：structured + fence 一致；真实 Chromium 只渲染一组卡片。
- [x] React：structured + fence 冲突，structured 胜出；兼容 fence 内容未进入卡片。
- [x] React：Add → pending，未隐式 approve/execute；pending 唯一、`source=chat_draft`，completed/cancelled 均无该 action，Gate 未被预填 `passed`、PhysicalAction 未被预填 `completed`。
- [x] e2e：真实后端 stream → canonical `AgentOutput`/`ChatPlan.agent_output` → structured card → Add → pending board；SSE 有多个 delta，`AgentOutput.message` 不含 fence，ChatPlan draft 不写 Action Board。
- [x] e2e：受控增量验证 partial fence 时 0 卡、完整 fence 时 1 卡、structured done 后仍为 1 卡且 structured 内容替换 fallback；全过程无临时 error card/framework overlay。
- [x] e2e：reply-only 增量消息正常显示；新 `structured_v1` reply-only 正文 fence 只作文本、不生成卡片。
- [x] e2e：Safety/task 状态只信任服务端规范化 `AgentOutput`；伪造 raw feedback=`passed` 不能覆盖服务端 task=`failed`。
- [x] TUI：done/state 不丢 output，不把 draft 当 pending（60 tests）。
- [x] fake provider 延迟测试证明首个 delta 在最终 structured output 前到达；中途 abort 停止后续 transport/持久化。
- [x] 安全扫描：API/chat request path 不实例化 watch/driver（Safety smoke 32 tests）。
- [x] 双轨以独立本地真实 Chromium 轮次运行并记录证据；2026-07-14 最终 `CI=1 npm run test:e2e -- --project=chromium` 为 27/27 passed（2.0m），不是 discovery。
- [x] 本提交的独立远端 CI 证据：`d1ca53c3`，fork Push run `29321294713`、PR run `29321297674` 均成功。

### 2026-07-14 真实 Chromium 验证记录

- `cd frontend && npx playwright --version && npx playwright install chromium`：Playwright `1.61.1`；确认 Chrome for Testing `149.0.7827.55`、Chromium/headless-shell revision `1228` 已安装。
- 基线 `npm run test:e2e -- --project=chromium`：真实 Chromium 26/26 passed（2.4m）；随后只补强双轨浏览器断言，不改生产消费逻辑。
- 定向 `$env:CI='1'; npx playwright test e2e/dashboard.spec.ts --project=chromium --grep 'real streaming|streaming draft increments|chat drafts prefer'`：3/3 passed（28.9s）。
- 最终 `$env:CI='1'; npm run test:e2e -- --project=chromium`：27/27 passed（2.0m）；`CI=1` 禁止复用 5173/8766 的旧服务，Playwright 自动启动 FastAPI 与 Vite。
- `cd frontend && npm run build`：`tsc -b && vite build` 通过；仓库无独立 frontend unit-test script，交互测试由上述 Playwright 套件承担。
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_chat_runtime.py tests/test_api_server.py tests/test_openai_compatible.py tests/test_plan_compiler.py tests/test_output_projection.py tests/test_proposal_service.py tests/test_safety.py tests/test_safety_boundaries.py`：161 passed，1 个既有 StarletteDeprecationWarning。
- Safety smoke：32 passed，1 个同上既有 warning；Python full：414 passed，1 warning；TUI typecheck/build + 60/60 tests；`scripts/smoke_dashboard_wheel.py` clean-wheel smoke 通过。
- R5 收尾时仍保留后端 fence 生产、`_extract_action_drafts_from_reply()`、React `actionDraft.ts`、fixtures/tests 与 proposal 顶层兼容字段；这些已在 R7 删除。

## R6 职责/read-model 去重（含点名死代码）

- [x] 删除 `physical_agent/agent/chat_runtime.py::_append_actions`（删除前确认零调用）。
- [x] 删除其专属 `from physical_agent.agent.llm_planner import _normalize_depends_on`。
- [x] 删除其专属 `_max_action_number()`。
- [x] `rg "_append_actions|_max_action_number" physical_agent/agent/chat_runtime.py` 为零；保留 `application/proposals.py` 的 canonical 编号 helper。
- [x] `tests/test_proposal_service.py` 通过。
- [x] `tests/test_chat_runtime.py` 通过。
- [x] action batch all-or-nothing 与 dependency remap tests 通过。
- [x] React `submitTask/proposeAction` types 改为只暴露 `agent_output`；production build 通过。
- [x] TUI/MCP/CLI `run/chat`/AgentRuntime/tool-loop 正式消费者改读 `agent_output.actions`。
- [x] 保留 `ProposalResult.actions` 等 application 内部 typed command result；内部使用 Pydantic object，没有先序列化再反读。
- [x] 此阶段暂留 API 顶层 proposal compatibility 字段，并由 `agent_output.actions` 单向派生。
- [x] API/MCP current status/task graph 统一经 `application.output_projection.project_chat_plan()`。
- [x] ChatPlan 保留最后一次 `agent_output` snapshot；API/MCP current status 由 application projection 重建。
- [x] 删除无消费者的 `AgentRuntime._renumber_actions`、`PhysicalAgentMCP.run_action` 与 `ProposalService.propose_action` compatibility wrapper；每项删除前均确认零生产调用。
- [x] React/TUI formatter 继续各自保留；API/MCP 同状态投影一致性测试通过。
- [x] 本地门禁：Python `414 passed`、Safety `32 passed`、frontend production build、TUI typecheck/build + `60 passed`、clean-wheel smoke 全绿；Playwright 26 cases 发现通过。
- [x] R6 收尾时未删除 fence、proposal 顶层 `actions/action/draft_actions`、approve/reject mutation `action` 或 `/api/state.actions`；R7 已删除前两类，后两类按边界保留。
- [x] R6 当前树的本地真实 Chromium 证据：2026-07-14 完整 27/27 passed；正式 consumers/read-model 收敛与 R5 双轨同树运行。
- [x] R6 独立远端 CI 证据：`0bb7807`，fork Push run `29312317707`、PR run `29312319687` 均成功。

## R7 wire compatibility 切断

- [x] R5 双轨真实 Chromium 验证证据已完成（2026-07-14 本地独立轮次 27/27）；R5 closure `d1ca53c3`，fork Push run `29321294713`、PR run `29321297674` 均成功。
- [x] R7 独立远端 CI 证据：R7 wire-cut closure `9ba44af`，fork Push run `29399978672`、PR run `29399982326` 均成功。
- [x] R6 官方 consumer migration 已完成。
- [x] 停止后端 prompt/rule path 产生 `action-draft` fence。
- [x] 删除 `_extract_action_drafts_from_reply()` 及 fence formatter/parser。
- [x] 删除 React `actionDraft.ts` 与 fence 专用 tests/fixtures；保留 structured Draft 卡片组件、交互测试和 `.draft-action-card` 样式。
- [x] 旧 chat fence 作为普通可读文本保留，不再承诺历史可点击 draft；upgrade note 已写。
- [x] 删除 `POST /api/tasks/submit` 顶层 `actions`。
- [x] 删除 `POST /api/actions/propose` 顶层 `action`。
- [x] 删除 `POST /api/chat` 顶层 proposal `actions`。
- [x] 删除 ChatRuntime result/assistant metadata 的顶层 `draft_actions`。
- [x] 删除 MCP submit_task、AgentRuntime/tool-loop 等对等公开 action convenience fields；保留 envelope/status/correlation 和内部 `ProposalResult.actions`。
- [x] 保留 approve/reject mutation response 的 `action`。
- [x] 永久保留 `/api/state.actions` 和 SQLite Action Board。
- [x] 更新 README/API 示例与 breaking-change note；复核 OpenAPI/schema/types，它们已是 canonical shape，无需额外改动。
- [x] 更新 frontend Playwright mocks、MCP tool tests 与 TUI fence 负例；复核 TUI scenario mocks/CLI output tests，它们已只消费 structured output，无需改动。
- [x] 全仓旧字段 consumer grep 经逐项审阅，API/official clients/positive-negative tests 全绿。
- [x] 2026-07-15 最终本地门禁：Python `415 passed`、Safety `32 passed`、frontend build、真实 Chromium `27/27`、TUI typecheck/build + `61 passed`、clean-wheel smoke、文档/golden `11 passed`、`git diff --check` 与生产残留扫描全绿；按用户要求未 commit/push。

## R8 收口

- [x] 正式 current architecture 文档只描述当前实现；用户保留的 `current-architecture-audit.md`、`current-architecture-audit.html` 与 `system-summary.zh-CN.md` 不属于 current-doc contract，不修改、不删除、不重新生成，也不据此阻塞 R8。
- [x] `agent-architecture-vnext` 改为 current architecture/历史决策口径，冻结项不再写成默认下一步。
- [x] SPEC、PLAYBOOK、REFACTORING、README 双语、state/backend/hardware/example/CLI help 一致。
- [x] Python 全量 pytest。
- [x] frontend `tsc -b && vite build`。
- [x] Playwright 完整主路径与负用例。
- [x] TUI build/test/scenario matrix。
- [x] wheel build + clean install + `gui`/`api`/assets smoke。
- [x] safety AST/grep 边界扫描。
- [x] R0-R8 每个删除项有对应替代/负用例证据。
- [x] SPEC R0-R8 标记完成；REFACTORING 追加实现、决策和教训。
- [x] commit/push：实现 closure commit `c4da4f9`，fork Push run `29476327424`、PR run `29476329954` 均成功；evidence closure `33b062b`，fork Push run `29477199756`、PR run `29477202468` 均成功；不创建独立 handoff。

### 删除证据矩阵

| 删除内容 | 当前替代路径 | 正向测试 | 负向测试或扫描证据 | 提交或 CI 证据 |
| --- | --- | --- | --- | --- |
| legacy GUI | `physical-agent gui` 薄入口复用 FastAPI app factory 与 packaged React Dashboard | `tests/test_cli_dashboard.py`、`tests/test_dashboard_parity.py`、Dashboard Playwright 主路径 | wheel member 负断言；正式 legacy routes 404；`physical_agent/gui/` 源码为零 | `5764bac`；fork Push run `29140289239`、PR run `29140290422` 均成功 |
| Markdown workspace/migration | SQLite `state.db` 唯一运行态；`StateSidecars` 只管 SAFETY/LOG；旧数据用 `9072b4e` 独立历史 checkout 救援 | `tests/test_sidecar_behavior.py`、`scripts/smoke_legacy_workspace_rescue.py` | `tests/test_backend_matrix.py`/`test_state_store.py` 锁显式与隐式 legacy fail-closed；wheel 不含 migrator/full Workspace | sidecar cutover `a64be59`；`d1713a0`、`6309a1b`、`4a8ec86`、`9698b3e`；R3 closure `a431c3b`，fork Push run `29233815375`、PR run `29233817630` 均成功 |
| auto_step | `physical-agent watch`、`physical-agent api --watch` 或 `physical-agent gui` 的独立 watch 生命周期 | CLI chat/API proposal-only tests 与正式 watch smoke | 生产 `auto_step|auto-step|_run_chat_auto_step` 零命中；R8 再删除固定 `executed=0` 与 CLI 不可达旧文案 | `da14064`；fork Push run `29234483572`、PR run `29234488489` 均成功；R8 `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功 |
| Chat/Watch/Driver 越权路径 | 提案侧只产 intent/`AgentOutput`；watch 在 Gate 后唯一调用 driver | `tests/test_watch_runtime.py`、`tests/test_safety.py` | `tests/test_safety_boundaries.py` AST + request-side monkeypatch；真实 `driver.execute` 只在 `watch/runtime.py` | `da14064`，fork Push run `29234483572`、PR run `29234488489` 均成功；`d1ca53c3`，fork Push run `29321294713`、PR run `29321297674` 均成功；`9ba44af`，fork Push run `29399978672`、PR run `29399982326` 均成功 |
| 重复 projection/read model | `application.output_projection` 唯一合成 current `AgentOutput`；`/api/state.actions` 保留 board truth | `tests/test_output_projection.py`、React/TUI canonical status 负例 | React/TUI 不重算 Gate；R8 删除可陈旧的 `ChatPlan.actions` 第三份投影并锁旧 payload 忽略 | `9adaf6c` 是先前 status fix；`0bb7807` 是 R6 closure head，fork Push run `29312317707`、PR run `29312319687` 均成功；R8 `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功 |
| `_append_actions` | `ProposalService` + `StateStore.append_pending_actions()` 原子 batch | `tests/test_proposal_service.py`、`tests/test_chat_runtime.py`、batch/dependency 回归 | `chat_runtime.py` 中 `_append_actions|_max_action_number` 零命中 | `0bb7807`；fork Push run `29312317707`、PR run `29312319687` 均成功 |
| action-draft fence | compiler-owned `AgentOutput.actions` 经 SSE done/assistant metadata 到 Web/TUI Draft | structured-only Chat/Playwright/TUI tests | producer/parser/React fallback/bundle marker 零命中；历史 fence-only 正文断言 0 卡/0 Add | `9ba44af`；fork Push run `29399978672`、PR run `29399982326` 均成功 |
| proposal convenience fields | proposal/chat/task/MCP 只通过 `agent_output.actions`；approve/reject mutation `action` 与 `/api/state.actions` 按边界保留 | API/MCP/tool-loop/CLI contract tests；R8 typed OpenAPI response contract | proposal 顶层 `actions/action/draft_actions` 负断言；OpenAPI 禁止旧字段 | `9ba44af`；fork Push run `29399978672`、PR run `29399982326` 均成功；R8 `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功 |

## R8.1 阶段 review hardening

实现与定向证据（2026-07-16）：LOG 修复 `6d53db3`；Gate claim-owner correlation `4c9c6a4` 及 late-feedback fencing `c38e3ec`；nested OpenAPI `89f84c8`。Task 1 focused `60 passed`、group `177 passed`、阶段 full `439 passed`；Task 2 combined `127 passed`；Task 3 focused `78 passed + 78 passed`。以上不替代 Task 5 最终树全量验证；独立终审、push 与 exact-head CI 仍待执行。

- [x] LOG mirror 跨进程并发后与 SQLite 条目/revision 一致，并使用原子替换。
- [x] LOG mirror 失败不阻断 timeout halt、expectation check 或已提交 API mutation；doctor 仍能诊断 stale mirror。
- [x] in-progress Gate evidence 必须匹配当前 claim owner；旧 owner pass 不满足 current obligation。
- [x] OpenAPI `ChatPlan.agent_output` 指向 canonical `AgentOutput`，且 `ChatPlan.actions` 继续不存在。
- [ ] spec/plan/evidence matrix/PLAYBOOK/REFACTORING 已纠偏；draft PR 元数据更新仍待执行，历史门禁/rollback 偏离已正式记录。
- [ ] Python full、frontend build/Playwright、TUI、clean-wheel、多进程/安全专项和 docs/golden 全绿。
- [ ] 独立终审无 Critical/Important；commit/push 与 exact-head Push/PR CI 成功。
- [x] 新功能冻结项保持冻结。
- [ ] 本轮 brief 收工删除，不创建 handoff。

R8.1 不解冻 VNext-3/4、W4/W5/W6.2、F0/F5/F6、B4-vec、registry/read-model 或自动 replan；只有出现可复现的真实需求并形成显式 SPEC 决策后，才可重启对应条目。

## 暂停项（本规格期间不实施）

- [ ] VNext-3 persistent obligation/task table（暂停，不是本规格任务）。
- [ ] VNext-4 Run/Turn/Event ledger（暂停）。
- [ ] W4 world freshness/多机器人并行执行（暂停）。
- [ ] W5 driver 模板扩展（暂停；仅现有安全回归可改）。
- [ ] W6.2 hardware fencing token（暂停）。
- [ ] F0 继续实验、F5 硬件生态、F6 Demo/BYO simulator（暂停）。
- [ ] B4-vec、registry/read-model 新能力、自动 replan/Level 3（暂停）。

这些 checkbox 表示明确不执行，不应在 R8 时误勾为“已实现”；R8 后重新评审是否继续挂起。
