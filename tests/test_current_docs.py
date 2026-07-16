from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _section(document: str, heading: str) -> str:
    start = document.index(heading)
    remainder = document[start + len(heading) :]
    next_heading = remainder.find("\n## ")
    return document[start:] if next_heading < 0 else document[start : start + len(heading) + next_heading]


def _dashboard_entry_bundle() -> str:
    index = _read("physical_agent/dashboard/dist/index.html")
    match = re.search(
        r'<script type="module" crossorigin src="/(?P<asset>assets/index-[^"]+\.js)"></script>',
        index,
    )
    assert match is not None
    return _read(f"physical_agent/dashboard/dist/{match.group('asset')}")


def test_readmes_describe_sqlite_runtime_without_current_migration_compatibility() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")

    assert "Markdown audit / migration compatibility" not in english
    assert "旧 workspace 迁移输入" not in chinese
    assert "完整 Markdown loop" not in chinese
    assert "with a two-process runtime" not in english
    assert "采用双进程架构" not in chinese
    assert "`physical-agent run` 和 `physical-agent chat` 是认知侧入口，负责读取当前 StateStore、理解任务、生成结构化 action intent，并写入 pending action。" not in chinese
    assert "SQLite" in english
    assert "SAFETY.md" in english
    assert "SQLite" in chinese
    assert "SAFETY.md" in chinese
    assert "`physical-agent chat` 只返回结构化 Draft" not in chinese
    assert "`physical-agent chat` 的 rule/LLM 主路径只返回 structured draft" in chinese
    assert "plan.agent_output.actions" in english
    assert "plan.agent_output.actions" in chinese


def test_readmes_keep_driver_coding_validation_static_and_request_side_only() -> None:
    english = _section(_read("README.md"), "## Driver Contract")
    chinese_document = _read("README.zh-CN.md")
    chinese = _section(chinese_document, "## 硬件接入助手")

    english_boundary = " ".join(
        paragraph
        for paragraph in english.split("\n\n")
        if "Request-side validation" in paragraph
    )
    assert english_boundary
    for fragment in (
        "static manifest/Python/interface validation",
        "Request-side validation",
        "never imports",
        "connects",
        "executes",
        "watch-side workflow",
    ):
        assert fragment in english_boundary

    chinese_boundary = " ".join(
        paragraph
        for paragraph in chinese.split("\n\n")
        if "请求侧" in paragraph and "候选 driver" in paragraph
    )
    assert chinese_boundary
    for fragment in ("请求侧", "静态", "manifest", "Python", "候选 driver", "watch 侧"):
        assert fragment in chinese_boundary
    assert "interface" in chinese_boundary or "接口" in chinese_boundary
    assert any(negation in chinese_boundary for negation in ("不会", "不得", "不能", "绝不"))
    assert "加载" in chinese_boundary or "load" in chinese_boundary or "import" in chinese_boundary
    assert "连接" in chinese_boundary or "connect" in chinese_boundary
    assert "执行" in chinese_boundary or "execute" in chinese_boundary
    assert "在 mock 模式下验证候选 driver" not in chinese
    assert "候选 driver 必须通过 Python 编译" not in chinese
    assert "driver.execute(observe)" not in chinese
    assert "LLM driver coding、mock 验证、CLI/chat/GUI 入口" not in chinese_document


def test_english_hardware_panel_keeps_request_side_validation_static_only() -> None:
    english = _read("README.md")
    hardware_panel = " ".join(
        paragraph
        for paragraph in english.split("\n\n")
        if "The Hardware integration panel" in paragraph
    )

    assert hardware_panel
    for fragment in (
        "Request-side",
        "static manifest/Python/interface validation",
        "never imports, connects, or executes",
        "dynamic conformance",
        "watch-side workflow",
    ):
        assert fragment in hardware_panel
    assert "validated in mock mode" not in hardware_panel


