from __future__ import annotations

import re
from typing import Any

import yaml

from physical_agent.protocol.schemas import WorkspaceDocument


FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
ATX_HEADING_RE = re.compile(
    r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*$",
)
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)$")


def dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False).strip()


def fenced_yaml(data: Any) -> str:
    return f"```yaml\n{dump_yaml(data)}\n```"


def parse_front_matter(text: str) -> WorkspaceDocument:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError("Workspace Markdown documents must start with YAML front matter.")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Front matter must be a YAML mapping.")
    for key in ("schema", "owner"):
        if key not in metadata:
            raise ValueError(f"Front matter is missing required key: {key}")
    if "revision" not in metadata and "updated_at" not in metadata:
        raise ValueError("Front matter must include revision or updated_at.")
    return WorkspaceDocument(metadata=metadata, body=match.group(2))


def render_front_matter(metadata: dict[str, Any], body: str) -> str:
    for key in ("schema", "owner"):
        if key not in metadata:
            raise ValueError(f"Front matter is missing required key: {key}")
    if "revision" not in metadata and "updated_at" not in metadata:
        raise ValueError("Front matter must include revision or updated_at.")
    front = dump_yaml(metadata)
    clean_body = body.lstrip("\n")
    return f"---\n{front}\n---\n\n{clean_body.rstrip()}\n"


def extract_yaml_block_after_heading(body: str, heading: str, *, level: int = 2) -> Any:
    marker = "#" * level
    heading_re = re.compile(
        rf"^{re.escape(marker)}\s+{re.escape(heading)}\s*$",
        re.MULTILINE,
    )
    heading_match = heading_re.search(body)
    if not heading_match:
        return None
    rest = body[heading_match.end() :]
    block_match = YAML_BLOCK_RE.search(rest)
    if not block_match:
        return None
    value = yaml.safe_load(block_match.group(1))
    return value if value is not None else {}


def extract_markdown_sections(
    body: str,
    heading: str,
    *,
    level: int = 2,
) -> list[str]:
    """Return exact ATX-heading sections without matching headings in fences.

    This helper deliberately does not change the legacy
    :func:`extract_yaml_block_after_heading` behavior. Callers that need a
    bounded or unique section contract can opt into the stricter primitive.
    A section ends at the next heading of the same or a higher level.
    """

    lines = body.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    headings: list[tuple[int, int, str, int]] = []
    fence_character: str | None = None
    fence_length = 0
    for index, line in enumerate(lines):
        clean_line = line.rstrip("\r\n")
        fence_match = FENCE_RE.match(clean_line)
        if fence_match is not None:
            marker = fence_match.group(1)
            marker_character = marker[0]
            if fence_character is None:
                fence_character = marker_character
                fence_length = len(marker)
            elif (
                marker_character == fence_character
                and len(marker) >= fence_length
                and not fence_match.group(2).strip()
            ):
                fence_character = None
                fence_length = 0
            continue
        if fence_character is not None:
            continue

        heading_match = ATX_HEADING_RE.match(clean_line)
        if heading_match is None:
            continue
        marker, raw_title = heading_match.groups()
        title = re.sub(r"[ \t]+#+[ \t]*$", "", raw_title).strip()
        headings.append((index, len(marker), title, offsets[index] + len(line)))

    sections: list[str] = []
    for heading_index, heading_level, title, content_start in headings:
        if heading_level != level or title != heading:
            continue
        content_end = len(body)
        for next_index, next_level, _next_title, _next_start in headings:
            if next_index > heading_index and next_level <= heading_level:
                content_end = offsets[next_index]
                break
        sections.append(body[content_start:content_end].strip())
    return sections
