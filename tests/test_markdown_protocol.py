from physical_agent.protocol.markdown import (
    extract_markdown_sections,
    parse_front_matter,
    render_front_matter,
)


def test_front_matter_parse_render_roundtrip():
    text = render_front_matter(
        {"schema": "physical-agent/example/v1", "owner": "test", "revision": 1},
        "# Example\n\nHello",
    )
    doc = parse_front_matter(text)
    assert doc.schema == "physical-agent/example/v1"
    assert doc.owner == "test"
    assert doc.revision == 1
    assert "Hello" in doc.body


def test_extract_markdown_sections_is_bounded_and_ignores_fenced_headings():
    body = (
        "# Policy\n\n"
        "## Rules\n\n"
        "first section\n\n"
        "```markdown\n## Rules\nfenced impostor\n```\n\n"
        "## Agent Guidance\n\n"
        "second section\n"
    )

    assert extract_markdown_sections(body, "Rules", level=2) == [
        "first section\n\n```markdown\n## Rules\nfenced impostor\n```"
    ]
    assert extract_markdown_sections(body, "Agent Guidance", level=2) == [
        "second section"
    ]


def test_extract_markdown_sections_does_not_treat_info_fence_as_closer():
    body = (
        "# Policy\n\n"
        "```markdown\n"
        "```yaml\n"
        "## Rules\n"
        "```\n"
        "still fenced\n"
        "```\n\n"
        "## Rules\n\n"
        "real section\n"
    )

    assert extract_markdown_sections(body, "Rules", level=2) == ["real section"]