def test_dashboard_hardware_locale_is_static_in_source_and_shipped_bundle() -> None:
    english_source = _read("frontend/src/locales/en.ts")
    chinese_source = _read("frontend/src/locales/zh.ts")
    shipped_bundle = _dashboard_entry_bundle()

    for document in (english_source, shipped_bundle):
        for fragment in (
            "static manifest/Python/interface validation",
            "never imports, connects to, or executes the candidate driver",
            "explicit watch-side workflow",
        ):
            assert fragment in document

    for document in (chinese_source, shipped_bundle):
        for fragment in (
            "静态 manifest/Python/interface 校验",
            "请求侧绝不 import、连接或执行候选 driver",
            "显式 watch 侧工作流",
        ):
            assert fragment in document

    for document in (english_source, chinese_source, shipped_bundle):
        assert "validates them in mock mode" not in document
        assert "only runtime that loads drivers and touches hardware" not in document
        assert "在 mock 模式验证" not in document
        assert "只有 watch 运行时会加载 driver 并触碰硬件" not in document


def test_current_docs_split_web_add_from_tui_cli_display_and_tool_loop_submission() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")
    spec_main = _section(_read("docs/SPEC.zh-CN.md"), "## 1. 系统与产品框架")
    playbook_f1 = _section(
        _read("docs/PLAYBOOK.zh-CN.md"),
        "## F1 提案卡片 + Approve + 审批流",
    )
    refactoring_r8 = _section(
        _read("docs/REFACTORING.zh-CN.md"),
        "### R8：当前架构、发布契约与本地门禁收口",
    )
    architecture = _read("docs/agent-architecture-vnext.zh-CN.md")
    architecture_main = _section(architecture, "## 0. 结论：当前唯一架构主链")
    architecture_modules = _section(architecture, "## 5. 软件分层")

    assert "Web/TUI/CLI Draft card" not in english
    for document in (chinese, spec_main, architecture_main):
        assert "Web/TUI/CLI structured consumer" not in document
    assert "Web/TUI/CLI Draft → 用户 Add" not in refactoring_r8

    for fragment in (
        "rule/LLM chat path",
        "React/Web renders actionable Draft cards",
        "TUI/CLI only displays the structured draft",
        "no direct Add control",
        "`tool_loop` is the exception",
        "proposal-only tools can submit pending actions directly",
        "never approve or execute",
        "task/manual/run proposal paths",
    ):
        assert fragment in english

    for document in (chinese, spec_main, playbook_f1, refactoring_r8, architecture_main):
        for fragment in (
            "rule/LLM chat 主路径",
            "React/Web 显示可操作 Draft card",
            "TUI/CLI 只显示 structured draft",
            "不提供从该 draft 直接 Add",
            "`tool_loop`",
            "proposal-only tool",
            "绝不 approve 或 execute",
            "task/manual/run proposal 路径",
        ):
            assert fragment in document

    for fragment in (
        "chat_runtime.py",
        "rule/LLM",
        "structured draft",
        "tool_loop",
        "proposal-only",
        "pending",
    ):
        assert fragment in architecture_modules


def test_readme_openai_chat_sections_keep_drafts_out_of_the_action_board() -> None:
    english = _section(_read("README.md"), "## OpenAI-Compatible API Planner")
    chinese = _section(_read("README.zh-CN.md"), "## OpenAI 兼容 API 和 Chat Agent")

    for forbidden in (
        "the LLM only writes proposed actions to StateStore",
        "It can answer, remember notes, propose physical actions",
        "It writes replies, current intent, and proposed actions back to StateStore",
        "Watch still validates and executes those actions",
        "Execute the proposed actions by running watch in another terminal",
    ):
        assert forbidden not in english

    for fragment in (
        "Direct task/run and MCP proposal paths submit pending actions to the Action Board",
        "ordinary rule/LLM chat path produces a structured draft without creating pending actions",
        "TUI/CLI only displays that draft; React/Web can submit it with Add to Actions",
        "Explicit `--planner tool_loop` may submit pending actions through proposal-only tools",
        "does not submit those drafts by default",
        "Watch only processes actions that have already been submitted to the Action Board",
        "A draft shown by ordinary CLI chat is not in the Action Board and is therefore invisible to watch",
    ):
        assert fragment in english

    for forbidden in (
        "LLM 只写 proposed actions 或 watch 侧 driver 草稿",
        "它可以聊天、记忆、提交物理动作",
    ):
        assert forbidden not in chinese

    for fragment in (
        "task/run 与 MCP proposal 路径会把 pending action 提交到 Action Board",
        "普通 rule/LLM chat 只产生 structured draft，不创建 pending",
        "TUI/CLI 只显示该 draft；React/Web 可由用户 Add to Actions",
        "显式 `--planner tool_loop` 可经 proposal-only tool 提交 pending",
        "普通 chat 默认不会把这些 draft 提交到 Action Board",
        "watch 只处理已经提交到 Action Board 的 action",
        "普通 CLI chat 显示的 draft 不在 Action Board 中，因此 watch 看不到",
    ):
        assert fragment in chinese


