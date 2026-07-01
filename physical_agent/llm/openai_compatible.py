from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from jsonschema import SchemaError, ValidationError, validate as validate_json_schema

from physical_agent.llm.settings import (
    DEFAULT_API_MODE,
    SUPPORTED_API_MODES,
    resolve_llm_settings_values,
)

try:  # Keep the base package lightweight; the SDK is installed via .[llm].
    import openai  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised when users omit the llm extra.
    openai = None  # type: ignore[assignment]


DEFAULT_MODEL = "gpt-5.4"
UNSUPPORTED_ENDPOINT_SUFFIXES = ("/chat/completions", "/responses")


class OpenAICompatibleError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        kind: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind

    @property
    def is_bad_request(self) -> bool:
        return self.kind == "bad_request" or self.status_code == 400


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    api_key: str
    base_url: str
    model: str
    timeout_s: int = 60
    api_mode: str = "chat_completions"

    def __post_init__(self) -> None:
        api_key = self.api_key.strip()
        base_url = _validate_api_root(self.base_url)
        model = self.model.strip()
        api_mode = self.api_mode.strip()
        if not api_key:
            raise OpenAICompatibleError(
                "Missing API key. Set OPENAI_API_KEY or GPT_KEY in .env."
            )
        if not model:
            raise OpenAICompatibleError(
                "Missing model. Set OPENAI_MODEL or GPT_MODEL in .env."
            )
        if api_mode not in SUPPORTED_API_MODES:
            raise OpenAICompatibleError(
                "Unsupported API mode. Set OPENAI_API_MODE to chat_completions or responses."
            )
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "api_mode", api_mode)

    @classmethod
    def from_env(
        cls,
        *,
        env_file: str | Path = ".env",
        model: str | None = None,
        timeout_s: int = 60,
        settings_file: str | Path | None = None,
        workspace_path: str | Path | None = None,
    ) -> "OpenAICompatibleSettings":
        values = resolve_llm_settings_values(
            env_file=env_file,
            model=model,
            settings_file=settings_file,
            workspace_path=workspace_path,
        )
        return cls(
            api_key=values["api_key"],
            base_url=values["base_url"],
            model=values["model"],
            timeout_s=timeout_s,
            api_mode=values["api_mode"],
        )

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def responses_url(self) -> str:
        return f"{self.base_url}/responses"

    def public_summary(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "api_mode": self.api_mode,
            "chat_completions_url": self.chat_completions_url,
            "responses_url": self.responses_url,
            "model": self.model,
            "api_key": "<set>",
            "timeout_s": self.timeout_s,
        }


