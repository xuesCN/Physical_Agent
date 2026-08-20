# CI 说明

CI（Continuous Integration，持续集成）是在每次 push 或 pull request 时，让 GitHub 自动在干净机器上跑一组检查。它的目标不是限制重构，而是在代码合入前提醒维护者：安全底线、构建产物或主要交互流程可能被改坏了。

本仓库的 CI 配置在 `.github/workflows/ci.yml`。

## 当前策略：删除期主路径全部阻塞

Physical Agent 连接真实物理执行链路，CI 必须守住安全宪法；同时项目仍在快速重构，CI 不能把每一次内部拆分都卡成重活。因此当前采用以下分层策略：

| 层级 | 默认阻塞 | 作用 |
| --- | --- | --- |
| 必跑检查 | 是 | 守住安全边界、前端构建与 TUI 跨客户端契约 |
| PR 完整后端 | 是（仅 PR） | 用 Python 3.12 跑完整 pytest，防止跨层回归 |
| 浏览器主路径 | 是（PR/手动） | 跑真实 Chromium e2e，防止删除/迁移静默丢失用户能力 |
| 手动 full run | 手动触发 | 收口、发版或大重构后再跑 Python 3.11/3.12 完整矩阵 |

## 自动检查

push 和 pull request 默认会跑：

1. `Python safety smoke`
   - Python 3.12
   - 安装 `.[dev,server,llm]`
   - 只跑关键安全/执行边界测试：
     - `tests/test_safety_boundaries.py`
     - `tests/test_safety.py`
     - API 请求侧不得实例化 watch 或执行 driver
     - HTTP proposal handlers 不得启动 watch
     - SQLite 默认状态后端 smoke
     - watch 单步执行 smoke

2. `Frontend build + packaged wheel smoke`
   - Node 24
   - `cd frontend && npm ci`
   - `npm run build`，实际包含 `tsc -b && vite build`
   - 检查提交的 `physical_agent/dashboard/dist` 与当前源码一致
   - 构建 wheel，在两个干净 venv 分别验证 base wheel 的 `[server]` 安装提示，
     以及 wheel + server extra 下 `physical-agent gui`、`physical-agent api`、
     `/`、hashed assets 和 `/api/health`

3. `Ink TUI contract`
   - Node 24
   - `cd tui && npm ci`
   - 依次运行 `npm run typecheck`、`npm test`、`npm run build`
   - TUI 是 API-only 客户端；命令 parser、场景验收和请求 payload 属于跨客户端合同，失败会阻塞合入

这三项失败时，一般应该先修。它们分别代表安全底线、主 GUI 可构建性和 TUI/API 合同仍一致。

工作流中的 GitHub 官方 `checkout`、`setup-python`、`setup-node` actions 统一使用 v7，避免旧 action 内部 Node.js 20 runtime 被 hosted runner 强制切到 Node.js 24 的弃用警告；这里的 action runtime 与项目显式选择的 Node 24 测试运行时是两个概念，但两者保持同代可减少环境分叉。

pull request 还会额外运行 `Python 3.12 full pytest (PR)`，执行完整 `python -m pytest -q`。push 继续只跑快速 smoke，避免每次分支保存都重复完整后端测试；Python 3.11 兼容性仍留在手动矩阵中验证。

注意：GitHub Actions 的 workflow `env:` map 会把变量名按大小写不敏感处理。因此不能同时写 `HTTP_PROXY` 和 `http_proxy`、`NO_PROXY` 和 `no_proxy`。CI 里只保留一套大写代理变量；如果需要在测试进程内处理更多宿主环境差异，应放到测试 fixture 或命令步骤里，而不是在同一个 `env:` map 中重复声明。

## 浏览器主路径检查

R0-R8 删除/迁移期间，Playwright 与其他 PR 检查一样阻塞：

1. `Playwright dashboard`
   - PR 和手动运行时触发
   - 启动临时 API 与 Vite dev server
   - 跑 `cd frontend && npm run test:e2e`

失败时先判断是已知环境波动、测试本身过时，还是确实把用户流程改坏了；在修复或得到明确的维护者豁免前不得合并。R8 后若要恢复 advisory，需依据实际 flaky 数据重新决策，不能自动降级。

## 手动 full run

在 GitHub Actions 页面选择 `CI` → `Run workflow`，把 `full` 选为 `true`，会额外跑：

- Python 3.11 / 3.12 矩阵
- `python -m pytest -q`

适合这些场景：

- 大重构收口
- 准备发布或打 tag
- 修改状态层、watch、安全边界、API 合同时
- 自动 smoke 通过，但你想确认没有更远处的回归

## 本地复现

后端 smoke：

```bash
python -m pip install -e ".[dev,server,llm]"
python -m pytest -q \
  tests/test_safety_boundaries.py \
  tests/test_safety.py \
  tests/test_api_server.py::test_api_requests_do_not_instantiate_watch_or_execute_driver \
  tests/test_api_watch_events.py::test_http_proposal_handlers_do_not_start_watch \
  tests/test_backend_matrix.py::test_default_init_setup_and_state_check_use_sqlite_with_safety_file \
  tests/test_state_store.py::test_open_state_store_defaults_to_sqlite \
  tests/test_watch_runtime.py::test_watch_runtime_step_executes_action
```

前端构建与 wheel smoke：

```bash
cd frontend
npm ci
npm run build
cd ..
python -m pip install build
python scripts/smoke_dashboard_wheel.py
```

TUI：

```bash
cd tui
npm ci
npm run typecheck
npm test
npm run build
```

浏览器 e2e：

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

全量后端：

```bash
python -m pytest -q
```

## 写新测试时的边界

优先测试行为和契约，不要锁死内部实现。适合放进 smoke 的测试应满足至少一个条件：

- 它保护 `driver.execute` 的唯一执行权。
- 它保护 SafetyGate 和 `SAFETY.md` 文件真源。
- 它证明请求/API/LLM/GUI 侧只能提案，不能执行。
- 它能快速发现主 GUI 无法构建。

不建议轻易放进默认阻塞 CI：

- 大量 snapshot。
- 依赖精确 DOM 结构的测试。
- 耗时或易受浏览器环境影响的 e2e。
- 只验证私有函数调用顺序的测试。

## 失败时怎么判断

如果阻塞检查失败，默认按真实回归处理，除非能证明测试已经过时。

如果浏览器检查失败，先看失败类型：

- 构建或类型错误：通常要修。
- 浏览器超时、截图、trace 失败：判断是环境波动还是用户流程坏了。
- 测试断言旧实现细节：重构时可以同步改测试，让它继续表达外部行为。

CI 的原则是：内部重构可以自由，但安全边界、状态契约和用户主要路径不能悄悄坏掉。
