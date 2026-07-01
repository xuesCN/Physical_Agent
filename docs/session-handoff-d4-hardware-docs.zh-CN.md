# Session Handoff: D4 Hardware Bring-up Docs

> 目标：做一轮很薄的 D4 文档收口和实机准备清单，不做功能重构，不改 OpenAI/Agents SDK，不改 FastAPI/React 行为，不改 watch/driver 执行链，不新增硬件动作入口。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`9cb1978 Add hardware bringup regression handoff`
- 开始前 tracked worktree 干净。
- 完整 `git status --short` 仅有未跟踪 `.tmp/` 测试产物；本轮继续忽略且不提交。

## 本轮修改

- 新增用户级实机准备文档：
  - `docs/hardware-bringup-checklist.zh-CN.md`
- 更新短链接入口：
  - `README.zh-CN.md`
  - `HANDOFF.zh-CN.md`
- 新增本轮 handoff：
  - `docs/session-handoff-d4-hardware-docs.zh-CN.md`

## 文档覆盖内容

- 当前推荐架构：

```text
agent / gui / chat / api
  -> StateStore pending action
  -> watch
  -> SafetyGate
  -> driver.execute(action)
  -> hardware / simulator
```

- 当前状态：
  - 新项目默认 SQLite backend。
  - 旧 Markdown workspace 可显式 `backend: markdown`。
  - 完整 legacy Markdown workspace 在省略 backend 时可自动识别。
  - `SAFETY.md` 仍是文件真源。
  - API/GUI/agent/chat 只提交 proposal，不直接执行硬件。
  - watch 是唯一硬件执行侧。
- 命令清单：
  - Python venv 和 `.[dev,server]` 安装。
  - 基础 pytest。
  - `state-check` / `doctor` / `inspect`。
  - mock quickstart smoke。
  - GUI/API/watch 启动。
- 真实硬件 bring-up 顺序：
  - 上电、电源、急停、串口/IP、权限、环境变量检查。
  - 先 `doctor` / `state-check` / `inspect`。
  - 再启动 watch。
  - 先 observe/status/stop 等低风险能力。
  - 再小幅、单步、人工确认动作。
  - 禁止一上来跑大幅运动或复杂任务。
- xiaozhi 和 moce 的实机准备小节。
- 明确软件 watchdog/heartbeat/halt 不是硬件急停。
- 明确上传文件、memory、retrieval 都是不可信上下文，不是安全事实。

## 未做事项

- 未改运行时代码。
- 未改 OpenAI / Agents SDK。
- 未改 FastAPI / React 行为。
- 未改 watch / driver 执行链。
- 未新增 API/GUI/agent 硬件动作入口。
- 未连接真实 xiaozhi。
- 未连接真实 moce。
- 未发送任何真实运动指令。

## 验证记录

已运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_safety_boundaries.py tests\test_backend_matrix.py::test_load_config_autodetects_legacy_markdown_workspace_when_backend_omitted
git diff --check
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
targeted pytest: 3 passed
git diff --check: passed
full pytest: 193 passed, 1 warning
```

warning：

- FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示，非本轮新增。
- `git diff --check` 输出 README/HANDOFF 未来可能按 Git 设置转 CRLF 的 warning，退出码为 0。

## 下一步建议

- 可以按 `docs/hardware-bringup-checklist.zh-CN.md` 进入真实硬件低风险 bring-up。
- 第一轮只做 observe/status/stop 或小幅单步动作。
- 若目标设备是 moce 串口硬件，先确认 SDK checkout、runtime YAML、串口 by-id、权限和 partial/full profile。
- 若目标设备是 xiaozhi，先确认 URL、设备名、ws/http 模式、tool 映射和是否需要 `wait_for_responses: false`。