def test_readmes_distinguish_request_paths_watch_ownership_and_inert_doctor() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")

    for fragment in (
        "Request/proposal paths never load drivers.",
        "Watch is the only path that connects drivers, owns their operational lifecycle, and calls `driver.execute(action)`.",
        "`physical-agent doctor` is an operator-only inert loadability diagnostic",
        "may import and instantiate drivers",
        "never connects them or calls `driver.execute`",
    ):
        assert fragment in english

    for fragment in (
        "请求/提案路径绝不加载 driver",
        "watch 是唯一连接 driver、拥有其操作生命周期并调用 `driver.execute(action)` 的路径",
        "`physical-agent doctor` 是仅供 operator 使用的惰性可加载性诊断",
        "可以 import 并实例化 driver",
        "绝不 connect，也绝不调用 `driver.execute`",
    ):
        assert fragment in chinese

    for forbidden in (
        "only component that loads drivers",
        "only its call stack can touch drivers",
        "generated driver is loaded only by watch",
    ):
        assert forbidden not in english
    assert "只有 watch 调用栈能接触 driver" not in chinese


def test_agent_instructions_and_ci_status_match_the_single_backend_blocking_gates() -> None:
    instructions = _read("AGENTS.md")
    spec = _read("docs/SPEC.zh-CN.md")
    refactoring = _read("docs/REFACTORING.zh-CN.md")

    assert "两个状态后端（markdown/sqlite）" not in instructions
    assert "TUI/e2e 为 advisory" not in spec
    assert "旧 Markdown 文件只作为迁移输入读取" not in refactoring
    assert "慢 e2e、TUI 与 Python 版本矩阵提供信号但不默认卡住" not in refactoring


def test_spec_b6_records_that_the_current_migrator_is_retired() -> None:
    spec = _read("docs/SPEC.zh-CN.md")

    assert "退役 markdown 后端（保留 renderer 与迁移命令）" not in spec
    assert "当前版本不再提供迁移命令" in spec


def test_r8_current_doc_contract_excludes_protected_snapshots() -> None:
    plan_r8 = _section(
        _read("docs/specs/001-architecture-simplification/plan.md"),
        "## 8. 文档、发布形态与全量验证收口",
    )
    tasks_r8 = _section(
        _read("docs/specs/001-architecture-simplification/tasks.md"),
        "## R8 收口",
    )

    for section in (plan_r8, tasks_r8):
        assert "current-architecture-audit.md" in section
        assert "system-summary.zh-CN.md" in section
        assert "不属于 current-doc contract" in section
        assert "不修改" in section
    assert "过期 snapshot/HTML 删除或重新生成" not in tasks_r8
    assert "重写或删除过期的 current architecture snapshot/HTML" not in plan_r8


def test_r8_release_evidence_uses_the_tracked_dashboard_dist() -> None:
    refactoring_r8 = _section(
        _read("docs/REFACTORING.zh-CN.md"),
        "### R8：当前架构、发布契约与本地门禁收口",
    )
    final_evidence = " ".join(
        paragraph
        for paragraph in refactoring_r8.split("\n\n")
        if paragraph.startswith("最终本地证据：")
    )

    assert final_evidence
    assert "tracked `physical_agent/dashboard/dist`" in final_evidence
    assert "locale 修复后已重建 tracked `physical_agent/dashboard/dist`" in final_evidence
    assert "source + shipped bundle contract" in final_evidence
    assert "ignored `frontend/dist` 不作为发布证据" in final_evidence
    assert "tracked `physical_agent/dashboard/dist` 无差异" not in final_evidence
    assert "`frontend/dist` 无差异" not in final_evidence
    assert (
        "实现 closure commit 为 `c4da4f9`；fork Push run `29476327424`、"
        "PR run `29476329954` 均 completed success，headSha 均为 `c4da4f9`。"
        in final_evidence
    )
    assert "仍未 commit、未 push" not in final_evidence
    assert "远端 CI 尚无 R8 本轮证据" not in final_evidence

    for fragment in (
        "终审继续发现并修复三项",
        "locale source 与 shipped bundle",
        "React/Web",
        "TUI/CLI",
        "`tool_loop`",
        "operator `doctor`",
    ):
        assert fragment in refactoring_r8


