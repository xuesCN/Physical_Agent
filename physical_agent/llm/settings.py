from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from physical_agent.env import load_dotenv


DEFAULT_LLM_SETTINGS_NAME = ".llm.json"
DEFAULT_API_MODE = "chat_completions"
SUPPORTED_API_MODES = {"chat_completions", "responses"}
LLM_SETTING_KEYS = ("base_url", "api_key", "model", "api_mode")


class LLMSettingsError(ValueError):
    """Raised when local LLM settings cannot be read or written."""


def llm_settings_path(workspace_path: str | Path) -> Path:
    return Path(workspace_path).resolve() / DEFAULT_LLM_SETTINGS_NAME


def default_llm_settings_path(env_file: str | Path = ".env") -> Path:
    env_path = Path(env_file)
    base_dir = env_path.parent if env_path.parent != Path("") else Path(".")
    return (base_dir / "workspace" / DEFAULT_LLM_SETTINGS_NAME).resolve()


def read_llm_settings_file(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    settings_path = Path(path)
    if not settings_path.exists():
        return {}
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LLMSettingsError(f"Could not parse {settings_path}: {exc.msg}") from exc
    except OSError as exc:
        raise LLMSettingsError(f"Could not read {settings_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise LLMSettingsError(f"{settings_path} must contain a JSON object.")
    return _normalize_settings(raw)


def write_llm_settings_file(
    path: str | Path,
    values: Mapping[str, Any],
    *,
    preserve_existing_api_key: bool = True,
) -> dict[str, str]:
    settings_path = Path(path)
    existing = read_llm_settings_file(settings_path)
    data: dict[str, str] = dict(existing)

    for key in ("base_url", "model", "api_mode"):
        if key in values:
            data[key] = _coerce_text(values.get(key))

    if "api_key" in values:
        api_key = _coerce_text(values.get("api_key"))
        if api_key or not preserve_existing_api_key:
            data["api_key"] = api_key

    if not data.get("api_mode"):
        data["api_mode"] = DEFAULT_API_MODE
    if data["api_mode"] not in SUPPORTED_API_MODES:
        raise LLMSettingsError(
            "Unsupported API mode. Use chat_completions or responses."
        )

    output = {key: data.get(key, "") for key in LLM_SETTING_KEYS if data.get(key, "")}
    output.setdefault("api_mode", DEFAULT_API_MODE)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def resolve_llm_settings_values(
    *,
    env_file: str | Path = ".env",
    model: str | None = None,
    settings_file: str | Path | None = None,
    workspace_path: str | Path | None = None,
) -> dict[str, str]:
    loaded = load_dotenv(env_file, override=True)
    local_settings = read_llm_settings_file(
        settings_file
        if settings_file is not None
        else (
            llm_settings_path(workspace_path)
            if workspace_path is not None
            else default_llm_settings_path(env_file)
        )
    )
    return {
        "api_key": (
            local_settings.get("api_key")
            or _env_value(loaded, "OPENAI_API_KEY", "GPT_KEY", "API_KEY")
            or ""
        ).strip(),
        "base_url": (
            local_settings.get("base_url")
            or _env_value(loaded, "OPENAI_BASE_URL", "GPT_URL", "BASE_URL")
            or "https://api.openai.com/v1"
        ).strip(),
        "model": (
            model
            or local_settings.get("model")
            or _env_value(loaded, "OPENAI_MODEL", "GPT_MODEL", "MODEL")
            or "gpt-5.4"
        ).strip(),
        "api_mode": (
            local_settings.get("api_mode")
            or _env_value(loaded, "OPENAI_API_MODE", "GPT_API_MODE", "API_MODE")
            or DEFAULT_API_MODE
        ).strip(),
    }


def public_llm_settings_summary(
    settings: Mapping[str, Any],
    *,
    settings_path: str | Path | None = None,
) -> dict[str, Any]:
    api_key = _coerce_text(settings.get("api_key"))
    summary: dict[str, Any] = {
        "base_url": _coerce_text(settings.get("base_url")),
        "model": _coerce_text(settings.get("model")),
        "api_mode": _coerce_text(settings.get("api_mode")) or DEFAULT_API_MODE,
        "has_api_key": bool(api_key),
        "masked_api_key": _mask_api_key(api_key),
    }
    if settings_path is not None:
        summary["settings_path"] = str(Path(settings_path).resolve())
    return summary


def _normalize_settings(raw: Mapping[str, Any]) -> dict[str, str]:
    data = {
        key: _coerce_text(raw.get(key))
        for key in LLM_SETTING_KEYS
        if key in raw
    }
    if not data.get("api_mode"):
        data["api_mode"] = DEFAULT_API_MODE
    if data["api_mode"] not in SUPPORTED_API_MODES:
        raise LLMSettingsError(
            "Unsupported API mode. Use chat_completions or responses."
        )
    return data


def _coerce_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _env_value(loaded: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = loaded.get(name)
        if value:
            return value
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    suffix = api_key[-4:]
    return f"****{suffix}"