class OpenAICompatibleClient:
    def __init__(self, settings: OpenAICompatibleSettings):
        self.settings = settings
        self._client = self._new_sdk_client()

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        if self.settings.api_mode == "responses":
            parsed = self.responses_create(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                text_format=_responses_text_format(response_format),
                metadata=metadata,
            )
            return _extract_responses_text(parsed)

        parsed = self.chat_completion_create(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            metadata=metadata,
        )

        try:
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAICompatibleError(
                "API response did not match OpenAI chat completions shape: "
                f"{_short_error(json.dumps(parsed, ensure_ascii=True))}"
            ) from exc
        if not isinstance(content, str):
            raise OpenAICompatibleError("Chat completion content must be a string.")
        return content

    def stream_chat_text(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        metadata: dict[str, str] | None = None,
    ) -> Iterator[str]:
        """Yield assistant text deltas from the configured compatible API mode."""

        if self.settings.api_mode == "responses":
            yield from self._stream_responses_text(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                metadata=metadata,
            )
            return

        yield from self._stream_chat_completions_text(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
        )

    def structured_json(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        schema_name: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object validated locally against the supplied schema."""

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }
        try:
            content = self.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                metadata=metadata,
            )
        except OpenAICompatibleError as exc:
            if not exc.is_bad_request:
                raise
            fallback_messages = _messages_with_json_mode_instruction(
                messages,
                schema=schema,
                schema_name=schema_name,
            )
            content = self.chat(
                fallback_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                metadata=metadata,
            )
        return _parse_and_validate_json(content, schema=schema)

    def responses_create(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        text_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        instructions, input_items = _messages_to_responses_parts(messages)
        return self.responses_create_input(
            input_items,
            instructions=instructions or None,
            temperature=temperature,
            max_tokens=max_tokens,
            text_format=text_format,
            tools=tools,
            metadata=metadata,
        )

    def chat_completion_create(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if metadata:
            payload["metadata"] = metadata
        try:
            response = self._client.chat.completions.create(**payload)
        except Exception as exc:  # noqa: BLE001 - normalize SDK errors for callers.
            raise self._to_compatible_error(exc) from exc
        return _ensure_dict(_to_plain_data(response))

    def _stream_chat_completions_text(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        metadata: dict[str, str] | None,
    ) -> Iterator[str]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if metadata:
            payload["metadata"] = metadata

        stream = None
        try:
            stream = self._client.chat.completions.create(**payload)
            for chunk in stream:
                for content in _chat_delta_contents(chunk):
                    if content:
                        yield content
        except Exception as exc:  # noqa: BLE001 - normalize SDK and iterator errors.
            raise self._to_compatible_error(exc) from exc
        finally:
            _close_stream(stream)

    def responses_create_input(
        self,
        input_items: list[dict[str, Any]],
        *,
        instructions: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        text_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "input": input_items,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if instructions:
            payload["instructions"] = instructions
        if text_format is not None:
            payload["text"] = {"format": text_format}
        if tools is not None:
            payload["tools"] = tools
        if metadata:
            payload["metadata"] = metadata
        try:
            response = self._client.responses.create(**payload)
        except Exception as exc:  # noqa: BLE001 - normalize SDK errors for callers.
            raise self._to_compatible_error(exc) from exc
        return _ensure_dict(_to_plain_data(response))

    def _stream_responses_text(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        metadata: dict[str, str] | None,
    ) -> Iterator[str]:
        instructions, input_items = _messages_to_responses_parts(messages)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "input": input_items,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "stream": True,
        }
        if instructions:
            payload["instructions"] = instructions
        if metadata:
            payload["metadata"] = metadata

        stream = None
        try:
            stream = self._client.responses.create(**payload)
            for event in stream:
                event_type = _event_type(event)
                if event_type == "response.output_text.delta":
                    delta = _event_field(event, "delta")
                    if isinstance(delta, str) and delta:
                        yield delta
                elif event_type in {"response.completed", "response.output_text.done"}:
                    return
                elif event_type in {"error", "response.failed"}:
                    raise _stream_event_error(event, self.settings)
        except OpenAICompatibleError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize SDK and iterator errors.
            raise self._to_compatible_error(exc) from exc
        finally:
            _close_stream(stream)

    def test_connection(self, *, prompt: str = "Reply with exactly: pong") -> dict[str, Any]:
        content = self.chat(
            [
                {
                    "role": "system",
                    "content": "You are a terse connectivity test endpoint.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=32,
        )
        return {
            "ok": True,
            "model": self.settings.model,
            "endpoint": (
                self.settings.responses_url
                if self.settings.api_mode == "responses"
                else self.settings.chat_completions_url
            ),
            "api_mode": self.settings.api_mode,
            "content": content.strip(),
        }

    def _new_sdk_client(self) -> Any:
        if openai is None:
            raise OpenAICompatibleError(
                "The OpenAI Python SDK is not installed. Install with `pip install -e .[llm]` "
                "or `pip install -e .[dev,llm]`."
            )
        try:
            return openai.OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 - SDK init failures should be readable.
            message = _sanitize_error(str(exc), self.settings)
            raise OpenAICompatibleError(
                f"Could not initialize OpenAI SDK client: {_short_error(message)}",
                kind="sdk_init",
            ) from exc

    def _to_compatible_error(self, exc: Exception) -> OpenAICompatibleError:
        status_code = _status_code(exc)
        kind = _sdk_error_kind(exc, status_code=status_code)
        detail = _sanitize_error(str(exc), self.settings)
        if kind == "rate_limit":
            message = (
                "OpenAI-compatible API rate limited the request"
                f"{_status_suffix(status_code)}: {_short_error(detail)}"
            )
        elif kind == "timeout":
            message = (
                f"OpenAI-compatible API request timed out after {self.settings.timeout_s}s: "
                f"{_short_error(detail)}"
            )
        elif kind == "connection":
            message = (
                "OpenAI-compatible API connection failed: "
                f"{_short_error(detail)}"
            )
        elif kind == "bad_request":
            message = (
                "OpenAI-compatible API rejected the request as invalid"
                f"{_status_suffix(status_code)}: {_short_error(detail)}"
            )
        elif kind == "status":
            message = (
                "OpenAI-compatible API request failed"
                f"{_status_suffix(status_code)}: {_short_error(detail)}"
            )
        else:
            message = f"OpenAI-compatible API request failed: {_short_error(detail)}"
        return OpenAICompatibleError(message, status_code=status_code, kind=kind)


def _validate_api_root(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if not url:
        raise OpenAICompatibleError(
            "Missing base URL. Set OPENAI_BASE_URL or GPT_URL in .env."
        )
    lowered = url.lower()
    for suffix in UNSUPPORTED_ENDPOINT_SUFFIXES:
        if lowered.endswith(suffix):
            raise OpenAICompatibleError(
                "Base URL must be the compatible API root, not a full endpoint. "
                "For example, use `https://ark.cn-beijing.volces.com/api/v3`, "
                "not a URL ending in `/chat/completions` or `/responses`."
            )
    return url


def _messages_to_responses_parts(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    items: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        if role == "system":
            if content:
                instructions.append(content)
            continue
        items.append({"role": role, "content": content})
    return "\n\n".join(instructions), items


def _responses_text_format(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
    if response_format is None:
        return None
    if response_format.get("type") != "json_schema":
        return response_format
    json_schema = response_format.get("json_schema", {})
    return {
        "type": "json_schema",
        "name": json_schema.get("name", "structured_response"),
        "strict": bool(json_schema.get("strict", True)),
        "schema": json_schema.get("schema", {"type": "object"}),
    }


def _extract_responses_text(parsed: dict[str, Any]) -> str:
    direct = parsed.get("output_text")
    if isinstance(direct, str):
        return direct

    fragments: list[str] = []
    output = parsed.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    fragments.append(text)
    if fragments:
        return "".join(fragments)
    raise OpenAICompatibleError(
        "API response did not match OpenAI responses shape: "
        f"{_short_error(json.dumps(parsed, ensure_ascii=True))}"
    )


def _messages_with_json_mode_instruction(
    messages: list[dict[str, Any]],
    *,
    schema: dict[str, Any],
    schema_name: str,
) -> list[dict[str, Any]]:
    instruction = (
        "Return only one valid JSON object. The JSON object must satisfy this "
        f"JSON Schema named `{schema_name}`: {json.dumps(schema, ensure_ascii=True)}"
    )
    updated = [dict(message) for message in messages]
    for message in updated:
        if str(message.get("role", "")) == "system":
            existing = str(message.get("content", "")).strip()
            message["content"] = f"{existing}\n\n{instruction}" if existing else instruction
            return updated
    return [{"role": "system", "content": instruction}, *updated]


def _parse_and_validate_json(content: str, *, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OpenAICompatibleError(
            f"Structured response was not valid JSON: {_short_error(content)}"
        ) from exc
    if not isinstance(value, dict):
        raise OpenAICompatibleError("Structured response must be a JSON object.")
    try:
        validate_json_schema(instance=value, schema=schema)
    except SchemaError as exc:
        raise OpenAICompatibleError(
            f"Structured response schema is invalid: {_short_error(str(exc))}"
        ) from exc
    except ValidationError as exc:
        raise OpenAICompatibleError(
            f"Structured response did not match schema: {_short_error(exc.message)}"
        ) from exc
    return value


def _to_plain_data(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "model_dump_json"):
        return json.loads(value.model_dump_json())
    return value


def _ensure_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpenAICompatibleError("API response must be a JSON object.")
    return value


def _chat_delta_contents(chunk: Any) -> list[str]:
    choices = _field(_to_plain_data(chunk), "choices", [])
    if not isinstance(choices, list):
        return []
    contents: list[str] = []
    for choice in choices:
        delta = _field(choice, "delta", {})
        content = _field(delta, "content")
        if isinstance(content, str):
            contents.append(content)
        elif isinstance(content, list):
            contents.extend(_text_part_contents(content))
    return contents


def _text_part_contents(parts: list[Any]) -> list[str]:
    contents: list[str] = []
    for part in parts:
        if isinstance(part, str):
            contents.append(part)
            continue
        text = _field(part, "text")
        if isinstance(text, str):
            contents.append(text)
    return contents


def _event_type(event: Any) -> str:
    value = _event_field(event, "type")
    return value if isinstance(value, str) else ""


def _event_field(event: Any, name: str, default: Any = None) -> Any:
    return _field(_to_plain_data(event), name, default)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _stream_event_error(
    event: Any,
    settings: OpenAICompatibleSettings,
) -> OpenAICompatibleError:
    error = _event_field(event, "error", {})
    message = _field(error, "message")
    if not isinstance(message, str) or not message:
        message = _event_field(event, "message", "Responses stream emitted an error event.")
    message = _sanitize_error(str(message), settings)
    return OpenAICompatibleError(
        f"OpenAI-compatible API stream failed: {_short_error(message)}",
        kind="stream_error",
    )


def _close_stream(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        close()


def _sdk_error_kind(exc: Exception, *, status_code: int | None) -> str:
    names = {cls.__name__ for cls in type(exc).__mro__}
    if "RateLimitError" in names or status_code == 429:
        return "rate_limit"
    if "APITimeoutError" in names or "Timeout" in names:
        return "timeout"
    if "APIConnectionError" in names or "ConnectionError" in names:
        return "connection"
    if "BadRequestError" in names or status_code == 400:
        return "bad_request"
    if "APIStatusError" in names or status_code is not None:
        return "status"
    return "sdk"


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    return None


def _status_suffix(status_code: int | None) -> str:
    return f" (HTTP {status_code})" if status_code is not None else ""


def _sanitize_error(message: str, settings: OpenAICompatibleSettings) -> str:
    sanitized = message
    if settings.api_key:
        sanitized = sanitized.replace(settings.api_key, "<redacted>")
    sanitized = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer <redacted>",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"(api[_-]?key=)[^&\s]+",
        r"\1<redacted>",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def _short_error(body: str, *, limit: int = 500) -> str:
    compact = " ".join(body.split())
    if len(compact) > limit:
        return compact[: limit - 3] + "..."
    return compact