def test_agent_architecture_is_current_contract_with_frozen_history() -> None:
    architecture = _read("docs/agent-architecture-vnext.zh-CN.md")

    assert architecture.startswith("# Physical Agent 当前架构")
    assert "日期：2026-07-16" in architecture
    assert "用户 Chat" in architecture
    assert "rule/LLM action intents" in architecture
    assert "trusted PlanCompiler" in architecture
    assert "structured AgentOutput / ChatPlan.agent_output" in architecture
    assert "Draft card" in architecture
    assert "Watch SafetyGate" in architecture
    assert "canonical feedback/read model" in architecture
    assert "不是默认开发路线" in architecture
    assert "因此演进顺序必须改为" not in architecture
    assert "Assurance loop 稳定后再推进" not in architecture


def test_r8_deletion_evidence_matrix_covers_every_retired_surface() -> None:
    tasks_r8 = _section(
        _read("docs/specs/001-architecture-simplification/tasks.md"),
        "## R8 收口",
    )

    for column in (
        "删除内容",
        "当前替代路径",
        "正向测试",
        "负向测试或扫描证据",
        "提交或 CI 证据",
    ):
        assert column in tasks_r8
    retired_surfaces = (
        "legacy GUI",
        "Markdown workspace/migration",
        "auto_step",
        "Chat/Watch/Driver 越权路径",
        "重复 projection/read model",
        "_append_actions",
        "action-draft fence",
        "proposal convenience fields",
    )
    matrix_rows = {}
    for line in tasks_r8.splitlines():
        first_cell = re.match(r"^\| (?P<name>.*?) \|", line)
        if first_cell is None:
            continue
        retired_surface = first_cell.group("name").strip("`")
        if retired_surface in retired_surfaces:
            assert retired_surface not in matrix_rows
            matrix_rows[retired_surface] = line
    assert set(matrix_rows) == set(retired_surfaces)

    evidence_by_surface = {
        retired_surface: row.rsplit("|", 2)[1].strip()
        for retired_surface, row in matrix_rows.items()
    }
    expected_ci_evidence = {
        "legacy GUI": "`5764bac`；fork Push run `29140289239`、PR run `29140290422` 均成功",
        "auto_step": "`da14064`；fork Push run `29234483572`、PR run `29234488489` 均成功",
        "_append_actions": "`0bb7807`；fork Push run `29312317707`、PR run `29312319687` 均成功",
        "action-draft fence": "`9ba44af`；fork Push run `29399978672`、PR run `29399982326` 均成功",
        "proposal convenience fields": "`9ba44af`；fork Push run `29399978672`、PR run `29399982326` 均成功",
    }
    for retired_surface, expected_evidence in expected_ci_evidence.items():
        assert expected_evidence in evidence_by_surface[retired_surface]

    chat_watch_driver_evidence = evidence_by_surface["Chat/Watch/Driver 越权路径"]
    for expected_evidence in (
        "`da14064`，fork Push run `29234483572`、PR run `29234488489` 均成功",
        "`d1ca53c3`，fork Push run `29321294713`、PR run `29321297674` 均成功",
        "`9ba44af`，fork Push run `29399978672`、PR run `29399982326` 均成功",
    ):
        assert expected_evidence in chat_watch_driver_evidence
    assert "VNext/R4/R7 安全提交；fork Push/PR CI 成功" not in chat_watch_driver_evidence

    projection_evidence = evidence_by_surface["重复 projection/read model"]
    for fragment in (
        "`9adaf6c` 是先前 status fix",
        "`0bb7807` 是 R6 closure head",
        "fork Push run `29312317707`",
        "PR run `29312319687`",
        "R8 `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功",
    ):
        assert fragment in projection_evidence

    proposal_evidence = evidence_by_surface["proposal convenience fields"]
    assert (
        "R8 `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功"
        in proposal_evidence
    )


