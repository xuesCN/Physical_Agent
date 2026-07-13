from physical_agent.protocol.chat_summary import summarize_chat_messages
from physical_agent.protocol.schemas import ChatMessage


def test_chat_summary_trim_respects_tiny_budget():
    summary = summarize_chat_messages(
        [ChatMessage(role="user", content="x" * 100)],
        running_summary="older " * 20,
        max_chars=10,
    )

    assert summary == "[Earlier s"
    assert len(summary) <= 10
