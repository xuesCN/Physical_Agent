from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from physical_agent.env import load_dotenv


DEFAULT_MODEL = "gpt-5.4"


class OpenAICompatibleError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    api_key: str
    base_url: str
    model: str
    timeout_s: int = 60
    api_mode: str = "chat_completions"

    @classmethod
    def from_env(
        cls,
        *,
        env_file: str | Path = ".env",
        model: str | None = None,
        timeout_s: int = 60,
    ) -> "OpenAICompatibleSettings":
        load_dotenv(env_file, override=True)
        api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("GPT_KEY")
            or os.getenv("API_KEY")
            or ""
        ).strip()
        base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("GPT_URL")
            or os.getenv("BASE_URL")
            or "https://api.openai.com/v1"
        ).strip()
        resolved_model = (
            model
            or os.getenv("OPENAI_MODEL")
            or os.getenv("GPT_MODEL")
            or os.getenv("MODEL")
            or DEFAULT_MODEL
        ).strip()
        api_mode = (
            os.getenv("OPENAI_API_MODE")
            or os.getenv("GPT_API_MODE")
            or os.getenv("API_MODE")
            or "chat_completions"
        ).strip()
        if not api_key:
            raise OpenAICompatibleError(
                "Missing API key. Set OPENAI_API_KEY or GPT_KEY in .env."
            )
        if not base_url:
            raise OpenAICompatibleError(
                "Missing base URL. Set OPENAI_BASE_URL or GPT_URL in .env."
            )
        if not resolved_model:
            raise OpenAICompatibleError(
                "Missing model. Set OPENAI_MODEL or GPT_MODEL in .env."
            )
        if api_mode not in {"chat_completions", "responses"}:
            raise OpenAICompatibleError(
                "Unsupported API mode. Set OPENAI_API_MODE to chat_completions or responses."
            )
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=resolved_model,
            timeout_s=timeout_s,
            api_mode=api_mode,
        )

    @property
    def chat_completions_url(self) -> str:
        url = self.base_url.rstrip("/")
        if url.endswith("/chat/completions"):
            return url
        if url.endswith("/v1"):
            return f"{url}/chat/completions"
        return f"{url}/v1/chat/completions"

    @property
    def responses_url(self) -> str:
        url = self.base_url.rstrip("/")
        if url.endswith("/responses"):
            return url
        if url.endswith("/v1"):
            return f"{url}/responses"
        return f"{url}/v1/responses"

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
            return parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAICompatibleError(
                f"API response did not match OpenAI chat completions shape: {_short_error(json.dumps(parsed))}"
            ) from exc

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
        """Request a strict JSON object while preserving the existing chat fallback.

        The default mode keeps provider compatibility through Chat Completions
        `response_format`. Set OPENAI_API_MODE=responses to use the Responses API.
        """

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }
        content = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            metadata=metadata,
        )
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAICompatibleError(
                f"Structured response was not valid JSON: {_short_error(content)}"
            ) from exc
        if not isinstance(value, dict):
            raise OpenAICompatibleError("Structured response must be a JSON object.")
        return value

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
        return self._post_json(self.settings.chat_completions_url, payload)

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
        return self._post_json(self.settings.responses_url, payload)

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

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_s) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenAICompatibleError(
                f"API request failed with HTTP {exc.code}: {_short_error(body)}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OpenAICompatibleError(f"API request failed: {exc.reason}") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OpenAICompatibleError(
                f"API response was not JSON: {_short_error(body)}"
            ) from exc
        if not isinstance(parsed, dict):
            raise OpenAICompatibleError("API response must be a JSON object.")
        return parsed


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
        f"API response did not match OpenAI responses shape: {_short_error(json.dumps(parsed))}"
    )


def _short_error(body: str, *, limit: int = 500) -> str:
    compact = " ".join(body.split())
    if len(compact) > limit:
        return compact[: limit - 3] + "..."
    return compact