def test_r5_remote_ci_items_record_the_successful_push_and_pr_runs() -> None:
    tasks_r5 = _section(
        _read("docs/specs/001-architecture-simplification/tasks.md"),
        "## R5 structured Chat Turn + 双轨",
    )

    remote_ci_items = [
        line
        for line in tasks_r5.splitlines()
        if "独立远端 CI 证据" in line
    ]
    assert len(remote_ci_items) == 2
    for item in remote_ci_items:
        assert item.startswith("- [x] ")
        assert "`d1ca53c3`" in item
        assert "fork Push run `29321294713`" in item
        assert "PR run `29321297674`" in item
        assert "均成功" in item

    tasks_r7 = _section(
        _read("docs/specs/001-architecture-simplification/tasks.md"),
        "## R7 wire compatibility 切断",
    )

    r5_items = [line for line in tasks_r7.splitlines() if line.startswith("- [x] R5 双轨")]
    r7_items = [
        line
        for line in tasks_r7.splitlines()
        if line.startswith("- [x] R7 独立远端 CI 证据")
    ]
    assert len(r5_items) == 1
    assert len(r7_items) == 1

    r5_item = r5_items[0]
    assert "`d1ca53c3`" in r5_item
    assert "fork Push run `29321294713`" in r5_item
    assert "PR run `29321297674`" in r5_item
    assert "`9ba44af`" not in r5_item

    r7_item = r7_items[0]
    assert "`9ba44af`" in r7_item
    assert "fork Push run `29399978672`" in r7_item
    assert "PR run `29399982326`" in r7_item
    assert "`d1ca53c3`" not in r7_item


def test_r8_final_status_maps_every_gate_and_remote_evidence_to_its_document() -> None:
    tasks_r8 = _section(
        _read("docs/specs/001-architecture-simplification/tasks.md"),
        "## R8 收口",
    )

    checklist = [line for line in tasks_r8.splitlines() if line.startswith("- [")]
    expected_checklist = (
        "- [x] 正式 current architecture 文档只描述当前实现；用户保留的 `current-architecture-audit.md`、`current-architecture-audit.html` 与 `system-summary.zh-CN.md` 不属于 current-doc contract，不修改、不删除、不重新生成，也不据此阻塞 R8。",
        "- [x] `agent-architecture-vnext` 改为 current architecture/历史决策口径，冻结项不再写成默认下一步。",
        "- [x] SPEC、PLAYBOOK、REFACTORING、README 双语、state/backend/hardware/example/CLI help 一致。",
        "- [x] Python 全量 pytest。",
        "- [x] frontend `tsc -b && vite build`。",
        "- [x] Playwright 完整主路径与负用例。",
        "- [x] TUI build/test/scenario matrix。",
        "- [x] wheel build + clean install + `gui`/`api`/assets smoke。",
        "- [x] safety AST/grep 边界扫描。",
        "- [x] R0-R8 每个删除项有对应替代/负用例证据。",
        "- [x] SPEC R0-R8 标记完成；REFACTORING 追加实现、决策和教训。",
        "- [x] commit/push：实现 closure commit `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功；不创建独立 handoff。",
    )
    assert checklist == list(expected_checklist)
    assert all("暂停" not in item for item in checklist)

    spec_backlog = _section(_read("docs/SPEC.zh-CN.md"), "## 4. 待办矩阵")
    spec_r8_rows = [
        line for line in spec_backlog.splitlines() if line.startswith("| **R0-R8** |")
    ]
    assert len(spec_r8_rows) == 1
    spec_r8_status = spec_r8_rows[0].rsplit(" | ", 1)[1].removesuffix(" |")
    assert spec_r8_status.startswith("✅ 2026-07-16 完成：")
    assert (
        "实现 closure commit `c4da4f9`；fork Push run `29476327424`、"
        "PR run `29476329954` 均成功"
        in spec_r8_status
    )
    for boundary in (
        "`AgentOutput`/`ChatPlan.agent_output` 是唯一 Draft 机器通道",
        "`/api/state.actions` 仍是 board truth",
        "approve/reject mutation `action`",
        "pending/approval/SafetyGate",
        "watch 唯一执行权",
        "冻结项不自动恢复",
    ):
        assert boundary in spec_r8_status
    assert "等待最终提交和远端 CI" not in spec_r8_status
    assert "commit/push 尚未执行" not in spec_r8_status

    playbook_r8 = _section(
        _read("docs/PLAYBOOK.zh-CN.md"),
        "## R0-R8 架构减法与兼容面退役",
    )
    progress_paragraphs = [
        paragraph
        for paragraph in playbook_r8.split("\n\n")
        if paragraph.startswith("**当前进度**：")
    ]
    assert len(progress_paragraphs) == 1
    current_progress = progress_paragraphs[0]
    assert "R8 已完成收口" in current_progress
    assert (
        "实现 closure commit `c4da4f9`；fork Push run `29476327424`、"
        "PR run `29476329954` 均成功"
        in current_progress
    )
    assert "冻结项不自动恢复" in current_progress
    assert "等待最终 commit/push 和远端 CI" not in current_progress

    refactoring_table = _section(
        _read("docs/REFACTORING.zh-CN.md"),
        "## 1. 阶段速查表",
    )
    refactoring_r8_rows = [
        line for line in refactoring_table.splitlines() if line.startswith("| R8 |")
    ]
    assert refactoring_r8_rows == [
        "| R8 | 当前架构、文档、示例、OpenAPI、发布包与全量门禁收口 | `c4da4f9`；fork Push run `29476327424`、PR run `29476329954` 均成功 |"
    ]

    refactoring_lessons = _section(
        _read("docs/REFACTORING.zh-CN.md"),
        "## 4. 经验教训（流程侧）",
    )
    checkbox_lessons = [
        line
        for line in refactoring_lessons.splitlines()
        if line.startswith("- **checkbox 测试必须锁门槛身份、阶段与证据语义**")
    ]
    assert checkbox_lessons == [
        "- **checkbox 测试必须锁门槛身份、阶段与证据语义**（R8 review-fix 的教训）：pre-closure 阶段应逐一锁定 11 个本地门槛为 `[x]`，第 11 项沿用 SPEC 🟡 的“实现与本地验收完成、等待最终提交和远端 CI”，第 12 项 commit/push 为 `[ ]`；只有真实 closure commit 已 push 且 fork Push/PR CI 均成功后，才能切换为 12 项全部 `[x]` 与 SPEC ✅ 完成，最终状态测试还必须逐项锁定完整门槛身份和对应 commit/run 证据。"
    ]


