from physical_agent.protocol.markdown import (
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
