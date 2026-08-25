from __future__ import annotations

import ast
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import Field

from physical_agent.agent.onboarding import HardwareIntegrationAssistant, IntegrationResult, SourceProfile
from physical_agent.llm import OpenAICompatibleClient, OpenAICompatibleSettings
from physical_agent.protocol.schemas import DriverManifest, StrictModel


class ChatClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        ...


class SDKContextFile(StrictModel):
    path: str
    text: str


class SDKContext(StrictModel):
    files: list[SDKContextFile] = Field(default_factory=list)
    api_hints: list[str] = Field(default_factory=list)


class DriverCodingResult(StrictModel):
    integration: IntegrationResult
    output_path: Path
    llm_used: bool = False
    llm_error: str | None = None
    summary: str = ""
    next_steps: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    generated_files: list[str] = Field(default_factory=list)
    attempts: int = 0


class DriverCodingAgent:
    """Use an LLM to turn an SDK/repo into a watch-side Physical Agent driver draft."""

    def __init__(
        self,
        source: str | Path,
        *,
        output_dir: str | Path | None = None,
        name: str | None = None,
        base_dir: str | Path | None = None,
        settings: OpenAICompatibleSettings | None = None,
        client: ChatClient | None = None,
        env_file: str | Path = ".env",
        model: str | None = None,
        max_context_chars: int = 28000,
        max_attempts: int = 2,
    ):
        self.base_dir = Path(base_dir).resolve() if base_dir is not None else Path.cwd().resolve()
        self.scaffold_assistant = HardwareIntegrationAssistant(
            source,
            output_dir=output_dir,
            name=name,
            base_dir=self.base_dir,
        )
        self.env_file = Path(env_file)
        if not self.env_file.is_absolute():
            self.env_file = self.base_dir / self.env_file
        self.settings = settings
        self.client = client
        self.model = model
        self.max_context_chars = max_context_chars
        self.max_attempts = max(1, max_attempts)

    def generate(self) -> DriverCodingResult:
        integration = self.scaffold_assistant.generate()
        context = self._collect_sdk_context(integration.source)
        existing = _read_scaffold_files(integration.output_path)
        errors: list[str] = []
        llm_error: str | None = None
        last_validation: dict[str, Any] = {
            "ok": True,
            "errors": [],
            "checks": ["scaffold generated"],
        }

        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self._request_driver_code(
                    profile=integration.source,
                    context=context,
                    existing=existing,
                    previous_errors=errors,
                )
            except Exception as exc:
                llm_error = str(exc)
                break

            files = _extract_file_updates(payload)
            if not files:
                llm_error = "LLM response did not contain any allowed file updates."
                break

            with tempfile.TemporaryDirectory(prefix="physical-agent-driver-candidate-") as tmp:
                candidate = Path(tmp) / "candidate"
                shutil.copytree(integration.output_path, candidate)
                _apply_file_updates(candidate, files)
                validation = _validate_driver_scaffold(candidate)
                last_validation = validation
                if validation.get("ok"):
                    _apply_file_updates(integration.output_path, files)
                    final_validation = _validate_driver_scaffold(integration.output_path)
                    report_path = integration.output_path / "llm-coding-report.md"
                    report_path.write_text(
                        _render_llm_report(
                            payload=payload,
                            validation=final_validation,
                            context=context,
                            attempts=attempt,
                        ),
                        encoding="utf-8",
                    )
                    generated = sorted(
                        str((integration.output_path / path).resolve()) for path in files
                    )
                    generated.append(str(report_path.resolve()))
                    return DriverCodingResult(
                        integration=integration,
                        output_path=integration.output_path,
                        llm_used=True,
                        summary=str(payload.get("summary") or "LLM driver draft generated."),
                        next_steps=[str(item) for item in payload.get("next_steps", [])],
                        validation=final_validation,
                        generated_files=generated,
                        attempts=attempt,
                    )
                errors = [str(item) for item in validation.get("errors", [])]

        report_path = integration.output_path / "llm-coding-report.md"
        report_path.write_text(
            _render_llm_report(
                payload={"summary": "LLM driver coding did not produce a valid loadable draft."},
                validation=last_validation,
                context=context,
                attempts=self.max_attempts,
                llm_error=llm_error,
            ),
            encoding="utf-8",
        )
        return DriverCodingResult(
            integration=integration,
            output_path=integration.output_path,
            llm_used=False,
            llm_error=llm_error or "; ".join(errors) or "LLM draft failed validation.",
            summary="Kept the safe scaffold because LLM coding did not validate.",
            next_steps=integration.source.next_steps,
            validation=last_validation,
            generated_files=integration.generated_files + [str(report_path.resolve())],
            attempts=self.max_attempts,
        )

    def _client(self) -> ChatClient:
        if self.client is not None:
            return self.client
        settings = self.settings or OpenAICompatibleSettings.from_env(
            env_file=self.env_file,
            model=self.model,
        )
        self.client = OpenAICompatibleClient(settings)
        return self.client

    def _request_driver_code(
        self,
        *,
        profile: SourceProfile,
        context: SDKContext,
        existing: dict[str, str],
        previous_errors: list[str],
    ) -> dict[str, Any]:
        content = self._client().chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the SDK-to-Physical-Agent driver coding agent. "
                        "Generate a watch-side driver draft only. Return one JSON object and no Markdown. "
                        "Schema: {\"summary\":\"...\",\"files\":[{\"path\":\"driver.py\","
                        "\"content\":\"...\"}],\"next_steps\":[\"...\"],\"tests\":[\"...\"]}. "
                        "Allowed paths are driver.py, physical_driver.yaml, README.md, README.zh-CN.md, "
                        "integration-report.md, and tests/test_generated_driver.py. "
                        "The driver must subclass PhysicalDriver and must not parse Markdown, import the "
                        "agent runtime, call workspace files, or execute hardware at import time. "
                        "Keep mock mode loadable without the vendor SDK installed. Put real SDK imports "
                        "inside hardware-mode branches or helper methods. Use DriverContext.config for "
                        "endpoint, serial port, tokens, and mode. Keep hardware execution behind "
                        "driver.execute(action), so watch remains the only execution path."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "driver_profile": profile.model_dump(mode="json"),
                            "sdk_context": context.model_dump(mode="json"),
                            "existing_scaffold": existing,
                            "previous_validation_errors": previous_errors,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=5000,
        )
        return _extract_json_object(content)

    def _collect_sdk_context(self, profile: SourceProfile) -> SDKContext:
        files: list[SDKContextFile] = []
        api_hints: list[str] = []
        remaining = self.max_context_chars
        for path in _iter_context_files(profile.resolved_path):
            if remaining <= 0:
                break
            text = _safe_read(path)
            if not text.strip():
                continue
            relative = path.relative_to(profile.resolved_path).as_posix()
            clipped = text[: min(len(text), 5000, remaining)]
            remaining -= len(clipped)
            files.append(SDKContextFile(path=relative, text=clipped))
            api_hints.extend(_extract_api_hints(clipped, relative))
        return SDKContext(files=files, api_hints=api_hints[:80])