def test_moce_example_documents_current_capabilities_and_dashboard_flow() -> None:
    english = _read("examples/moce_arm/README.md")
    chinese = _read("examples/moce_arm/README.zh-CN.md")
    integration_report = _read("examples/moce_arm/integration-report.md")

    for document in (english, integration_report):
        for capability in (
            "observe",
            "home",
            "stop",
            "move_joint",
            "move_joints",
            "set_gripper",
            "open_gripper",
            "close_gripper",
        ):
            assert capability in document
        for retired_scaffold_capability in ("say", "set_light", "move_to", "pick", "place"):
            assert retired_scaffold_capability not in document

    assert "Start watch" not in chinese
    assert "Run one watch step" not in chinese
    assert "Add to Actions" in chinese


def test_moce_minimal_workflow_does_not_recommend_world_writable_serial_permissions() -> None:
    minimal_workflow = _section(
        _read("examples/moce_arm/README.zh-CN.md"),
        "## 12. 当前建议的最小工作流",
    )

    fenced_blocks = re.findall(r"```[^\n]*\n(.*?)```", minimal_workflow, flags=re.DOTALL)
    assert fenced_blocks
    command_lines = [
        line.strip()
        for block in fenced_blocks
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    world_writable_chmod = re.compile(
        r"""
        ^(?:\$\s*)?
        (?:sudo(?:\s+-\S+)*\s+)?
        chmod\b
        (?:\s+(?:-[A-Za-z]+|--[A-Za-z-]+))*\s+
        ["']?
        (?:
            [0-7]{2,3}[2367]
            |
            (?:a|[ugo]*o[ugo]*)(?:\+|=)[rwx]*w[rwx]*
        )
        ["']?(?:\s|$)
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    offenders = [line for line in command_lines if world_writable_chmod.search(line)]

    assert offenders == []