def _read_scaffold_files(path: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for relative in ["physical_driver.yaml", "driver.py", "README.md", "README.zh-CN.md"]:
        target = path / relative
        if target.exists():
            files[relative] = target.read_text(encoding="utf-8", errors="ignore")
    return files


def _iter_context_files(root: Path):
    priority = [
        "README.md",
        "README.zh-CN.md",
        "README.rst",
        "pyproject.toml",
        "package.json",
    ]
    seen: set[Path] = set()
    for name in priority:
        path = root / name
        if path.exists() and path.is_file():
            seen.add(path.resolve())
            yield path
    ignored = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
    suffixes = {".py", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".ts", ".js"}
    for path in root.rglob("*"):
        if any(part in ignored for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield path


def _extract_api_hints(text: str, relative_path: str) -> list[str]:
    hints: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^(class|def|async def)\s+[A-Za-z_][A-Za-z0-9_]*", stripped):
            hints.append(f"{relative_path}: {stripped}")
            continue
        if re.search(r"\b(connect|disconnect|move|pick|place|grab|grasp|release|observe|scan|speak|light)\b", stripped, re.IGNORECASE):
            if len(stripped) <= 180:
                hints.append(f"{relative_path}: {stripped}")
    return hints


def _safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("LLM driver coding response must be a JSON object.")
    return value


def _extract_file_updates(payload: dict[str, Any]) -> dict[str, str]:
    updates: dict[str, str] = {}
    files = payload.get("files", [])
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip().replace("\\", "/")
            content = item.get("content")
            if isinstance(content, str) and _is_allowed_output_path(path):
                updates[path] = content
    for key, path in [
        ("driver_py", "driver.py"),
        ("physical_driver_yaml", "physical_driver.yaml"),
        ("readme_md", "README.md"),
        ("readme_zh_cn_md", "README.zh-CN.md"),
    ]:
        value = payload.get(key)
        if isinstance(value, str):
            updates[path] = value
    return updates


def _is_allowed_output_path(path: str) -> bool:
    if not path or path.startswith("/") or ":" in path:
        return False
    parts = Path(path).parts
    if ".." in parts:
        return False
    allowed = {
        "driver.py",
        "physical_driver.yaml",
        "README.md",
        "README.zh-CN.md",
        "integration-report.md",
        "tests/test_generated_driver.py",
    }
    return path in allowed


def _apply_file_updates(root: Path, updates: dict[str, str]) -> None:
    for relative, content in updates.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.rstrip() + "\n", encoding="utf-8")


def _validate_driver_scaffold(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[str] = []
    manifest_path = path / "physical_driver.yaml"
    driver_py = path / "driver.py"
    manifest: DriverManifest | None = None

    if not manifest_path.exists():
        errors.append("physical_driver.yaml is missing")
    else:
        try:
            manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            manifest = DriverManifest.model_validate(manifest_payload)
            if manifest.schema != "physical-agent/driver/v1":
                errors.append(f"unsupported driver manifest schema: {manifest.schema}")
            else:
                checks.append("physical_driver.yaml matches the v1 manifest contract")
        except Exception as exc:
            errors.append(f"physical_driver.yaml failed static validation: {exc}")

    if not driver_py.exists():
        errors.append("driver.py is missing")
        return {"ok": False, "errors": errors, "checks": checks}

    tree: ast.Module | None = None
    try:
        source = driver_py.read_text(encoding="utf-8")
        compile(source, str(driver_py), "exec")
        tree = ast.parse(source, filename=str(driver_py))
        checks.append("driver.py compiles")
    except SyntaxError as exc:
        errors.append(f"driver.py failed to compile: {exc.msg}")

    if manifest is not None and tree is not None:
        if manifest.entrypoint.module != "driver":
            errors.append(
                "entrypoint.module must be `driver`; request-side validation does not import arbitrary modules"
            )
        class_node = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef)
                and node.name == manifest.entrypoint.class_name
            ),
            None,
        )
        if class_node is None:
            errors.append(
                f"driver.py does not define entrypoint class {manifest.entrypoint.class_name}"
            )
        else:
            base_names = {_ast_name(base) for base in class_node.bases}
            if "PhysicalDriver" not in base_names:
                errors.append(
                    f"{manifest.entrypoint.class_name} must statically inherit PhysicalDriver"
                )
            required_methods = {
                "connect",
                "disconnect",
                "health",
                "observe",
                "capabilities",
                "execute",
            }
            method_names = {
                node.name
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            missing = sorted(required_methods - method_names)
            if missing:
                errors.append(
                    "entrypoint class is missing required methods: " + ", ".join(missing)
                )
            if not missing and "PhysicalDriver" in base_names:
                checks.append("entrypoint class statically satisfies the PhysicalDriver surface")

    checks.append(
        "dynamic connect/observe/execute validation deferred to an explicit watch-side conformance run"
    )
    return {"ok": not errors, "errors": errors, "checks": checks}


def _ast_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _render_llm_report(
    *,
    payload: dict[str, Any],
    validation: dict[str, Any],
    context: SDKContext,
    attempts: int,
    llm_error: str | None = None,
) -> str:
    summary = str(payload.get("summary") or "")
    errors = "\n".join(f"- {item}" for item in validation.get("errors", [])) or "- none"
    checks = "\n".join(f"- {item}" for item in validation.get("checks", [])) or "- none"
    files = "\n".join(f"- {item.path}" for item in context.files) or "- none"
    next_steps = payload.get("next_steps", [])
    if not isinstance(next_steps, list):
        next_steps = []
    next_steps_text = "\n".join(f"- {item}" for item in next_steps) or "- none"
    error_text = f"\n## LLM Error\n\n{llm_error}\n" if llm_error else ""
    return (
        "# LLM Driver Coding Report\n\n"
        f"Attempts: {attempts}\n\n"
        f"Summary: {summary or 'No summary provided.'}\n\n"
        "## Validation Checks\n\n"
        f"{checks}\n\n"
        "## Validation Errors\n\n"
        f"{errors}\n"
        f"{error_text}\n"
        "## SDK Files Used\n\n"
        f"{files}\n\n"
        "## Next Steps\n\n"
        f"{next_steps_text}\n"
    )
